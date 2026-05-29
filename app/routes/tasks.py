from flask import Blueprint, request, jsonify
from ..middleware.auth_middleware import admin_required, employee_required
from ..models.task import TaskModel
from ..models.employee import EmployeeModel
from flask_jwt_extended import get_jwt_identity, get_jwt
from bson import ObjectId
from datetime import datetime, date
import os, uuid
from werkzeug.utils import secure_filename

tasks_bp = Blueprint('tasks', __name__)

UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'static', 'uploads', 'tasks')
ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png', 'gif', 'pdf', 'doc', 'docx', 'xlsx', 'xls', 'txt'}
VALID_STATUSES = ['assigned', 'in_progress', 'under_review', 'approved', 'rejected', 'completed', 'pending', 'cancelled']

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def serialize_task(task):
    task['_id'] = str(task['_id'])
    if task.get('created_at'):
        task['created_at'] = task['created_at'].isoformat() + 'Z'
    if task.get('updated_at'):
        task['updated_at'] = task['updated_at'].isoformat() + 'Z'
    if task.get('completed_at'):
        task['completed_at'] = task['completed_at'].isoformat() + 'Z'
    return task

@tasks_bp.route('/', methods=['GET'])
@admin_required
def get_all_tasks():
    model = TaskModel()
    filters = {}
    status = request.args.get('status')
    priority = request.args.get('priority')
    assigned_to = request.args.get('assigned_to')
    search = request.args.get('search', '')
    if status:
        filters['status'] = status
    if priority:
        filters['priority'] = priority
    if assigned_to:
        filters['assigned_to'] = assigned_to
    if search:
        filters['$or'] = [
            {'title': {'$regex': search, '$options': 'i'}},
            {'task_id': {'$regex': search, '$options': 'i'}},
            {'assigned_by_name': {'$regex': search, '$options': 'i'}}
        ]
    tasks = model.get_all(filters)
    return jsonify({'tasks': [serialize_task(t) for t in tasks], 'total': len(tasks)}), 200

@tasks_bp.route('/', methods=['POST'])
@admin_required
def create_task():
    identity = get_jwt_identity()
    claims = get_jwt()
    data = request.get_json()
    if not data or not data.get('title'):
        return jsonify({'error': 'Title is required'}), 400
    assigned_to = data.get('assigned_to', [])
    bypass_attendance = data.get('bypass_attendance', False)
    
    # Validation logic
    if not bypass_attendance and assigned_to:
        from ..models.attendance import AttendanceModel
        att_model = AttendanceModel()
        for emp_id in assigned_to:
            rec = att_model.get_today_record(emp_id)
            if not rec or rec.get('check_out'):
                return jsonify({
                    'error': 'attendance_warning',
                    'message': 'This employee is currently marked as absent or has already checked out for today. Are you sure you want to assign this task?',
                    'employee_id': emp_id
                }), 409
                
    data['assigned_by'] = identity
    data['assigned_by_name'] = claims.get('name', 'Admin')
    if not data.get('status'):
        data['status'] = 'assigned'
    model = TaskModel()
    result = model.create(data)
    task_id = str(result.inserted_id)
    from ..extensions import socketio
    from .notifications import create_notification
    assigned_to = data.get('assigned_to', [])
    for emp_id in assigned_to:
        create_notification(emp_id, 'task', 'New Task Assigned', f'You have been assigned: {data.get("title", "")}', '/employee/tasks')
    socketio.emit('task_created', {'task_id': task_id, 'title': data.get('title', '')}, room='admin')
    return jsonify({'message': 'Task created', 'id': task_id}), 201

@tasks_bp.route('/<task_id>', methods=['GET'])
@employee_required
def get_task(task_id):
    model = TaskModel()
    task = model.find_by_id(task_id)
    if not task:
        return jsonify({'error': 'Task not found'}), 404
    return jsonify(serialize_task(task)), 200

