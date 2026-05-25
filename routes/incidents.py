from flask import Blueprint, request, jsonify, g
from bson.objectid import ObjectId
from datetime import datetime
from extensions.mongodb import get_db
from middlewares.auth import login_required

bp = Blueprint('incidents', __name__, url_prefix='/api/incidents')

def _serialize(inc, db):
    inc = dict(inc)
    inc['_id'] = str(inc['_id'])
    inc['id'] = inc['_id']
    for field in ['started_at', 'ended_at', 'acknowledged_at']:
        if inc.get(field):
            inc[field] = inc[field].isoformat() + 'Z'
    ep = db.endpoints.find_one({"_id": ObjectId(inc['endpoint_id'])})
    inc['endpoint_name'] = ep['name'] if ep else 'Unknown'
    inc['endpoint_url'] = ep['url'] if ep else ''
    return inc

def _user_endpoint_ids(db, user_id):
    eps = list(db.endpoints.find({"user_id": user_id}, {"_id": 1}))
    return [str(e['_id']) for e in eps]

@bp.route('', methods=['GET'])
@login_required
def get_incidents():
    db = get_db()
    user_id = str(g.current_user['_id'])
    limit = int(request.args.get('limit', 50))
    offset = int(request.args.get('offset', 0))
    active_only = request.args.get('active_only', 'false').lower() == 'true'
    endpoint_id = request.args.get('endpoint_id')

    ep_ids = _user_endpoint_ids(db, user_id)
    query = {"endpoint_id": {"$in": ep_ids}}

    if endpoint_id:
        if endpoint_id not in ep_ids:
            return jsonify({"error": "Access denied"}), 403
        query["endpoint_id"] = endpoint_id

    if active_only:
        query["ended_at"] = None

    total = db.incidents.count_documents(query)
    raw = list(db.incidents.find(query)
               .sort("started_at", -1)
               .skip(offset)
               .limit(limit))

    result = [_serialize(i, db) for i in raw]

    # Статистика
    pipeline = [
        {"$match": {"endpoint_id": {"$in": ep_ids}}},
        {"$group": {
            "_id": None,
            "active_count": {"$sum": {"$cond": [{"$eq": ["$ended_at", None]}, 1, 0]}},
            "avg_duration": {"$avg": "$duration_seconds"},
            "max_duration": {"$max": "$duration_seconds"},
        }}
    ]
    agg = list(db.incidents.aggregate(pipeline))
    stats = agg[0] if agg else {"active_count": 0, "avg_duration": None, "max_duration": None}
    stats.pop('_id', None)

    return jsonify({
        "incidents": result,
        "total": total,
        "offset": offset,
        "limit": limit,
        "stats": stats,
    })

@bp.route('/<incident_id>/acknowledge', methods=['POST'])
@login_required
def acknowledge_incident(incident_id):
    db = get_db()
    user_id = str(g.current_user['_id'])
    data = request.json or {}

    inc = db.incidents.find_one({"_id": ObjectId(incident_id)})
    if not inc:
        return jsonify({"error": "Not found"}), 404

    ep_ids = _user_endpoint_ids(db, user_id)
    if inc['endpoint_id'] not in ep_ids:
        return jsonify({"error": "Access denied"}), 403

    if inc.get('status') == 'resolved':
        return jsonify({"error": "Already resolved"}), 400

    db.incidents.update_one(
        {"_id": ObjectId(incident_id)},
        {"$set": {
            "status": "acknowledged",
            "acknowledged_at": datetime.utcnow(),  # ← убрал + 'Z'
            "acknowledged_by": user_id,
            "note": data.get("note", ""),
        }}
    )
    return jsonify({"message": "Acknowledged"})


@bp.route('/<incident_id>/resolve', methods=['POST'])
@login_required
def resolve_incident(incident_id):
    db = get_db()
    user_id = str(g.current_user['_id'])
    data = request.json or {}

    inc = db.incidents.find_one({"_id": ObjectId(incident_id)})
    if not inc:
        return jsonify({"error": "Not found"}), 404

    ep_ids = _user_endpoint_ids(db, user_id)
    if inc['endpoint_id'] not in ep_ids:
        return jsonify({"error": "Access denied"}), 403

    ended_at = datetime.utcnow()  # ← убрал + 'Z'
    duration = int((ended_at - inc['started_at']).total_seconds())

    db.incidents.update_one(
        {"_id": ObjectId(incident_id)},
        {"$set": {
            "status": "resolved",
            "ended_at": ended_at,
            "duration_seconds": duration,
            "resolved_manually": True,
            "resolution_note": data.get("note", ""),
        }}
    )
    return jsonify({"message": "Resolved"})