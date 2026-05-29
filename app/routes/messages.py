from flask import Blueprint, request, jsonify
from flask_jwt_extended import get_jwt_identity, get_jwt
from datetime import datetime
from ..models.message import MessageModel
from ..models.employee import EmployeeModel
from ..models.admin import AdminModel
from ..middleware.auth_middleware import admin_required, employee_required
from bson import ObjectId

messages_bp = Blueprint('messages', __name__)

def serialize_message(msg):
    msg['_id'] = str(msg['_id'])
    if msg.get('created_at'):
        msg['created_at'] = msg['created_at'].isoformat() + 'Z'
    return msg

@messages_bp.route('/users', methods=['GET'])
@employee_required
def get_chat_users():
    identity = get_jwt_identity()
    claims = get_jwt()
    role = claims.get('role')
    
    users = []
    # Fetch all admins
    admins = AdminModel().collection.find()
    for a in admins:
        if str(a['_id']) == identity: continue
        users.append({
            'id': str(a['_id']),
            'name': a.get('name', 'Admin'),
            'role': 'admin',
            'is_online': True # Admins are assumed always online or we can fetch
        })
        
    # Fetch all employees
    employees = EmployeeModel().get_all({'is_active': True})
    for e in employees:
        if str(e['_id']) == identity: continue
        users.append({
            'id': str(e['_id']),
            'name': e.get('name', 'Employee'),
            'role': 'employee',
            'is_online': e.get('is_online', False),
            'department': e.get('department', '')
        })
        
    # Get unread counts
    model = MessageModel()
    for u in users:
        u['unread'] = model.count_unread_from_sender(u['id'], identity)
        
    # Sort by online first, then name
    users.sort(key=lambda x: (not x['is_online'], x['name']))
    return jsonify({'users': users}), 200

@messages_bp.route('/history/<user_id>', methods=['GET'])
@employee_required
def get_history(user_id):
    identity = get_jwt_identity()
    model = MessageModel()
    
    # Mark as read since we are viewing
    model.mark_read(sender_id=user_id, recipient_id=identity)
    
    messages = model.get_conversation(identity, user_id)
    return jsonify({'messages': [serialize_message(m) for m in messages]}), 200

@messages_bp.route('/send', methods=['POST'])
@employee_required
def send_message():
    identity = get_jwt_identity()
    claims = get_jwt()
    data = request.get_json()
    
    if not data or not data.get('recipient_id') or not data.get('message'):
        return jsonify({'error': 'Recipient and message are required'}), 400
        
    model = MessageModel()
    recipient_id = data['recipient_id']
    recipient_name = data.get('recipient_name', '')
    recipient_role = data.get('recipient_role', 'employee')
    
    if not recipient_name:
        emp = EmployeeModel().collection.find_one({'_id': ObjectId(recipient_id)})
        if emp:
            recipient_name = emp.get('name', 'Employee')
            recipient_role = 'employee'
        else:
            adm = AdminModel().collection.find_one({'_id': ObjectId(recipient_id)})
            if adm:
                recipient_name = adm.get('name', 'Admin')
                recipient_role = 'admin'
    
    msg_data = {
        'sender_id': identity,
        'sender_name': claims.get('name', 'User'),
        'sender_role': claims.get('role', 'employee'),
        'recipient_id': recipient_id,
        'recipient_name': recipient_name,
        'recipient_role': recipient_role,
        'message': data['message']
    }
    
    result = model.create(msg_data)
    return jsonify({'message': 'Sent successfully', 'id': str(result.inserted_id)}), 201

@messages_bp.route('/global-log', methods=['GET'])
@admin_required
def get_global_log():
    model = MessageModel()
    messages = model.get_global_log()
    return jsonify({'messages': [serialize_message(m) for m in messages]}), 200

@messages_bp.route('/unread-count', methods=['GET'])
@employee_required
def get_unread_count():
    identity = get_jwt_identity()
    model = MessageModel()
    count = model.count_unread(identity)
    return jsonify({'unread_count': count}), 200

# -----------------------------------------------------------------------------
# V2 ADVANCED MESSAGING ENDPOINTS
# -----------------------------------------------------------------------------
from ..models.message import ChatRoomModel

