from flask import Blueprint, Response, g, stream_with_context
from middlewares.auth import login_required
from extensions.mongodb import get_db
import json
import time

bp = Blueprint('sse', __name__, url_prefix='/api/sse')

def serialize_endpoint(e):
    e = dict(e)
    e['_id'] = str(e['_id'])
    e['id'] = e['_id']
    e['status'] = e.pop('last_status', None) or 'unknown'
    for field in ['last_check_at', 'created_at', 'updated_at']:
        if e.get(field):
            e[field] = e[field].isoformat() + 'Z'
    e.pop('user_id', None)
    return e

@bp.route('/endpoints')
@login_required
def stream_endpoints():
    user_id = str(g.current_user['_id'])

    def generate():
        last_data = None
        while True:
            try:
                db = get_db()
                endpoints = list(db.endpoints.find({"user_id": user_id}))
                serialized = [serialize_endpoint(e) for e in endpoints]
                data = json.dumps(serialized)

                if data != last_data:
                    last_data = data
                    yield f"data: {data}\n\n"
                else:
                    yield ": ping\n\n"

            except GeneratorExit:
                break
            except Exception as ex:
                yield f"data: {json.dumps({'error': str(ex)})}\n\n"

            time.sleep(5)

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
            'Connection': 'keep-alive',
        }
    )