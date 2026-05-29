from flask import Blueprint, request, jsonify
from flask_jwt_extended import get_jwt_identity, get_jwt
from ..extensions import get_db
from ..middleware.auth_middleware import admin_required, employee_required
from bson import ObjectId
from datetime import datetime, timedelta

gamification_bp = Blueprint('gamification_bp', __name__)

BADGE_DEFINITIONS = {
    'perfect_attendance_7': {
        'name': 'Perfect Attendance',
        'description': '7 consecutive days of on-time attendance',
        'icon': '🏆',
        'points': 50,
    },
    'fast_completer': {
        'name': 'Fast Completer',
        'description': 'Completed 5+ tasks before their deadline',
        'icon': '⚡',
        'points': 40,
    },
    'no_late': {
        'name': 'Punctuality Star',
        'description': 'No late arrivals in 30 days',
        'icon': '⏰',
        'points': 30,
    },
    'top_performer': {
        'name': 'Top Performer',
        'description': 'Ranked #1 in productivity score',
        'icon': '🌟',
        'points': 100,
    },
    'task_master': {
        'name': 'Task Master',
        'description': 'Completed 20+ tasks in a month',
        'icon': '✅',
        'points': 60,
    },
}


def serialize_badge(badge):
    """Convert ObjectId and datetime for JSON."""
    badge['_id'] = str(badge['_id'])
    if badge.get('earned_at') and isinstance(badge['earned_at'], datetime):
        badge['earned_at'] = badge['earned_at'].isoformat() + 'Z'
    return badge


def _check_badges_for_employee(db, employee_id, employee_name):
    """
    Evaluate badge eligibility for a single employee and award new badges.
    Returns list of newly awarded badge types.
    """
    now = datetime.utcnow()
    today_str = now.strftime('%Y-%m-%d')
    thirty_days_ago = (now - timedelta(days=30)).strftime('%Y-%m-%d')
    seven_days_ago = (now - timedelta(days=7)).strftime('%Y-%m-%d')

    # Existing badges for this employee
    existing = set(
        b['badge'] for b in db.gamification.find({'employee_id': employee_id}, {'badge': 1})
    )

    newly_awarded = []

    # --- perfect_attendance_7 ---
    if 'perfect_attendance_7' not in existing:
        recent_att = list(db.attendance.find({
            'employee_id': employee_id,
            'date': {'$gte': seven_days_ago}
        }).sort('date', -1))
        if len(recent_att) >= 7 and all(not a.get('is_late', True) for a in recent_att[:7]):
            newly_awarded.append('perfect_attendance_7')

    # --- no_late ---
    if 'no_late' not in existing:
        month_att = list(db.attendance.find({
            'employee_id': employee_id,
            'date': {'$gte': thirty_days_ago}
        }))
        if len(month_att) >= 20:  # at least 20 working days
            late_count = sum(1 for a in month_att if a.get('is_late'))
            if late_count == 0:
                newly_awarded.append('no_late')

    # --- fast_completer ---
    if 'fast_completer' not in existing:
        completed_tasks = list(db.tasks.find({
            'assigned_to': employee_id,
            'status': 'completed',
            'completed_at': {'$exists': True},
            'due_date': {'$exists': True}
        }))
        early_count = 0
        for t in completed_tasks:
            due = t.get('due_date', '')
            completed = t.get('completed_at')
            if due and completed:
                completed_str = completed.strftime('%Y-%m-%d') if isinstance(completed, datetime) else str(completed)[:10]
                if completed_str <= due:
                    early_count += 1
        if early_count >= 5:
            newly_awarded.append('fast_completer')

    # --- task_master ---
    if 'task_master' not in existing:
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        month_completed = db.tasks.count_documents({
            'assigned_to': employee_id,
            'status': 'completed',
            'completed_at': {'$gte': month_start}
        })
        if month_completed >= 20:
            newly_awarded.append('task_master')

    # Insert newly awarded badges
    for badge_type in newly_awarded:
        badge_def = BADGE_DEFINITIONS[badge_type]
        db.gamification.insert_one({
            'employee_id': employee_id,
            'employee_name': employee_name,
            'badge': badge_type,
            'badge_name': badge_def['name'],
            'description': badge_def['description'],
            'icon': badge_def['icon'],
            'points': badge_def['points'],
            'earned_at': now,
        })

    return newly_awarded


