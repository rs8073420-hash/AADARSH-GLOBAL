from flask import Blueprint, request, jsonify
from flask_jwt_extended import get_jwt_identity, get_jwt
from ..extensions import get_db
from ..middleware.auth_middleware import admin_required
import pymongo

automation_bp = Blueprint('automation_bp', __name__)

@automation_bp.route('/logs', methods=['GET'])
@admin_required
def get_automation_logs():
    try:
        page = max(int(request.args.get('page', 1)), 1)
        limit = min(int(request.args.get('limit', 20)), 100)
        skip = limit * (page - 1)
        
        filters = {}
        
        priority = request.args.get('priority')
        if priority:
            filters['priority'] = priority
            
        action_type = request.args.get('action_type')
        if action_type:
            if action_type == 'Reassignment':
                filters['reassigned'] = True
            elif action_type == 'Initial':
                filters['reassigned'] = False

        db = get_db()
        total = db.lead_assignment_logs.count_documents(filters)
        
        logs = list(
            db.lead_assignment_logs.find(filters)
            .sort('assigned_at', pymongo.DESCENDING)
            .skip(skip)
            .limit(limit)
        )
        
        # Fetch employee names for better UI display
        emp_ids = set()
        for log in logs:
            if log.get('assigned_from') and log['assigned_from'] not in ['SYSTEM', 'MANUAL_CREATE', 'AUTO_SYSTEM']:
                emp_ids.add(log['assigned_from'])
            if log.get('assigned_to'):
                emp_ids.add(log['assigned_to'])
                
        # Get emp details
        from bson import ObjectId
        valid_emp_ids = [ObjectId(eid) for eid in emp_ids if len(eid) == 24]
        employees = {str(emp['_id']): emp['name'] for emp in db.employees.find({'_id': {'$in': valid_emp_ids}})}
        
        formatted_logs = []
        for log in logs:
            log['_id'] = str(log['_id'])
            log['lead_id'] = str(log.get('lead_id', ''))
            
            # Format names
            af = log.get('assigned_from', 'SYSTEM')
            at = log.get('assigned_to', '')
            log['assigned_from_name'] = employees.get(af, af)
            log['assigned_to_name'] = employees.get(at, 'Unknown')
            
            # Serialize datetime
            if log.get('assigned_at'):
                log['assigned_at'] = log['assigned_at'].isoformat() + 'Z'
                
            formatted_logs.append(log)
            
        return jsonify({
            'logs': formatted_logs,
            'total': total,
            'page': page,
            'limit': limit,
            'pages': (total + limit - 1) // limit
        }), 200
        
    except Exception as e:
        return jsonify({'error': 'Failed to fetch automation logs', 'details': str(e)}), 500
