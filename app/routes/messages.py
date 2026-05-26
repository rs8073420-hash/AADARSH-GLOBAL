from flask import Blueprint, request, jsonify
from flask_jwt_extended import get_jwt_identity, get_jwt
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