@messages_bp.route('/v2/rooms', methods=['GET'])
@employee_required
def v2_get_rooms():
    identity = get_jwt_identity()
    rooms_model = ChatRoomModel()
    msg_model = MessageModel()
    emp_model = EmployeeModel()
    
    rooms = rooms_model.get_user_rooms(identity)
    
    # Enrich rooms with unread status and names if direct
    enriched = []
    for r in rooms:
        r['_id'] = str(r['_id'])
        if r.get('created_at'): r['created_at'] = r['created_at'].isoformat() + 'Z'
        if r.get('last_message_at'): r['last_message_at'] = r['last_message_at'].isoformat() + 'Z'
        
        # Determine name for direct chats
        if r.get('type') == 'direct':
            other_id = next((m for m in r['members'] if m != identity), None)
            if other_id:
                emp = emp_model.collection.find_one({'_id': ObjectId(other_id)})
                if emp:
                    r['name'] = emp.get('name', 'User')
                    r['avatar'] = emp.get('name', 'U')[0].upper()
                    r['is_online'] = emp.get('is_online', False)
                else:
                    adm = AdminModel().collection.find_one({'_id': ObjectId(other_id)})
                    if adm:
                        r['name'] = adm.get('name', 'Admin')
                        r['avatar'] = adm.get('name', 'A')[0].upper()
                        r['is_online'] = True
        else:
            r['avatar'] = r.get('name', 'G')[0].upper() if r.get('name') else '#'
            
        # Check unread
        unread = msg_model.collection.count_documents({'room_id': r['_id'], 'seen_by': {'$ne': identity}})
        r['unread'] = unread
        enriched.append(r)
        
    return jsonify({'rooms': enriched}), 200

@messages_bp.route('/v2/room/direct/<target_id>', methods=['GET'])
@employee_required
def v2_get_direct_room(target_id):
    identity = get_jwt_identity()
    rooms_model = ChatRoomModel()
    
    room = rooms_model.get_direct_room(identity, target_id)
    if not room:
        # Create it
        res = rooms_model.create_room({
            'type': 'direct',
            'members': [identity, target_id],
            'created_by': identity
        })
        room = rooms_model.get_room_by_id(res.inserted_id)
        
    room['_id'] = str(room['_id'])
    return jsonify({'room': room}), 200

@messages_bp.route('/v2/messages/<room_id>', methods=['GET'])
@employee_required
def v2_get_messages(room_id):
    identity = get_jwt_identity()
    msg_model = MessageModel()
    
    # Mark as seen
    msg_model.mark_room_seen(room_id, identity)
    
    limit = int(request.args.get('limit', 50))
    skip = int(request.args.get('skip', 0))
    
    messages = msg_model.get_room_messages(room_id, limit, skip)
    messages.reverse() # chronological order for chat window
    
    return jsonify({'messages': [serialize_message(m) for m in messages]}), 200

@messages_bp.route('/v2/send', methods=['POST'])
@employee_required
def v2_send_message():
    identity = get_jwt_identity()
    claims = get_jwt()
    data = request.get_json()
    
    if not data or not data.get('room_id'):
        return jsonify({'error': 'Room ID is required'}), 400
    if not data.get('message') and not data.get('attachments'):
        return jsonify({'error': 'Message or attachment is required'}), 400
        
    model = MessageModel()
    rooms_model = ChatRoomModel()
    
    msg_data = {
        'room_id': data['room_id'],
        'sender_id': identity,
        'sender_name': claims.get('name', 'User'),
        'message': data.get('message', ''),
        'reply_to': data.get('reply_to'),
        'attachments': data.get('attachments', [])
    }
    
    result = model.create_v2(msg_data)
    
    # Update room last message
    msg_text = data.get('message', '')
    snippet = msg_text[:50] + ('...' if len(msg_text) > 50 else '') if msg_text else '📎 Attachment'
    rooms_model.update_last_message(data['room_id'], snippet)
    
    msg_data['_id'] = str(result.inserted_id)
    if msg_data.get('created_at'): msg_data['created_at'] = msg_data['created_at'].isoformat() + 'Z'
    else: msg_data['created_at'] = datetime.utcnow().isoformat() + 'Z'
    
    # Emit to room via socketio
    from ..extensions import socketio
    socketio.emit('new_message', msg_data, room=data['room_id'])
    
    room = rooms_model.get_room_by_id(data['room_id'])
    if room and room.get('members'):
        from .notifications import create_notification
        for member_id in room['members']:
            if member_id != identity:
                notif_text = data.get('message', '')[:40] if data.get('message') else '📎 Attachment'
                create_notification(member_id, 'message', 'New Message', f'{claims.get("name", "User")}: {notif_text}', '/employee/messages')
                
    return jsonify({'message': 'Sent successfully', 'data': msg_data}), 201