@tasks_bp.route('/<task_id>', methods=['PUT'])
@admin_required
def update_task(task_id):
    identity = get_jwt_identity()
    claims = get_jwt()
    data = request.get_json()
    model = TaskModel()
    task = model.find_by_id(task_id)
    if not task:
        return jsonify({'error': 'Task not found'}), 404
    log = {
        'action': 'task_updated',
        'description': f'Task details updated by {claims.get("name", "Admin")}',
        'by_id': identity,
        'by_name': claims.get('name', 'Admin'),
        'by_role': 'admin'
    }
    model.add_activity_log(task_id, log)
    model.update(task_id, data)
    from ..extensions import socketio
    socketio.emit('task_updated', {'task_id': task_id}, room='admin')
    for emp_id in task.get('assigned_to', []):
        socketio.emit('task_updated', {'task_id': task_id, 'title': task.get('title', '')}, room=emp_id)
    return jsonify({'message': 'Task updated'}), 200

@tasks_bp.route('/<task_id>/status', methods=['POST'])
@employee_required
def update_status(task_id):
    identity = get_jwt_identity()
    claims = get_jwt()
    data = request.get_json()
    status = data.get('status')
    if status not in VALID_STATUSES:
        return jsonify({'error': 'Invalid status'}), 400
    model = TaskModel()
    task = model.find_by_id(task_id)
    if not task:
        return jsonify({'error': 'Task not found'}), 404
    old_status = task.get('status', 'assigned')
    update = {'status': status}
    if status == 'completed':
        update['completed_at'] = datetime.utcnow()
    model.update(task_id, update)
    log = {
        'action': 'status_changed',
        'description': f'Status changed from {old_status} to {status}',
        'from': old_status,
        'to': status,
        'by_id': identity,
        'by_name': claims.get('name', ''),
        'by_role': claims.get('role', 'employee'),
        'note': data.get('note', '')
    }
    model.add_activity_log(task_id, log)
    from ..extensions import socketio
    socketio.emit('task_status_changed', {
        'task_id': task_id, 'status': status, 'old_status': old_status,
        'changed_by': claims.get('name', ''), 'title': task.get('title', '')
    }, room='admin')
    for emp_id in task.get('assigned_to', []):
        socketio.emit('task_status_changed', {'task_id': task_id, 'status': status}, room=emp_id)
    return jsonify({'message': 'Status updated'}), 200

@tasks_bp.route('/<task_id>/comment', methods=['POST'])
@employee_required
def add_comment(task_id):
    identity = get_jwt_identity()
    claims = get_jwt()
    data = request.get_json()
    text = data.get('text', '').strip()
    if not text:
        return jsonify({'error': 'Comment text required'}), 400
    model = TaskModel()
    task = model.find_by_id(task_id)
    if not task:
        return jsonify({'error': 'Task not found'}), 404
    comment = {
        'text': text,
        'author_id': identity,
        'author_name': claims.get('name', ''),
        'author_role': claims.get('role', 'employee'),
        'is_admin': claims.get('role') == 'admin'
    }
    model.add_comment(task_id, comment)
    log = {
        'action': 'comment_added',
        'description': f'Comment added by {claims.get("name", "")}',
        'by_id': identity,
        'by_name': claims.get('name', ''),
        'by_role': claims.get('role', 'employee')
    }
    model.add_activity_log(task_id, log)
    from ..extensions import socketio
    comment_data = {**comment, 'task_id': task_id}
    socketio.emit('new_comment', comment_data, room=f'task_{task_id}')
    socketio.emit('new_comment', comment_data, room='admin')
    for emp_id in task.get('assigned_to', []):
        if emp_id != identity:
            socketio.emit('new_comment', comment_data, room=emp_id)
    return jsonify({'message': 'Comment added', 'comment': comment}), 201

