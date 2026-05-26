from flask import Blueprint, request, jsonify
from ..middleware.auth_middleware import admin_required, employee_required
from ..models.attendance import AttendanceModel
from ..models.employee import EmployeeModel
from ..models.task import TaskModel
from flask_jwt_extended import get_jwt_identity, get_jwt
from bson import ObjectId
from datetime import date, datetime, timedelta

attendance_bp = Blueprint('attendance', __name__)

def serialize_record(rec):
    rec['_id'] = str(rec['_id'])
    if rec.get('check_in'):
        rec['check_in'] = rec['check_in'].isoformat() + 'Z'
    if rec.get('check_out'):
        rec['check_out'] = rec['check_out'].isoformat() + 'Z'
    if rec.get('created_at'):
        rec['created_at'] = rec['created_at'].isoformat() + 'Z'
    return rec

@attendance_bp.route('/check-in', methods=['POST'])
@employee_required
def check_in():
    identity = get_jwt_identity()
    claims = get_jwt()
    model = AttendanceModel()
    today_record = model.get_today_record(identity)
    if today_record and today_record.get('check_out') is None:
        return jsonify({'error': 'Already checked in. Please check out first.'}), 400
        
    data = request.get_json(silent=True) or {}
    remarks = data.get('remarks', '').strip()
    
    from datetime import datetime, timedelta
    now = datetime.utcnow()
    ist = now + timedelta(hours=5, minutes=30)
    is_late = ist.hour > 10 or (ist.hour == 10 and ist.minute > 0)
    
    if is_late and not remarks and not today_record:
        return jsonify({'error': 'remarks_required', 'message': 'You are checking in late (after 10:00 AM). Remarks are compulsory.'}), 400
        
    emp_name = claims.get('name', '')
    result = model.check_in(identity, emp_name, remarks=remarks)
    EmployeeModel().set_online(identity, True)
    
    from ..extensions import socketio
    socketio.emit('attendance_update', {'action': 'check_in', 'employee_name': emp_name}, room='admin')
    
    return jsonify({'message': 'Checked in successfully'}), 201

@attendance_bp.route('/check-out', methods=['POST'])
@employee_required
def check_out():
    identity = get_jwt_identity()
    claims = get_jwt()
    model = AttendanceModel()
    today_record = model.get_today_record(identity)
    if not today_record:
        return jsonify({'error': 'No check-in record found for today'}), 400
    if today_record.get('check_out'):
        return jsonify({'error': 'Already checked out'}), 400
    
    data = request.get_json(silent=True) or {}
    remarks = data.get('remarks', '').strip()
    tomorrow_plan = data.get('tomorrow_plan', '')
    
    from datetime import datetime, timedelta
    now = datetime.utcnow()
    ist = now + timedelta(hours=5, minutes=30)
    is_early = ist.hour < 19
    
    if is_early and not remarks:
        return jsonify({'error': 'remarks_required', 'message': 'You are checking out early (before 7:00 PM). Remarks are compulsory.'}), 400
    
    # Calculate productivity
    task_model = TaskModel()
    tasks = task_model.get_for_employee(identity)
    
    today_str = date.today().strftime('%Y-%m-%d')
    # Assigned today: Created today or due today
    # For simplicity, we define "assigned tasks" as anything currently pending + completed today
    completed_today = 0
    pending = 0
    for t in tasks:
        if t.get('status') == 'completed':
            completed_at = t.get('completed_at')
            if completed_at and completed_at.strftime('%Y-%m-%d') == today_str:
                completed_today += 1
        elif t.get('status') not in ['approved', 'cancelled']:
            pending += 1
            
    total_assigned = completed_today + pending
    productivity = (completed_today / total_assigned * 100) if total_assigned > 0 else 0.0

    model.check_out(today_record, remarks, tomorrow_plan, completed_today, pending, productivity)
    EmployeeModel().set_offline(identity)
    
    from ..extensions import socketio
    emp_name = claims.get('name', '')
    socketio.emit('attendance_update', {'action': 'check_out', 'employee_name': emp_name}, room='admin')
    
    return jsonify({'message': 'Checked out successfully'}), 200

