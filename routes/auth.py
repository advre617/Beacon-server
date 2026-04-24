from flask import Blueprint, request, jsonify, g
from utils.security import hash_password, verify_password, generate_access_token, generate_refresh_token
from models.user import User
from middlewares.auth import login_required
from utils.security import decode_token

bp = Blueprint('auth', __name__, url_prefix='/api/auth')

@bp.route('/register', methods=['POST'])
def register():
    data = request.json
    
    required_fields = ['email', 'username', 'password']
    for field in required_fields:
        if field not in data:
            return jsonify({"error": f"Missing field: {field}"}), 400
    
    email = data['email']
    username = data['username']
    password = data['password']
    
    if len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters"}), 400
    
    if '@' not in email:
        return jsonify({"error": "Invalid email format"}), 400
    
    existing_user = User.find_by_email(email)
    if existing_user:
        return jsonify({"error": "User with this email already exists"}), 409
    
    password_hash = hash_password(password)
    user_id = User.create_user(email, username, password_hash)
    
    access_token = generate_access_token(user_id)
    refresh_token = generate_refresh_token(user_id)
    
    return jsonify({
        "message": "User registered successfully",
        "user_id": user_id,
        "access_token": access_token,
        "refresh_token": refresh_token
    }), 201

@bp.route('/login', methods=['POST'])
def login():
    data = request.json
    
    if not data.get('email') or not data.get('password'):
        return jsonify({"error": "Email and password required"}), 400
    
    user = User.find_by_email(data['email'])
    
    if not user:
        return jsonify({"error": "Invalid credentials"}), 401
    
    if not verify_password(data['password'], user['password_hash']):
        return jsonify({"error": "Invalid credentials"}), 401
    
    if not user.get('is_active', True):
        return jsonify({"error": "Account is disabled"}), 403
    
    User.update_last_login(str(user['_id']))
    
    access_token = generate_access_token(str(user['_id']))
    refresh_token = generate_refresh_token(str(user['_id']))
    
    return jsonify({
        "message": "Login successful",
        "user": User.to_dict(user),
        "access_token": access_token,
        "refresh_token": refresh_token
    }), 200

@bp.route('/refresh', methods=['POST'])
def refresh_token():
    data = request.json
    
    if not data.get('refresh_token'):
        return jsonify({"error": "Refresh token required"}), 400
    
    try:
        payload = decode_token(data['refresh_token'])
        
        if payload.get('type') != 'refresh':
            return jsonify({"error": "Invalid token type"}), 401
        
        user = User.find_by_id(payload['user_id'])
        if not user:
            return jsonify({"error": "User not found"}), 401
        
        new_access_token = generate_access_token(str(user['_id']))
        
        return jsonify({
            "access_token": new_access_token
        }), 200
        
    except Exception as e:
        return jsonify({"error": str(e)}), 401

@bp.route('/me', methods=['GET'])
@login_required
def get_current_user():
    return jsonify({
        "user": User.to_dict(g.current_user)
    }), 200

@bp.route('/logout', methods=['POST'])
@login_required
def logout():
    return jsonify({"message": "Logged out successfully"}), 200