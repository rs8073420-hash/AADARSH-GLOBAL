from flask import Blueprint, request, jsonify
from flask_jwt_extended import get_jwt_identity, get_jwt
from ..extensions import get_db, socketio
from ..middleware.auth_middleware import admin_required, employee_required
from bson import ObjectId
from datetime import datetime
import csv
import io

lead_bp = Blueprint('lead_bp', __name__)

LEAD_STATUSES = ['New', 'Contacted', 'Interested', 'Site Visit', 'Negotiation', 'Closed']


def serialize_lead(lead):
    """Convert ObjectId and datetime fields for JSON serialization."""
    lead['_id'] = str(lead['_id'])
    for field in ('created_at', 'updated_at', 'assigned_at'):
        if lead.get(field) and isinstance(lead[field], datetime):
            lead[field] = lead[field].isoformat() + 'Z'
    return lead


# ---------------------------------------------------------------------------
# GET / - List leads with pagination & filters
# ---------------------------------------------------------------------------
@lead_bp.route('/', methods=['GET'])
@employee_required
def get_leads():
    try:
        page = max(int(request.args.get('page', 1)), 1)
        limit = min(int(request.args.get('limit', 20)), 100)
        skip = limit * (page - 1)

        filters = {}

        identity = get_jwt_identity()
        claims = get_jwt()
        
        # If employee, force assigned_to filter to their own ID
        if claims.get('role') == 'employee':
            filters['assigned_to'] = identity
        else:
            # Admin can filter by assigned_to
            assigned_to = request.args.get('assigned_to')
            if assigned_to:
                filters['assigned_to'] = assigned_to

        status = request.args.get('status')
        if status and status in LEAD_STATUSES:
            filters['status'] = status


        source = request.args.get('source')
        if source:
            filters['source'] = source

        search = request.args.get('search', '').strip()
        if search:
            filters['$or'] = [
                {'name': {'$regex': search, '$options': 'i'}},
                {'phone': {'$regex': search, '$options': 'i'}},
                {'email': {'$regex': search, '$options': 'i'}},
                {'city': {'$regex': search, '$options': 'i'}},
            ]

        db = get_db()
        total = db.leads_master.count_documents(filters)
        leads = list(
            db.leads_master.find(filters)
            .sort('created_at', -1)
            .skip(skip)
            .limit(limit)
        )

        return jsonify({
            'leads': [serialize_lead(l) for l in leads],
            'total': total,
            'page': page,
            'limit': limit,
            'pages': (total + limit - 1) // limit
        }), 200
    except Exception as e:
        return jsonify({'error': 'Failed to fetch leads', 'details': str(e)}), 500


# ---------------------------------------------------------------------------
# POST / - Create single lead (with duplicate phone detection)
# ---------------------------------------------------------------------------
@lead_bp.route('/', methods=['POST'])
@admin_required
def create_lead():
    try:
        data = request.get_json() or {}
        if not data.get('name') or not data.get('phone'):
            return jsonify({'error': 'Name and phone are required'}), 400

        if data.get('status') and data['status'] not in LEAD_STATUSES:
            return jsonify({'error': f'Invalid status. Must be one of: {", ".join(LEAD_STATUSES)}'}), 400

        db = get_db()

        # Duplicate phone detection
        existing = db.leads_master.find_one({'phone': data['phone']})
        if existing:
            return jsonify({
                'error': 'duplicate_phone',
                'message': f'A lead with phone {data["phone"]} already exists',
                'existing_lead_id': str(existing['_id'])
            }), 409

        identity = get_jwt_identity()
        claims = get_jwt()

        lead = {
            'name': data.get('name', ''),
            'phone': data.get('phone', ''),
            'email': data.get('email', ''),
            'city': data.get('city', ''),
            'budget': data.get('budget', ''),
            'source': data.get('source', ''),
            'notes': data.get('notes', ''),
            'priority': data.get('priority', 'Medium'),
            'auto_reassign': data.get('auto_reassign', True),
            'assigned_to': data.get('assigned_to', ''),
            'assigned_to_name': data.get('assigned_to_name', ''),
            'status': data.get('status', 'New'),
            'created_by': identity,
            'created_by_name': claims.get('name', 'Admin'),
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow(),
            'assigned_at': datetime.utcnow() if data.get('assigned_to') else None,
            'last_updated_at': datetime.utcnow(),
            'reassigned_count': 0
        }
        
        # Determine interval based on priority
        interval_map = {'High': 30, 'Medium': 1440, 'Low': 0}
        lead['reassign_interval_minutes'] = interval_map.get(lead['priority'], 1440)

        result = db.leads_master.insert_one(lead)
        lead_id = str(result.inserted_id)
        
        # Round Robin Assignment if unassigned
        if not lead.get('assigned_to'):
            from app.services.lead_engine import LeadEngine
            LeadEngine().assign_lead(lead_id, assigned_from="MANUAL_CREATE")
        else:
            from app.models.assignment_log import LeadAssignmentLogModel
            LeadAssignmentLogModel().log_assignment(
                lead_id, lead['assigned_to'], assigned_from="ADMIN", 
                reassigned=False, lead_name=lead['name'], priority=lead['priority']
            )

        # Emit socket event
        lead['_id'] = lead_id
        socketio.emit('lead_created', serialize_lead(lead.copy()), room='admin')

        return jsonify({'message': 'Lead created', 'id': lead_id}), 201
    except Exception as e:
        return jsonify({'error': 'Failed to create lead', 'details': str(e)}), 500


