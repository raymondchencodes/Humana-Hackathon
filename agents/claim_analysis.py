import os
import argparse
from google.cloud import speech
from google.cloud import bigquery
from vertexai.generative_models import GenerativeModel, Part
from vertexai.generative_models import GenerationConfig
import json
import vertexai

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
    
    # Updated to point to the humana_hackathon dataset
    dataset_id = "humana_hackathon" 
    query = f"""
        SELECT 
            c.claim_id, c.member_id, c.patient_name, c.provider_name, c.service_date, c.total_amount, c.status, c.denial_code, c.cpt_code,
            r.auth_status, 
            r.expiration_date as roi_expiry
        FROM `{project}.{dataset_id}.claims` AS c
        LEFT JOIN `{project}.{dataset_id}.roi_authorizations` AS r 
            ON c.member_id = r.member_id
        WHERE c.claim_id = @identifier 
           OR c.member_id = @identifier 
           OR c.patient_name = @identifier
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

def analyze_claim(audio_bytes, transcript, metadata=None):
    """Uses Gemini to predict, explain, and generate a claim timeline."""
    # Initialize Vertex AI with your project and location
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
    location = "us-central1"
    
    if not project_id:
        raise ValueError("The GOOGLE_CLOUD_PROJECT environment variable must be set.")

    vertexai.init(project=project_id, location=location)
    
    # Using System Instruction for the Pro model to ensure persona and grounding
    model_pro = GenerativeModel(
        "gemini-2.5-pro",
        system_instruction=[
            "You are an expert AI Claims Solutions Architect and Medical Claims Adjuster.",
            "Your goal is to explain healthcare insurance outcomes to members in simple, empathetic, and highly concise language.",
            "Always ground your response in the provided EXISTING RECORDS.",
            "Never hallucinate policy rules. If data is missing, suggest the member contact their provider.",
            "You must return a JSON object containing both the structured data for the dashboard and the 'claim_story' in Markdown format.",
            "Keep the 'claim_story_markdown' extremely brief. Use bullet points and short sentences to explain complex information simply. Avoid long paragraphs.",
            "Ground all resolution timelines in the data or standard 5-7 business day windows for typical appeals."
        ]
    )
    model_flash = GenerativeModel("gemini-2.5-flash")

    # Create an audio Part for native multimodal understanding
    audio_part = Part.from_data(data=audio_bytes, mime_type="audio/wav")

    if not metadata:
        try:
            # Pass the audio part directly to Flash for extraction
            id_prompt = "Extract the Claim ID, Member ID, or Patient Name mentioned in this audio. Respond with only the value. If none found, respond with 'UNKNOWN'."
            claim_id_response = model_flash.generate_content([audio_part, id_prompt])
            claim_id = claim_id_response.text.strip()
            if claim_id and claim_id != "UNKNOWN":
                metadata = get_claim_metadata(claim_id)
        except Exception as e:
            metadata = {"error": "Could not retrieve automated metadata"}

    metadata_context = f"\nEXISTING SYSTEM RECORDS:\n{json.dumps(metadata, indent=2)}" if metadata else "\nNO SYSTEM RECORDS FOUND."

    # Define the expected JSON structure
    response_schema = {
        "type": "OBJECT",
        "properties": {
            "claim_id": {"type": "STRING"},
            "claim_status": {"type": "STRING"},
            "root_cause": {"type": "STRING"},
            "required_actions": {"type": "ARRAY", "items": {"type": "STRING"}},
            "estimated_resolution_days": {"type": "INTEGER"},
            "confidence_score": {"type": "NUMBER"},
            "cpt_codes": {"type": "ARRAY", "items": {"type": "STRING"}},
            "claim_story_markdown": {"type": "STRING"}
        },
        "required": ["claim_id", "claim_status", "claim_story_markdown"]
    }

    prompt = f"""
    ANALYSIS REQUEST:
    STT TRANSCRIPT (FOR REFERENCE):
    "{transcript}"
    {metadata_context}

    Generate a production-ready, simplified Claim Explanation Report. 
    The 'claim_story_markdown' field should use these headers and be kept to concise bullet points or 1-2 short sentences per section:
    ### What Happened | ### Why It Happened | ### Evidence Used | ### What You Need To Do | ### What Happens Next | ### Estimated Resolution Time
    """

    response = model_pro.generate_content(
        [audio_part, prompt],
        generation_config=GenerationConfig(
            response_mime_type="application/json",
            response_schema=response_schema
        )
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
        # Step 1: Speech to Text
        transcript = transcribe_audio(args.audio_file)
        if not transcript:
            print("Failed to generate transcript. Check audio quality or format.")
            return

        print("\n--- Transcript ---")
        print(transcript)

        # Step 2: Prediction and Timeline Generation
        # Fixed: Updated to pass audio bytes as required by the multimodal analyze_claim signature
        with open(args.audio_file, "rb") as audio_file:
            audio_bytes = audio_file.read()
            
        analysis = analyze_claim(audio_bytes, transcript)

        print("\n--- Claim Analysis Report ---")
        print(analysis)

    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    main()