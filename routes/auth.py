from flask import Blueprint, request, jsonify, g
from datetime import datetime, timedelta
from extensions.mongodb import get_db
from bson.objectid import ObjectId
from utils.security import hash_password, verify_password, generate_access_token, generate_refresh_token, decode_token
from models.user import User
from middlewares.auth import login_required

bp = Blueprint('auth', __name__, url_prefix='/api/auth')


def _upsert_session(user_id: str, refresh_token: str):
    db = get_db()
    ua = request.headers.get('User-Agent', 'Unknown')
    ip = request.remote_addr or 'Unknown'

    db.sessions.insert_one({
        "user_id": user_id,
        "refresh_token": refresh_token,
        "user_agent": ua,
        "ip_address": ip,
        "created_at": datetime.utcnow(),
        "last_used_at": datetime.utcnow(),
        "expires_at": datetime.utcnow() + timedelta(days=30),
    })


@bp.route('/register', methods=['POST'])
def register():
    data = request.json or {}

    for field in ['email', 'username', 'password']:
        if not data.get(field):
            return jsonify({"error": f"Missing field: {field}"}), 400

    email = data['email'].strip().lower()
    username = data['username'].strip()
    password = data['password']

    if len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters"}), 400

    if '@' not in email:
        return jsonify({"error": "Invalid email format"}), 400

    if User.find_by_email(email):
        return jsonify({"error": "User with this email already exists"}), 409

    password_hash = hash_password(password)
    user_id = User.create_user(email, username, password_hash)

    access_token = generate_access_token(user_id)
    refresh_token = generate_refresh_token(user_id)
    _upsert_session(user_id, refresh_token)

    return jsonify({
        "message": "User registered successfully",
        "user_id": user_id,
        "access_token": access_token,
        "refresh_token": refresh_token,
    }), 201


@bp.route('/login', methods=['POST'])
def login():
    data = request.json or {}

    if not data.get('email') or not data.get('password'):
        return jsonify({"error": "Email and password required"}), 400

    user = User.find_by_email(data['email'].strip().lower())

    if not user or not verify_password(data['password'], user['password_hash']):
        return jsonify({"error": "Invalid credentials"}), 401

    if not user.get('is_active', True):
        return jsonify({"error": "Account is disabled"}), 403

    User.update_last_login(str(user['_id']))

    access_token = generate_access_token(str(user['_id']))
    refresh_token = generate_refresh_token(str(user['_id']))
    _upsert_session(str(user['_id']), refresh_token)

    return jsonify({
        "message": "Login successful",
        "user": User.to_dict(user),
        "access_token": access_token,
        "refresh_token": refresh_token,
    }), 200


@bp.route('/refresh', methods=['POST'])
def refresh_token():
    data = request.json or {}

    if not data.get('refresh_token'):
        return jsonify({"error": "Refresh token required"}), 400

    db = get_db()

    try:
        payload = decode_token(data['refresh_token'])
        if payload.get('type') != 'refresh':
            return jsonify({"error": "Invalid token type"}), 401
    except Exception as e:
        return jsonify({"error": str(e)}), 401

    session = db.sessions.find_one({
        "refresh_token": data['refresh_token'],
        "expires_at": {"$gt": datetime.utcnow()},
    })
    if not session:
        return jsonify({"error": "Session expired or revoked"}), 401

    user = User.find_by_id(payload['user_id'])
    if not user:
        return jsonify({"error": "User not found"}), 401

    db.sessions.update_one(
        {"_id": session['_id']},
        {"$set": {"last_used_at": datetime.utcnow()}}
    )

    new_access_token = generate_access_token(str(user['_id']))
    return jsonify({"access_token": new_access_token}), 200


@bp.route('/me', methods=['GET'])
@login_required
def get_current_user():
    return jsonify({"user": User.to_dict(g.current_user)}), 200


