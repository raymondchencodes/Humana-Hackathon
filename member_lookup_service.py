from google.cloud import bigquery

class MemberLookupService:
    def __init__(self, dataset_id='humana_hackathon'):
        self.client = bigquery.Client()
        self.dataset_id = dataset_id

    def find_member_by_name(self, name: str):
        """
        Returns member record if found, else None.
        """
        if not name:
            return None
        
        query = f"""
            SELECT * FROM `{self.client.project}.{self.dataset_id}.members`
            WHERE LOWER(
                TRIM(
                    CONCAT(IFNULL(first_name, ''), ' ', IFNULL(last_name, ''))
                )
            ) = LOWER(TRIM(@name))
            LIMIT 1
        """
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("name", "STRING", name),
            ]
        )
        
        query_job = self.client.query(query, job_config=job_config)
        results = list(query_job.result())
        
        return dict(results[0]) if results else None