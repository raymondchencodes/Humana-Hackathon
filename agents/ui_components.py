import streamlit as st

def apply_custom_styles():
    """Properly injects premium healthcare portal CSS styles."""
    style_html = """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

    /* Global reset and typography */
    html, body, [class*="st-"] {
        font-family: 'Inter', -apple-system, sans-serif;
        color: #1E293B;
    }
    
    .stApp {
        background-color: #FFFFFF;
    }

    .main {
        background-color: #F8FAFC;
    }

    /* Top Header Styling */
    .healthcare-header {
        background-color: #FFFFFF;
        padding: 1rem 2rem;
        border-bottom: 1px solid #E2E8F0;
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 2rem;
        box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.05);
    }

    .header-logo {
        color: #00A651;
        font-weight: 800;
        font-size: 1.5rem;
        letter-spacing: -0.025em;
    }

    /* Sidebar adjustments */
    [data-testid="stSidebar"] {
        background-color: #FFFFFF;
        border-right: 1px solid #E2E8F0;
    }
    
    .nav-item {
        padding: 0.75rem 1rem;
        margin: 0.25rem 0;
        border-radius: 0.5rem;
        color: #475569;
        font-weight: 500;
        transition: all 0.2s ease;
        cursor: pointer;
        display: flex;
        align-items: center;
        gap: 0.75rem;
    }
    
    .nav-item:hover {
        background-color: #EAF7EE;
        color: #00A651;
    }

    .nav-active {
        background-color: #EAF7EE;
        color: #00A651;
        border-left: 4px solid #00A651;
    }

    /* Premium Cards */
    .healthcare-card {
        background-color: #FFFFFF;
        border: 1px solid #E2E8F0;
        border-radius: 1rem;
        padding: 1.5rem;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
        margin-bottom: 1.5rem;
    }

    .hero-banner {
        background: linear-gradient(135deg, #00A651 0%, #6CC24A 100%);
        color: white;
        padding: 2rem;
        border-radius: 1rem;
        margin-bottom: 2rem;
    }

    /* Conversation UI */
    .chat-bubble {
        padding: 1rem;
        border-radius: 1rem;
        margin-bottom: 1rem;
        max-width: 85%;
        font-size: 0.95rem;
        line-height: 1.5;
    }

    .agent-bubble {
        background-color: #EAF7EE;
        color: #064E3B;
        border-bottom-left-radius: 0.25rem;
        border: 1px solid #D1FAE5;
    }

    .member-bubble {
        background-color: #F1F5F9;
        color: #1E293B;
        margin-left: auto;
        border-bottom-right-radius: 0.25rem;
        border: 1px solid #E2E8F0;
    }

    /* Status Badges */
    .badge {
        padding: 0.25rem 0.75rem;
        border-radius: 9999px;
        font-size: 0.75rem;
        font-weight: 700;
        text-transform: uppercase;
    }

    .badge-approved { background-color: #D1FAE5; color: #065F46; }
    .badge-denied { background-color: #FEE2E2; color: #991B1B; }
    .badge-pending { background-color: #FEF3C7; color: #92400E; }

    /* Layout tweaks */
    [data-testid="stHorizontalBlock"] {
        gap: 2.5rem;
    }
    
    hr { margin: 1.5rem 0; opacity: 0.1; }
    </style>
    """
    st.markdown(style_html, unsafe_allow_html=True)

def render_header():
    """Renders the top enterprise navigation bar."""
    st.markdown("""
        <div class="healthcare-header">
            <div class="header-logo">Humana.</div>
            <div style="display: flex; gap: 2rem; align-items: center; color: #64748B; font-weight: 500;">
                <span>Claims Search</span>
                <span>Notifications 🔔</span>
                <div style="display: flex; align-items: center; gap: 0.5rem; color: #1E293B;">
                    <div style="width: 32px; height: 32px; background: #E2E8F0; border-radius: 50%;"></div>
                    <span>Support Agent</span>
                </div>
            </div>
        </div>
    """, unsafe_allow_html=True)

def render_hero_banner():
    """Renders the central hero card."""
    st.markdown("""
        <div class="hero-banner">
            <h1 style="margin: 0; font-size: 1.75rem; font-weight: 700;">AI Claims Assistant</h1>
            <p style="margin: 0.5rem 0 0 0; opacity: 0.9; font-weight: 400;">Intelligent claim explanation and resolution engine.</p>
        </div>
    """, unsafe_allow_html=True)

def render_metrics_panel(structured_data):
    """Renders the metrics and recommended actions in the right panel."""
    status = structured_data.get('claim_status', 'Pending')
    badge_type = "badge-pending"
    if "denied" in status.lower(): badge_type = "badge-denied"
    elif "approved" in status.lower() or "paid" in status.lower(): badge_type = "badge-approved"

    denial_html = ""
    denial_reason = structured_data.get('denial_reason')
    if denial_reason and denial_reason.lower() not in ["null", "n/a", "none", "unknown"]:
        denial_html = f'<p style="font-size: 0.9rem; color: #991B1B; margin: 0.5rem 0;"><strong>Denial Reason:</strong> {denial_reason}</p>'

    st.markdown(f"""
        <div class="healthcare-card">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem;">
                <span style="font-weight: 700; font-size: 0.85rem; color: #64748B;">CLAIM STATUS</span>
                <span class="badge {badge_type}">{status}</span>
            </div>
            <h2 style="font-size: 1.25rem; margin-top: 0;">ID: {structured_data.get('claim_id', structured_data.get('member_id', 'N/A'))}</h2>
            <p style="font-size: 0.9rem; color: #64748B; margin: 0.25rem 0;">CPT: <strong>{", ".join(structured_data.get('cpt_codes', []))}</strong></p>
            <p style="font-size: 0.9rem; color: #64748B; margin: 0.25rem 0;">Confidence Score: <strong>{structured_data.get('confidence_score', 0) * 100:.0f}%</strong></p>
            {denial_html}
            <hr>
            <div style="background-color: #EAF7EE; padding: 1rem; border-radius: 0.75rem; border: 1px solid #D1FAE5; text-align: center;">
                <p style="font-size: 0.75rem; font-weight: 700; color: #059669; margin: 0 0 0.25rem 0; letter-spacing: 0.05em;">ESTIMATED RESOLUTION</p>
                <p style="font-size: 1.25rem; font-weight: 700; color: #064E3B; margin: 0;">{structured_data.get('estimated_resolution_days', '5-7')} Business Days</p>
            </div>
        </div>
    """, unsafe_allow_html=True)
    
    st.markdown("<p style='font-weight: 700; margin-bottom: 0.75rem; color: #475569;'>REQUIRED ACTIONS</p>", unsafe_allow_html=True)
    actions = structured_data.get('required_actions', [])
    for action in actions:
        st.markdown(f"""
            <div style="display: flex; gap: 0.75rem; margin-bottom: 0.5rem; color: #00A651; font-weight: 600; font-size: 0.9rem;">
                <span>✅</span> <span>{action}</span>
            </div>
        """, unsafe_allow_html=True)