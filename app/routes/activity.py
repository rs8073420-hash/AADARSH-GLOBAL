from flask import Blueprint, request, jsonify
from flask_jwt_extended import get_jwt_identity, get_jwt
from ..extensions import get_db, socketio
from ..middleware.auth_middleware import admin_required, employee_required
from bson import ObjectId
from datetime import datetime, timedelta

activity_bp = Blueprint('activity_bp', __name__)

# Thresholds for presence status
ONLINE_THRESHOLD_SECONDS = 60      # heartbeat within 60s  → online
IDLE_THRESHOLD_SECONDS = 300       # heartbeat within 5min → idle
# Beyond idle threshold → offline


def serialize_log(log):
    """Convert ObjectId and datetime for JSON."""
    log['_id'] = str(log['_id'])
    if log.get('timestamp') and isinstance(log['timestamp'], datetime):
        log['timestamp'] = log['timestamp'].isoformat() + 'Z'
    return log


# ---------------------------------------------------------------------------
# POST /heartbeat - Employee sends heartbeat
# ---------------------------------------------------------------------------
@activity_bp.route('/heartbeat', methods=['POST'])
@employee_required
def heartbeat():
    try:
        identity = get_jwt_identity()
        claims = get_jwt()
        data = request.get_json() or {}

        current_page = data.get('current_page', '')
        action = data.get('action', 'heartbeat')

        db = get_db()
        now = datetime.utcnow()

        # Upsert the latest heartbeat into a fast-lookup collection
        db.activity_status.update_one(
            {'employee_id': identity},
            {'$set': {
                'employee_id': identity,
                'employee_name': claims.get('name', ''),
                'current_page': current_page,
                'last_action': action,
                'last_heartbeat': now,
                'role': claims.get('role', 'employee'),
            }},
            upsert=True
        )

        # Also append to activity_logs for history
        db.activity_logs.insert_one({
            'employee_id': identity,
            'employee_name': claims.get('name', ''),
            'action': action,
            'page': current_page,
            'timestamp': now,
        })

        return jsonify({'status': 'ok', 'server_time': now.isoformat() + 'Z'}), 200
    except Exception as e:
        return jsonify({'error': 'Heartbeat failed', 'details': str(e)}), 500


# ---------------------------------------------------------------------------
# GET /online - Admin gets list of online/idle/offline employees
# ---------------------------------------------------------------------------
@activity_bp.route('/online', methods=['GET'])
@admin_required
def get_online():
    try:
        db = get_db()
        now = datetime.utcnow()
        online_cutoff = now - timedelta(seconds=ONLINE_THRESHOLD_SECONDS)
        idle_cutoff = now - timedelta(seconds=IDLE_THRESHOLD_SECONDS)

        # Fetch all employees from the employees collection
        employees = list(db.employees.find({'is_active': True}, {'name': 1, 'employee_id': 1, 'department': 1, 'designation': 1, 'avatar': 1}))

        # Build a map of recent activity statuses
        statuses = list(db.activity_status.find())
        status_map = {s['employee_id']: s for s in statuses}

        result = []
        online_count = 0
        idle_count = 0
        offline_count = 0

        for emp in employees:
            emp_id = str(emp['_id'])
            activity = status_map.get(emp_id, {})
            last_heartbeat = activity.get('last_heartbeat')

            if last_heartbeat and last_heartbeat >= online_cutoff:
                presence = 'online'
                online_count += 1
            elif last_heartbeat and last_heartbeat >= idle_cutoff:
                presence = 'idle'
                idle_count += 1
            else:
                presence = 'offline'
                offline_count += 1

            result.append({
                'employee_id': emp_id,
                'employee_code': emp.get('employee_id', ''),
                'name': emp.get('name', ''),
                'department': emp.get('department', ''),
                'designation': emp.get('designation', ''),
                'avatar': emp.get('avatar', ''),
                'status': presence,
                'current_page': activity.get('current_page', ''),
                'last_action': activity.get('last_action', ''),
                'last_heartbeat': last_heartbeat.isoformat() + 'Z' if last_heartbeat else None,
            })

        # Sort: online first, then idle, then offline
        order = {'online': 0, 'idle': 1, 'offline': 2}
        result.sort(key=lambda x: (order.get(x['status'], 3), x['name']))

        return jsonify({
            'employees': result,
            'summary': {
                'online': online_count,
                'idle': idle_count,
                'offline': offline_count,
                'total': len(result)
            }
        }), 200
    except Exception as e:
        return jsonify({'error': 'Failed to fetch online status', 'details': str(e)}), 500


# ---------------------------------------------------------------------------
# GET /logs/<employee_id> - Activity log for specific employee
# ---------------------------------------------------------------------------
@activity_bp.route('/logs/<employee_id>', methods=['GET'])
@admin_required
def get_activity_logs(employee_id):
    try:
        page = max(int(request.args.get('page', 1)), 1)
        limit = min(int(request.args.get('limit', 50)), 200)
        skip = limit * (page - 1)

        db = get_db()

        # Optional date filter
        date_from = request.args.get('from')  # YYYY-MM-DD
        date_to = request.args.get('to')

        query = {'employee_id': employee_id}
        if date_from or date_to:
            date_filter = {}
            if date_from:
                date_filter['$gte'] = datetime.strptime(date_from, '%Y-%m-%d')
            if date_to:
                date_filter['$lte'] = datetime.strptime(date_to, '%Y-%m-%d') + timedelta(days=1)
            query['timestamp'] = date_filter

        total = db.activity_logs.count_documents(query)
        logs = list(
            db.activity_logs.find(query)
            .sort('timestamp', -1)
            .skip(skip)
            .limit(limit)
        )

        return jsonify({
            'logs': [serialize_log(l) for l in logs],
            'total': total,
            'page': page,
            'limit': limit,
            'pages': (total + limit - 1) // limit
        }), 200
    except Exception as e:
        return jsonify({'error': 'Failed to fetch activity logs', 'details': str(e)}), 500
