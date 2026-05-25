from datetime import datetime
from bson.objectid import ObjectId
from extensions.mongodb import get_db

class Incident:
    """Модель для работы с инцидентами"""
    
    @staticmethod
    def create_incident(endpoint_id: str, reason: str = None):
        """Создаёт новый инцидент"""
        db = get_db()
        
        # Проверяем, нет ли уже открытого инцидента
        existing = db.incidents.find_one({
            "endpoint_id": endpoint_id,
            "ended_at": None
        })
        
        if existing:
            return str(existing['_id'])
        
        incident = {
            "endpoint_id": endpoint_id,
            "started_at": datetime.utcnow(),
            "ended_at": None,
            "duration_seconds": None,
            "reason": reason or "Service unavailable",
            "severity": "high"  # high, medium, low
        }
        
        result = db.incidents.insert_one(incident)
        return str(result.inserted_id)
    
    @staticmethod
    def close_incident(endpoint_id: str):
        """Закрывает активный инцидент"""
        db = get_db()
        
        incident = db.incidents.find_one({
            "endpoint_id": endpoint_id,
            "ended_at": None
        })
        
        if incident:
            ended_at = datetime.utcnow()
            duration = int((ended_at - incident['started_at']).total_seconds())
            
            db.incidents.update_one(
                {"_id": incident['_id']},
                {"$set": {
                    "ended_at": ended_at,
                    "duration_seconds": duration
                }}
            )
            return True
        return False
    
    @staticmethod
    def get_active_incidents():
        """Получает все активные инциденты"""
        db = get_db()
        incidents = list(db.incidents.find({"ended_at": None}))
        
        for inc in incidents:
            inc['_id'] = str(inc['_id'])
            inc['started_at'] = inc['started_at'].isoformat() + 'Z'
        
        return incidents
    
    @staticmethod
    def get_incidents_by_endpoint(endpoint_id: str, limit: int = 50):
        """Получает инциденты для конкретного эндпоинта"""
        db = get_db()
        incidents = list(db.incidents.find(
            {"endpoint_id": endpoint_id}
        ).sort("started_at", -1).limit(limit))
        
        for inc in incidents:
            inc['_id'] = str(inc['_id'])
            inc['started_at'] = inc['started_at'].isoformat() + 'Z'
            if inc.get('ended_at'):
                inc['ended_at'] = inc['ended_at'].isoformat() + 'Z'
        
        return incidents
    
    @staticmethod
    def get_all_incidents(limit: int = 100, offset: int = 0):
        """Получает все инциденты с пагинацией"""
        db = get_db()
        incidents = list(db.incidents.find()
                         .sort("started_at", -1)
                         .skip(offset)
                         .limit(limit))
        
        for inc in incidents:
            inc['_id'] = str(inc['_id'])
            inc['started_at'] = inc['started_at'].isoformat() + 'Z'
            if inc.get('ended_at'):
                inc['ended_at'] = inc['ended_at'].isoformat() + 'Z'
        
        return incidents
    
    @staticmethod
    def get_incident_stats(endpoint_id: str = None):
        """Получает статистику по инцидентам"""
        db = get_db()
        
        match_stage = {}
        if endpoint_id:
            match_stage = {"endpoint_id": endpoint_id}
        
        pipeline = [
            {"$match": match_stage},
            {"$group": {
                "_id": None,
                "total_incidents": {"$sum": 1},
                "avg_duration": {"$avg": "$duration_seconds"},
                "max_duration": {"$max": "$duration_seconds"},
                "active_count": {"$sum": {"$cond": [{"$eq": ["$ended_at", None]}, 1, 0]}}
            }}
        ]
        
        result = list(db.incidents.aggregate(pipeline))
        
        if result:
            stats = result[0]
            stats['_id'] = None
            return stats
        
        return {
            "total_incidents": 0,
            "avg_duration": None,
            "max_duration": None,
            "active_count": 0
        }