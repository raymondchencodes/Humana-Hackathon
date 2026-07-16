import csv
import json
import os
from authorization_service import AuthorizationService
try:
    from roi_agent import ROIAgent
    HAS_ROI_AGENT = True
except ImportError:
    HAS_ROI_AGENT = False

def print_result(label, result):
    """Helper to print formatted test results."""
    status_color = "\033[92m" if result['authorized'] else "\033[91m"
    reset = "\033[0m"
    auth_text = "AUTHORIZED" if result['authorized'] else "DENIED"
    
    print(f"{label.ljust(40)} | Status: {status_color}{auth_text}{reset} | Reason: {result['reason']} | Exp: {result['expiration_date']}")

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
                "status": "identity_verified",
                "member_id": m.member_id,
                "is_self": True,
                "caller_name": name,
                "member_name": name
            })
            print_result(f"Member: {name}", result)
    except Exception as e:
        print(f"Error fetching sample members: {e}")

    # --- 2. LIVE ROI DISCOVERY: Test with actual ROIs in BigQuery ---
    print("\n--- 2. Testing with Sample Active ROIs found in BigQuery ---")
    roi_query = f"""
        SELECT m.member_id, m.first_name, m.last_name, a.authorized_caller_name, a.expiration_date
        FROM `{client.project}.{dataset}.roi_authorizations` a
        JOIN `{client.project}.{dataset}.members` m ON a.member_id = m.member_id
        ORDER BY a.expiration_date DESC
        LIMIT 3
    """
    try:
        rois = list(client.query(roi_query).result())
        if not rois:
            print("No active ROI records found in BigQuery.")
        for r in rois:
            m_name = f"{r.first_name} {r.last_name}"
            result = auth_engine.validate_caller({
                "status": "identity_verified",
                "member_id": r.member_id,
                "is_self": False,
                "caller_name": r.authorized_caller_name,
                "member_name": m_name
            })
            print_result(f"Rep: {r.authorized_caller_name} (for {m_name})", result)
    except Exception as e:
        if "Not found: Table" in str(e):
            available_tables = [t.table_id for t in client.list_tables(dataset)]
            print(f"Error: Table 'roi_authorizations' not found. Available tables in '{dataset}': {available_tables}")
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
                    "status": "identity_verified",
                    "member_id": m_id,
                    "is_self": True,
                    "caller_name": member_name,
                    "member_name": member_name
                })
                print_result(f"CSV Member: {member_name} ({m_id})", result)

    # --- 4. END-TO-END SCENARIO TESTS ---
    if HAS_ROI_AGENT:
        print("\n--- 4. Specific End-to-End Scenario Tests ---")
        agent = ROIAgent()

        # Scenario A: Fake Name
        fake_transcript = "My name is Bob Saget and I'm calling for my friend Dave Coulier born 1959-09-22."
        print(f"\nScenario A (Fake Name): \"{fake_transcript}\"")
        identity_a = agent.verify(fake_transcript)
        auth_a = auth_engine.validate_caller(identity_a)
        print_result("Result: Fake Person", auth_a)

        # Scenario B: Actual Member from members list
        real_transcript = "I am Maria Fisher and I'm calling about my own coverage. My birthday is 1992-05-28."
        print(f"\nScenario B (Real Member): \"{real_transcript}\"")
        identity_b = agent.verify(real_transcript)
        
        # If the Identity Agent found her, proceed to Authorization Engine
        if identity_b.get('status') == 'identity_verified':
            auth_b = auth_engine.validate_caller(identity_b)
            print_result("Result: Maria Fisher", auth_b)
        else:
            print(f"\033[91mIdentity Verification Failed for Maria Fisher:\033[0m {identity_b.get('error')}")
    else:
        print("\n[!] Skipping End-to-End Scenarios: ROIAgent (Identity Agent) not found.")

    # --- 5. RAW JSON OUTPUT VERIFICATION ---
    print("\n--- 5. Raw JSON Output Verification (Scenario B) ---")
    if HAS_ROI_AGENT:
        # Re-running Maria Fisher to show the exact JSON format
        real_transcript = "I am Maria Fisher and I'm calling about my own coverage. My birthday is 1992-05-28."
        identity = agent.verify(real_transcript)
        if identity.get('status') == 'identity_verified':
            final_json = auth_engine.validate_caller(identity)
            print(json.dumps(final_json, indent=2))
        else:
            print("Identity verification failed for JSON test.")


if __name__ == "__main__":
    test_engine()