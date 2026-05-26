from flask import Blueprint, request, jsonify
from ..middleware.auth_middleware import employee_required
from ..models.employee import EmployeeModel
from ..models.task import TaskModel
from ..models.attendance import AttendanceModel
from flask_jwt_extended import get_jwt_identity, get_jwt
from bson import ObjectId
from ..extensions import get_db

employee_bp = Blueprint('employee', __name__)

@employee_bp.route('/profile', methods=['GET'])
@employee_required
def get_profile():
    identity = get_jwt_identity()
    model = EmployeeModel()
    emp = model.find_by_id(identity)
    if not emp:
        return jsonify({'error': 'Not found'}), 404
    emp['_id'] = str(emp['_id'])
    emp.pop('password', None)
    if emp.get('created_at'):
        emp['created_at'] = emp['created_at'].isoformat() + 'Z'
    if emp.get('last_login'):
        emp['last_login'] = emp['last_login'].isoformat() + 'Z'
    return jsonify(emp), 200

@employee_bp.route('/profile', methods=['PUT'])
@employee_required
def update_profile():
    identity = get_jwt_identity()
    data = request.get_json()
    allowed = ['address', 'avatar', 'email']
    update_data = {k: v for k, v in data.items() if k in allowed}
    model = EmployeeModel()
    model.update(identity, update_data)
    return jsonify({'message': 'Profile updated'}), 200

@employee_bp.route('/dashboard-stats', methods=['GET'])
@employee_required
def dashboard_stats():
    identity = get_jwt_identity()
    task_model = TaskModel()
    att_model = AttendanceModel()
    db = get_db()
    
    from datetime import date, datetime
    today = date.today().strftime('%Y-%m-%d')
    today_start = datetime.combine(date.today(), datetime.min.time())
    today_end = datetime.combine(date.today(), datetime.max.time())

    tasks = task_model.get_for_employee(identity)
    
    pending = sum(1 for t in tasks if t['status'] in ['pending', 'assigned'])
    in_progress = sum(1 for t in tasks if t['status'] == 'in_progress')
    completed = sum(1 for t in tasks if t['status'] == 'completed')
    
    tasks_assigned_today = db.tasks.count_documents({'assigned_to': identity, 'created_at': {'$gte': today_start, '$lte': today_end}})
    tasks_completed_today = db.tasks.count_documents({'assigned_to': identity, 'status': 'completed', 'completed_at': {'$gte': today_start, '$lte': today_end}})

    # Productivity Score
    total_assigned = len([t for t in tasks if t['status'] != 'cancelled'])
    productivity_score = round((completed / total_assigned * 100) if total_assigned > 0 else 0, 1)

    # Attendance Percentage (current month)
    import calendar
    today_dt = date.today()
    _, last_day = calendar.monthrange(today_dt.year, today_dt.month)
    month_start = f"{today_dt.year}-{today_dt.month:02d}-01"
    month_end = f"{today_dt.year}-{today_dt.month:02d}-{last_day:02d}"
    
    days_present = db.attendance.count_documents({'employee_id': identity, 'date': {'$gte': month_start, '$lte': month_end}})
    workdays_so_far = max(1, today_dt.day) # simplifying working days
    attendance_percentage = round((days_present / workdays_so_far) * 100, 1)

    today_att = att_model.get_today_record(identity)
    
    return jsonify({
        'total_tasks': len(tasks),
        'pending_tasks': pending,
        'in_progress_tasks': in_progress,
        'completed_tasks': completed,
        'tasks_assigned_today': tasks_assigned_today,
        'tasks_completed_today': tasks_completed_today,
        'productivity_score': productivity_score,
        'attendance_percentage': min(100, attendance_percentage),
        'checked_in_today': today_att is not None,
        'checked_out': today_att.get('check_out') is not None if today_att else False,
        'is_half_day': today_att.get('is_half_day', False) if today_att else False,
        'working_hours': round(today_att.get('working_hours', 0), 2) if today_att else 0,
        'check_in_time': today_att.get('check_in') if today_att else None,
        'check_out_time': today_att.get('check_out') if today_att else None
    }), 200
