from flask import Blueprint, request, jsonify
from flask_jwt_extended import get_jwt_identity, get_jwt
from ..extensions import get_db, socketio
from ..middleware.auth_middleware import employee_required
from bson import ObjectId
from datetime import datetime

notifications_bp = Blueprint('notifications_bp', __name__)


def serialize_notification(notif):
    """Convert ObjectId and datetime for JSON."""
    notif['_id'] = str(notif['_id'])
    if notif.get('created_at') and isinstance(notif['created_at'], datetime):
        notif['created_at'] = notif['created_at'].isoformat() + 'Z'
    return notif


def create_notification(recipient_id, notif_type, title, message, link=None):
    """
    Helper: insert a notification and emit a socket event to the recipient.
    Can be imported and called from any module.
    """
    db = get_db()
    notif = {
        'recipient_id': recipient_id,
        'type': notif_type,
        'title': title,
        'message': message,
        'link': link or '',
        'is_read': False,
        'created_at': datetime.utcnow(),
    }
    result = db.notifications.insert_one(notif)
    notif_id = str(result.inserted_id)

    # Emit real-time socket event to recipient room
    socketio.emit('new_notification', {
        'id': notif_id,
        'type': notif_type,
        'title': title,
        'message': message,
        'link': link or '',
        'created_at': notif['created_at'].isoformat() + 'Z',
    }, room=recipient_id)

    return notif_id


# ---------------------------------------------------------------------------
# GET / - Get notifications for current user (paginated)
# ---------------------------------------------------------------------------
@notifications_bp.route('/', methods=['GET'])
@employee_required
def get_notifications():
    try:
        identity = get_jwt_identity()
        page = max(int(request.args.get('page', 1)), 1)
        limit = min(int(request.args.get('limit', 20)), 100)
        skip = limit * (page - 1)

        db = get_db()
        query = {'recipient_id': identity}

        # Optional filter for unread only
        unread_only = request.args.get('unread')
        if unread_only and unread_only.lower() in ('true', '1', 'yes'):
            query['is_read'] = False

        total = db.notifications.count_documents(query)
        notifications = list(
            db.notifications.find(query)
            .sort('created_at', -1)
            .skip(skip)
            .limit(limit)
        )

        return jsonify({
            'notifications': [serialize_notification(n) for n in notifications],
            'total': total,
            'page': page,
            'limit': limit,
            'pages': (total + limit - 1) // limit
        }), 200
    except Exception as e:
        return jsonify({'error': 'Failed to fetch notifications', 'details': str(e)}), 500


# ---------------------------------------------------------------------------
# GET /unread-count - Get unread count
# ---------------------------------------------------------------------------
@notifications_bp.route('/unread-count', methods=['GET'])
@employee_required
def unread_count():
    try:
        identity = get_jwt_identity()
        db = get_db()
        count = db.notifications.count_documents({'recipient_id': identity, 'is_read': False})
        return jsonify({'unread_count': count}), 200
    except Exception as e:
        return jsonify({'error': 'Failed to fetch unread count', 'details': str(e)}), 500


# ---------------------------------------------------------------------------
# POST /<notif_id>/read - Mark single notification as read
# ---------------------------------------------------------------------------
@notifications_bp.route('/<notif_id>/read', methods=['POST'])
@employee_required
def mark_read(notif_id):
    try:
        identity = get_jwt_identity()
        db = get_db()

        result = db.notifications.update_one(
            {'_id': ObjectId(notif_id), 'recipient_id': identity},
            {'$set': {'is_read': True}}
        )

        if result.matched_count == 0:
            return jsonify({'error': 'Notification not found'}), 404

        return jsonify({'message': 'Notification marked as read'}), 200
    except Exception as e:
        return jsonify({'error': 'Failed to mark notification', 'details': str(e)}), 500


# ---------------------------------------------------------------------------
# POST /read-all - Mark all notifications as read
# ---------------------------------------------------------------------------
@notifications_bp.route('/read-all', methods=['POST'])
@employee_required
def mark_all_read():
    try:
        identity = get_jwt_identity()
        db = get_db()

        result = db.notifications.update_many(
            {'recipient_id': identity, 'is_read': False},
            {'$set': {'is_read': True}}
        )

        return jsonify({
            'message': 'All notifications marked as read',
            'updated': result.modified_count
        }), 200
    except Exception as e:
        return jsonify({'error': 'Failed to mark all as read', 'details': str(e)}), 500
