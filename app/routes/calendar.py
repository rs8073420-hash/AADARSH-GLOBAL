from flask import Blueprint, request, jsonify
from flask_jwt_extended import get_jwt_identity, get_jwt
from ..extensions import get_db
from ..middleware.auth_middleware import employee_required
from bson import ObjectId
from datetime import datetime

calendar_bp = Blueprint('calendar_bp', __name__)

EVENT_TYPES = ['task', 'meeting', 'leave', 'deadline', 'follow_up']

EVENT_COLORS = {
    'task': '#6366f1',
    'meeting': '#3b82f6',
    'leave': '#f59e0b',
    'deadline': '#ef4444',
    'follow_up': '#10b981',
}


def serialize_event(event):
    """Convert ObjectId and datetime for JSON."""
    event['_id'] = str(event['_id'])
    for field in ('start', 'end', 'created_at', 'updated_at'):
        if event.get(field) and isinstance(event[field], datetime):
            event[field] = event[field].isoformat() + 'Z'
    return event


# ---------------------------------------------------------------------------
# GET / - Get events for date range
# ---------------------------------------------------------------------------
@calendar_bp.route('/', methods=['GET'])
@employee_required
def get_events():
    try:
        identity = get_jwt_identity()
        claims = get_jwt()
        db = get_db()

        query = {}

        # Date range filtering
        start = request.args.get('start')  # ISO string e.g. 2026-05-01
        end = request.args.get('end')

        if start:
            try:
                start_dt = datetime.strptime(start, '%Y-%m-%d')
                query['end'] = {'$gte': start_dt}
            except ValueError:
                pass

        if end:
            try:
                end_dt = datetime.strptime(end, '%Y-%m-%d')
                if 'end' in query:
                    # event.end >= start AND event.start <= end (overlap query)
                    query['start'] = {'$lte': end_dt}
                else:
                    query['start'] = {'$lte': end_dt}
            except ValueError:
                pass

        # Type filter
        event_type = request.args.get('type')
        if event_type and event_type in EVENT_TYPES:
            query['type'] = event_type

        # Non-admin users only see events assigned to them or created by them
        if claims.get('role') != 'admin':
            query['$or'] = [
                {'assigned_to': identity},
                {'created_by': identity},
                {'assigned_to': ''},   # events with no assignment (public)
                {'assigned_to': None},
            ]

        events = list(
            db.calendar_events.find(query)
            .sort('start', 1)
        )

        # Attach color based on type
        serialized = []
        for evt in events:
            s = serialize_event(evt)
            s['color'] = EVENT_COLORS.get(s.get('type', ''), '#6366f1')
            serialized.append(s)

        return jsonify({'events': serialized}), 200
    except Exception as e:
        return jsonify({'error': 'Failed to fetch events', 'details': str(e)}), 500


# ---------------------------------------------------------------------------
# POST / - Create event
# ---------------------------------------------------------------------------
@calendar_bp.route('/', methods=['POST'])
@employee_required
def create_event():
    try:
        identity = get_jwt_identity()
        claims = get_jwt()
        data = request.get_json() or {}

        if not data.get('title'):
            return jsonify({'error': 'Title is required'}), 400
        if not data.get('start'):
            return jsonify({'error': 'Start datetime is required'}), 400

        event_type = data.get('type', 'task')
        if event_type not in EVENT_TYPES:
            return jsonify({'error': f'Invalid type. Must be one of: {", ".join(EVENT_TYPES)}'}), 400

        # Parse dates
        try:
            start_dt = datetime.fromisoformat(data['start'].replace('Z', '+00:00').replace('+00:00', ''))
        except (ValueError, AttributeError):
            start_dt = datetime.strptime(data['start'], '%Y-%m-%dT%H:%M:%S')

        end_dt = start_dt  # default end = start
        if data.get('end'):
            try:
                end_dt = datetime.fromisoformat(data['end'].replace('Z', '+00:00').replace('+00:00', ''))
            except (ValueError, AttributeError):
                end_dt = datetime.strptime(data['end'], '%Y-%m-%dT%H:%M:%S')

        db = get_db()
        event = {
            'title': data['title'],
            'description': data.get('description', ''),
            'start': start_dt,
            'end': end_dt,
            'type': event_type,
            'assigned_to': data.get('assigned_to', identity),
            'assigned_to_name': data.get('assigned_to_name', ''),
            'created_by': identity,
            'created_by_name': claims.get('name', ''),
            'all_day': data.get('all_day', False),
            'color': EVENT_COLORS.get(event_type, '#6366f1'),
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow(),
        }

        result = db.calendar_events.insert_one(event)
        event_id = str(result.inserted_id)

        return jsonify({'message': 'Event created', 'id': event_id}), 201
    except Exception as e:
        return jsonify({'error': 'Failed to create event', 'details': str(e)}), 500


