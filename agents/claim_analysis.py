import os
import argparse
from google.cloud import speech
from google.cloud import bigquery
from vertexai.generative_models import GenerativeModel, Part, GenerationConfig
import json
import vertexai

BAD_VALUES = {"", "unknown", "n/a", "none", "null"}


def safe_merge(target: dict, source: dict):
    """Merge source into target, but never overwrite a real value with junk,
    and never erase an existing value with an empty one."""
    for key, value in source.items():
        if value is None:
            continue
        if isinstance(value, str) and value.strip().lower() in BAD_VALUES:
            continue
        if isinstance(value, list) and not value:
            continue
        target[key] = value
    return target


def transcribe_audio(file_path):
    """Converts speech in an audio file to text using Google Cloud Speech-to-Text."""
    # Explicitly setting the quota_project_id helps resolve authentication issues with ADC
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
    client_options = {"quota_project_id": project_id} if project_id else None
    client = speech.SpeechClient(client_options=client_options)

    with open(file_path, "rb") as audio_file:
        content = audio_file.read()

    audio = speech.RecognitionAudio(content=content)
    config = speech.RecognitionConfig(
        # Removing hardcoded encoding allows the API to auto-detect the format (e.g. WAV from mic)
        language_code="en-US",
        enable_automatic_punctuation=True,
    )

    print(f"Transcribing {file_path}...")
    response = client.recognize(config=config, audio=audio)

    transcript = ""
    for result in response.results:
        transcript += result.alternatives[0].transcript + " "

    return transcript.strip()


def get_claim_metadata(claim_id):
    """Fetches claim and ROI authorization data from BigQuery."""
    project = os.getenv("GOOGLE_CLOUD_PROJECT")
    if not project:
        raise ValueError("Project ID is not set in environment variables.")

    client = bigquery.Client(project=project)

    dataset_id = "humana_hackathon"
    query = f"""
        SELECT 
            c.claim_id, c.member_id, c.patient_name, c.provider_name, c.service_date, c.total_amount, c.status, c.denial_code, c.cpt_code,
            r.auth_status, 
            r.expiration_date as roi_expiry
        FROM `{project}.{dataset_id}.claims` AS c
        LEFT JOIN `{project}.{dataset_id}.roi_authorizations` AS r 
            ON c.member_id = r.member_id
        WHERE TRIM(c.claim_id) = @identifier 
           OR TRIM(c.member_id) = @identifier 
           OR LOWER(TRIM(c.patient_name)) = LOWER(TRIM(@identifier))
        ORDER BY c.service_date DESC
        LIMIT 1
    """

    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("identifier", "STRING", claim_id)
        ]
    )

    query_job = client.query(query, job_config=job_config)
    results = query_job.result()

    metadata = {}
    for row in results:
        metadata = dict(row.items())

    return metadata


def extract_identifiers(model_flash, audio_part):
    """Extract ALL identifiers from the audio as structured JSON."""
    id_schema = {
        "type": "OBJECT",
        "properties": {
            "claim_id": {"type": "STRING", "nullable": True},
            "member_id": {"type": "STRING", "nullable": True},
            "patient_name": {"type": "STRING", "nullable": True},
        },
    }
    prompt = (
        "Listen to this audio and extract any identifiers mentioned: "
        "Claim ID, Member ID, and the caller's full name. "
        "Return null for any identifier not mentioned. "
        "Return digits without spaces (e.g. 'one two three' -> '123')."
    )
    response = model_flash.generate_content(
        [audio_part, prompt],
        generation_config=GenerationConfig(
            response_mime_type="application/json",
            response_schema=id_schema,
        ),
    )
    ids = json.loads(response.text)
    return {
        k: v for k, v in ids.items()
        if v and str(v).strip().lower() not in BAD_VALUES
    }


