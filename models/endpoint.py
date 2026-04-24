from datetime import datetime
from urllib.parse import urlparse
from bson.objectid import ObjectId
from extensions.mongodb import get_db

class Endpoint:
    """Модель для работы с эндпоинтами мониторинга"""
    
    @staticmethod
    def create_endpoint(user_id: str, name: str, url: str, **kwargs):
        """Создаёт новый эндпоинт"""
        db = get_db()
        
        # Нормализация URL
        if not url.startswith(('http://', 'https://')):
            url = 'http://' + url
        
        endpoint = {
            "user_id": user_id,
            "name": name,
            "url": url,
            "method": kwargs.get('method', 'GET'),
            "expected_status": kwargs.get('expected_status', 200),
            "timeout": kwargs.get('timeout', 5),
            "interval": kwargs.get('interval', 60),
            "active": kwargs.get('active', True),
            "type": kwargs.get('type', 'http'),  # http, tcp, ping
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "last_check_at": None,
            "last_status": None
        }
        
        # Дополнительные поля для TCP/Ping
        if endpoint['type'] == 'tcp':
            endpoint['port'] = kwargs.get('port', 80)
        elif endpoint['type'] == 'ping':
            endpoint['host'] = kwargs.get('host') or urlparse(url).hostname
        
        result = db.endpoints.insert_one(endpoint)
        return str(result.inserted_id)
    
    @staticmethod
    def get_user_endpoints(user_id: str, active_only: bool = False):
        """Получает все эндпоинты пользователя"""
        db = get_db()
        query = {"user_id": user_id}
        
        if active_only:
            query["active"] = True
        
        endpoints = list(db.endpoints.find(query))
        
        for ep in endpoints:
            ep['_id'] = str(ep['_id'])
            ep.pop('user_id', None)
        
        return endpoints
    
    @staticmethod
    def get_endpoint_by_id(endpoint_id: str, user_id: str = None):
        """Получает эндпоинт по ID"""
        db = get_db()
        query = {"_id": ObjectId(endpoint_id)}
        
        if user_id:
            query["user_id"] = user_id
        
        endpoint = db.endpoints.find_one(query)
        
        if endpoint:
            endpoint['_id'] = str(endpoint['_id'])
            endpoint.pop('user_id', None)
        
        return endpoint
    
    @staticmethod
    def update_endpoint(endpoint_id: str, user_id: str, update_data: dict):
        """Обновляет эндпоинт"""
        db = get_db()
        
        allowed_fields = ['name', 'url', 'method', 'expected_status', 
                         'timeout', 'interval', 'active', 'type']
        
        update_dict = {k: v for k, v in update_data.items() if k in allowed_fields}
        update_dict['updated_at'] = datetime.utcnow()
        
        # Нормализация URL если обновляется
        if 'url' in update_dict:
            url = update_dict['url'].strip()
            if not url.startswith(('http://', 'https://')):
                url = 'http://' + url
            update_dict['url'] = url
        
        result = db.endpoints.update_one(
            {"_id": ObjectId(endpoint_id), "user_id": user_id},
            {"$set": update_dict}
        )
        
        return result.modified_count > 0
    
    @staticmethod
    def delete_endpoint(endpoint_id: str, user_id: str):
        """Удаляет эндпоинт и связанные данные"""
        db = get_db()
        
        # Удаляем эндпоинт
        result = db.endpoints.delete_one({
            "_id": ObjectId(endpoint_id),
            "user_id": user_id
        })
        
        if result.deleted_count > 0:
            # Удаляем связанные проверки и инциденты
            db.checks.delete_many({"endpoint_id": endpoint_id})
            db.incidents.delete_many({"endpoint_id": endpoint_id})
            return True
        
        return False
    
    @staticmethod
    def toggle_endpoint(endpoint_id: str, user_id: str):
        """Включает/выключает мониторинг эндпоинта"""
        db = get_db()
        
        endpoint = db.endpoints.find_one({
            "_id": ObjectId(endpoint_id),
            "user_id": user_id
        })
        
        if not endpoint:
            return None
        
        new_status = not endpoint.get('active', True)
        
        db.endpoints.update_one(
            {"_id": ObjectId(endpoint_id)},
            {"$set": {"active": new_status, "updated_at": datetime.utcnow()}}
        )
        
        return new_status