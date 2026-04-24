from flask import Blueprint, request, jsonify, g
from bson.objectid import ObjectId
from extensions.mongodb import get_db
from middlewares.auth import login_required
from models.incident import Incident

bp = Blueprint('incidents', __name__, url_prefix='/api/incidents')

@bp.route('', methods=['GET'])
@login_required
def get_incidents():
    """Получить список инцидентов"""
    limit = int(request.args.get('limit', 50))
    offset = int(request.args.get('offset', 0))
    endpoint_id = request.args.get('endpoint_id')
    active_only = request.args.get('active_only', 'false').lower() == 'true'
    
    db = get_db()
    user_id = str(g.current_user['_id'])
    
    # Сначала получаем эндпоинты пользователя
    user_endpoints = list(db.endpoints.find(
        {"user_id": user_id},
        {"_id": 1}
    ))
    user_endpoint_ids = [str(ep['_id']) for ep in user_endpoints]
    
    # Строим запрос для инцидентов
    query = {"endpoint_id": {"$in": user_endpoint_ids}}
    
    if endpoint_id:
        if endpoint_id not in user_endpoint_ids:
            return jsonify({"error": "Access denied"}), 403
        query["endpoint_id"] = endpoint_id
    
    if active_only:
        query["ended_at"] = None
    
    # Получаем инциденты
    incidents = list(db.incidents.find(query)
                     .sort("started_at", -1)
                     .skip(offset)
                     .limit(limit))
    
    # Добавляем информацию об эндпоинтах
    for inc in incidents:
        inc['_id'] = str(inc['_id'])
        inc['started_at'] = inc['started_at'].isoformat()
        if inc.get('ended_at'):
            inc['ended_at'] = inc['ended_at'].isoformat()
        
        # Находим название эндпоинта
        endpoint = db.endpoints.find_one({"_id": ObjectId(inc['endpoint_id'])})
        inc['endpoint_name'] = endpoint['name'] if endpoint else 'Unknown'
    
    # Статистика
    stats = Incident.get_incident_stats()
    
    return jsonify({
        "incidents": incidents,
        "total": len(incidents),
        "offset": offset,
        "limit": limit,
        "stats": stats
    })

@bp.route('/<incident_id>', methods=['GET'])
@login_required
def get_incident(incident_id):
    """Получить детали конкретного инцидента"""
    db = get_db()
    user_id = str(g.current_user['_id'])
    
    try:
        incident = db.incidents.find_one({"_id": ObjectId(incident_id)})
        
        if not incident:
            return jsonify({"error": "Incident not found"}), 404
        
        # Проверяем доступ
        endpoint = db.endpoints.find_one({
            "_id": ObjectId(incident['endpoint_id']),
            "user_id": user_id
        })
        
        if not endpoint:
            return jsonify({"error": "Access denied"}), 403
        
        # Форматируем ответ
        incident['_id'] = str(incident['_id'])
        incident['started_at'] = incident['started_at'].isoformat()
        if incident.get('ended_at'):
            incident['ended_at'] = incident['ended_at'].isoformat()
        
        incident['endpoint'] = {
            "id": str(endpoint['_id']),
            "name": endpoint['name'],
            "url": endpoint['url']
        }
        
        # Получаем связанные проверки
        checks = list(db.checks.find({
            "endpoint_id": incident['endpoint_id'],
            "checked_at": {"$gte": incident['started_at']}
        }).sort("checked_at", 1).limit(10))
        
        for check in checks:
            check['_id'] = str(check['_id'])
            check['checked_at'] = check['checked_at'].isoformat()
        
        incident['related_checks'] = checks
        
        return jsonify(incident)
        
    except:
        return jsonify({"error": "Invalid incident id"}), 400

@bp.route('/active', methods=['GET'])
@login_required
def get_active_incidents():
    """Получить все активные инциденты"""
    db = get_db()
    user_id = str(g.current_user['_id'])
    
    # Получаем эндпоинты пользователя
    user_endpoints = list(db.endpoints.find(
        {"user_id": user_id},
        {"_id": 1, "name": 1}
    ))
    
    user_endpoint_ids = [str(ep['_id']) for ep in user_endpoints]
    
    # Активные инциденты
    incidents = list(db.incidents.find({
        "endpoint_id": {"$in": user_endpoint_ids},
        "ended_at": None
    }).sort("started_at", -1))
    
    for inc in incidents:
        inc['_id'] = str(inc['_id'])
        inc['started_at'] = inc['started_at'].isoformat()
        
        # Добавляем информацию об эндпоинте
        endpoint = next((ep for ep in user_endpoints if str(ep['_id']) == inc['endpoint_id']), None)
        inc['endpoint_name'] = endpoint['name'] if endpoint else 'Unknown'
    
    return jsonify({
        "active_incidents": incidents,
        "count": len(incidents)
    })

@bp.route('/stats', methods=['GET'])
@login_required
def get_incident_stats():
    """Получить статистику по инцидентам"""
    db = get_db()
    user_id = str(g.current_user['_id'])
    
    # Получаем эндпоинты пользователя
    user_endpoints = list(db.endpoints.find(
        {"user_id": user_id},
        {"_id": 1}
    ))
    user_endpoint_ids = [str(ep['_id']) for ep in user_endpoints]
    
    # Статистика по всем инцидентам пользователя
    pipeline = [
        {"$match": {"endpoint_id": {"$in": user_endpoint_ids}}},
        {"$group": {
            "_id": None,
            "total_incidents": {"$sum": 1},
            "avg_duration": {"$avg": "$duration_seconds"},
            "max_duration": {"$max": "$duration_seconds"},
            "active_count": {"$sum": {"$cond": [{"$eq": ["$ended_at", None]}, 1, 0]}}
        }}
    ]
    
    result = list(db.incidents.aggregate(pipeline))
    stats = result[0] if result else {
        "total_incidents": 0,
        "avg_duration": None,
        "max_duration": None,
        "active_count": 0
    }
    
    # Статистика по каждому эндпоинту
    per_endpoint = []
    for ep in user_endpoints:
        ep_stats = list(db.incidents.aggregate([
            {"$match": {"endpoint_id": str(ep['_id'])}},
            {"$group": {
                "_id": "$endpoint_id",
                "count": {"$sum": 1},
                "active": {"$sum": {"$cond": [{"$eq": ["$ended_at", None]}, 1, 0]}}
            }}
        ]))
        
        if ep_stats:
            endpoint_data = db.endpoints.find_one({"_id": ep['_id']})
            per_endpoint.append({
                "endpoint_id": str(ep['_id']),
                "endpoint_name": endpoint_data['name'] if endpoint_data else 'Unknown',
                "incident_count": ep_stats[0]['count'],
                "active_incidents": ep_stats[0]['active']
            })
    
    return jsonify({
        "global": stats,
        "per_endpoint": per_endpoint
    })