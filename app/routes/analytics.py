from flask import Blueprint, request, jsonify
from ..middleware.auth_middleware import admin_required, employee_required
from ..extensions import get_db
from flask_jwt_extended import get_jwt_identity, get_jwt
from datetime import datetime, date, timedelta
from bson import ObjectId

analytics_bp = Blueprint('analytics', __name__)

@analytics_bp.route('/tasks-overview', methods=['GET'])
@admin_required
def tasks_overview():
    db = get_db()
    pipeline = [
        {'$group': {'_id': '$status', 'count': {'$sum': 1}}}
    ]
    result = list(db.tasks.aggregate(pipeline))
    data = {r['_id']: r['count'] for r in result}
    return jsonify(data), 200

@analytics_bp.route('/tasks-by-priority', methods=['GET'])
@admin_required
def tasks_by_priority():
    db = get_db()
    pipeline = [
        {'$group': {'_id': '$priority', 'count': {'$sum': 1}}}
    ]
    result = list(db.tasks.aggregate(pipeline))
    data = {r['_id']: r['count'] for r in result}
    return jsonify(data), 200

@analytics_bp.route('/attendance-trend', methods=['GET'])
@admin_required
def attendance_trend():
    db = get_db()
    days = int(request.args.get('days', 7))
    today = date.today()
    dates = [(today - timedelta(days=i)).strftime('%Y-%m-%d') for i in range(days-1, -1, -1)]
    
    data = []
    for d in dates:
        count = db.attendance.count_documents({'date': d})
        late = db.attendance.count_documents({'date': d, 'is_late': True})
        data.append({'date': d, 'present': count, 'late': late})
    
    return jsonify({'trend': data}), 200

@analytics_bp.route('/employee-productivity', methods=['GET'])
@admin_required
def employee_productivity():
    db = get_db()
    employees = list(db.employees.find({'is_active': True}, {'name': 1, '_id': 1, 'employee_id': 1}))
    result = []
    for emp in employees:
        emp_id = str(emp['_id'])
        total = db.tasks.count_documents({'assigned_to': emp_id})
        completed = db.tasks.count_documents({'assigned_to': emp_id, 'status': 'completed'})
        score = round((completed / total * 100) if total > 0 else 0, 1)
        result.append({
            'name': emp['name'],
            'employee_id': emp.get('employee_id', ''),
            'total_tasks': total,
            'completed': completed,
            'productivity': score
        })
    result.sort(key=lambda x: x['productivity'], reverse=True)
    return jsonify({'employees': result}), 200

@analytics_bp.route('/monthly-tasks', methods=['GET'])
@admin_required
def monthly_tasks():
    db = get_db()
    today = date.today()
    months = []
    for i in range(5, -1, -1):
        d = date(today.year, today.month, 1) - timedelta(days=i*30)
        months.append({'year': d.year, 'month': d.month, 'label': d.strftime('%b %Y')})
    
    data = []
    for m in months:
        start = f"{m['year']}-{m['month']:02d}-01"
        import calendar
        _, last_day = calendar.monthrange(m['year'], m['month'])
        end = f"{m['year']}-{m['month']:02d}-{last_day:02d}"
        
        created = db.tasks.count_documents({'created_at': {'$gte': datetime(m['year'], m['month'], 1), '$lte': datetime(m['year'], m['month'], last_day, 23, 59)}})
        completed = db.tasks.count_documents({
            'status': 'completed',
            'completed_at': {'$gte': datetime(m['year'], m['month'], 1), '$lte': datetime(m['year'], m['month'], last_day, 23, 59)}
        })
        data.append({'label': m['label'], 'created': created, 'completed': completed})
    
    return jsonify({'monthly': data}), 200

@analytics_bp.route('/my-stats', methods=['GET'])
@employee_required
def my_stats():
    identity = get_jwt_identity()
    db = get_db()
    
    days = int(request.args.get('days', 30))
    today = date.today()
    dates = [(today - timedelta(days=i)).strftime('%Y-%m-%d') for i in range(days-1, -1, -1)]
    
    attendance_data = []
    for d in dates:
        present = 1 if db.attendance.find_one({'employee_id': identity, 'date': d}) else 0
        attendance_data.append({'date': d, 'present': present})
    
    task_pipeline = [
        {'$match': {'assigned_to': identity}},
        {'$group': {'_id': '$status', 'count': {'$sum': 1}}}
    ]
    task_stats = list(db.tasks.aggregate(task_pipeline))
    task_data = {r['_id']: r['count'] for r in task_stats}
    
    return jsonify({'attendance_trend': attendance_data, 'task_stats': task_data}), 200

