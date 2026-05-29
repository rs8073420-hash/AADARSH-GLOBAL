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

@analytics_bp.route('/crm-stats', methods=['GET'])
@admin_required
def crm_stats():
    db = get_db()
    today = date.today().strftime('%Y-%m-%d')
    tomorrow = (date.today() + timedelta(days=1)).strftime('%Y-%m-%d')
    
    # Basic counts
    total = db.leads_master.count_documents({})
    new_leads = db.leads_master.count_documents({'status': 'New'})
    assigned = db.leads_master.count_documents({'assigned_to': {'$ne': ''}})
    converted = db.leads_master.count_documents({'status': 'Closed'})
    missed = db.leads_master.count_documents({'status': 'Lost'})
    reassigned = db.leads_master.count_documents({'reassigned_count': {'$gt': 0}})
    
    # Today's followups
    today_followups = db.leads_master.count_documents({
        'followup_at': {'$gte': today, '$lt': tomorrow}
    })
    
    # Top performing employee
    pipeline = [
        {'$match': {'status': 'Closed'}},
        {'$group': {'_id': '$assigned_to', 'count': {'$sum': 1}}},
        {'$sort': {'count': -1}},
        {'$limit': 1}
    ]
    top_emp_data = list(db.leads_master.aggregate(pipeline))
    top_employee_name = "N/A"
    if top_emp_data and top_emp_data[0]['_id']:
        emp = db.employees.find_one({'_id': ObjectId(top_emp_data[0]['_id'])})
        if emp:
            top_employee_name = emp.get('name')
            
    return jsonify({
        'total_leads': total,
        'new_leads': new_leads,
        'high_priority': db.leads_master.count_documents({'priority': 'High'}),
        'medium_priority': db.leads_master.count_documents({'priority': 'Medium'}),
        'low_priority': db.leads_master.count_documents({'priority': 'Low'}),
        'assigned_leads': assigned,
        'converted_leads': converted,
        'missed_leads': missed,
        'reassigned_leads': reassigned,
        'todays_followups': today_followups,
        'top_employee': top_employee_name
    }), 200

@analytics_bp.route('/employee-monitoring', methods=['GET'])
@admin_required
def employee_monitoring():
    db = get_db()
    employees = list(db.employees.find({'is_active': True}))
    
    monitoring_data = []
    for emp in employees:
        emp_id = str(emp['_id'])
        
        assigned = db.leads_master.count_documents({'assigned_to': emp_id})
        closed = db.leads_master.count_documents({'assigned_to': emp_id, 'status': 'Closed'})
        
        # Ignored leads (auto_reassigned away from this employee)
        # We can find this in assignment logs where assigned_to was this employee, but they didn't respond
        ignored = db.lead_assignment_logs.count_documents({
            'assigned_to': emp_id,
            'updated_by_employee': False,
            'reassigned': True
        })
        
        updated = db.lead_assignment_logs.count_documents({
            'assigned_to': emp_id,
            'updated_by_employee': True
        })
        
        conversion_rate = round((closed / assigned * 100), 1) if assigned > 0 else 0
        
        monitoring_data.append({
            'name': emp.get('name'),
            'assigned': assigned,
            'updated': updated,
            'ignored': ignored,
            'reassigned': ignored, # Ignored leads usually trigger reassignment
            'conversion': conversion_rate
        })
        
    return jsonify({'monitoring': monitoring_data}), 200

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
    
    # Convert ObjectId to string
    for a in activities:
        if 'task_id' in a and hasattr(a['task_id'], '__str__'):
            a['task_id'] = str(a['task_id'])
        if 'timestamp' in a and hasattr(a['timestamp'], 'isoformat'):
            a['timestamp'] = a['timestamp'].isoformat() + 'Z'
    
    # We could also merge attendance activities here, but keeping it simple for now, sorting in python
    activities.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
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

# -----------------------------------------------------------------------------
# V2 ADVANCED ANALYTICS ENDPOINTS
# -----------------------------------------------------------------------------

