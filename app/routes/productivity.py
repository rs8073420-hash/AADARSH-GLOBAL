from flask import Blueprint, request, jsonify
from flask_jwt_extended import get_jwt_identity, get_jwt
from ..extensions import get_db
from ..middleware.auth_middleware import admin_required, employee_required
from bson import ObjectId
from datetime import datetime, timedelta

productivity_bp = Blueprint('productivity_bp', __name__)

# Weights for the productivity score calculation
WEIGHT_ATTENDANCE = 0.30
WEIGHT_WORK_HOURS = 0.25
WEIGHT_TASK_COMPLETION = 0.30
WEIGHT_PUNCTUALITY = 0.15


def _calculate_productivity(db, employee_id):
    """
    Calculate a productivity score (0-100) for an employee based on:
      - Attendance score  (30%)  – days present / working days
      - Work hours score  (25%)  – avg daily hours / 8 target
      - Task completion   (30%)  – completed tasks / total assigned
      - Punctuality       (15%)  – on-time days / present days
    All over the last 30 days.
    """
    now = datetime.utcnow()
    thirty_days_ago = (now - timedelta(days=30)).strftime('%Y-%m-%d')
    today_str = now.strftime('%Y-%m-%d')

    # --- Attendance ---
    attendances = list(db.attendance.find({
        'employee_id': employee_id,
        'date': {'$gte': thirty_days_ago, '$lte': today_str}
    }))
    present_days = len(attendances)
    working_days = max(22, 1)  # assume ~22 working days in a month
    attendance_score = min(present_days / working_days, 1.0) * 100

    # --- Work Hours ---
    total_hours = sum(a.get('working_hours', 0) for a in attendances)
    avg_hours = total_hours / max(present_days, 1)
    work_hours_score = min(avg_hours / 8.0, 1.0) * 100

    # --- Task Completion ---
    tasks = list(db.tasks.find({
        'assigned_to': employee_id,
    }))
    # Count tasks created / assigned in last 30 days
    recent_tasks = [t for t in tasks if t.get('created_at') and t['created_at'] >= now - timedelta(days=30)]
    total_tasks = len(recent_tasks)
    completed_tasks = sum(1 for t in recent_tasks if t.get('status') in ('completed', 'approved'))
    task_completion_score = (completed_tasks / max(total_tasks, 1)) * 100

    # --- Punctuality ---
    on_time_days = sum(1 for a in attendances if not a.get('is_late', False))
    punctuality_score = (on_time_days / max(present_days, 1)) * 100

    # --- Weighted final score ---
    final_score = (
        attendance_score * WEIGHT_ATTENDANCE +
        work_hours_score * WEIGHT_WORK_HOURS +
        task_completion_score * WEIGHT_TASK_COMPLETION +
        punctuality_score * WEIGHT_PUNCTUALITY
    )
    final_score = round(max(min(final_score, 100), 0), 2)

    # Persist / upsert
    db.productivity.update_one(
        {'employee_id': employee_id},
        {'$set': {
            'employee_id': employee_id,
            'score': final_score,
            'attendance_score': round(attendance_score, 2),
            'work_hours_score': round(work_hours_score, 2),
            'task_completion_score': round(task_completion_score, 2),
            'punctuality_score': round(punctuality_score, 2),
            'present_days': present_days,
            'total_hours': round(total_hours, 2),
            'total_tasks': total_tasks,
            'completed_tasks': completed_tasks,
            'on_time_days': on_time_days,
            'updated_at': now,
        }},
        upsert=True
    )

    return {
        'score': final_score,
        'attendance_score': round(attendance_score, 2),
        'work_hours_score': round(work_hours_score, 2),
        'task_completion_score': round(task_completion_score, 2),
        'punctuality_score': round(punctuality_score, 2),
        'present_days': present_days,
        'total_hours': round(total_hours, 2),
        'total_tasks': total_tasks,
        'completed_tasks': completed_tasks,
        'on_time_days': on_time_days,
    }


# ---------------------------------------------------------------------------
# GET /score/<employee_id> - Get productivity score
# ---------------------------------------------------------------------------
@productivity_bp.route('/score/<employee_id>', methods=['GET'])
@employee_required
def get_score(employee_id):
    try:
        identity = get_jwt_identity()
        claims = get_jwt()

        # Non-admin can only view their own score
        if claims.get('role') != 'admin' and identity != employee_id:
            return jsonify({'error': 'You can only view your own productivity score'}), 403

        db = get_db()

        # Check if recalculation is needed (older than 1 hour)
        existing = db.productivity.find_one({'employee_id': employee_id})
        needs_recalc = True
        if existing and existing.get('updated_at'):
            age = datetime.utcnow() - existing['updated_at']
            if age.total_seconds() < 3600:  # less than 1 hour old
                needs_recalc = False

        if needs_recalc:
            result = _calculate_productivity(db, employee_id)
        else:
            result = {
                'score': existing.get('score', 0),
                'attendance_score': existing.get('attendance_score', 0),
                'work_hours_score': existing.get('work_hours_score', 0),
                'task_completion_score': existing.get('task_completion_score', 0),
                'punctuality_score': existing.get('punctuality_score', 0),
                'present_days': existing.get('present_days', 0),
                'total_hours': existing.get('total_hours', 0),
                'total_tasks': existing.get('total_tasks', 0),
                'completed_tasks': existing.get('completed_tasks', 0),
                'on_time_days': existing.get('on_time_days', 0),
            }

        # Fetch employee name
        emp = db.employees.find_one({'_id': ObjectId(employee_id)}, {'name': 1})
        result['employee_id'] = employee_id
        result['employee_name'] = emp.get('name', '') if emp else ''

        return jsonify(result), 200
    except Exception as e:
        return jsonify({'error': 'Failed to fetch productivity score', 'details': str(e)}), 500