@bp.route('/logout/all', methods=['POST'])
@login_required
def logout_all():
    """Завершить все сессии кроме текущей"""
    db = get_db()
    user_id = str(g.current_user['_id'])
    
    ua = request.headers.get('User-Agent', '')
    ip = request.remote_addr or ''
    
    current_session = db.sessions.find_one({
        "user_id": user_id,
        "user_agent": ua,
        "ip_address": ip,
    })
    
    if current_session:
        db.sessions.delete_many({
            "user_id": user_id,
            "_id": {"$ne": current_session['_id']}
        })
    else:
        db.sessions.delete_many({"user_id": user_id})
    
    return jsonify({"message": "All other sessions terminated"}), 200


@bp.route('/me', methods=['DELETE'])
@login_required
def delete_account():
    """Полное удаление аккаунта"""
    db = get_db()
    user_id = str(g.current_user['_id'])
    
    db.sessions.delete_many({"user_id": user_id})
    
    result = db.users.delete_one({"_id": ObjectId(user_id)})
    
    if result.deleted_count == 0:
        return jsonify({"error": "User not found"}), 404
    
    return jsonify({"message": "Account permanently deleted"}), 200

@bp.route('/me', methods=['PUT'])
@login_required
def update_profile():
    """Обновить профиль пользователя (username, email)"""
    db = get_db()
    data = request.json or {}
    user_id = str(g.current_user['_id'])
    
    # Проверяем, что есть что обновлять
    if 'username' not in data and 'email' not in data:
        return jsonify({"error": "Nothing to update"}), 400
    
    update_data = {}
    
    # Обновляем username если передан
    if 'username' in data and data['username']:
        username = data['username'].strip()
        if len(username) < 3:
            return jsonify({"error": "Username must be at least 3 characters"}), 400
        
        # Проверяем, не занят ли username другим пользователем
        existing = db.users.find_one({
            "username": username,
            "_id": {"$ne": ObjectId(user_id)}
        })
        if existing:
            return jsonify({"error": "Username already taken"}), 409
        
        update_data['username'] = username
    
    # Обновляем email если передан
    if 'email' in data and data['email']:
        email = data['email'].strip().lower()
        if '@' not in email:
            return jsonify({"error": "Invalid email format"}), 400
        
        # Проверяем, не занят ли email другим пользователем
        existing = db.users.find_one({
            "email": email,
            "_id": {"$ne": ObjectId(user_id)}
        })
        if existing:
            return jsonify({"error": "Email already in use"}), 409
        
        update_data['email'] = email
    
    if not update_data:
        return jsonify({"error": "No valid fields to update"}), 400
    
    update_data['updated_at'] = datetime.utcnow()
    
    db.users.update_one(
        {"_id": ObjectId(user_id)},
        {"$set": update_data}
    )
    
    # Возвращаем обновленного пользователя
    updated_user = User.find_by_id(user_id)
    return jsonify({"user": User.to_dict(updated_user)}), 200


@bp.route('/me/password', methods=['PUT'])
@login_required
def change_password():
    """Сменить пароль"""
    db = get_db()
    data = request.json or {}
    user_id = str(g.current_user['_id'])

    current = data.get('current', '')
    new_password = data.get('new', '')
    confirm = data.get('confirm', '')

    if not current or not new_password or not confirm:
        return jsonify({"error": "All fields are required"}), 400

    if new_password != confirm:
        return jsonify({"error": "Passwords do not match"}), 400

    if len(new_password) < 6:
        return jsonify({"error": "Password must be at least 6 characters"}), 400

    user = User.find_by_id(user_id)
    if not verify_password(current, user['password_hash']):
        return jsonify({"error": "Current password is incorrect"}), 401

    db.users.update_one(
        {"_id": ObjectId(user_id)},
        {"$set": {"password_hash": hash_password(new_password), "updated_at": datetime.utcnow()}}
    )
    return jsonify({"message": "Password updated"}), 200


@bp.route('/logout', methods=['POST'])
@login_required
def logout():
    db = get_db()
    data = request.json or {}
    user_id = str(g.current_user['_id'])

    if data.get('refresh_token'):
        db.sessions.delete_one({
            "user_id": user_id,
            "refresh_token": data['refresh_token'],
        })
    else:
        ua = request.headers.get('User-Agent', '')
        ip = request.remote_addr or ''
        db.sessions.delete_one({
            "user_id": user_id,
            "user_agent": ua,
            "ip_address": ip,
        })

    return jsonify({"message": "Logged out successfully"}), 200