@analytics_bp.route('/v2/kpis', methods=['GET'])
@admin_required
def v2_kpis():
    db = get_db()
    today = date.today().strftime('%Y-%m-%d')
    now = datetime.utcnow()
    
    total_employees = db.employees.count_documents({'is_active': True})
    total_leads = db.leads_master.count_documents({})
    high_priority = db.leads_master.count_documents({'priority': 'High'})
    medium_priority = db.leads_master.count_documents({'priority': 'Medium'})
    low_priority = db.leads_master.count_documents({'priority': 'Low'})
    converted = db.leads_master.count_documents({'status': 'Closed'})
    pending = db.leads_master.count_documents({'status': {'$in': ['New', 'Contacted', 'Interested', 'Negotiation']}})
    reassigned = db.leads_master.count_documents({'reassigned_count': {'$gt': 0}})
    
    completed_tasks = db.tasks.count_documents({'status': 'completed'})
    overdue_tasks = db.tasks.count_documents({'due_date': {'$lt': today, '$ne': ''}, 'status': {'$nin': ['completed', 'approved']}})
    
    present = db.attendance.count_documents({'date': today})
    late = db.attendance.count_documents({'date': today, 'is_late': True})
    
    return jsonify({
        'total_employees': total_employees,
        'online_employees': 0, # Frontend will populate
        'total_leads': total_leads,
        'high_priority_leads': high_priority,
        'medium_priority_leads': medium_priority,
        'low_priority_leads': low_priority,
        'converted_leads': converted,
        'reassigned_leads': reassigned,
        'pending_leads': pending,
        'completed_tasks': completed_tasks,
        'overdue_tasks': overdue_tasks,
        'present_employees': present,
        'late_employees': late
    }), 200

@analytics_bp.route('/v2/leads', methods=['GET'])
@admin_required
def v2_leads():
    db = get_db()
    pipeline_counts = {
        'New': db.leads_master.count_documents({'status': 'New'}),
        'Contacted': db.leads_master.count_documents({'status': 'Contacted'}),
        'Interested': db.leads_master.count_documents({'status': 'Interested'}),
        'Site Visit': db.leads_master.count_documents({'status': 'Site Visit'}),
        'Negotiation': db.leads_master.count_documents({'status': 'Negotiation'}),
        'Closed': db.leads_master.count_documents({'status': 'Closed'}),
        'Lost': db.leads_master.count_documents({'status': 'Lost'})
    }
    sources_raw = list(db.leads_master.aggregate([{'$group': {'_id': '$source', 'count': {'$sum': 1}}}]))
    sources = {s['_id']: s['count'] for s in sources_raw if s['_id']}
    
    today = date.today()
    dates = [(today - timedelta(days=i)).strftime('%Y-%m-%d') for i in range(6, -1, -1)]
    trend = []
    for d in dates:
        start = datetime.strptime(d, '%Y-%m-%d')
        end = start + timedelta(days=1)
        converted = db.leads_master.count_documents({'status': 'Closed', 'updated_at': {'$gte': start, '$lt': end}})
        trend.append(converted)
        
    return jsonify({
        'pipeline': pipeline_counts,
        'sources': sources,
        'conversion_dates': dates,
        'conversion_trend': trend
    }), 200

@analytics_bp.route('/v2/attendance', methods=['GET'])
@admin_required
def v2_attendance():
    db = get_db()
    today = date.today()
    dates = [(today - timedelta(days=i)).strftime('%Y-%m-%d') for i in range(13, -1, -1)]
    daily = []
    for d in dates:
        present = db.attendance.count_documents({'date': d})
        absent = max(0, db.employees.count_documents({'is_active': True}) - present)
        late = db.attendance.count_documents({'date': d, 'is_late': True})
        early = db.attendance.count_documents({'date': d, 'early_exit': True})
        daily.append({'date': d, 'present': present, 'absent': absent, 'late': late, 'early': early})
    return jsonify({'daily': daily}), 200

