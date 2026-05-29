from flask import Blueprint, request, jsonify
from flask_jwt_extended import get_jwt_identity, get_jwt
from ..extensions import get_db
from ..middleware.auth_middleware import employee_required
from bson import ObjectId
from datetime import datetime

notes_bp = Blueprint('notes_bp', __name__)

VALID_COLORS = ['yellow', 'green', 'blue', 'pink', 'purple', 'orange']


def serialize_note(note):
    """Convert ObjectId and datetime for JSON."""
    note['_id'] = str(note['_id'])
    for field in ('created_at', 'updated_at'):
        if note.get(field) and isinstance(note[field], datetime):
            note[field] = note[field].isoformat() + 'Z'
    return note


# ---------------------------------------------------------------------------
# GET / - Get all notes for current user
# ---------------------------------------------------------------------------
@notes_bp.route('/', methods=['GET'])
@employee_required
def get_notes():
    try:
        identity = get_jwt_identity()
        db = get_db()

        notes = list(
            db.notes.find({'employee_id': identity})
            .sort('updated_at', -1)
        )

        return jsonify({
            'notes': [serialize_note(n) for n in notes],
            'total': len(notes)
        }), 200
    except Exception as e:
        return jsonify({'error': 'Failed to fetch notes', 'details': str(e)}), 500


# ---------------------------------------------------------------------------
# POST / - Create note
# ---------------------------------------------------------------------------
@notes_bp.route('/', methods=['POST'])
@employee_required
def create_note():
    try:
        identity = get_jwt_identity()
        data = request.get_json() or {}

        content = data.get('content', '').strip()
        if not content:
            return jsonify({'error': 'Content is required'}), 400

        color = data.get('color', 'yellow')
        if color not in VALID_COLORS:
            color = 'yellow'

        db = get_db()
        note = {
            'employee_id': identity,
            'content': content,
            'color': color,
            'position_x': data.get('position_x', 0),
            'position_y': data.get('position_y', 0),
            'width': data.get('width', 200),
            'height': data.get('height', 200),
            'pinned': data.get('pinned', False),
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow(),
        }

        result = db.notes.insert_one(note)
        note_id = str(result.inserted_id)

        return jsonify({'message': 'Note created', 'id': note_id}), 201
    except Exception as e:
        return jsonify({'error': 'Failed to create note', 'details': str(e)}), 500


# ---------------------------------------------------------------------------
# PUT /<note_id> - Update note
# ---------------------------------------------------------------------------
@notes_bp.route('/<note_id>', methods=['PUT'])
@employee_required
def update_note(note_id):
    try:
        identity = get_jwt_identity()
        db = get_db()

        note = db.notes.find_one({'_id': ObjectId(note_id), 'employee_id': identity})
        if not note:
            return jsonify({'error': 'Note not found'}), 404

        data = request.get_json() or {}

        update = {}
        if 'content' in data:
            update['content'] = data['content']
        if 'color' in data:
            update['color'] = data['color'] if data['color'] in VALID_COLORS else note.get('color', 'yellow')
        if 'position_x' in data:
            update['position_x'] = data['position_x']
        if 'position_y' in data:
            update['position_y'] = data['position_y']
        if 'width' in data:
            update['width'] = data['width']
        if 'height' in data:
            update['height'] = data['height']
        if 'pinned' in data:
            update['pinned'] = bool(data['pinned'])

        update['updated_at'] = datetime.utcnow()
        db.notes.update_one({'_id': ObjectId(note_id)}, {'$set': update})

        return jsonify({'message': 'Note updated'}), 200
    except Exception as e:
        return jsonify({'error': 'Failed to update note', 'details': str(e)}), 500


# ---------------------------------------------------------------------------
# DELETE /<note_id> - Delete note
# ---------------------------------------------------------------------------
@notes_bp.route('/<note_id>', methods=['DELETE'])
@employee_required
def delete_note(note_id):
    try:
        identity = get_jwt_identity()
        db = get_db()

        result = db.notes.delete_one({'_id': ObjectId(note_id), 'employee_id': identity})
        if result.deleted_count == 0:
            return jsonify({'error': 'Note not found'}), 404

        return jsonify({'message': 'Note deleted'}), 200
    except Exception as e:
        return jsonify({'error': 'Failed to delete note', 'details': str(e)}), 500
