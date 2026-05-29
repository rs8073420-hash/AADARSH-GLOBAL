from flask import Blueprint, jsonify
from flask_jwt_extended import get_jwt_identity, get_jwt
from ..extensions import get_db
from ..middleware.auth_middleware import admin_required, employee_required
from bson import ObjectId
from datetime import datetime, timedelta
import subprocess
import json

ai_bp = Blueprint('ai_bp', __name__)

OLLAMA_MODEL = 'llama3'
OLLAMA_TIMEOUT = 30  # seconds


def _call_ollama(prompt):
    """
    Try to call Ollama CLI. Returns the response text or None on failure.
    """
    try:
        result = subprocess.run(
            ['ollama', 'run', OLLAMA_MODEL, prompt],
            capture_output=True,
            text=True,
            timeout=OLLAMA_TIMEOUT
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
        pass
    return None


def _get_employee_data(db, employee_id):
    """Gather data about an employee for summary generation."""
    now = datetime.utcnow()
    thirty_days_ago = (now - timedelta(days=30)).strftime('%Y-%m-%d')

    emp = db.employees.find_one({'_id': ObjectId(employee_id)}, {
        'name': 1, 'department': 1, 'designation': 1, 'employee_id': 1
    })
    if not emp:
        return None

    # Attendance
    attendances = list(db.attendance.find({
        'employee_id': employee_id,
        'date': {'$gte': thirty_days_ago}
    }))
    present_days = len(attendances)
    total_hours = round(sum(a.get('working_hours', 0) for a in attendances), 2)
    late_days = sum(1 for a in attendances if a.get('is_late'))

    # Tasks
    tasks = list(db.tasks.find({'assigned_to': employee_id}))
    recent_tasks = [t for t in tasks if t.get('created_at') and t['created_at'] >= now - timedelta(days=30)]
    total_tasks = len(recent_tasks)
    completed = sum(1 for t in recent_tasks if t.get('status') in ('completed', 'approved'))
    pending = sum(1 for t in recent_tasks if t.get('status') in ('assigned', 'in_progress'))
    overdue = sum(1 for t in recent_tasks if t.get('due_date') and t['due_date'] < now.strftime('%Y-%m-%d') and t.get('status') not in ('completed', 'approved'))

    # Productivity score
    prod = db.productivity.find_one({'employee_id': employee_id})
    score = prod.get('score', 0) if prod else 0

    return {
        'name': emp.get('name', ''),
        'employee_code': emp.get('employee_id', ''),
        'department': emp.get('department', ''),
        'designation': emp.get('designation', ''),
        'present_days': present_days,
        'total_hours': total_hours,
        'late_days': late_days,
        'total_tasks': total_tasks,
        'completed_tasks': completed,
        'pending_tasks': pending,
        'overdue_tasks': overdue,
        'productivity_score': score,
    }


def _generate_fallback_summary(data):
    """Generate a data-driven summary without AI."""
    name = data['name']
    lines = [f"**Performance Summary for {name}** (Last 30 days)"]
    lines.append('')

    # Attendance
    lines.append(f"📅 **Attendance**: {data['present_days']} days present, {data['late_days']} late arrivals")
    lines.append(f"⏱️ **Total Work Hours**: {data['total_hours']} hours")

    avg_hours = round(data['total_hours'] / max(data['present_days'], 1), 1)
    lines.append(f"📊 **Avg Daily Hours**: {avg_hours} hours")

    # Tasks
    lines.append(f"📋 **Tasks**: {data['completed_tasks']}/{data['total_tasks']} completed")
    if data['overdue_tasks'] > 0:
        lines.append(f"⚠️ **Overdue Tasks**: {data['overdue_tasks']}")
    if data['pending_tasks'] > 0:
        lines.append(f"🔄 **Pending Tasks**: {data['pending_tasks']}")

    # Score
    lines.append(f"🏆 **Productivity Score**: {data['productivity_score']}/100")

    # Assessment
    score = data['productivity_score']
    if score >= 80:
        lines.append("\n✅ **Overall**: Excellent performer. Consistently meeting targets.")
    elif score >= 60:
        lines.append("\n👍 **Overall**: Good performance with room for improvement.")
    elif score >= 40:
        lines.append("\n⚡ **Overall**: Average performance. Focus areas identified.")
    else:
        lines.append("\n🔴 **Overall**: Needs improvement. Recommend closer monitoring.")

    return '\n'.join(lines)


def _generate_fallback_task_suggestions(data):
    """Generate task suggestions from data without AI."""
    suggestions = []

    if data['overdue_tasks'] > 0:
        suggestions.append({
            'priority': 'high',
            'suggestion': f'Complete {data["overdue_tasks"]} overdue task(s) immediately',
            'reason': 'Overdue tasks negatively impact productivity score'
        })

    if data['late_days'] > 3:
        suggestions.append({
            'priority': 'medium',
            'suggestion': 'Improve punctuality — set morning reminders',
            'reason': f'{data["late_days"]} late arrivals in 30 days'
        })

    if data['total_hours'] / max(data['present_days'], 1) < 7:
        suggestions.append({
            'priority': 'medium',
            'suggestion': 'Increase daily work hours to meet 8-hour target',
            'reason': f'Averaging only {round(data["total_hours"] / max(data["present_days"], 1), 1)} hours/day'
        })

    completion_rate = data['completed_tasks'] / max(data['total_tasks'], 1)
    if completion_rate < 0.7:
        suggestions.append({
            'priority': 'high',
            'suggestion': 'Focus on task completion rate',
            'reason': f'Only {round(completion_rate * 100)}% tasks completed'
        })

    if data['pending_tasks'] > 5:
        suggestions.append({
            'priority': 'medium',
            'suggestion': 'Prioritize and clear pending task backlog',
            'reason': f'{data["pending_tasks"]} tasks pending'
        })

    if not suggestions:
        suggestions.append({
            'priority': 'low',
            'suggestion': 'Maintain current performance and mentor peers',
            'reason': 'All metrics are healthy'
        })

    return suggestions


# ---------------------------------------------------------------------------
# GET /summary/<employee_id> - AI summary for employee
# ---------------------------------------------------------------------------
@ai_bp.route('/summary/<employee_id>', methods=['GET'])
@employee_required
def get_summary(employee_id):
    try:
        identity = get_jwt_identity()
        claims = get_jwt()

        if claims.get('role') != 'admin' and identity != employee_id:
            return jsonify({'error': 'Not authorized'}), 403

        db = get_db()
        data = _get_employee_data(db, employee_id)
        if not data:
            return jsonify({'error': 'Employee not found'}), 404

        # Try AI first
        prompt = (
            f"Summarize this employee's performance in 3-4 sentences: "
            f"Name: {data['name']}, Dept: {data['department']}, "
            f"Present days: {data['present_days']}/30, Late: {data['late_days']}, "
            f"Work hours: {data['total_hours']}h, "
            f"Tasks completed: {data['completed_tasks']}/{data['total_tasks']}, "
            f"Overdue: {data['overdue_tasks']}, Score: {data['productivity_score']}/100"
        )
        ai_response = _call_ollama(prompt)

        if ai_response:
            return jsonify({
                'employee_id': employee_id,
                'employee_name': data['name'],
                'summary': ai_response,
                'source': 'ai',
                'data': data,
            }), 200
        else:
            summary = _generate_fallback_summary(data)
            return jsonify({
                'employee_id': employee_id,
                'employee_name': data['name'],
                'summary': summary,
                'source': 'data',
                'data': data,
            }), 200
    except Exception as e:
        return jsonify({'error': 'Failed to generate summary', 'details': str(e)}), 500


# ---------------------------------------------------------------------------
# GET /company-summary - Company-wide AI summary
# ---------------------------------------------------------------------------
@ai_bp.route('/company-summary', methods=['GET'])
@admin_required
def company_summary():
    try:
        db = get_db()
        now = datetime.utcnow()
        thirty_days_ago = (now - timedelta(days=30)).strftime('%Y-%m-%d')
        today_str = now.strftime('%Y-%m-%d')

        # Gather company-wide stats
        total_employees = db.employees.count_documents({'is_active': True})

        # Today's attendance
        today_present = db.attendance.count_documents({'date': today_str})
        today_late = db.attendance.count_documents({'date': today_str, 'is_late': True})

        # Tasks last 30 days
        month_start = now - timedelta(days=30)
        total_tasks = db.tasks.count_documents({'created_at': {'$gte': month_start}})
        completed_tasks = db.tasks.count_documents({'status': {'$in': ['completed', 'approved']}, 'created_at': {'$gte': month_start}})
        overdue_tasks = db.tasks.count_documents({
            'due_date': {'$lt': today_str},
            'status': {'$nin': ['completed', 'approved', 'cancelled']}
        })

        # Leads
        total_leads = db.leads.count_documents({})
        new_leads = db.leads.count_documents({'created_at': {'$gte': month_start}})
        closed_leads = db.leads.count_documents({'status': 'Closed'})

        # Average productivity
        prod_scores = list(db.productivity.find({}, {'score': 1}))
        avg_score = round(sum(p.get('score', 0) for p in prod_scores) / max(len(prod_scores), 1), 2)

        company_data = {
            'total_employees': total_employees,
            'today_present': today_present,
            'today_absent': total_employees - today_present,
            'today_late': today_late,
            'total_tasks_30d': total_tasks,
            'completed_tasks_30d': completed_tasks,
            'overdue_tasks': overdue_tasks,
            'total_leads': total_leads,
            'new_leads_30d': new_leads,
            'closed_leads': closed_leads,
            'avg_productivity': avg_score,
        }

        # Try AI
        prompt = (
            f"Give a brief company performance overview: "
            f"{total_employees} employees, {today_present} present today ({today_late} late), "
            f"{completed_tasks}/{total_tasks} tasks completed (30d), {overdue_tasks} overdue, "
            f"{new_leads} new leads, {closed_leads} deals closed, avg productivity {avg_score}/100"
        )
        ai_response = _call_ollama(prompt)

        if ai_response:
            summary = ai_response
            source = 'ai'
        else:
            lines = ["**Company Performance Overview** (Last 30 days)", ""]
            lines.append(f"👥 **Team**: {total_employees} active employees")
            lines.append(f"📅 **Today**: {today_present} present, {total_employees - today_present} absent, {today_late} late")
            lines.append(f"📋 **Tasks**: {completed_tasks}/{total_tasks} completed, {overdue_tasks} overdue")
            lines.append(f"💼 **Leads**: {new_leads} new, {closed_leads} closed, {total_leads} total")
            lines.append(f"📊 **Avg Productivity**: {avg_score}/100")

            if avg_score >= 70:
                lines.append("\n✅ Company is performing well overall.")
            elif avg_score >= 50:
                lines.append("\n👍 Moderate performance. Some areas need attention.")
            else:
                lines.append("\n⚠️ Performance needs significant improvement.")

            summary = '\n'.join(lines)
            source = 'data'

        return jsonify({
            'summary': summary,
            'source': source,
            'data': company_data,
        }), 200
    except Exception as e:
        return jsonify({'error': 'Failed to generate company summary', 'details': str(e)}), 500


# ---------------------------------------------------------------------------
# GET /task-suggestions/<employee_id> - AI task suggestions
# ---------------------------------------------------------------------------
@ai_bp.route('/task-suggestions/<employee_id>', methods=['GET'])
@employee_required
def task_suggestions(employee_id):
    try:
        identity = get_jwt_identity()
        claims = get_jwt()

        if claims.get('role') != 'admin' and identity != employee_id:
            return jsonify({'error': 'Not authorized'}), 403

        db = get_db()
        data = _get_employee_data(db, employee_id)
        if not data:
            return jsonify({'error': 'Employee not found'}), 404

        # Try AI
        prompt = (
            f"Give 3-5 actionable task suggestions for this employee: "
            f"{data['name']}, {data['completed_tasks']}/{data['total_tasks']} tasks done, "
            f"{data['overdue_tasks']} overdue, {data['late_days']} late days, "
            f"score {data['productivity_score']}/100. Return as numbered list."
        )
        ai_response = _call_ollama(prompt)

        if ai_response:
            return jsonify({
                'employee_id': employee_id,
                'employee_name': data['name'],
                'suggestions_text': ai_response,
                'source': 'ai',
            }), 200
        else:
            suggestions = _generate_fallback_task_suggestions(data)
            return jsonify({
                'employee_id': employee_id,
                'employee_name': data['name'],
                'suggestions': suggestions,
                'source': 'data',
            }), 200
    except Exception as e:
        return jsonify({'error': 'Failed to generate suggestions', 'details': str(e)}), 500


# ---------------------------------------------------------------------------
# GET /risk-alerts - Attendance risk predictions
# ---------------------------------------------------------------------------
@ai_bp.route('/risk-alerts', methods=['GET'])
@admin_required
def risk_alerts():
    try:
        db = get_db()
        now = datetime.utcnow()
        fourteen_days_ago = (now - timedelta(days=14)).strftime('%Y-%m-%d')
        today_str = now.strftime('%Y-%m-%d')

        employees = list(db.employees.find({'is_active': True}, {'name': 1, 'department': 1}))
        alerts = []

        for emp in employees:
            emp_id = str(emp['_id'])
            emp_name = emp.get('name', '')

            # Last 14 days attendance
            recent_att = list(db.attendance.find({
                'employee_id': emp_id,
                'date': {'$gte': fourteen_days_ago, '$lte': today_str}
            }))
            present_days = len(recent_att)
            late_days = sum(1 for a in recent_att if a.get('is_late'))
            early_exits = sum(1 for a in recent_att if a.get('early_exit'))

            risk_level = 'low'
            risk_reasons = []

            # Risk: Low attendance
            if present_days < 7:  # less than 50% in 14 days
                risk_level = 'high'
                risk_reasons.append(f'Only {present_days}/14 days present')

            # Risk: Frequent late
            if late_days >= 5:
                risk_level = 'high' if risk_level != 'high' else risk_level
                risk_reasons.append(f'{late_days} late arrivals in 14 days')
            elif late_days >= 3:
                if risk_level == 'low':
                    risk_level = 'medium'
                risk_reasons.append(f'{late_days} late arrivals in 14 days')

            # Risk: Early exits
            if early_exits >= 4:
                if risk_level == 'low':
                    risk_level = 'medium'
                risk_reasons.append(f'{early_exits} early exits in 14 days')

            # Risk: declining pattern (compare last 7 to previous 7)
            seven_days_ago = (now - timedelta(days=7)).strftime('%Y-%m-%d')
            recent_7 = sum(1 for a in recent_att if a.get('date', '') >= seven_days_ago)
            older_7 = present_days - recent_7
            if older_7 > 0 and recent_7 < older_7 - 2:
                if risk_level == 'low':
                    risk_level = 'medium'
                risk_reasons.append('Declining attendance pattern')

            if risk_reasons:
                alerts.append({
                    'employee_id': emp_id,
                    'name': emp_name,
                    'department': emp.get('department', ''),
                    'risk_level': risk_level,
                    'reasons': risk_reasons,
                    'present_days_14': present_days,
                    'late_days_14': late_days,
                })

        # Sort by risk level: high > medium > low
        risk_order = {'high': 0, 'medium': 1, 'low': 2}
        alerts.sort(key=lambda x: risk_order.get(x['risk_level'], 3))

        return jsonify({
            'alerts': alerts,
            'total': len(alerts),
            'high_risk': sum(1 for a in alerts if a['risk_level'] == 'high'),
            'medium_risk': sum(1 for a in alerts if a['risk_level'] == 'medium'),
        }), 200
    except Exception as e:
        return jsonify({'error': 'Failed to generate risk alerts', 'details': str(e)}), 500
