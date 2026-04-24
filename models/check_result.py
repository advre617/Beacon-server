from datetime import datetime, timedelta
from bson.objectid import ObjectId
from extensions.mongodb import get_db

class CheckResult:
    """Модель для работы с результатами проверок"""
    
    @staticmethod
    def create_check(endpoint_id: str, status: str, latency_ms: int = None, 
                     http_status: int = None, error_message: str = None):
        """Создаёт новую запись о проверке"""
        db = get_db()
        check = {
            "endpoint_id": endpoint_id,
            "status": status,  # 'up' or 'down'
            "latency_ms": latency_ms,
            "http_status": http_status,
            "error_message": error_message,
            "checked_at": datetime.utcnow()
        }
        result = db.checks.insert_one(check)
        return str(result.inserted_id)
    
    @staticmethod
    def get_last_check(endpoint_id: str):
        """Получает последнюю проверку эндпоинта"""
        db = get_db()
        return db.checks.find_one(
            {"endpoint_id": endpoint_id},
            sort=[("checked_at", -1)]
        )
    
    @staticmethod
    def get_checks_history(endpoint_id: str, limit: int = 100):
        """Получает историю проверок"""
        db = get_db()
        checks = list(db.checks.find(
            {"endpoint_id": endpoint_id}
        ).sort("checked_at", -1).limit(limit))
        
        for check in checks:
            check['_id'] = str(check['_id'])
            check['checked_at'] = check['checked_at'].isoformat()
        
        return checks
    
    @staticmethod
    def get_checks_by_period(endpoint_id: str, start_date: datetime, end_date: datetime):
        """Получает проверки за период"""
        db = get_db()
        checks = list(db.checks.find({
            "endpoint_id": endpoint_id,
            "checked_at": {"$gte": start_date, "$lte": end_date}
        }).sort("checked_at", 1))
        
        for check in checks:
            check['_id'] = str(check['_id'])
            check['checked_at'] = check['checked_at'].isoformat()
        
        return checks
    
    @staticmethod
    def calculate_uptime(endpoint_id: str, hours: int = 24):
        """Рассчитывает uptime в процентах за последние N часов"""
        db = get_db()
        since = datetime.utcnow() - timedelta(hours=hours)
        
        checks = list(db.checks.find({
            "endpoint_id": endpoint_id,
            "checked_at": {"$gte": since}
        }))
        
        if not checks:
            return 0
        
        up_count = sum(1 for c in checks if c['status'] == 'up')
        return (up_count / len(checks)) * 100
    
    @staticmethod
    def get_average_latency(endpoint_id: str, hours: int = 24):
        """Рассчитывает среднюю задержку за последние N часов"""
        db = get_db()
        since = datetime.utcnow() - timedelta(hours=hours)
        
        checks = list(db.checks.find({
            "endpoint_id": endpoint_id,
            "checked_at": {"$gte": since},
            "latency_ms": {"$ne": None}
        }))
        
        if not checks:
            return None
        
        latencies = [c['latency_ms'] for c in checks if c.get('latency_ms')]
        return sum(latencies) / len(latencies) if latencies else None