@attendance_bp.route('/today', methods=['GET'])
@employee_required
def today_status():
    identity = get_jwt_identity()
    model = AttendanceModel()
    record = model.get_today_record(identity)
    if not record:
        return jsonify({'checked_in': False}), 200
    return jsonify({'checked_in': True, 'record': serialize_record(record)}), 200

@attendance_bp.route('/history', methods=['GET'])
@employee_required
def history():
    identity = get_jwt_identity()
    limit = int(request.args.get('limit', 30))
    model = AttendanceModel()
    records = model.get_history(identity, limit)
    return jsonify({'records': [serialize_record(r) for r in records]}), 200

@attendance_bp.route('/all', methods=['GET'])
@admin_required
def all_attendance():
    model = AttendanceModel()
    start = request.args.get('start', date.today().strftime('%Y-%m-%d'))
    end = request.args.get('end', date.today().strftime('%Y-%m-%d'))
    emp_id = request.args.get('employee_id')
    search = request.args.get('search', '').lower()
    
    # Optional filters
    status_filter = request.args.get('status') # 'late', 'overtime', 'early_exit'
    
    records = model.get_by_date_range(start, end, emp_id)
    
    if search:
        records = [r for r in records if search in r.get('employee_name', '').lower() or search in r.get('employee_id', '').lower()]
    
    if status_filter == 'late':
        records = [r for r in records if r.get('is_late')]
    elif status_filter == 'overtime':
        records = [r for r in records if r.get('overtime')]
    elif status_filter == 'early_exit':
        records = [r for r in records if r.get('early_exit')]
        
    return jsonify({'records': [serialize_record(r) for r in records], 'total': len(records)}), 200

@attendance_bp.route('/admin/dashboard', methods=['GET'])
@admin_required
def admin_dashboard():
    model = AttendanceModel()
    today_records = model.get_today_all()
    
    from ..extensions import get_db
    total_employees = get_db().employees.count_documents({'is_active': True})
    
    present = len(today_records)
    absent = total_employees - present
    late = sum(1 for r in today_records if r.get('is_late'))
    overtime = sum(1 for r in today_records if r.get('overtime'))
    checked_out = sum(1 for r in today_records if r.get('check_out'))
    
    attendance_pct = (present / total_employees * 100) if total_employees > 0 else 0
    
    # Basic trends for chart (last 7 days)
    trends = {'dates': [], 'present': [], 'absent': []}
    for i in range(6, -1, -1):
        d = (datetime.utcnow() - timedelta(days=i)).strftime('%Y-%m-%d')
        trends['dates'].append(d)
        d_records = model.get_by_date_range(d, d)
        trends['present'].append(len(d_records))
        trends['absent'].append(total_employees - len(d_records))

    return jsonify({
        'total_employees': total_employees,
        'present': present,
        'absent': absent,
        'late': late,
        'checked_out': checked_out,
        'overtime': overtime,
        'attendance_percentage': attendance_pct,
        'trends': trends
    }), 200

@attendance_bp.route('/employee/dashboard', methods=['GET'])
@employee_required
def employee_dashboard():
    identity = get_jwt_identity()
    model = AttendanceModel()
    
    today_record = model.get_today_record(identity)
    
    task_model = TaskModel()
    tasks = task_model.get_for_employee(identity)
    
    today_str = date.today().strftime('%Y-%m-%d')
    completed_today = 0
    pending = 0
    for t in tasks:
        if t.get('status') == 'completed':
            completed_at = t.get('completed_at')
            if completed_at and completed_at.strftime('%Y-%m-%d') == today_str:
                completed_today += 1
        elif t.get('status') not in ['approved', 'cancelled']:
            pending += 1
            
    total_assigned = completed_today + pending
    productivity = (completed_today / total_assigned * 100) if total_assigned > 0 else 0.0

    now = datetime.utcnow()
    month_records = model.get_monthly_summary(identity, now.year, now.month)
    
    late_count = sum(1 for r in month_records if r.get('is_late'))
    overtime_count = sum(1 for r in month_records if r.get('overtime'))
    
    return jsonify({
        'today': serialize_record(today_record) if today_record else None,
        'productivity_score': productivity,
        'tasks_completed': completed_today,
        'tasks_pending': pending,
        'monthly_late': late_count,
        'monthly_overtime': overtime_count,
        'monthly_present': len(month_records)
    }), 200
