import csv
import os
from authorization_service import AuthorizationService
try:
    from roi_agent import ROIAgent
    HAS_ROI_AGENT = True
except ImportError:
    HAS_ROI_AGENT = False

def print_result(label, result):
    """Helper to print formatted test results."""
    status_color = "\033[92m" if result['status'] == "Authorized" else "\033[91m"
    reset = "\033[0m"
    print(f"{label.ljust(40)} | Status: {status_color}{result['status']}{reset} | Reason: {result['reason']}")
    if result.get('reminder'):
        print(f"  > REMINDER: {result['reminder']}")

def test_engine():
    auth_engine = AuthorizationService()
    client = auth_engine.client
    dataset = auth_engine.dataset_id
    
    print("=== HUMANA HACKATHON: AUTHORIZATION VALIDATION ===\n")
    print(f"Connected to BigQuery Project: {client.project}")
    print(f"Using Dataset: {dataset}\n")

    if HAS_ROI_AGENT:
        print("Identity Agent (ROIAgent) detected and loaded.\n")

    # --- 1. LIVE DATA DISCOVERY: Test with actual members in BigQuery ---
    print("--- 1. Testing with Sample Members found in BigQuery ---")
    discovery_query = f"SELECT member_id, first_name, last_name FROM `{client.project}.{dataset}.members` LIMIT 3"
    try:
        members = list(client.query(discovery_query).result())
        if not members:
            print("No members found in BigQuery table 'members'.")
        for m in members:
            name = f"{m.first_name} {m.last_name}"
            result = auth_engine.validate_caller({
                "member_id": m.member_id,
                "caller_type": "member",
                "caller_name": name,
                "member_name": name
            })
            print_result(f"Member: {name}", result)
    except Exception as e:
        print(f"Error fetching sample members: {e}")

    # --- 2. LIVE ROI DISCOVERY: Test with actual ROIs in BigQuery ---
    print("\n--- 2. Testing with Sample Active ROIs found in BigQuery ---")
    roi_query = f"""
        SELECT m.member_id, m.first_name, m.last_name, a.authorized_caller_name 
        FROM `{client.project}.{dataset}.authorizations` a
        JOIN `{client.project}.{dataset}.members` m ON a.member_id = m.member_id
        WHERE a.expiration_date > CURRENT_DATE()
        LIMIT 3
    """
    try:
        rois = list(client.query(roi_query).result())
        if not rois:
            print("No active ROI records found in BigQuery.")
        for r in rois:
            m_name = f"{r.first_name} {r.last_name}"
            result = auth_engine.validate_caller({
                "member_id": r.member_id,
                "caller_type": "representative",
                "caller_name": r.authorized_caller_name,
                "member_name": m_name
            })
            print_result(f"Rep: {r.authorized_caller_name} (for {m_name})", result)
    except Exception as e:
        if "Not found: Table" in str(e):
            available_tables = [t.table_id for t in client.list_tables(dataset)]
            print(f"Error: Table 'authorizations' not found. Available tables in '{dataset}': {available_tables}")
        else:
            print(f"Error fetching sample ROIs: {e}")

    # --- 3. LOCAL FILE VALIDATION ---
    print("\n--- 3. Validating Local CSV Data ---")
    base_path = '/home/student_02_35b28d5bb2b5/Humana-Hackathon'
    members_dir = os.path.join(base_path, 'members')
    
    files_to_process = []
    if os.path.isdir(members_dir):
        files_to_process = [os.path.join(members_dir, f) for f in os.listdir(members_dir) if f.endswith('.csv')]
    elif os.path.exists(os.path.join(base_path, 'members.csv')):
        files_to_process = [os.path.join(base_path, 'members.csv')]

    for file_path in files_to_process:
        print(f"File: {os.path.basename(file_path)}")
        with open(file_path, mode='r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                member_name = row.get('member_name') or \
                             f"{row.get('first_name', '')} {row.get('last_name', '')}".strip()
                
                if not member_name or member_name == " ":
                    continue
                
                m_id = row.get('member_id', 'UNKNOWN')

                result = auth_engine.validate_caller({
                    "member_id": m_id,
                    "caller_type": "member",
                    "caller_name": member_name,
                    "member_name": member_name
                })
                print_result(f"CSV Member: {member_name} ({m_id})", result)

if __name__ == "__main__":
    test_engine()