@analytics_bp.route('/activity-feed', methods=['GET'])
@admin_required
def activity_feed():
    db = get_db()
    limit = int(request.args.get('limit', 20))
    # Aggregate task activities
    pipeline = [
        {'$unwind': '$activity_logs'},
        {'$sort': {'activity_logs.timestamp': -1}},
        {'$limit': limit},
        {'$project': {
            '_id': 0,
            'type': 'task',
            'task_id': '$_id',
            'title': '$title',
            'action': '$activity_logs.action',
            'description': '$activity_logs.description',
            'by_name': '$activity_logs.by_name',
            'timestamp': '$activity_logs.timestamp'
        }}
    ]
    activities = list(db.tasks.aggregate(pipeline))
    
    # We could also merge attendance activities here, but keeping it simple for now, sorting in python
    activities.sort(key=lambda x: x['timestamp'], reverse=True)
    return jsonify({'feed': activities[:limit]}), 200

@analytics_bp.route('/smart-alerts', methods=['GET'])
@admin_required
def smart_alerts():
    db = get_db()
    today = date.today().strftime('%Y-%m-%d')
    alerts = []
    
    # 1. High Workload Alert (Employees with > 5 pending tasks)
    pipeline_workload = [
        {'$match': {'status': {'$in': ['assigned', 'pending', 'in_progress']}}},
        {'$unwind': '$assigned_to'},
        {'$group': {'_id': '$assigned_to', 'count': {'$sum': 1}}},
        {'$match': {'count': {'$gt': 5}}}
    ]
    high_workload = list(db.tasks.aggregate(pipeline_workload))
    for hw in high_workload:
        emp = db.employees.find_one({'_id': ObjectId(hw['_id'])})
        if emp:
            alerts.append({'type': 'warning', 'title': 'High Workload', 'message': f"{emp['name']} has {hw['count']} pending tasks.", 'timestamp': datetime.utcnow().isoformat() + 'Z'})
            
    # 2. Unassigned Urgent Tasks
    unassigned = db.tasks.count_documents({'priority': 'high', 'assigned_to': {'$size': 0}, 'status': {'$ne': 'completed'}})
    if unassigned > 0:
        alerts.append({'type': 'danger', 'title': 'Unassigned Urgent Tasks', 'message': f"There are {unassigned} urgent tasks with no assignee.", 'timestamp': datetime.utcnow().isoformat() + 'Z'})

    # 3. Overdue Tasks
    overdue = db.tasks.count_documents({'due_date': {'$lt': today, '$ne': ''}, 'status': {'$nin': ['completed', 'approved']}})
    if overdue > 0:
        alerts.append({'type': 'danger', 'title': 'Overdue Tasks', 'message': f"{overdue} tasks have passed their deadline.", 'timestamp': datetime.utcnow().isoformat() + 'Z'})

    # 4. Absent but Assigned Tasks Today
    # Get all employees assigned tasks today
    today_start = datetime.combine(date.today(), datetime.min.time())
    today_end = datetime.combine(date.today(), datetime.max.time())
    tasks_today = db.tasks.find({'created_at': {'$gte': today_start, '$lte': today_end}})
    assigned_emps = set()
    for t in tasks_today:
        for a in t.get('assigned_to', []):
            assigned_emps.add(a)
            
    for emp_id in assigned_emps:
        att = db.attendance.find_one({'employee_id': emp_id, 'date': today})
        if not att:
            emp = db.employees.find_one({'_id': ObjectId(emp_id)})
            if emp:
                alerts.append({'type': 'warning', 'title': 'Absent Employee Assigned', 'message': f"{emp['name']} was assigned a task today but is marked absent.", 'timestamp': datetime.utcnow().isoformat() + 'Z'})
    
    # Limit alerts to 10 most critical
    return jsonify({'alerts': alerts[:10]}), 200

