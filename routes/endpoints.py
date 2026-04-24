from flask import Blueprint, request, jsonify, g
from bson.objectid import ObjectId
from datetime import datetime
from extensions.mongodb import get_db
from middlewares.auth import login_required

bp = Blueprint('endpoints', __name__, url_prefix='/api/endpoints')

@bp.route('', methods=['GET'])
@login_required
def list_endpoints():
    """Список всех эндпоинтов текущего пользователя"""
    db = get_db()
    user_id = str(g.current_user['_id'])
    
    endpoints = list(db.endpoints.find({"user_id": user_id}))
    for e in endpoints:
        e['_id'] = str(e['_id'])
        e.pop('user_id', None)
    
    return jsonify(endpoints)

@bp.route('', methods=['POST'])
@login_required
def create_endpoint():
    """Создать новый эндпоинт для мониторинга"""
    data = request.json
    
    # Валидация
    if not data.get('name') or not data.get('url'):
        return jsonify({"error": "name and url are required"}), 400
    
    # Нормализация URL
    url = data['url'].strip()
    if not url.startswith(('http://', 'https://')):
        url = 'http://' + url
    
    db = get_db()
    endpoint = {
        "name": data['name'],
        "url": url,
        "method": data.get('method', 'GET'),
        "expected_status": data.get('expected_status', 200),
        "timeout": data.get('timeout', 5),
        "interval": data.get('interval', 60),  # секунд между проверками
        "active": data.get('active', True),
        "user_id": str(g.current_user['_id']),
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
        "last_check_at": None,
        "last_status": None
    }
    
    result = db.endpoints.insert_one(endpoint)
    
    return jsonify({
        "message": "Endpoint created",
        "id": str(result.inserted_id)
    }), 201

@bp.route('/<endpoint_id>', methods=['GET'])
@login_required
def get_endpoint(endpoint_id):
    """Получить детали конкретного эндпоинта"""
    db = get_db()
    user_id = str(g.current_user['_id'])
    
    try:
        endpoint = db.endpoints.find_one({
            "_id": ObjectId(endpoint_id),
            "user_id": user_id
        })
        
        if not endpoint:
            return jsonify({"error": "Endpoint not found"}), 404
        
        endpoint['_id'] = str(endpoint['_id'])
        endpoint.pop('user_id', None)
        
        # Добавляем последние проверки
        last_checks = list(db.checks.find(
            {"endpoint_id": endpoint_id}
        ).sort("checked_at", -1).limit(10))
        
        for check in last_checks:
            check['_id'] = str(check['_id'])
            check['checked_at'] = check['checked_at'].isoformat()
        
        endpoint['last_checks'] = last_checks
        
        return jsonify(endpoint)
        
    except:
        return jsonify({"error": "Invalid endpoint id"}), 400

@bp.route('/<endpoint_id>', methods=['PUT'])
@login_required
def update_endpoint(endpoint_id):
    """Обновить эндпоинт"""
    db = get_db()
    user_id = str(g.current_user['_id'])
    data = request.json
    
    # Разрешаем обновлять только определённые поля
    allowed_fields = ['name', 'url', 'method', 'expected_status', 
                     'timeout', 'interval', 'active']
    update_data = {k: v for k, v in data.items() if k in allowed_fields}
    
    if 'url' in update_data:
        url = update_data['url'].strip()
        if not url.startswith(('http://', 'https://')):
            url = 'http://' + url
        update_data['url'] = url
    
    update_data['updated_at'] = datetime.utcnow()
    
    result = db.endpoints.update_one(
        {"_id": ObjectId(endpoint_id), "user_id": user_id},
        {"$set": update_data}
    )
    
    if result.matched_count == 0:
        return jsonify({"error": "Endpoint not found"}), 404
    
    return jsonify({"message": "Endpoint updated"})

@bp.route('/<endpoint_id>', methods=['DELETE'])
@login_required
def delete_endpoint(endpoint_id):
    """Удалить эндпоинт и все связанные проверки"""
    db = get_db()
    user_id = str(g.current_user['_id'])
    
    try:
        # Удаляем сам эндпоинт
        result = db.endpoints.delete_one({
            "_id": ObjectId(endpoint_id),
            "user_id": user_id
        })
        
        if result.deleted_count == 0:
            return jsonify({"error": "Endpoint not found"}), 404
        
        # Удаляем все проверки и инциденты связанные с ним
        db.checks.delete_many({"endpoint_id": endpoint_id})
        db.incidents.delete_many({"endpoint_id": endpoint_id})
        
        return jsonify({"message": "Endpoint and related data deleted"})
        
    except:
        return jsonify({"error": "Invalid endpoint id"}), 400

@bp.route('/<endpoint_id>/toggle', methods=['PATCH'])
@login_required
def toggle_endpoint(endpoint_id):
    """Включить/выключить мониторинг эндпоинта"""
    db = get_db()
    user_id = str(g.current_user['_id'])
    
    endpoint = db.endpoints.find_one({
        "_id": ObjectId(endpoint_id),
        "user_id": user_id
    })
    
    if not endpoint:
        return jsonify({"error": "Endpoint not found"}), 404
    
    new_status = not endpoint.get('active', True)
    
    db.endpoints.update_one(
        {"_id": ObjectId(endpoint_id)},
        {"$set": {"active": new_status, "updated_at": datetime.utcnow()}}
    )
    
    return jsonify({
        "message": f"Monitoring {'enabled' if new_status else 'disabled'}",
        "active": new_status
    })