import streamlit as st
import os
import tempfile
import uuid
from claim_analysis import transcribe_audio, analyze_claim, parse_gemini_response, safe_merge
from ui_components import apply_custom_styles, render_metrics_panel, render_header, render_hero_banner

# Set page configuration
st.set_page_config(
    page_title="Claim Analysis Expert",
    page_icon="📋",
    layout="wide"
)

# Initialize session state for memory management
if "audio_input_key" not in st.session_state:
    st.session_state.audio_input_key = 0
if "analysis_data" not in st.session_state:
    st.session_state.analysis_data = None
if "persistent_metadata" not in st.session_state:
    st.session_state.persistent_metadata = {}
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())

def reset_consultation():
    st.session_state.audio_input_key += 1
    st.session_state.analysis_data = None
    st.session_state.persistent_metadata = {}
    st.session_state.chat_history = []
    st.rerun()

# Apply modular UI styles
apply_custom_styles()

# Healthcare Sidebar Navigation
with st.sidebar:
    st.markdown("<div style='margin-bottom: 2rem;'></div>", unsafe_allow_html=True)
    st.markdown("""
        <div class="nav-item">📊 Dashboard</div>
        <div class="nav-item nav-active">📄 Claims Assistant</div>
        <div class="nav-item">🏥 Member Benefits</div>
        <div class="nav-item">⚖️ Appeals Center</div>
        <div class="nav-item">💬 Support</div>
    """, unsafe_allow_html=True)
    
    st.divider()
    project_id = st.text_input(
        "Project Context", 
        value=os.getenv("GOOGLE_CLOUD_PROJECT", ""),
    )
    if project_id:
        os.environ["GOOGLE_CLOUD_PROJECT"] = project_id
    else:
        st.warning("Please enter a GCP Project ID to begin.")
    st.divider()
    
    st.caption(f"Session ID: `{st.session_state.session_id}`")
    if st.button("🆕 New Conversation", use_container_width=True, type="primary"):
        reset_consultation()

# Top Navigation Bar
render_header()

# Welcome banner
render_hero_banner()

# Define the 3-panel layout
col_left, col_right = st.columns([2, 1])

with col_left:
    st.markdown("<p style='font-weight: 700; color: #64748B;'>MEMBER CONSULTATION</p>", unsafe_allow_html=True)
    audio_file = st.audio_input(
        "Begin member recording",
        key=f"audio_input_{st.session_state.audio_input_key}"
    )

    if audio_file is None:
        if not st.session_state.chat_history:
            st.markdown("""
                <div class="healthcare-card" style="text-align: center; padding: 4rem 2rem;">
                    <div style="font-size: 3rem; margin-bottom: 1.5rem;">🎙️</div>
                    <h3 style="margin-bottom: 0.5rem; color: #1E293B;">Ready to Assist</h3>
                    <p style="color: #64748B;">Capture a conversation. Please ensure the member provides their Member ID and full name (Claim ID is optional).</p>
                </div>
            """, unsafe_allow_html=True)

with col_right:
    st.markdown("<p style='font-weight: 700; color: #64748B;'>CLAIM INTELLIGENCE</p>", unsafe_allow_html=True)
    if audio_file is None and not st.session_state.chat_history:
        st.markdown("""
            <div class="healthcare-card" style="opacity: 0.5;">
                <p>Metrics will populate after analysis.</p>
            </div>
        """, unsafe_allow_html=True)

if audio_file is not None:
    with st.spinner("Processing Consultation..."):
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp_file:
                tmp_file.write(audio_file.getvalue())
                tmp_path = tmp_file.name

            try:
                transcript = transcribe_audio(tmp_path)
            finally:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)

            if not transcript:
                 # For native multimodal, we need the bytes even if STT is empty
                 transcript = "[No speech detected in transcript, performing audio-only analysis]"
            
            if transcript not in st.session_state.chat_history:
                st.session_state.chat_history.append(transcript)

            # Pass cumulative metadata to ensure session-based memory
            raw_analysis = analyze_claim(audio_file.getvalue(), transcript, metadata=st.session_state.persistent_metadata)
            structured_data, markdown_story = parse_gemini_response(raw_analysis)

            # Update memory: Merge new extracted data into persistent metadata
            # Only carry forward identifiers from the model's output, and only real values.
            # BigQuery facts (status, denial_code, etc.) already live in
            # persistent_metadata via analyze_claim's merge — never let model
            # output overwrite them with 'UNKNOWN' or empty strings.
            safe_merge(st.session_state.persistent_metadata, {k: structured_data.get(k) for k in ("claim_id", "member_id", "patient_name")})
            st.session_state.analysis_data = (structured_data, markdown_story)


        except Exception as e:
            st.error(f"An error occurred: {str(e)}")

if st.session_state.chat_history and st.session_state.analysis_data:
    structured_data, markdown_story = st.session_state.analysis_data
    with col_left:
        st.markdown('<div class="chat-bubble agent-bubble">Hello! I am your Claims Assistant. To get started, please provide your Member ID and full name.</div>', unsafe_allow_html=True)
        for msg in st.session_state.chat_history:
            st.markdown(f'<div class="chat-bubble member-bubble">{msg}</div>', unsafe_allow_html=True)

        st.markdown("<p style='font-weight: 700; color: #64748B;'>CLAIM STORY</p>", unsafe_allow_html=True)
        st.markdown(f"""
            <div class="healthcare-card">
                <div style="color: #00A651; margin-bottom: 1rem; font-weight: 700;">Expert Summary</div>
                {markdown_story}
            </div>
        """, unsafe_allow_html=True)
        
        if st.button("🎤 Speak again to provide more details", use_container_width=True):
            st.session_state.audio_input_key += 1
            st.rerun()

    with col_right:
        render_metrics_panel(structured_data)

st.markdown("<div style='text-align: center; color: #94A3B8; font-size: 0.75rem; margin-top: 4rem; padding-bottom: 2rem;'>© 2026 Humana AI Enterprise Solutions • Trusted Healthcare Claims Intelligence</div>", unsafe_allow_html=True)