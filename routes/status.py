from flask import Blueprint, request, jsonify, g
from bson.objectid import ObjectId
from datetime import datetime, timedelta
from extensions.mongodb import get_db
from middlewares.auth import login_required

bp = Blueprint('status', __name__, url_prefix='/api/status')

@bp.route('/current', methods=['GET'])
@login_required
def current_status():
    """Текущий статус всех эндпоинтов пользователя"""
    db = get_db()
    user_id = str(g.current_user['_id'])
    
    endpoints = list(db.endpoints.find({"user_id": user_id}))
    
    result = []
    for endpoint in endpoints:
        # Получаем последнюю проверку
        last_check = db.checks.find_one(
            {"endpoint_id": str(endpoint['_id'])},
            sort=[("checked_at", -1)]
        )
        
        result.append({
            "id": str(endpoint['_id']),
            "name": endpoint['name'],
            "url": endpoint['url'],
            "active": endpoint.get('active', True),
            "status": last_check.get('status') if last_check else 'unknown',
            "latency_ms": last_check.get('latency_ms') if last_check else None,
            "last_check_at": last_check['checked_at'].isoformat() if last_check and last_check.get('checked_at') else None,
            "error_message": last_check.get('error_message') if last_check else None
        })
    
    return jsonify(result)

@bp.route('/<endpoint_id>', methods=['GET'])
@login_required
def endpoint_status(endpoint_id):
    """Детальный статус конкретного эндпоинта с метриками"""
    db = get_db()
    user_id = str(g.current_user['_id'])
    
    # Проверяем доступность эндпоинта
    endpoint = db.endpoints.find_one({
        "_id": ObjectId(endpoint_id),
        "user_id": user_id
    })
    
    if not endpoint:
        return jsonify({"error": "Endpoint not found"}), 404
    
    # Получаем последние 100 проверок
    checks = list(db.checks.find(
        {"endpoint_id": endpoint_id}
    ).sort("checked_at", -1).limit(100))
    
    # Считаем uptime за последние 24 часа
    day_ago = datetime.utcnow() - timedelta(hours=24)
    day_checks = [c for c in checks if c['checked_at'] >= day_ago]
    uptime_24h = 0
    if day_checks:
        up_count = sum(1 for c in day_checks if c['status'] == 'up')
        uptime_24h = (up_count / len(day_checks)) * 100
    
    # Средняя latency
    latencies = [c['latency_ms'] for c in checks if c.get('latency_ms')]
    avg_latency = sum(latencies) / len(latencies) if latencies else None
    
    return jsonify({
        "endpoint": {
            "id": str(endpoint['_id']),
            "name": endpoint['name'],
            "url": endpoint['url'],
            "interval": endpoint.get('interval', 60),
            "active": endpoint.get('active', True)
        },
        "metrics": {
            "uptime_24h": round(uptime_24h, 2),
            "avg_latency_ms": round(avg_latency, 2) if avg_latency else None,
            "total_checks": len(checks),
            "last_check": checks[0]['checked_at'].isoformat() if checks else None,
            "current_status": checks[0]['status'] if checks else 'unknown'
        },
        "recent_checks": [
            {
                "status": c['status'],
                "latency_ms": c.get('latency_ms'),
                "checked_at": c['checked_at'].isoformat(),
                "error_message": c.get('error_message')
            } for c in checks[:20]
        ]
    })

@bp.route('/history/<endpoint_id>', methods=['GET'])
@login_required
def status_history(endpoint_id):
    """История статусов за период (для графиков)"""
    db = get_db()
    user_id = str(g.current_user['_id'])
    
    # Проверяем доступ
    endpoint = db.endpoints.find_one({
        "_id": ObjectId(endpoint_id),
        "user_id": user_id
    })
    
    if not endpoint:
        return jsonify({"error": "Endpoint not found"}), 404
    
    # Параметры: hours (по умолчанию 24), resolution (в минутах, по умолчанию 60)
    hours = int(request.args.get('hours', 24))
    resolution = int(request.args.get('resolution', 60))  # минут
    
    since = datetime.utcnow() - timedelta(hours=hours)
    
    checks = list(db.checks.find({
        "endpoint_id": endpoint_id,
        "checked_at": {"$gte": since}
    }).sort("checked_at", 1))
    
    # Агрегируем по интервалам
    history = []
    for check in checks:
        history.append({
            "timestamp": check['checked_at'].isoformat(),
            "status": check['status'],
            "latency_ms": check.get('latency_ms')
        })
    
    return jsonify({
        "endpoint_id": endpoint_id,
        "period_hours": hours,
        "data": history
    })

@bp.route('/summary', methods=['GET'])
@login_required
def global_summary():
    """Агрегированная статистика по всем эндпоинтам пользователя"""
    db = get_db()
    user_id = str(g.current_user['_id'])
    
    endpoints = list(db.endpoints.find({"user_id": user_id}))
    
    total = len(endpoints)
    active = sum(1 for e in endpoints if e.get('active', True))
    
    # Получаем последний статус для каждого
    up_count = 0
    down_count = 0
    
    for endpoint in endpoints:
        last_check = db.checks.find_one(
            {"endpoint_id": str(endpoint['_id'])},
            sort=[("checked_at", -1)]
        )
        if last_check:
            if last_check['status'] == 'up':
                up_count += 1
            else:
                down_count += 1
    
    return jsonify({
        "total_endpoints": total,
        "active_endpoints": active,
        "up_endpoints": up_count,
        "down_endpoints": down_count,
        "uptime_percentage": round((up_count / active * 100), 2) if active > 0 else 0
    })