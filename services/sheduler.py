from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from datetime import datetime, timedelta
from extensions.mongodb import get_db
from services.checker import check_endpoint
import atexit

scheduler = None

def check_and_update_endpoint(endpoint):
    db = get_db()
    endpoint_id = str(endpoint['_id'])

    print(f"[{datetime.utcnow()}] Checking: {endpoint['name']} ({endpoint['url']})")

    result = check_endpoint(endpoint)

    last_check = db.checks.find_one(
        {"endpoint_id": endpoint_id},
        sort=[("checked_at", -1)]
    )

    previous_status = last_check['status'] if last_check else None
    current_status = result['status']

    db.checks.insert_one(result)

    db.endpoints.update_one(
        {"_id": endpoint['_id']},
        {"$set": {
            "last_check_at": result['checked_at'],
            "last_status": result['status'],
            "latency_ms": result.get('latency_ms'),
        }}
    )

    if previous_status == 'up' and current_status == 'down':
        create_incident(endpoint_id, result['error_message'])
        print(f"    INCIDENT: {endpoint['name']} is DOWN!")
    elif previous_status == 'down' and current_status == 'up':
        close_incident(endpoint_id)
        print(f"   RECOVERED: {endpoint['name']} is UP again!")
    else:
        icon = "✅" if current_status == "up" else "❌"
        print(f"  {icon} Status: {current_status} ({result.get('latency_ms', 'N/A')}ms)")

    return result


def create_incident(endpoint_id, reason):
    db = get_db()
    existing = db.incidents.find_one({"endpoint_id": endpoint_id, "ended_at": None})
    if not existing:
        db.incidents.insert_one({
            "endpoint_id": endpoint_id,
            "started_at": datetime.utcnow(),
            "ended_at": None,
            "duration_seconds": None,
            "reason": reason or "Service unavailable",
            "status": "open",           # ← новое
            "acknowledged_at": None,    # ← новое
            "acknowledged_by": None,    # ← новое
            "note": "",                 # ← новое
            "resolved_manually": False, # ← новое
            "resolution_note": "",      # ← новое
        })

def close_incident(endpoint_id):
    db = get_db()
    incident = db.incidents.find_one({"endpoint_id": endpoint_id, "ended_at": None})
    if incident:
        ended_at = datetime.utcnow()
        db.incidents.update_one(
            {"_id": incident['_id']},
            {"$set": {
                "ended_at": ended_at,
                "duration_seconds": int((ended_at - incident['started_at']).total_seconds()),
                "status": "resolved",  # ← новое
            }}
        )


def run_due_checks():
    """
    Запускает проверки только тех эндпоинтов,
    у которых прошло достаточно времени с последней проверки.
    """
    db = get_db()
    now = datetime.utcnow()

    # Берём все активные эндпоинты — фильтрацию делаем в Python,
    # потому что interval у каждого свой
    endpoints = list(db.endpoints.find({"active": True}))

    if not endpoints:
        print(f"[{now}] No active endpoints")
        return

    due = []
    for ep in endpoints:
        interval = ep.get('interval', 60)  # секунды
        last_check = ep.get('last_check_at')

        if last_check is None:
            # Никогда не проверялся — проверяем сразу
            due.append(ep)
        elif (now - last_check).total_seconds() >= interval:
            due.append(ep)

    if not due:
        print(f"[{now}] No endpoints due for check")
        return

    print(f"\n{'='*60}")
    print(f"[{now}] Checking {len(due)}/{len(endpoints)} endpoints")
    print(f"{'='*60}")

    for ep in due:
        try:
            check_and_update_endpoint(ep)
        except Exception as e:
            print(f"  ❌ Error checking {ep['name']}: {e}")

    print(f"{'='*60}\n")


def start_scheduler():
    global scheduler

    if scheduler is not None:
        print("Scheduler already running")
        return

    scheduler = BackgroundScheduler()

    # Тик каждые 15 секунд — достаточно часто, чтобы не пропустить
    # эндпоинт с interval=30s, но не перегружать сервер
    scheduler.add_job(
        func=run_due_checks,
        trigger=IntervalTrigger(seconds=15),
        id='monitor_checks',
        name='Run due endpoint checks',
        replace_existing=True
    )

    scheduler.start()
    print("Scheduler started (tick every 15s, per-endpoint intervals respected)")
    atexit.register(shutdown_scheduler)


def shutdown_scheduler():
    global scheduler
    if scheduler:
        scheduler.shutdown()
        print("Scheduler stopped")