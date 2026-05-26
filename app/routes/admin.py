from flask import Blueprint, request, jsonify
from ..middleware.auth_middleware import admin_required
from ..models.employee import EmployeeModel
from ..extensions import get_db
from bson import ObjectId

admin_bp = Blueprint('admin', __name__)

@admin_bp.route('/employees', methods=['GET'])
@admin_required
def get_employees():
    model = EmployeeModel()
    search = request.args.get('search', '')
    dept = request.args.get('department', '')
    filters = {}
    if search:
        import re
        filters['$or'] = [
            {'name': {'$regex': search, '$options': 'i'}},
            {'employee_id': {'$regex': search, '$options': 'i'}},
            {'mobile': {'$regex': search, '$options': 'i'}}
        ]
    if dept:
        filters['department'] = dept
    employees = model.get_all(filters)
    for e in employees:
        e['_id'] = str(e['_id'])
        e.pop('password', None)
        if e.get('created_at'):
            e['created_at'] = e['created_at'].isoformat() + 'Z'
        if e.get('last_login'):
            e['last_login'] = e['last_login'].isoformat() + 'Z'
    return jsonify({'employees': employees, 'total': len(employees)}), 200

@admin_bp.route('/employees', methods=['POST'])
@admin_required
def create_employee():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    required = ['name', 'mobile', 'employee_id', 'password']
    for field in required:
        if not data.get(field):
            return jsonify({'error': f'{field} is required'}), 400
    model = EmployeeModel()
    existing = model.find_by_employee_id(data['employee_id'])
    if existing:
        return jsonify({'error': 'Employee ID already exists'}), 409
    result = model.create(data)
    return jsonify({'message': 'Employee created', 'id': str(result.inserted_id)}), 201

@admin_bp.route('/employees/<emp_id>', methods=['GET'])
@admin_required
def get_employee(emp_id):
    model = EmployeeModel()
    emp = model.find_by_id(emp_id)
    if not emp:
        return jsonify({'error': 'Employee not found'}), 404
    emp['_id'] = str(emp['_id'])
    emp.pop('password', None)
    if emp.get('created_at'):
        emp['created_at'] = emp['created_at'].isoformat() + 'Z'
    if emp.get('last_login'):
        emp['last_login'] = emp['last_login'].isoformat() + 'Z'
    return jsonify(emp), 200

@admin_bp.route('/employees/<emp_id>', methods=['PUT'])
@admin_required
def update_employee(emp_id):
    data = request.get_json()
    model = EmployeeModel()
    model.update(emp_id, data)
    return jsonify({'message': 'Employee updated'}), 200

@admin_bp.route('/employees/<emp_id>', methods=['DELETE'])
@admin_required
def delete_employee(emp_id):
    model = EmployeeModel()
    model.delete(emp_id)
    return jsonify({'message': 'Employee deleted'}), 200

@admin_bp.route('/employees/<emp_id>/toggle-active', methods=['POST'])
@admin_required
def toggle_active(emp_id):
    data = request.get_json()
    status = data.get('is_active', True)
    model = EmployeeModel()
    model.toggle_active(emp_id, status)
    return jsonify({'message': 'Status updated'}), 200

@admin_bp.route('/dashboard-stats', methods=['GET'])
@admin_required
def dashboard_stats():
    db = get_db()
    from datetime import date, datetime
    today = date.today().strftime('%Y-%m-%d')
    today_start = datetime.combine(date.today(), datetime.min.time())
    today_end = datetime.combine(date.today(), datetime.max.time())

    total_employees = db.employees.count_documents({'is_active': True})
    present_today = db.attendance.count_documents({'date': today})
    absent_today = max(0, total_employees - present_today)
    late_today = db.attendance.count_documents({'date': today, 'is_late': True})
    checked_out = db.attendance.count_documents({'date': today, 'check_out': {'$ne': None}})
    working_now = present_today - checked_out
    
    # Overtime calculation (check_out past 19:00, or simple working hours > 9)
    # Since working_hours is stored as float, we can query it
    overtime_employees = db.attendance.count_documents({'date': today, 'working_hours': {'$gt': 9.0}})

    active_departments = len(db.employees.distinct('department', {'is_active': True}))

    total_tasks_today = db.tasks.count_documents({'created_at': {'$gte': today_start, '$lte': today_end}})
    completed_today = db.tasks.count_documents({'status': 'completed', 'completed_at': {'$gte': today_start, '$lte': today_end}})
    
    pending_tasks = db.tasks.count_documents({'status': {'$in': ['assigned', 'pending']}})
    rejected_tasks = db.tasks.count_documents({'status': 'rejected'})
    overdue_tasks = db.tasks.count_documents({'due_date': {'$lt': today, '$ne': ''}, 'status': {'$nin': ['completed', 'approved']}})

    # Average Productivity = (Completed / Assigned) * 100 system-wide
    total_assigned = db.tasks.count_documents({'status': {'$ne': 'cancelled'}})
    total_completed = db.tasks.count_documents({'status': 'completed'})
    avg_productivity = round((total_completed / total_assigned * 100) if total_assigned > 0 else 0, 1)

    return jsonify({
        'total_employees': total_employees,
        'present_today': present_today,
        'absent_today': absent_today,
        'late_today': late_today,
        'checked_out': checked_out,
        'working_now': working_now,
        'overtime_employees': overtime_employees,
        'active_departments': active_departments,
        'total_tasks_today': total_tasks_today,
        'completed_today': completed_today,
        'pending_tasks': pending_tasks,
        'rejected_tasks': rejected_tasks,
        'overdue_tasks': overdue_tasks,
        'avg_productivity': avg_productivity,
        'online_employees': working_now # using working_now for online count
    }), 200
