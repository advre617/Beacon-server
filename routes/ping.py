from flask import Blueprint, jsonify
from datetime import datetime
from extensions.mongodb import get_db

bp = Blueprint('ping', __name__, url_prefix='/ping')

@bp.route('', methods=['GET'])
def ping():
    """Простой healthcheck для API"""
    return jsonify({
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat() + 'Z',
        "service": "Beacon Monitor API"
    })

@bp.route('/db', methods=['GET'])
def ping_db():
    """Проверка подключения к базе данных"""
    try:
        db = get_db()
        # Выполняем простую команду
        db.command('ping')
        
        # Считаем количество эндпоинтов
        endpoints_count = db.endpoints.count_documents({})
        checks_count = db.checks.count_documents({})
        
        return jsonify({
            "status": "ok",
            "database": "connected",
            "statistics": {
                "endpoints": endpoints_count,
                "checks": checks_count,
                "incidents": db.incidents.count_documents({}),
                "users": db.users.count_documents({})
            },
            "timestamp": datetime.utcnow().isoformat() + 'Z'
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "database": "disconnected",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat() + 'Z'
        }), 500

@bp.route('/info', methods=['GET'])
def system_info():
    """Информация о системе (для отладки)"""
    import platform
    import sys
    
    return jsonify({
        "service": "Beacon Monitor",
        "version": "1.0.0",
        "python_version": sys.version,
        "platform": platform.platform(),
        "timestamp": datetime.utcnow().isoformat() + 'Z'
    })