# ---------------------------------------------------------------------------
# POST /bulk - Bulk CSV import
# ---------------------------------------------------------------------------
@lead_bp.route('/bulk', methods=['POST'])
@admin_required
def bulk_import():
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No CSV file uploaded'}), 400

        file = request.files['file']
        if not file.filename or not file.filename.lower().endswith('.csv'):
            return jsonify({'error': 'Only CSV files are accepted'}), 400

        identity = get_jwt_identity()
        claims = get_jwt()
        db = get_db()

        stream = io.StringIO(file.stream.read().decode('utf-8-sig'))
        reader = csv.DictReader(stream)

        imported = 0
        skipped = 0
        errors = []

        for idx, row in enumerate(reader, start=2):  # row 1 is header
            name = (row.get('name') or row.get('Name') or '').strip()
            phone = (row.get('phone') or row.get('Phone') or row.get('mobile') or row.get('Mobile') or '').strip()

            if not name or not phone:
                errors.append(f'Row {idx}: Missing name or phone')
                skipped += 1
                continue

            # Skip duplicates
            if db.leads_master.find_one({'phone': phone}):
                skipped += 1
                continue

            status = (row.get('status') or row.get('Status') or 'New').strip()
            if status not in LEAD_STATUSES:
                status = 'New'

            lead = {
                'name': name,
                'phone': phone,
                'email': (row.get('email') or row.get('Email') or '').strip(),
                'city': (row.get('city') or row.get('City') or '').strip(),
                'budget': (row.get('budget') or row.get('Budget') or '').strip(),
                'source': (row.get('source') or row.get('Source') or 'CSV Import').strip(),
                'notes': (row.get('notes') or row.get('Notes') or '').strip(),
                'priority': (row.get('priority') or row.get('Priority') or 'Medium').strip(),
                'auto_reassign': str(row.get('auto_reassign') or row.get('Auto_Reassign') or 'true').lower() in ('true', '1', 'yes'),
                'assigned_to': (row.get('assigned_to') or '').strip(),
                'assigned_to_name': '',
                'status': status,
                'created_by': identity,
                'created_by_name': claims.get('name', 'Admin'),
                'created_at': datetime.utcnow(),
                'updated_at': datetime.utcnow(),
                'assigned_at': datetime.utcnow() if (row.get('assigned_to') or '').strip() else None,
                'last_updated_at': datetime.utcnow(),
                'reassigned_count': 0
            }
            
            interval_map = {'High': 30, 'Medium': 1440, 'Low': 0}
            lead['reassign_interval_minutes'] = interval_map.get(lead['priority'], 1440)
            res = db.leads_master.insert_one(lead)
            lead_id = str(res.inserted_id)
            
            if not lead.get('assigned_to'):
                from app.services.lead_engine import LeadEngine
                LeadEngine().assign_lead(lead_id, assigned_from="CSV_IMPORT")
                
            imported += 1

        socketio.emit('leads_bulk_imported', {'count': imported}, room='admin')

        return jsonify({
            'message': f'Bulk import complete',
            'imported': imported,
            'skipped': skipped,
            'errors': errors[:20]  # cap error messages
        }), 201
    except Exception as e:
        return jsonify({'error': 'Bulk import failed', 'details': str(e)}), 500