# ---------------------------------------------------------------------------
# GET /scores - Admin gets all employee scores (sorted)
# ---------------------------------------------------------------------------
@productivity_bp.route('/scores', methods=['GET'])
@admin_required
def get_all_scores():
    try:
        db = get_db()
        recalculate = request.args.get('recalculate', 'false').lower() in ('true', '1', 'yes')

        employees = list(db.employees.find({'is_active': True}, {'name': 1, 'employee_id': 1, 'department': 1}))

        scores = []
        for emp in employees:
            emp_id = str(emp['_id'])

            if recalculate:
                result = _calculate_productivity(db, emp_id)
            else:
                existing = db.productivity.find_one({'employee_id': emp_id})
                if existing:
                    result = {
                        'score': existing.get('score', 0),
                        'attendance_score': existing.get('attendance_score', 0),
                        'work_hours_score': existing.get('work_hours_score', 0),
                        'task_completion_score': existing.get('task_completion_score', 0),
                        'punctuality_score': existing.get('punctuality_score', 0),
                    }
                else:
                    result = _calculate_productivity(db, emp_id)

            scores.append({
                'employee_id': emp_id,
                'employee_code': emp.get('employee_id', ''),
                'name': emp.get('name', ''),
                'department': emp.get('department', ''),
                'score': result['score'],
                'attendance_score': result.get('attendance_score', 0),
                'work_hours_score': result.get('work_hours_score', 0),
                'task_completion_score': result.get('task_completion_score', 0),
                'punctuality_score': result.get('punctuality_score', 0),
            })

        # Sort by score descending
        scores.sort(key=lambda x: x['score'], reverse=True)

        # Add rank
        for i, entry in enumerate(scores, start=1):
            entry['rank'] = i

        return jsonify({'scores': scores, 'total': len(scores)}), 200
    except Exception as e:
        return jsonify({'error': 'Failed to fetch scores', 'details': str(e)}), 500


# ---------------------------------------------------------------------------
# GET /insights/<employee_id> - Detailed productivity breakdown
# ---------------------------------------------------------------------------
@productivity_bp.route('/insights/<employee_id>', methods=['GET'])
@employee_required
def get_insights(employee_id):
    try:
        identity = get_jwt_identity()
        claims = get_jwt()

        if claims.get('role') != 'admin' and identity != employee_id:
            return jsonify({'error': 'You can only view your own insights'}), 403

        db = get_db()
        result = _calculate_productivity(db, employee_id)

        # Employee info
        emp = db.employees.find_one({'_id': ObjectId(employee_id)}, {'name': 1, 'department': 1, 'designation': 1})

        # Determine strengths and weaknesses
        components = {
            'Attendance': result['attendance_score'],
            'Work Hours': result['work_hours_score'],
            'Task Completion': result['task_completion_score'],
            'Punctuality': result['punctuality_score'],
        }
        sorted_components = sorted(components.items(), key=lambda x: x[1], reverse=True)
        strengths = [c[0] for c in sorted_components[:2] if c[1] >= 60]
        weaknesses = [c[0] for c in sorted_components if c[1] < 60]

        # Suggestions
        suggestions = []
        if result['attendance_score'] < 70:
            suggestions.append('Try to maintain regular attendance to improve your score.')
        if result['work_hours_score'] < 70:
            suggestions.append('Your average work hours are below target. Aim for 8 hours daily.')
        if result['task_completion_score'] < 70:
            suggestions.append('Focus on completing assigned tasks within deadlines.')
        if result['punctuality_score'] < 80:
            suggestions.append('Arriving on time consistently will boost your punctuality score.')
        if not suggestions:
            suggestions.append('Great job! Keep up the excellent performance.')

        # Trend: compare to previous month (simple approach)
        now = datetime.utcnow()
        prev_month_start = (now.replace(day=1) - timedelta(days=1)).replace(day=1)
        prev_month_end = now.replace(day=1) - timedelta(days=1)
        prev_att = list(db.attendance.find({
            'employee_id': employee_id,
            'date': {
                '$gte': prev_month_start.strftime('%Y-%m-%d'),
                '$lte': prev_month_end.strftime('%Y-%m-%d')
            }
        }))
        prev_present = len(prev_att)
        prev_on_time = sum(1 for a in prev_att if not a.get('is_late', False))
        trend = 'stable'
        if result['present_days'] > prev_present + 2:
            trend = 'improving'
        elif result['present_days'] < prev_present - 2:
            trend = 'declining'

        return jsonify({
            'employee_id': employee_id,
            'employee_name': emp.get('name', '') if emp else '',
            'department': emp.get('department', '') if emp else '',
            'score': result['score'],
            'breakdown': {
                'attendance': {'score': result['attendance_score'], 'weight': '30%', 'days_present': result['present_days']},
                'work_hours': {'score': result['work_hours_score'], 'weight': '25%', 'total_hours': result['total_hours']},
                'task_completion': {'score': result['task_completion_score'], 'weight': '30%', 'completed': result['completed_tasks'], 'total': result['total_tasks']},
                'punctuality': {'score': result['punctuality_score'], 'weight': '15%', 'on_time_days': result['on_time_days']},
            },
            'strengths': strengths,
            'weaknesses': weaknesses,
            'suggestions': suggestions,
            'trend': trend,
        }), 200
    except Exception as e:
        return jsonify({'error': 'Failed to fetch insights', 'details': str(e)}), 500