# ---------------------------------------------------------------------------
# GET /leaderboard - Top employees by productivity score
# ---------------------------------------------------------------------------
@gamification_bp.route('/leaderboard', methods=['GET'])
@employee_required
def leaderboard():
    try:
        db = get_db()
        limit = min(int(request.args.get('limit', 20)), 50)

        # Aggregate total points per employee from gamification badges
        pipeline = [
            {'$group': {
                '_id': '$employee_id',
                'employee_name': {'$first': '$employee_name'},
                'total_points': {'$sum': '$points'},
                'badge_count': {'$sum': 1},
                'badges': {'$push': {
                    'badge': '$badge',
                    'badge_name': '$badge_name',
                    'icon': '$icon',
                    'earned_at': '$earned_at',
                }},
            }},
            {'$sort': {'total_points': -1}},
            {'$limit': limit},
        ]
        results = list(db.gamification.aggregate(pipeline))

        # Also pull productivity scores for combined ranking
        leaderboard_list = []
        for rank, doc in enumerate(results, start=1):
            emp_id = doc['_id']
            # Fetch productivity score if available
            prod = db.productivity.find_one({'employee_id': emp_id})
            productivity_score = prod.get('score', 0) if prod else 0

            # Serialize badge dates
            badges = []
            for b in doc.get('badges', []):
                if b.get('earned_at') and isinstance(b['earned_at'], datetime):
                    b['earned_at'] = b['earned_at'].isoformat() + 'Z'
                badges.append(b)

            leaderboard_list.append({
                'rank': rank,
                'employee_id': emp_id,
                'name': doc.get('employee_name', ''),
                'total_points': doc['total_points'],
                'badge_count': doc['badge_count'],
                'badges': badges,
                'productivity_score': productivity_score,
                'combined_score': round(doc['total_points'] + productivity_score, 2),
            })

        # Re-sort by combined score
        leaderboard_list.sort(key=lambda x: x['combined_score'], reverse=True)
        for i, entry in enumerate(leaderboard_list, start=1):
            entry['rank'] = i

        return jsonify({'leaderboard': leaderboard_list}), 200
    except Exception as e:
        return jsonify({'error': 'Failed to fetch leaderboard', 'details': str(e)}), 500


# ---------------------------------------------------------------------------
# GET /badges/<employee_id> - Get badges for employee
# ---------------------------------------------------------------------------
@gamification_bp.route('/badges/<employee_id>', methods=['GET'])
@employee_required
def get_badges(employee_id):
    try:
        db = get_db()
        badges = list(
            db.gamification.find({'employee_id': employee_id})
            .sort('earned_at', -1)
        )

        total_points = sum(b.get('points', 0) for b in badges)

        # Also list unearned badges
        earned_types = set(b['badge'] for b in badges)
        unearned = []
        for badge_type, badge_def in BADGE_DEFINITIONS.items():
            if badge_type not in earned_types:
                unearned.append({
                    'badge': badge_type,
                    'badge_name': badge_def['name'],
                    'description': badge_def['description'],
                    'icon': badge_def['icon'],
                    'points': badge_def['points'],
                    'earned': False,
                })

        return jsonify({
            'badges': [serialize_badge(b) for b in badges],
            'unearned': unearned,
            'total_points': total_points,
        }), 200
    except Exception as e:
        return jsonify({'error': 'Failed to fetch badges', 'details': str(e)}), 500


# ---------------------------------------------------------------------------
# POST /check-badges - Admin triggers badge check for all employees
# ---------------------------------------------------------------------------
@gamification_bp.route('/check-badges', methods=['POST'])
@admin_required
def check_badges():
    try:
        db = get_db()
        employees = list(db.employees.find({'is_active': True}, {'name': 1}))

        total_new = 0
        results = []

        for emp in employees:
            emp_id = str(emp['_id'])
            emp_name = emp.get('name', '')
            newly = _check_badges_for_employee(db, emp_id, emp_name)
            if newly:
                total_new += len(newly)
                results.append({'employee_id': emp_id, 'name': emp_name, 'new_badges': newly})

        # --- top_performer badge (needs all scores first) ---
        prod_scores = list(db.productivity.find().sort('score', -1).limit(1))
        if prod_scores:
            top_emp_id = prod_scores[0].get('employee_id')
            existing_top = db.gamification.find_one({'employee_id': top_emp_id, 'badge': 'top_performer'})
            if not existing_top and top_emp_id:
                emp = db.employees.find_one({'_id': ObjectId(top_emp_id)})
                badge_def = BADGE_DEFINITIONS['top_performer']
                db.gamification.insert_one({
                    'employee_id': top_emp_id,
                    'employee_name': emp.get('name', '') if emp else '',
                    'badge': 'top_performer',
                    'badge_name': badge_def['name'],
                    'description': badge_def['description'],
                    'icon': badge_def['icon'],
                    'points': badge_def['points'],
                    'earned_at': datetime.utcnow(),
                })
                total_new += 1
                results.append({'employee_id': top_emp_id, 'new_badges': ['top_performer']})

        return jsonify({
            'message': f'Badge check complete. {total_new} new badges awarded.',
            'total_new': total_new,
            'details': results,
        }), 200
    except Exception as e:
        return jsonify({'error': 'Badge check failed', 'details': str(e)}), 500