@messages_bp.route('/v2/react', methods=['POST'])
@employee_required
def v2_react():
    identity = get_jwt_identity()
    data = request.get_json()
    if not data or not data.get('message_id') or not data.get('emoji'):
        return jsonify({'error': 'Missing parameters'}), 400
        
    model = MessageModel()
    action = data.get('action', 'add')
    if action == 'add':
        model.add_reaction(data['message_id'], data['emoji'], identity)
    else:
        model.remove_reaction(data['message_id'], data['emoji'], identity)
        
    return jsonify({'success': True}), 200

@messages_bp.route('/v2/directory', methods=['GET'])
@employee_required
def v2_get_directory():
    identity = get_jwt_identity()
    emp_model = EmployeeModel()
    
    users = []
    # Fetch all admins
    admins = AdminModel().collection.find()
    for a in admins:
        if str(a['_id']) == identity: continue
        users.append({
            'id': str(a['_id']),
            'name': a.get('name', 'Admin'),
            'role': 'admin',
            'department': 'Administration',
            'is_online': True,
            'last_active': datetime.utcnow().isoformat() + 'Z',
            'avatar': a.get('name', 'A')[0].upper()
        })
        
    # Fetch all employees
    employees = emp_model.get_all({'is_active': True})
    now = datetime.utcnow()
    for e in employees:
        if str(e['_id']) == identity: continue
        
        # Calculate status color based on last_active if not is_online
        is_online = e.get('is_online', False)
        last_active = e.get('last_active')
        status = 'offline'
        if is_online:
            status = 'online'
        elif last_active:
            diff = (now - last_active).total_seconds()
            if diff < 900: # 15 mins
                status = 'away'
            elif diff < 3600: # 1 hour
                status = 'busy'
                
        last_active_str = last_active.isoformat() + 'Z' if last_active else ''
        
        users.append({
            'id': str(e['_id']),
            'name': e.get('name', 'Employee'),
            'role': 'employee',
            'department': e.get('department', 'Staff'),
            'is_online': is_online,
            'status': status,
            'last_active': last_active_str,
            'avatar': e.get('name', 'E')[0].upper()
        })
        
    # Get unread counts
    msg_model = MessageModel()
    for u in users:
        u['unread'] = msg_model.count_unread_from_sender(u['id'], identity)
        
    # Sort by online status (online first, then away, busy, offline)
    status_order = {'online': 0, 'away': 1, 'busy': 2, 'offline': 3}
    users.sort(key=lambda x: (status_order.get(x.get('status', 'offline'), 3), x['name']))
    return jsonify({'directory': users}), 200

@messages_bp.route('/v2/monitor/all', methods=['GET'])
@admin_required
def v2_monitor_all():
    rooms_model = ChatRoomModel()
    emp_model = EmployeeModel()
    
    # Fetch all active rooms
    rooms = list(rooms_model.collection.find({'is_active': True}).sort('last_message_at', -1))
    
    enriched = []
    for r in rooms:
        r['_id'] = str(r['_id'])
        if r.get('created_at'): r['created_at'] = r['created_at'].isoformat() + 'Z'
        if r.get('last_message_at'): r['last_message_at'] = r['last_message_at'].isoformat() + 'Z'
        
        if r.get('type') == 'direct':
            names = []
            for m in r.get('members', []):
                emp = emp_model.collection.find_one({'_id': ObjectId(m)})
                if emp: names.append(emp.get('name', 'User'))
                else:
                    adm = AdminModel().collection.find_one({'_id': ObjectId(m)})
                    if adm: names.append(adm.get('name', 'Admin'))
            r['name'] = ' ↔ '.join(names) if names else 'Direct Chat'
            r['avatar'] = 'D'
        else:
            r['avatar'] = r.get('name', 'G')[0].upper() if r.get('name') else '#'
            
        enriched.append(r)
        
    return jsonify({'rooms': enriched}), 200


