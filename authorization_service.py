from google.cloud import bigquery
from datetime import datetime, timedelta, date
try:
    from .member_lookup_service import MemberLookupService
except ImportError:
    from member_lookup_service import MemberLookupService

class AuthorizationService:
    def __init__(self, dataset_id='humana_hackathon'):
        self.client = bigquery.Client()
        self.dataset_id = dataset_id
        self.lookup_service = MemberLookupService(dataset_id=dataset_id)

    def validate_caller(self, identity_data: dict):
        """
        Validates if the caller is authorized.
        identity_data expects: caller_type, caller_name, member_name
        """
        caller_type = identity_data.get('caller_type', '').lower()
        caller_name = identity_data.get('caller_name', '')
        member_name = identity_data.get('member_name', '')

        # 1. Member Lookup
        member = self.lookup_service.find_member_by_name(member_name)
        if not member:
            return {
                "status": "Unauthorized",
                "reason": f"Member '{member_name}' not found in system."
            }

        # 2. If Caller is the Member themselves
        if caller_type == 'member':
            return {"status": "Authorized", "reason": "Caller is the member."}

        # 3. ROI Validation for Representatives
        auth_record = self._get_authorization(member['member_id'], caller_name)
        
        if not auth_record:
            return {
                "status": "Unauthorized",
                "reason": "No Release of Information (ROI) on file for this caller."
            }

        # 4. Check Expiration
        expiration_str = auth_record.get('expiration_date')
        if not expiration_str:
            return {
                "status": "Unauthorized",
                "reason": "Internal Error: Authorization record is missing an expiration date."
            }
            
        # Handle both string (from CSV/legacy) and date objects (from BigQuery)
        if isinstance(expiration_str, (date, datetime)):
            exp_date = datetime.combine(expiration_str, datetime.min.time()) if isinstance(expiration_str, date) else expiration_str
        else:
            exp_date = datetime.strptime(expiration_str, '%Y-%m-%d')
            
        today = datetime.now()

        if exp_date < today:
            return {
                "status": "Unauthorized",
                "reason": f"Authorization expired on {auth_record['expiration_date']}."
            }

        # 5. Proactive Warning (expires within 14 days)
        reminder = None
        if exp_date <= today + timedelta(days=14):
            reminder = f"Note: ROI for {caller_name} expires soon on {auth_record['expiration_date']}."

        return {
            "status": "Authorized",
            "reason": "ROI verified and active.",
            "reminder": reminder,
            "authorized_caller": auth_record['authorized_caller_name'],
            "relationship": auth_record['relationship']
        }

    def _get_authorization(self, member_id, caller_name):
        """
        Internal helper to find the specific ROI record.
        """
        query = f"""
            SELECT * FROM `{self.client.project}.{self.dataset_id}.authorizations`
            WHERE member_id = @member_id 
            AND LOWER(authorized_caller_name) = LOWER(@caller_name)
            ORDER BY expiration_date DESC
            LIMIT 1
        """
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("member_id", "STRING", member_id),
                bigquery.ScalarQueryParameter("caller_name", "STRING", caller_name),
            ]
        )
        
        query_job = self.client.query(query, job_config=job_config)
        results = list(query_job.result())
        
        return dict(results[0]) if results else None