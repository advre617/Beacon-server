from flask import Blueprint, request, jsonify, g
from bson.objectid import ObjectId
from datetime import datetime
from extensions.mongodb import get_db
from middlewares.auth import login_required

bp = Blueprint('endpoints', __name__, url_prefix='/api/endpoints')

@bp.route('', methods=['GET'])
@login_required
def list_endpoints():
    db = get_db()
    user_id = str(g.current_user['_id'])
    
    endpoints = list(db.endpoints.find({"user_id": user_id}))
    result = []
    for e in endpoints:
        e['_id'] = str(e['_id'])
        e.pop('user_id', None)
        # Маппим last_status → status для фронта
        e['status'] = e.pop('last_status', None) or 'unknown'
        # Сериализуем datetime
        if e.get('last_check_at'):
            e['last_check_at'] = e['last_check_at'].isoformat() + 'Z'
        if e.get('created_at'):
            e['created_at'] = e['created_at'].isoformat() + 'Z'
        if e.get('updated_at'):
            e['updated_at'] = e['updated_at'].isoformat() + 'Z'
        result.append(e)
    
    return jsonify(result)

@bp.route('', methods=['POST'])
@login_required
def create_endpoint():
    data = request.json

    if not data.get('name') or not data.get('url'):
        return jsonify({"error": "name and url are required"}), 400

    url = data['url'].strip()
    if not url.startswith(('http://', 'https://')):
        url = 'http://' + url

    db = get_db()
    endpoint = {
        "name": data['name'],
        "url": url,
        "method": data.get('method', 'GET'),
        "expected_status": data.get('expected_status', 200),
        "expected_body": data.get('expected_body', ''),
        "expected_body_type": data.get('expected_body_type', 'none'),
        "timeout": data.get('timeout', 10),
        "interval": data.get('interval', 300),
        "active": data.get('active', True),

        "auth_type": data.get('auth_type', 'none'),
        "auth_bearer_token": data.get('auth_bearer_token', ''),
        "auth_basic_user": data.get('auth_basic_user', ''),
        "auth_basic_pass": data.get('auth_basic_pass', ''),
        "auth_api_key_header": data.get('auth_api_key_header', 'X-API-Key'),
        "auth_api_key_value": data.get('auth_api_key_value', ''),

        "headers": data.get('headers', []),
        "body": data.get('body', ''),
        "body_content_type": data.get('body_content_type', 'application/json'),

        "follow_redirects": data.get('follow_redirects', True),
        "ssl_verify": data.get('ssl_verify', True),
        "max_redirects": data.get('max_redirects', 5),

        "user_id": str(g.current_user['_id']),
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
        "last_check_at": None,
        "last_status": None,
        "latency_ms": None,
    }

    result = db.endpoints.insert_one(endpoint)
    return jsonify({"message": "Endpoint created", "id": str(result.inserted_id)}), 201

@bp.route('/<endpoint_id>', methods=['GET'])
@login_required
def get_endpoint(endpoint_id):
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
        endpoint['id'] = endpoint['_id']  
        endpoint['status'] = endpoint.pop('last_status', None) or 'unknown'
        
        for field in ['last_check_at', 'created_at', 'updated_at']:
            if endpoint.get(field):
                endpoint[field] = endpoint[field].isoformat() + 'Z'

        endpoint.pop('user_id', None)
        
        last_checks = list(db.checks.find(
            {"endpoint_id": endpoint_id}
        ).sort("checked_at", -1).limit(50)) 
        
        for check in last_checks:
            check['_id'] = str(check['_id'])
            if check.get('checked_at'):
                check['checked_at'] = check['checked_at'].isoformat() + 'Z'

        
        endpoint['last_checks'] = last_checks
        
        print(f"GET endpoint fields: {list(endpoint.keys())}") 
        
        return jsonify(endpoint)
        
    except Exception as e:
        print(f"GET endpoint error: {e}")  
        return jsonify({"error": "Invalid endpoint id"}), 400

@bp.route('/<endpoint_id>', methods=['PUT'])
@login_required
def update_endpoint(endpoint_id):
    db = get_db()
    user_id = str(g.current_user['_id'])
    data = request.json

    print(f"endpoint_id: {endpoint_id}")
    print(f"user_id: {user_id}")
    print(f"data keys: {list(data.keys()) if data else 'NO DATA'}")

    allowed_fields = [
        'name', 'url', 'method', 'expected_status', 'expected_body',
        'expected_body_type', 'timeout', 'interval', 'active',
        'auth_type', 'auth_bearer_token', 'auth_basic_user', 'auth_basic_pass',
        'auth_api_key_header', 'auth_api_key_value',
        'headers', 'body', 'body_content_type',
        'follow_redirects', 'ssl_verify', 'max_redirects',
    ]
    update_data = {k: v for k, v in data.items() if k in allowed_fields}
    
    print(f"update_data: {update_data}")

    update_data['updated_at'] = datetime.utcnow()

    result = db.endpoints.update_one(
        {"_id": ObjectId(endpoint_id), "user_id": user_id},
        {"$set": update_data}
    )

    print(f"matched: {result.matched_count}, modified: {result.modified_count}")

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