@tasks_bp.route('/<task_id>/attach', methods=['POST'])
@employee_required
def upload_attachment(task_id):
    identity = get_jwt_identity()
    claims = get_jwt()
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    if not allowed_file(file.filename):
        return jsonify({'error': 'File type not allowed'}), 400
    model = TaskModel()
    task = model.find_by_id(task_id)
    if not task:
        return jsonify({'error': 'Task not found'}), 404
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    ext = file.filename.rsplit('.', 1)[1].lower()
    unique_name = f"{uuid.uuid4().hex}.{ext}"
    save_path = os.path.join(UPLOAD_FOLDER, unique_name)
    file.save(save_path)
    attachment = {
        'filename': unique_name,
        'original_name': secure_filename(file.filename),
        'uploaded_by': identity,
        'uploaded_by_name': claims.get('name', ''),
        'uploaded_by_role': claims.get('role', 'employee'),
        'url': f'/static/uploads/tasks/{unique_name}'
    }
    model.add_attachment(task_id, attachment)
    log = {
        'action': 'file_uploaded',
        'description': f'File "{file.filename}" uploaded by {claims.get("name", "")}',
        'by_id': identity,
        'by_name': claims.get('name', ''),
        'by_role': claims.get('role', 'employee')
    }
    model.add_activity_log(task_id, log)
    from ..extensions import socketio
    socketio.emit('file_uploaded', {'task_id': task_id, 'filename': file.filename}, room='admin')
    return jsonify({'message': 'File uploaded', 'attachment': attachment}), 201

@tasks_bp.route('/<task_id>/activity', methods=['GET'])
@employee_required
def get_activity(task_id):
    model = TaskModel()
    task = model.find_by_id(task_id)
    if not task:
        return jsonify({'error': 'Task not found'}), 404
    logs = list(task.get('activity_logs', []))
    logs.reverse()
    return jsonify({'logs': logs}), 200

@tasks_bp.route('/<task_id>/reassign', methods=['POST'])
@admin_required
def reassign_task(task_id):
    identity = get_jwt_identity()
    claims = get_jwt()
    data = request.get_json()
    new_assigned = data.get('assigned_to', [])
    note = data.get('note', '')
    model = TaskModel()
    model.reassign(task_id, new_assigned, identity, claims.get('name', 'Admin'), note)
    log = {
        'action': 'task_reassigned',
        'description': f'Task reassigned by {claims.get("name", "Admin")}',
        'by_id': identity,
        'by_name': claims.get('name', 'Admin'),
        'by_role': 'admin',
        'note': note
    }
    model.add_activity_log(task_id, log)
    from ..extensions import socketio
    from .notifications import create_notification
    task = model.find_by_id(task_id)
    title = task.get('title', '') if task else 'A task'
    for emp_id in new_assigned:
        create_notification(emp_id, 'task', 'Task Reassigned', f'You have been assigned: {title}', '/employee/tasks')
    return jsonify({'message': 'Task reassigned'}), 200

@tasks_bp.route('/kanban', methods=['GET'])
@admin_required
def get_kanban():
    model = TaskModel()
    kanban_data = model.get_kanban_data({})
    serialized = {}
    for status, tasks in kanban_data.items():
        serialized[status] = [serialize_task(t) for t in tasks]
    return jsonify(serialized), 200

@tasks_bp.route('/<task_id>/kanban-move', methods=['PUT'])
@admin_required
def kanban_move(task_id):
    identity = get_jwt_identity()
    claims = get_jwt()
    data = request.get_json()
    new_status = data.get('status')
    if new_status not in VALID_STATUSES:
        return jsonify({'error': 'Invalid status'}), 400
    model = TaskModel()
    task = model.find_by_id(task_id)
    if not task:
        return jsonify({'error': 'Task not found'}), 404
    old_status = task.get('status', 'assigned')
    update = {'status': new_status}
    if new_status == 'completed':
        update['completed_at'] = datetime.utcnow()
    model.update(task_id, update)
    log = {
        'action': 'status_changed',
        'description': f'Status moved from {old_status} to {new_status} via Kanban',
        'from': old_status, 'to': new_status,
        'by_id': identity, 'by_name': claims.get('name', 'Admin'), 'by_role': 'admin'
    }
    model.add_activity_log(task_id, log)
    from ..extensions import socketio
    socketio.emit('task_status_changed', {'task_id': task_id, 'status': new_status}, room='admin')
    for emp_id in task.get('assigned_to', []):
        socketio.emit('task_status_changed', {'task_id': task_id, 'status': new_status}, room=emp_id)
    return jsonify({'message': 'Task moved'}), 200

