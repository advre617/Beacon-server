from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from datetime import datetime, timedelta
from extensions.mongodb import get_db
from services.checker import check_endpoint, check_tcp_endpoint, check_endpoint_advanced
import time
import atexit

scheduler = None

def check_and_update_endpoint(endpoint):
    """
    Проверяет один эндпоинт и обновляет статус в БД
    """
    db = get_db()
    endpoint_id = str(endpoint['_id'])
    
    print(f"[{datetime.utcnow()}] Checking: {endpoint['name']} ({endpoint['url']})")
    
    # Выполняем проверку
    result = check_endpoint(endpoint)
    
    # Получаем последний известный статус
    last_check = db.checks.find_one(
        {"endpoint_id": endpoint_id},
        sort=[("checked_at", -1)]
    )
    
    previous_status = last_check['status'] if last_check else None
    current_status = result['status']
    
    # Сохраняем результат проверки
    db.checks.insert_one(result)
    
    # Обновляем last_check в эндпоинте
    db.endpoints.update_one(
        {"_id": endpoint['_id']},
        {"$set": {
            "last_check_at": result['checked_at'],
            "last_status": result['status']
        }}
    )
    
    # Если статус изменился с up на down - создаём инцидент
    if previous_status == 'up' and current_status == 'down':
        create_incident(endpoint_id, result['error_message'])
        print(f"  ⚠️  INCIDENT: {endpoint['name']} is DOWN!")
    
    # Если статус изменился с down на up - закрываем инцидент
    elif previous_status == 'down' and current_status == 'up':
        close_incident(endpoint_id)
        print(f"  ✅ RECOVERED: {endpoint['name']} is UP again!")
    
    else:
        status_icon = "✅" if current_status == "up" else "❌"
        print(f"  {status_icon} Status: {current_status} ({result.get('latency_ms', 'N/A')}ms)")
    
    return result

def create_incident(endpoint_id, reason):
    """
    Создаёт новый инцидент
    """
    db = get_db()
    
    # Проверяем, есть ли уже открытый инцидент для этого эндпоинта
    existing = db.incidents.find_one({
        "endpoint_id": endpoint_id,
        "ended_at": None
    })
    
    if not existing:
        incident = {
            "endpoint_id": endpoint_id,
            "started_at": datetime.utcnow(),
            "ended_at": None,
            "duration_seconds": None,
            "reason": reason or "Service unavailable"
        }
        db.incidents.insert_one(incident)

def close_incident(endpoint_id):
    """
    Закрывает активный инцидент
    """
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

def run_all_checks():
    """
    Запускает проверку всех активных эндпоинтов
    """
    db = get_db()
    
    # Получаем все активные эндпоинты
    endpoints = list(db.endpoints.find({"active": True}))
    
    if not endpoints:
        print(f"[{datetime.utcnow()}] No active endpoints to check")
        return
    
    print(f"\n{'='*60}")
    print(f"[{datetime.utcnow()}] Running checks for {len(endpoints)} endpoints")
    print(f"{'='*60}")
    
    for endpoint in endpoints:
        try:
            check_and_update_endpoint(endpoint)
        except Exception as e:
            print(f"  ❌ Error checking {endpoint['name']}: {str(e)}")
    
    print(f"{'='*60}\n")

def run_due_checks():
    """
    Запускает проверки только для эндпоинтов, у которых наступило время проверки
    Более эффективно, чем проверять все сразу
    """
    db = get_db()
    
    now = datetime.utcnow()
    
    # Получаем эндпоинты, которые нужно проверить сейчас
    # (last_check_at + interval <= now)
    endpoints = list(db.endpoints.find({
        "active": True,
        "$or": [
            {"last_check_at": {"$exists": False}},
            {"last_check_at": None},
            {"last_check_at": {"$lte": now - timedelta(seconds={"$field": "interval"})}}
        ]
    }))
    
    # Простой вариант - пока проверяем все активные
    # Для реального использования нужно агрегирование с $expr
    endpoints = list(db.endpoints.find({"active": True}))
    
    for endpoint in endpoints:
        interval = endpoint.get('interval', 60)
        last_check = endpoint.get('last_check_at')
        
        if last_check:
            time_since_last = (now - last_check).total_seconds()
            if time_since_last < interval:
                continue
        
        try:
            check_and_update_endpoint(endpoint)
        except Exception as e:
            print(f"Error checking {endpoint['name']}: {str(e)}")

def start_scheduler():
    """
    Запускает фоновый планировщик
    """
    global scheduler
    
    if scheduler is not None:
        print("Scheduler already running")
        return
    
    scheduler = BackgroundScheduler()
    
    # Добавляем задачу - проверять каждые 30 секунд
    # В реальности лучше проверять каждую минуту, но для демо подойдёт
    scheduler.add_job(
        func=run_all_checks,
        trigger=IntervalTrigger(seconds=30),
        id='monitor_checks',
        name='Run all endpoint checks',
        replace_existing=True
    )
    
    scheduler.start()
    print("✅ Scheduler started - checking endpoints every 30 seconds")
    
    # Останавливаем планировщик при завершении приложения
    atexit.register(shutdown_scheduler)

def shutdown_scheduler():
    """
    Останавливает планировщик
    """
    global scheduler
    if scheduler:
        scheduler.shutdown()
        print("🛑 Scheduler stopped")

# Для тестирования без Flask
if __name__ == "__main__":
    import sys
    sys.path.append('.')
    
    from config import Config
    from pymongo import MongoClient
    
    # Инициализируем подключение к БД для теста
    client = MongoClient(Config.MONGO_URI)
    db = client[Config.DB_NAME]
    
    # Временная замена get_db
    def get_db():
        return db
    
    import builtins
    builtins.get_db = get_db
    
    # Запускаем одну проверку
    run_all_checks()