# ---------------------------------------------------------------------------
# PUT /<lead_id> - Update lead
# ---------------------------------------------------------------------------
@lead_bp.route('/<lead_id>', methods=['PUT'])
@employee_required
def update_lead(lead_id):
    try:
        db = get_db()
        lead = db.leads_master.find_one({'_id': ObjectId(lead_id)})
        if not lead:
            return jsonify({'error': 'Lead not found'}), 404

        identity = get_jwt_identity()
        claims = get_jwt()
        if claims.get('role') == 'employee' and lead.get('assigned_to') != identity:
            return jsonify({'error': 'You can only update leads assigned to you'}), 403


        data = request.get_json() or {}
        if data.get('status') and data['status'] not in LEAD_STATUSES:
            return jsonify({'error': f'Invalid status. Must be one of: {", ".join(LEAD_STATUSES)}'}), 400

        # Prevent changing phone to a duplicate
        if data.get('phone') and data['phone'] != lead.get('phone'):
            existing = db.leads_master.find_one({'phone': data['phone'], '_id': {'$ne': ObjectId(lead_id)}})
            if existing:
                return jsonify({'error': 'Another lead with this phone already exists'}), 409

        data['updated_at'] = datetime.utcnow()
        data['last_updated_at'] = datetime.utcnow()
        
        # If priority was changed, update interval
        if 'priority' in data:
            interval_map = {'High': 30, 'Medium': 1440, 'Low': 0}
            data['reassign_interval_minutes'] = interval_map.get(data['priority'], 1440)
            
        db.leads_master.update_one({'_id': ObjectId(lead_id)}, {'$set': data})

        if claims.get('role') == 'employee':
            from app.models.assignment_log import LeadAssignmentLogModel
            LeadAssignmentLogModel().mark_employee_response(lead_id, identity)

        socketio.emit('lead_updated', {'lead_id': lead_id}, room='admin')

        return jsonify({'message': 'Lead updated'}), 200
    except Exception as e:
        return jsonify({'error': 'Failed to update lead', 'details': str(e)}), 500


# ---------------------------------------------------------------------------
# DELETE /<lead_id> - Delete lead
# ---------------------------------------------------------------------------
@lead_bp.route('/<lead_id>', methods=['DELETE'])
@admin_required
def delete_lead(lead_id):
    try:
        db = get_db()
        result = db.leads_master.delete_one({'_id': ObjectId(lead_id)})
        if result.deleted_count == 0:
            return jsonify({'error': 'Lead not found'}), 404
        return jsonify({'message': 'Lead deleted'}), 200
    except Exception as e:
        return jsonify({'error': 'Failed to delete lead', 'details': str(e)}), 500