@tasks_bp.route('/calendar', methods=['GET'])
@admin_required
def get_calendar_tasks():
    model = TaskModel()
    tasks = model.get_all()
    events = []
    today = date.today().isoformat()
    color_map = {
        'assigned': '#6366f1', 'in_progress': '#3b82f6',
        'under_review': '#f59e0b', 'approved': '#10b981',
        'rejected': '#ef4444', 'completed': '#14b8a6',
        'pending': '#8b5cf6', 'cancelled': '#6b7280'
    }
    for t in tasks:
        if t.get('due_date'):
            status = t.get('status', 'assigned')
            color = color_map.get(status, '#6366f1')
            if t.get('due_date', '') < today and status not in ['completed', 'approved']:
                color = '#ef4444'
            events.append({
                'id': str(t['_id']), 'title': t.get('title', ''),
                'start': t.get('due_date', ''), 'end': t.get('due_date', ''),
                'color': color,
                'extendedProps': {
                    'status': status, 'priority': t.get('priority', 'medium'),
                    'task_id': t.get('task_id', '')
                }
            })
    return jsonify(events), 200

@tasks_bp.route('/analytics', methods=['GET'])
@admin_required
def get_task_analytics():
    model = TaskModel()
    analytics = model.get_analytics()
    emp_model = EmployeeModel()
    named_employee = {}
    for emp_id, count in analytics.get('by_employee', {}).items():
        try:
            emp = emp_model.find_by_id(emp_id)
            name = emp['name'] if emp else emp_id
        except:
            name = emp_id
        named_employee[name] = count
    analytics['by_employee_named'] = named_employee
    return jsonify(analytics), 200

@tasks_bp.route('/<task_id>', methods=['DELETE'])
@admin_required
def delete_task(task_id):
    model = TaskModel()
    model.delete(task_id)
    return jsonify({'message': 'Task deleted'}), 200

@tasks_bp.route('/my', methods=['GET'])
@employee_required
def my_tasks():
    identity = get_jwt_identity()
    model = TaskModel()
    status = request.args.get('status')
    if status:
        tasks = [t for t in model.get_for_employee(identity) if t['status'] == status]
    else:
        tasks = model.get_for_employee(identity)
    return jsonify({'tasks': [serialize_task(t) for t in tasks], 'total': len(tasks)}), 200

@tasks_bp.route('/my/calendar', methods=['GET'])
@employee_required
def my_calendar_tasks():
    identity = get_jwt_identity()
    model = TaskModel()
    tasks = model.get_for_employee(identity)
    events = []
    today = date.today().isoformat()
    color_map = {
        'assigned': '#6366f1', 'in_progress': '#3b82f6',
        'under_review': '#f59e0b', 'approved': '#10b981',
        'rejected': '#ef4444', 'completed': '#14b8a6',
    }
    for t in tasks:
        if t.get('due_date'):
            status = t.get('status', 'assigned')
            color = color_map.get(status, '#6366f1')
            if t.get('due_date', '') < today and status not in ['completed', 'approved']:
                color = '#ef4444'
            events.append({
                'id': str(t['_id']), 'title': t.get('title', ''),
                'start': t.get('due_date', ''), 'color': color,
                'extendedProps': {
                    'status': status, 'priority': t.get('priority', 'medium'),
                    'task_id': t.get('task_id', '')
                }
            })
    return jsonify(events), 200
