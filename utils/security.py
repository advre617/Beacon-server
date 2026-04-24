import bcrypt
import jwt
from datetime import datetime, timedelta
from flask import current_app

def hash_password(password: str) -> str:
    """Хэширует пароль с помощью bcrypt"""
    salt = bcrypt.gensalt(rounds=current_app.config['BCRYPT_ROUNDS'])
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

def verify_password(password: str, password_hash: str) -> bool:
    """Проверяет пароль"""
    return bcrypt.checkpw(
        password.encode('utf-8'), 
        password_hash.encode('utf-8')
    )

def generate_access_token(user_id: str) -> str:
    """Генерирует JWT access token"""
    payload = {
        'user_id': user_id,
        'exp': datetime.utcnow() + current_app.config['JWT_ACCESS_TOKEN_EXPIRES'],
        'iat': datetime.utcnow(),
        'type': 'access'
    }
    return jwt.encode(payload, current_app.config['JWT_SECRET'], algorithm='HS256')

def generate_refresh_token(user_id: str) -> str:
    """Генерирует JWT refresh token"""
    payload = {
        'user_id': user_id,
        'exp': datetime.utcnow() + current_app.config['JWT_REFRESH_TOKEN_EXPIRES'],
        'iat': datetime.utcnow(),
        'type': 'refresh'
    }
    return jwt.encode(payload, current_app.config['JWT_SECRET'], algorithm='HS256')

def decode_token(token: str) -> dict:
    """Декодирует и валидирует JWT токен"""
    try:
        payload = jwt.decode(
            token, 
            current_app.config['JWT_SECRET'], 
            algorithms=['HS256']
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise Exception("Token expired")
    except jwt.InvalidTokenError:
        raise Exception("Invalid token")