# ---------------------------------------------------------------------------
# POST /<lead_id>/assign - Assign lead to employee
# ---------------------------------------------------------------------------
@lead_bp.route('/<lead_id>/assign', methods=['POST'])
@admin_required
def assign_lead(lead_id):
    try:
        data = request.get_json() or {}
        assigned_to = data.get('assigned_to')
        assigned_to_name = data.get('assigned_to_name', '')

        if not assigned_to:
            return jsonify({'error': 'assigned_to is required'}), 400

        db = get_db()
        lead = db.leads_master.find_one({'_id': ObjectId(lead_id)})
        if not lead:
            return jsonify({'error': 'Lead not found'}), 404

        # If name not provided, look it up
        if not assigned_to_name:
            emp = db.employees.find_one({'_id': ObjectId(assigned_to)})
            if emp:
                assigned_to_name = emp.get('name', '')

        db.leads_master.update_one(
            {'_id': ObjectId(lead_id)},
            {'$set': {
                'assigned_to': assigned_to,
                'assigned_to_name': assigned_to_name,
                'assigned_at': datetime.utcnow(),
                'updated_at': datetime.utcnow(),
            }}
        )

        socketio.emit('lead_assigned', {
            'lead_id': lead_id,
            'lead_name': lead.get('name', ''),
            'assigned_to': assigned_to,
            'assigned_to_name': assigned_to_name,
        }, room='admin')

        # Also notify the assigned employee
        from .notifications import create_notification
        create_notification(assigned_to, 'info', 'Lead Assigned', f'You have been assigned lead: {lead.get("name", "")}', '/employee/leads')

        return jsonify({'message': 'Lead assigned successfully'}), 200
    except Exception as e:
        return jsonify({'error': 'Failed to assign lead', 'details': str(e)}), 500


# ---------------------------------------------------------------------------
# GET /pipeline - Lead counts by status for pipeline view
# ---------------------------------------------------------------------------
@lead_bp.route('/pipeline', methods=['GET'])
@admin_required
def get_pipeline():
    try:
        db = get_db()
        pipeline = db.leads_master.aggregate([
            {'$group': {'_id': '$status', 'count': {'$sum': 1}}},
            {'$sort': {'_id': 1}}
        ])

        result = {status: 0 for status in LEAD_STATUSES}
        for doc in pipeline:
            if doc['_id'] in result:
                result[doc['_id']] = doc['count']

        # Also provide leads grouped by status for pipeline cards
        pipeline_leads = {}
        for status in LEAD_STATUSES:
            leads = list(
                db.leads_master.find({'status': status})
                .sort('updated_at', -1)
                .limit(50)
            )
            pipeline_leads[status] = [serialize_lead(l) for l in leads]

        return jsonify({
            'counts': result,
            'total': sum(result.values()),
            'pipeline': pipeline_leads
        }), 200
    except Exception as e:
        return jsonify({'error': 'Failed to fetch pipeline', 'details': str(e)}), 500


# ---------------------------------------------------------------------------
# GET /stats - Lead statistics
# ---------------------------------------------------------------------------
@lead_bp.route('/stats', methods=['GET'])
@admin_required
def get_stats():
    try:
        db = get_db()
        total = db.leads_master.count_documents({})

        # By status
        by_status_cursor = db.leads_master.aggregate([
            {'$group': {'_id': '$status', 'count': {'$sum': 1}}}
        ])
        by_status = {doc['_id']: doc['count'] for doc in by_status_cursor}

        # By source
        by_source_cursor = db.leads_master.aggregate([
            {'$group': {'_id': '$source', 'count': {'$sum': 1}}},
            {'$sort': {'count': -1}}
        ])
        by_source = {doc['_id']: doc['count'] for doc in by_source_cursor if doc['_id']}

        # By assigned employee
        by_employee_cursor = db.leads_master.aggregate([
            {'$match': {'assigned_to': {'$ne': ''}}},
            {'$group': {'_id': '$assigned_to', 'name': {'$first': '$assigned_to_name'}, 'count': {'$sum': 1}}},
            {'$sort': {'count': -1}}
        ])
        by_employee = [{'employee_id': doc['_id'], 'name': doc.get('name', ''), 'count': doc['count']}
                       for doc in by_employee_cursor]

        # Recent leads (last 7 days)
        from datetime import timedelta
        week_ago = datetime.utcnow() - timedelta(days=7)
        recent_count = db.leads_master.count_documents({'created_at': {'$gte': week_ago}})

        # Conversion rate
        closed_count = by_status.get('Closed', 0)
        conversion_rate = round((closed_count / total * 100), 2) if total > 0 else 0

        return jsonify({
            'total': total,
            'by_status': by_status,
            'by_source': by_source,
            'by_employee': by_employee,
            'recent_7_days': recent_count,
            'conversion_rate': conversion_rate,
        }), 200
    except Exception as e:
        return jsonify({'error': 'Failed to fetch stats', 'details': str(e)}), 500
