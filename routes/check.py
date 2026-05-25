from flask import Blueprint, request, jsonify, g
from bson.objectid import ObjectId
from extensions.mongodb import get_db
from middlewares.auth import login_required
from services.checker import check_endpoint

bp = Blueprint('check', __name__, url_prefix='/api/check')

@bp.route('/now/<endpoint_id>', methods=['POST'])
@login_required
def check_now(endpoint_id):
    """Принудительно проверить эндпоинт"""
    db = get_db()
    user_id = str(g.current_user['_id'])
    
    endpoint = db.endpoints.find_one({
        "_id": ObjectId(endpoint_id),
        "user_id": user_id
    })
    
    if not endpoint:
        return jsonify({"error": "Endpoint not found"}), 404
    
    # Выполняем проверку
    result = check_endpoint(endpoint)
    
    # Сохраняем результат
    db.checks.insert_one(result)
    
    # Обновляем last_check в эндпоинте
    db.endpoints.update_one(
        {"_id": ObjectId(endpoint_id)},
        {"$set": {
            "last_check_at": result['checked_at'],
            "last_status": result['status'],
            "latency_ms": result.get('latency_ms'),  # ← добавь это
        }}
    )

    
    return jsonify({
        "status": result['status'],
        "latency_ms": result.get('latency_ms'),
        "error_message": result.get('error_message'),
        "checked_at": result['checked_at'].isoformat() + 'Z'
    })

@bp.route('/batch', methods=['POST'])
@login_required
def check_batch():
    """Проверить все активные эндпоинты пользователя"""
    db = get_db()
    user_id = str(g.current_user['_id'])
    
    endpoints = list(db.endpoints.find({
        "user_id": user_id,
        "active": True
    }))
    
    results = []
    for endpoint in endpoints:
        result = check_endpoint(endpoint)
        db.checks.insert_one(result)
        results.append({
            "endpoint_id": str(endpoint['_id']),
            "name": endpoint['name'],
            "status": result['status']
        })
    
    return jsonify({
        "total": len(results),
        "results": results
    })

# В routes/check.py - исправленная версия
@bp.route('/recent', methods=['GET'])
@login_required
def recent_checks():
    """Получить последние проверки для дашборда"""
    db = get_db()
    user_id = str(g.current_user['_id'])
    
    # Получаем все эндпоинты пользователя
    endpoints = list(db.endpoints.find({"user_id": user_id}))
    endpoint_ids = [str(e['_id']) for e in endpoints]
    
    if not endpoint_ids:
        return jsonify([])
    
    # Получаем последние проверки
    checks_list = list(db.checks.find(
        {"endpoint_id": {"$in": endpoint_ids}}
    ).sort("checked_at", -1).limit(50))
    
    # Создаём карту имён эндпоинтов
    endpoint_map = {str(e['_id']): e['name'] for e in endpoints}
    
    result = []
    for check in checks_list:
        result.append({
            "id": str(check['_id']),
            "endpoint_id": check['endpoint_id'],
            "endpoint_name": endpoint_map.get(check['endpoint_id'], 'Unknown'),
            "status": check['status'],
            "latency_ms": check.get('latency_ms'),
            "checked_at": check['checked_at'].isoformat() + 'Z' if check.get('checked_at') else None,
            "error_message": check.get('error_message')
        })
    
    return jsonify(result)