def analyze_claim(audio_bytes, transcript, metadata=None, conversation_history=None):
    """Uses Gemini to predict, explain, and generate a claim timeline."""
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
    location = "us-central1"

    if not project_id:
        raise ValueError("The GOOGLE_CLOUD_PROJECT environment variable must be set.")

    vertexai.init(project=project_id, location=location)

    model_pro = GenerativeModel(
        "gemini-1.5-pro",
        system_instruction=[
            "You are an expert AI Claims Solutions Architect and Medical Claims Adjuster.",
            "VERIFICATION RULES: Member ID and full name are the ONLY REQUIRED identifiers for verification. Claim ID is strictly OPTIONAL and should NOT be requested if you have the other two.",
            "Check EXISTING SYSTEM RECORDS and the FULL CONVERSATION before asking for anything. NEVER ask for information that already appears in either place. If you have Member ID and Name, proceed even if Claim ID is missing.",
            "If member_id or patient_name is genuinely missing from both the records and the conversation, politely ask ONLY for the missing item(s).",
            "In your JSON output, if you do not know a value, copy it from EXISTING SYSTEM RECORDS. Never output 'UNKNOWN' for a field that has a value in the records.",
            "Your goal is to explain healthcare insurance outcomes to members in simple, empathetic, and highly concise language.",
            "Always ground your response in the provided EXISTING SYSTEM RECORDS.",
            "SESSION MEMORY: If the user provides new or corrected information that contradicts the EXISTING RECORDS, update the fields in your JSON response with the new values.",
            "You must return a JSON object containing both the structured data for the dashboard and the 'claim_story' in Markdown format.",
            "Keep the 'claim_story_markdown' extremely brief. Use bullet points and short sentences to explain complex information simply. Avoid long paragraphs. The headers should be: ### Why It Happened | ### Evidence Used | ### What You Need To Do | ### What Happens Next | ### Estimated Resolution Time",
            "Keep the 'claim_story_markdown' extremely brief. Use bullet points and short sentences to explain complex information simply. Avoid long paragraphs. The sections should be formatted as bullet points with the section title followed by a colon, for example: * Why It Happened: | * Evidence Used: | * What You Need To Do: | * What Happens Next: | * Estimated Resolution Time:",
        ],
    )
    model_flash = GenerativeModel("gemini-1.5-flash")

    audio_part = Part.from_data(data=audio_bytes, mime_type="audio/wav")

    if metadata is None:
        metadata = {}

    try:
        # Extract ALL identifiers from this turn and remember them for the session
        extracted = extract_identifiers(model_flash, audio_part)
        safe_merge(metadata, extracted)

        # Look up the claim using accumulated session memory:
        # prefer claim_id, fall back to member_id, then name.
        lookup_key = (
            metadata.get("claim_id")
            or metadata.get("member_id")
            or metadata.get("patient_name")
        )
        # Skip re-querying if we already fetched the claim record this session
        if lookup_key and "status" not in metadata:
            print(f"DEBUG: Attempting database lookup for identifier: {lookup_key}")
            fresh_metadata = get_claim_metadata(lookup_key)
            if fresh_metadata:
                print(f"DEBUG: Found claim {fresh_metadata.get('claim_id')} for {lookup_key}")
                safe_merge(metadata, fresh_metadata)
    except Exception:
        pass  # keep whatever metadata we already have — do NOT reset it

    metadata_context = (
        f"\nEXISTING SYSTEM RECORDS:\n{json.dumps(metadata, indent=2, default=str)}"
        if metadata
        else "\nNO SYSTEM RECORDS FOUND."
    )

    history_context = ""
    if conversation_history:
        history_context = "\nFULL CONVERSATION SO FAR:\n" + "\n".join(
            f'Member said: "{t}"' for t in conversation_history
        )

    response_schema = {
        "type": "OBJECT",
        "properties": {
            "claim_id": {"type": "STRING"},
            "member_id": {"type": "STRING"},
            "patient_name": {"type": "STRING"},
            "claim_status": {"type": "STRING"},
            "denial_reason": {"type": "STRING"},
            "root_cause": {"type": "STRING"},
            "required_actions": {"type": "ARRAY", "items": {"type": "STRING"}},
            "estimated_resolution_days": {"type": "INTEGER"},
            "confidence_score": {"type": "NUMBER"},
            "cpt_codes": {"type": "ARRAY", "items": {"type": "STRING"}},
            "claim_story_markdown": {"type": "STRING"},
        },
        "required": ["claim_status", "claim_story_markdown"],
    }

    prompt = f"""
    ANALYSIS REQUEST:
    {history_context}
    CURRENT TURN TRANSCRIPT:
    "{transcript}"
    {metadata_context}

    Generate a production-ready, simplified Claim Explanation Report. 
    Ensure the 'claim_id', 'member_id', 'patient_name', and 'denial_reason' (interpreting the 'denial_code' if the status is Denied) fields in the JSON are populated using the data from EXISTING SYSTEM RECORDS if available.
    The 'claim_story_markdown' field should be kept to concise bullet points or 1-2 short sentences per section, using the following headers:
    ### Why It Happened | ### Evidence Used | ### What You Need To Do | ### What Happens Next | ### Estimated Resolution Time
    """

    response = model_pro.generate_content(
        [audio_part, prompt],
        generation_config=GenerationConfig(
            response_mime_type="application/json",
            response_schema=response_schema,
        ),
    )
    return response.text


def parse_gemini_response(response_text):
    """Helper to split the JSON data from the Markdown story."""
    try:
        data = json.loads(response_text)
        markdown = data.pop("claim_story_markdown", "No story generated.")
        return data, markdown
    except Exception as e:
        return {"error": str(e)}, response_text


def main():
    parser = argparse.ArgumentParser(description="Transcribe and analyze claims from audio.")
    parser.add_argument("audio_file", help="Path to the local audio file (e.g., .wav, .flac)")
    args = parser.parse_args()

    if not os.path.exists(args.audio_file):
        print(f"Error: File {args.audio_file} not found.")
        return

    try:
        transcript = transcribe_audio(args.audio_file)
        if not transcript:
            print("Failed to generate transcript. Check audio quality or format.")
            return

        print("\n--- Transcript ---")
        print(transcript)

        with open(args.audio_file, "rb") as audio_file:
            audio_bytes = audio_file.read()

        analysis = analyze_claim(audio_bytes, transcript)

        print("\n--- Claim Analysis Report ---")
        print(analysis)

    except Exception as e:
        print(f"An error occurred: {e}")


if __name__ == "__main__":
    main()