from functools import wraps
from flask import request, jsonify, g
from utils.security import decode_token
from models.user import User

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = None

        # Сначала из заголовка (обычные запросы)
        auth_header = request.headers.get('Authorization')
        if auth_header and auth_header.startswith('Bearer '):
            token = auth_header.split(' ')[1]

        # Fallback — из query параметра (для SSE, т.к. EventSource не поддерживает заголовки)
        if not token:
            token = request.args.get('token')

        if not token:
            return jsonify({"error": "Missing authorization"}), 401

        try:
            payload = decode_token(token)

            if payload.get('type') != 'access':
                return jsonify({"error": "Invalid token type"}), 401

            user = User.find_by_id(payload['user_id'])
            if not user:
                return jsonify({"error": "User not found"}), 401

            if not user.get('is_active'):
                return jsonify({"error": "User account is disabled"}), 401

            g.current_user = user

        except Exception as e:
            return jsonify({"error": str(e)}), 401

        return f(*args, **kwargs)

    return decorated_function