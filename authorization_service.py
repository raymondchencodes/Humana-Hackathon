from google.cloud import bigquery
from datetime import datetime, timedelta, date

class AuthorizationService:
    def __init__(self, dataset_id='humana_hackathon'):
        self.client = bigquery.Client()
        self.dataset_id = dataset_id

    def validate_caller(self, identity_data: dict):
        """
        Validates if the caller is authorized based on Identity Agent output.
        """
        member_id = identity_data.get('member_id')
        caller_name = identity_data.get('caller_name', '')
        member_name = identity_data.get('member_name', '')
        is_self = identity_data.get('is_self', False)

        # Default response structure
        result = {
            "authorized": False,
            "reason": "no_authorization",
            "caller_name": caller_name,
            "member_name": member_name,
            "expiration_date": "N/A"
        }

        if not member_id:
            return result

        # 1. ROI Validation for Representatives (and Members with records in the authorization table)
        auth_record = self._get_authorization(member_id, caller_name)
        
        if auth_record:
            expiration_val = auth_record.get('expiration_date')
            if expiration_val:
                result["expiration_date"] = str(expiration_val)

                # Handle both string (from CSV/legacy) and date objects (from BigQuery)
                if isinstance(expiration_val, (date, datetime)):
                    exp_date = datetime.combine(expiration_val, datetime.min.time()) if isinstance(expiration_val, date) else expiration_val
                else:
                    exp_date = datetime.strptime(expiration_val, '%Y-%m-%d')
                
                today = datetime.now()

                # If Caller is the Member themselves, they are always authorized regardless of ROI expiration
                if is_self:
                    result["authorized"] = True
                    result["reason"] = "caller_is_member"
                    return result

                # For representatives, check expiration
                if exp_date < today:
                    result["authorized"] = False
                    result["reason"] = "expired_authorization"
                    return result

                # Authorized Success
                result["authorized"] = True
                result["reason"] = "roi_verified"
                return result

        # 2. Fallback if no specific ROI record was found in the authorization table
        if is_self:
            result["authorized"] = True
            result["reason"] = "caller_is_member"
            result["expiration_date"] = "9999-12-31"  # Default fallback if no database record exists
            return result

        result["reason"] = "no_authorization"
        return result

    def _get_authorization(self, member_id, caller_name):
        """
        Internal helper to find the specific ROI record.
        """
        query = f"""
            SELECT * FROM `{self.client.project}.{self.dataset_id}.roi_authorizations`
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