# ---------------------------------------------------------------------------
# PUT /<event_id> - Update event
# ---------------------------------------------------------------------------
@calendar_bp.route('/<event_id>', methods=['PUT'])
@employee_required
def update_event(event_id):
    try:
        identity = get_jwt_identity()
        claims = get_jwt()
        db = get_db()

        event = db.calendar_events.find_one({'_id': ObjectId(event_id)})
        if not event:
            return jsonify({'error': 'Event not found'}), 404

        # Only creator or admin can update
        if str(event.get('created_by')) != identity and claims.get('role') != 'admin':
            return jsonify({'error': 'Not authorized to update this event'}), 403

        data = request.get_json() or {}

        if data.get('type') and data['type'] not in EVENT_TYPES:
            return jsonify({'error': f'Invalid type. Must be one of: {", ".join(EVENT_TYPES)}'}), 400

        update = {}
        for field in ('title', 'description', 'type', 'assigned_to', 'assigned_to_name', 'all_day'):
            if field in data:
                update[field] = data[field]

        # Parse dates if provided
        if data.get('start'):
            try:
                update['start'] = datetime.fromisoformat(data['start'].replace('Z', '+00:00').replace('+00:00', ''))
            except (ValueError, AttributeError):
                update['start'] = datetime.strptime(data['start'], '%Y-%m-%dT%H:%M:%S')

        if data.get('end'):
            try:
                update['end'] = datetime.fromisoformat(data['end'].replace('Z', '+00:00').replace('+00:00', ''))
            except (ValueError, AttributeError):
                update['end'] = datetime.strptime(data['end'], '%Y-%m-%dT%H:%M:%S')

        # Update color if type changed
        if 'type' in update:
            update['color'] = EVENT_COLORS.get(update['type'], '#6366f1')

        update['updated_at'] = datetime.utcnow()
        db.calendar_events.update_one({'_id': ObjectId(event_id)}, {'$set': update})

        return jsonify({'message': 'Event updated'}), 200
    except Exception as e:
        return jsonify({'error': 'Failed to update event', 'details': str(e)}), 500


# ---------------------------------------------------------------------------
# DELETE /<event_id> - Delete event
# ---------------------------------------------------------------------------
@calendar_bp.route('/<event_id>', methods=['DELETE'])
@employee_required
def delete_event(event_id):
    try:
        identity = get_jwt_identity()
        claims = get_jwt()
        db = get_db()

        event = db.calendar_events.find_one({'_id': ObjectId(event_id)})
        if not event:
            return jsonify({'error': 'Event not found'}), 404

        # Only creator or admin can delete
        if str(event.get('created_by')) != identity and claims.get('role') != 'admin':
            return jsonify({'error': 'Not authorized to delete this event'}), 403

        db.calendar_events.delete_one({'_id': ObjectId(event_id)})
        return jsonify({'message': 'Event deleted'}), 200
    except Exception as e:
        return jsonify({'error': 'Failed to delete event', 'details': str(e)}), 500