@analytics_bp.route('/v2/performance', methods=['GET'])
@admin_required
def v2_performance():
    db = get_db()
    employees = list(db.employees.find({'is_active': True}, {'name': 1, '_id': 1, 'avatar': 1}))
    result = []
    for emp in employees:
        emp_id = str(emp['_id'])
        
        assigned = db.leads_master.count_documents({'assigned_to': emp_id})
        converted = db.leads_master.count_documents({'assigned_to': emp_id, 'status': 'Closed'})
        reassigned = db.lead_assignment_logs.count_documents({'assigned_to': emp_id, 'updated_by_employee': False, 'reassigned': True})
        updated = db.lead_assignment_logs.count_documents({'assigned_to': emp_id, 'updated_by_employee': True})
        
        total_tasks = db.tasks.count_documents({'assigned_to': emp_id})
        completed_tasks = db.tasks.count_documents({'assigned_to': emp_id, 'status': 'completed'})
        
        lead_score = (converted / assigned * 100) if assigned > 0 else 0
        if reassigned > 0 and assigned > 0:
            lead_score -= (reassigned / assigned * 20)
        lead_score = max(0, lead_score)
        
        task_score = (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0
        unified_score = round((lead_score * 0.6) + (task_score * 0.4), 1)
        
        result.append({
            'name': emp['name'],
            'avatar': emp.get('avatar', ''),
            'assigned': assigned,
            'updated': updated,
            'converted': converted,
            'reassigned': reassigned,
            'score': unified_score
        })
    result.sort(key=lambda x: x['score'], reverse=True)
    return jsonify({'performance': result}), 200

@analytics_bp.route('/v2/tasks', methods=['GET'])
@admin_required
def v2_tasks():
    db = get_db()
    today = date.today()
    
    dates = [(today - timedelta(days=i)).strftime('%Y-%m-%d') for i in range(6, -1, -1)]
    completed_trend = []
    created_trend = []
    
    for d in dates:
        start = datetime.strptime(d, '%Y-%m-%d')
        end = start + timedelta(days=1)
        completed = db.tasks.count_documents({'status': 'completed', 'completed_at': {'$gte': start, '$lt': end}})
        created = db.tasks.count_documents({'created_at': {'$gte': start, '$lt': end}})
        completed_trend.append(completed)
        created_trend.append(created)
        
    return jsonify({
        'dates': dates,
        'completed_trend': completed_trend,
        'created_trend': created_trend
    }), 200

@analytics_bp.route('/v2/reassignments', methods=['GET'])
@admin_required
def v2_reassignments():
    db = get_db()
    
    pipeline = [
        {'$match': {'updated_by_employee': False, 'reassigned': True}},
        {'$group': {'_id': '$assigned_to', 'count': {'$sum': 1}}},
        {'$sort': {'count': -1}},
        {'$limit': 5}
    ]
    reassigned_raw = list(db.lead_assignment_logs.aggregate(pipeline))
    
    top_ignored = []
    for r in reassigned_raw:
        if r['_id']:
            emp = db.employees.find_one({'_id': ObjectId(r['_id'])})
            if emp:
                top_ignored.append({'name': emp['name'], 'ignored_count': r['count']})
                
    total_reassigned = db.leads_master.count_documents({'reassigned_count': {'$gt': 0}})
    high_priority_reassigned = db.leads_master.count_documents({'reassigned_count': {'$gt': 0}, 'priority': 'High'})
    
    today = date.today()
    dates = [(today - timedelta(days=i)).strftime('%Y-%m-%d') for i in range(6, -1, -1)]
    trend = []
    for d in dates:
        start = datetime.strptime(d, '%Y-%m-%d')
        end = start + timedelta(days=1)
        count = db.lead_assignment_logs.count_documents({'updated_by_employee': False, 'reassigned': True, 'timestamp': {'$gte': start, '$lt': end}})
        trend.append(count)

    return jsonify({
        'total_reassigned': total_reassigned,
        'high_priority_reassigned': high_priority_reassigned,
        'top_ignored_employees': top_ignored,
        'trend_dates': dates,
        'trend': trend
    }), 200
