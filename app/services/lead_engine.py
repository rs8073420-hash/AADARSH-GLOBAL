from datetime import datetime
from ..models.employee import EmployeeModel
from ..models.lead import LeadModel
from ..models.assignment_log import LeadAssignmentLogModel
from ..extensions import socketio

class LeadEngine:
    def __init__(self):
        self.employee_model = EmployeeModel()
        self.lead_model = LeadModel()
        self.assignment_log = LeadAssignmentLogModel()
        # In-memory counter for strict round robin across instances is tricky,
        # but since this is a lightweight app, we will assign by finding the active employee 
        # with the least number of active leads assigned to them. This provides natural load balancing.

    def assign_lead(self, lead_id, assigned_from="SYSTEM"):
        # Find active employees
        employees = self.employee_model.get_all({'is_active': True})
        if not employees:
            return None # Nobody to assign to

        # Filter out offline employees if we strictly want online only.
        # But maybe we just assign to active employees, preferring online.
        # Let's count current active leads per employee
        
        assigned_to_emp = None
        min_leads = float('inf')

        for emp in employees:
            # We can count leads in leads_master for this employee that are not closed/lost
            count = self.lead_model.count({
                'assigned_to': str(emp['_id']),
                'status': {'$nin': ['Closed', 'Lost']}
            })
            
            # Penalize offline employees by adding a weight, so they get leads only if online are overloaded
            weight = count if emp.get('is_online') else count + 100

            if weight < min_leads:
                min_leads = weight
                assigned_to_emp = str(emp['_id'])

        if assigned_to_emp:
            # Fetch lead to get priority and name
            lead = self.lead_model.collection.find_one({'_id': self.lead_model._get_object_id(lead_id)})
            lead_name = lead.get('name', 'Unknown') if lead else 'Unknown'
            priority = lead.get('priority', 'Medium') if lead else 'Medium'
            
            # Update lead
            self.lead_model.reassign(lead_id, assigned_to_emp, reason="Initial Assignment")
            # Log
            self.assignment_log.log_assignment(
                lead_id, assigned_to_emp, assigned_from=assigned_from, 
                reassigned=(assigned_from != "SYSTEM" and assigned_from != "MANUAL_CREATE"), 
                lead_name=lead_name, priority=priority
            )
            
            # Trigger realtime event
            from ..routes.notifications import create_notification
            create_notification(assigned_to_emp, 'info', 'New Lead Assigned', f'You have been assigned lead: {lead_name}', '/employee/leads')

        return assigned_to_emp

    def check_and_reassign_stale_leads(self):
        # Called every minute by background worker
        now = datetime.utcnow()
        
        # Only check leads where auto_reassign is True
        stale_leads = self.lead_model.collection.find({
            'auto_reassign': True,
            'status': 'New', # Only if they haven't updated status
            'reassigned_count': {'$lt': 3} # Limit to 3 reassignments max
        })

        count = 0
        for lead in stale_leads:
            # Skip if Low priority or interval is 0
            if lead.get('priority') == 'Low' or lead.get('reassign_interval_minutes', 0) == 0:
                continue
                
            interval = lead.get('reassign_interval_minutes', 1440)
            assigned_at = lead.get('assigned_at')
            if not assigned_at:
                continue
                
            elapsed_minutes = (now - assigned_at).total_seconds() / 60.0
            
            if elapsed_minutes >= interval:
                lead_id = str(lead['_id'])
                
                # Check if it was updated at all recently
                last_updated = lead.get('last_updated_at', lead.get('created_at'))
                if (now - last_updated).total_seconds() / 60.0 < interval:
                    continue # they had some activity
                
                # Verify in logs if employee responded
                latest_log = self.assignment_log.collection.find_one(
                    {'lead_id': lead_id},
                    sort=[('assigned_at', -1)]
                )
                
                if latest_log and not latest_log.get('updated_by_employee'):
                    # Reassign
                    old_emp = lead.get('assigned_to')
                    new_emp = self.assign_lead(lead_id, assigned_from="AUTO_SYSTEM")
                    if new_emp and new_emp != old_emp:
                        count += 1
                        socketio.emit('new_notification', {
                            'title': 'High Priority Reassignment', 
                            'message': f'Lead was reassigned after {interval} mins of inactivity.'
                        }, room='admin')
        return count
