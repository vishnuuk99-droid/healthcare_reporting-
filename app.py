"""
Healthcare Reporting AI
=======================
Streamlit application for uploading CMS PDF documents,
extracting text, using Gemini to identify structured
reporting requirements, collaborating with SMEs, and
mapping CMS concepts to FHIR US Core R4 resources.
"""

import json
from dotenv import load_dotenv
load_dotenv()

import streamlit as st


from modules.file_manager import (
    ensure_directories,
    save_uploaded_file,
    list_stored_files,
    OUTPUT_DIR,
    KNOWLEDGE_DIR,
)
from modules.pdf_extractor import extract_text_from_pdf, get_pdf_metadata

# ── Page Configuration ───────────────────────────────────────────────
st.set_page_config(
    page_title="Healthcare Reporting AI",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Create project directories on first run
ensure_directories()


# ── Custom Download Helper ───────────────────────────────────────────
import base64

def render_download_button(label: str, data, file_name: str, mime: str, use_container_width: bool = False, type: str = "secondary", key=None):
    if isinstance(data, str):
        data_bytes = data.encode('utf-8')
    elif isinstance(data, (bytes, bytearray)):
        data_bytes = data
    else:
        # Fallback for dict or other types that might be passed
        data_bytes = json.dumps(data, indent=2).encode('utf-8')
    
    b64 = base64.b64encode(data_bytes).decode('utf-8')
    
    # Determine button styles matching the dashboard theme
    if type == "primary":
        background = "linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%)"
        hover_background = "linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%)"
        border = "none"
        color = "#ffffff"
    else:
        background = "rgba(255, 255, 255, 0.05)"
        hover_background = "rgba(255, 255, 255, 0.1)"
        border = "1px solid rgba(255, 255, 255, 0.1)"
        color = "#f8fafc"
        
    width_style = "100%" if use_container_width else "auto"
    
    button_html = f'''
    <a href="data:{mime};base64,{b64}" download="{file_name}" target="_self" style="text-decoration: none; width: {width_style}; display: inline-block;">
        <button style="
            width: 100%;
            padding: 0.5rem 1rem;
            border-radius: 8px;
            border: {border};
            background: {background};
            color: {color};
            font-weight: 600;
            font-size: 14px;
            cursor: pointer;
            transition: all 0.2s ease;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            height: 38px;
        "
        onmouseover="this.style.filter='brightness(1.1)';"
        onmouseout="this.style.filter='brightness(1.0)';"
        >
            {label}
        </button>
    </a>
    '''
    st.markdown(button_html, unsafe_allow_html=True)


# ── Custom Styling ───────────────────────────────────────────────────
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:ital,wght@0,300;0,400;0,500;0,600;0,700;1,400&family=JetBrains+Mono:wght@400;500;700&display=swap');

    /* Global Typography */
    html, body, [class*="css"] {
        font-family: 'Plus Jakarta Sans', sans-serif;
    }

    code, pre, [class*="mono"] {
        font-family: 'JetBrains Mono', monospace !important;
    }

    /* Sidebar Background & Design */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #090d16 0%, #111827 100%) !important;
        border-right: 1px solid rgba(255, 255, 255, 0.05);
    }
    
    [data-testid="stSidebar"] .stMarkdown h1,
    [data-testid="stSidebar"] .stMarkdown h2,
    [data-testid="stSidebar"] .stMarkdown h3 {
        color: #f8fafc;
        font-weight: 700;
        letter-spacing: -0.025em;
    }
    [data-testid="stSidebar"] .stMarkdown p,
    [data-testid="stSidebar"] .stMarkdown li {
        color: #94a3b8;
    }

    /* Primary main header gradient text */
    .main-title {
        font-size: 2.5rem;
        font-weight: 800;
        background: linear-gradient(135deg, #a855f7 0%, #3b82f6 50%, #14b8a6 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0.5rem;
        letter-spacing: -0.03em;
    }

    /* Card Styling with Glassmorphism */
    .fact-card, .dim-card, .intent-card, .page-card, .drill-card, .dd-card, .msr-card, .dax-card, .diag-card, .pbip-valid-card, .pbip-missing-card, .pbip-empty-card {
        background: rgba(17, 24, 39, 0.45) !important;
        backdrop-filter: blur(12px);
        -webkit-backdrop-filter: blur(12px);
        border-radius: 16px !important;
        padding: 20px !important;
        margin-bottom: 16px !important;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.15) !important;
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;
    }

    /* Borders matching semantic elements */
    .fact-card {
        border: 1px solid rgba(59, 130, 246, 0.2) !important;
    }
    .fact-card:hover {
        border-color: rgba(59, 130, 246, 0.5) !important;
        box-shadow: 0 4px 25px rgba(59, 130, 246, 0.15) !important;
        transform: translateY(-2px);
    }
    
    .dim-card {
        border: 1px solid rgba(16, 185, 129, 0.2) !important;
    }
    .dim-card:hover {
        border-color: rgba(16, 185, 129, 0.5) !important;
        box-shadow: 0 4px 25px rgba(16, 185, 129, 0.15) !important;
        transform: translateY(-2px);
    }

    .intent-card {
        border: 1px solid rgba(245, 158, 11, 0.2) !important;
    }
    .intent-card:hover {
        border-color: rgba(245, 158, 11, 0.5) !important;
        box-shadow: 0 4px 25px rgba(245, 158, 11, 0.15) !important;
        transform: translateY(-2px);
    }

    .page-card {
        border: 1px solid rgba(99, 102, 241, 0.2) !important;
    }
    .page-card:hover {
        border-color: rgba(99, 102, 241, 0.5) !important;
        box-shadow: 0 4px 25px rgba(99, 102, 241, 0.15) !important;
        transform: translateY(-2px);
    }

    .drill-card {
        border: 1px solid rgba(168, 85, 247, 0.2) !important;
    }
    .drill-card:hover {
        border-color: rgba(168, 85, 247, 0.5) !important;
        box-shadow: 0 4px 25px rgba(168, 85, 247, 0.15) !important;
        transform: translateY(-2px);
    }

    .dd-card {
        border: 1px solid rgba(107, 114, 128, 0.2) !important;
    }
    .dd-card:hover {
        border-color: rgba(107, 114, 128, 0.5) !important;
        box-shadow: 0 4px 25px rgba(107, 114, 128, 0.15) !important;
        transform: translateY(-2px);
    }

    .msr-card {
        border: 1px solid rgba(79, 70, 229, 0.2) !important;
    }
    .msr-card:hover {
        border-color: rgba(79, 70, 229, 0.5) !important;
        box-shadow: 0 4px 25px rgba(79, 70, 229, 0.15) !important;
        transform: translateY(-2px);
    }

    .dax-card {
        border: 1px solid rgba(99, 102, 241, 0.25) !important;
    }
    .dax-card:hover {
        border-color: rgba(99, 102, 241, 0.6) !important;
        box-shadow: 0 4px 25px rgba(99, 102, 241, 0.2) !important;
        transform: translateY(-2px);
    }

    .diag-card {
        border: 1px solid rgba(148, 163, 184, 0.2) !important;
    }
    .diag-card:hover {
        border-color: rgba(148, 163, 184, 0.5) !important;
        box-shadow: 0 4px 25px rgba(148, 163, 184, 0.15) !important;
        transform: translateY(-2px);
    }

    .pbip-valid-card {
        border: 1px solid rgba(16, 185, 129, 0.3) !important;
        background: linear-gradient(135deg, rgba(6, 78, 59, 0.2) 0%, rgba(15, 23, 42, 0.4) 100%) !important;
    }
    .pbip-missing-card {
        border: 1px solid rgba(239, 68, 68, 0.3) !important;
        background: linear-gradient(135deg, rgba(127, 29, 29, 0.2) 0%, rgba(15, 23, 42, 0.4) 100%) !important;
    }
    .pbip-empty-card {
        border: 1px solid rgba(245, 158, 11, 0.3) !important;
        background: linear-gradient(135deg, rgba(120, 53, 4, 0.2) 0%, rgba(15, 23, 42, 0.4) 100%) !important;
    }

    /* Titles inside cards */
    .fact-card h4, .dim-card h4, .drill-card h4, .page-card h4, .dax-card .dax-name, .diag-card .diag-name {
        font-weight: 700 !important;
        letter-spacing: -0.02em !important;
        margin-top: 0 !important;
        margin-bottom: 6px !important;
    }
    .fact-card h4 { color: #60a5fa !important; }
    .dim-card h4 { color: #34d399 !important; }
    .drill-card h4 { color: #c084fc !important; }
    .page-card h4 { color: #a5b4fc !important; }
    .dax-card .dax-name { color: #818cf8 !important; }

    /* Custom badges */
    .badge-terminology, .badge-business-rule, .badge-preference, .conf-high, .conf-medium, .conf-low, .intent-badge {
        font-family: 'Plus Jakarta Sans', sans-serif !important;
        font-size: 0.75rem !important;
        font-weight: 700 !important;
        padding: 4px 12px !important;
        border-radius: 20px !important;
        text-transform: uppercase !important;
        letter-spacing: 0.05em !important;
        display: inline-block;
    }

    .badge-terminology { background: rgba(59, 130, 246, 0.15) !important; color: #60a5fa !important; border: 1px solid rgba(59, 130, 246, 0.3) !important; }
    .badge-business-rule { background: rgba(244, 63, 94, 0.15) !important; color: #fb7185 !important; border: 1px solid rgba(244, 63, 94, 0.3) !important; }
    .badge-preference { background: rgba(16, 185, 129, 0.15) !important; color: #34d399 !important; border: 1px solid rgba(16, 185, 129, 0.3) !important; }

    .conf-high { background: rgba(16, 185, 129, 0.15) !important; color: #34d399 !important; border: 1px solid rgba(16, 185, 129, 0.3) !important; }
    .conf-medium { background: rgba(245, 158, 11, 0.15) !important; color: #fbbf24 !important; border: 1px solid rgba(245, 158, 11, 0.3) !important; }
    .conf-low { background: rgba(239, 68, 68, 0.15) !important; color: #f87171 !important; border: 1px solid rgba(239, 68, 68, 0.3) !important; }

    /* Custom Metric Pills and Tags */
    .metric-pill, .col-tag, .col-req, .attr-chip, .visual-rec {
        font-family: 'Plus Jakarta Sans', sans-serif !important;
        font-size: 0.72rem !important;
        font-weight: 600 !important;
        padding: 4px 10px !important;
        border-radius: 8px !important;
        display: inline-block;
        margin: 3px 4px !important;
        transition: all 0.2s ease;
    }

    .metric-pill {
        background: rgba(99, 102, 241, 0.12) !important;
        color: #a5b4fc !important;
        border: 1px solid rgba(99, 102, 241, 0.25) !important;
    }
    .metric-pill:hover {
        background: rgba(99, 102, 241, 0.25) !important;
    }

    .col-tag {
        background: rgba(75, 85, 99, 0.15) !important;
        color: #cbd5e1 !important;
        border: 1px solid rgba(156, 163, 175, 0.2) !important;
    }
    .col-type {
        color: #94a3b8;
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.65rem;
        margin-left: 4px;
    }

    .col-req {
        background: rgba(245, 158, 11, 0.1) !important;
        color: #fde047 !important;
        border: 1px solid rgba(245, 158, 11, 0.2) !important;
    }

    .attr-chip {
        background: rgba(168, 85, 247, 0.12) !important;
        color: #e9d5ff !important;
        border: 1px solid rgba(168, 85, 247, 0.25) !important;
    }

    .visual-rec {
        background: rgba(6, 182, 212, 0.12) !important;
        color: #22d3ee !important;
        border: 1px solid rgba(6, 182, 212, 0.25) !important;
    }

    /* Relationship Row */
    .rel-row {
        background: rgba(30, 41, 59, 0.4) !important;
        border: 1px solid rgba(255, 255, 255, 0.05) !important;
        border-radius: 12px !important;
        padding: 12px 18px !important;
        margin-bottom: 8px !important;
        font-size: 0.85rem !important;
        display: flex;
        align-items: center;
    }
    .rel-row .arrow {
        color: #a855f7 !important;
        font-weight: 800 !important;
        padding: 0 10px !important;
    }
    .rel-row .key {
        color: #fde047 !important;
        font-family: 'JetBrains Mono', monospace !important;
        font-size: 0.78rem !important;
        background: rgba(0, 0, 0, 0.2);
        padding: 2px 6px;
        border-radius: 4px;
    }

    /* DAX and SQL formula blocks */
    .dax-block, .msr-card .msr-formula, .dax-card .dax-expr-block {
        background: #05070c !important;
        border: 1px solid rgba(255, 255, 255, 0.05) !important;
        border-radius: 10px !important;
        padding: 14px !important;
        font-family: 'JetBrains Mono', monospace !important;
        font-size: 0.8rem !important;
        color: #e2e8f0 !important;
        line-height: 1.5 !important;
    }

    /* Streamlit Metric Overrides */
    [data-testid="stMetricValue"] {
        font-size: 1.8rem !important;
        font-weight: 700 !important;
        font-family: 'Plus Jakarta Sans', sans-serif !important;
    }
    [data-testid="stMetricLabel"] {
        font-size: 0.82rem !important;
        text-transform: uppercase !important;
        letter-spacing: 0.05em !important;
        color: #94a3b8 !important;
        font-weight: 600 !important;
    }
    [data-testid="stMetric"] {
        background: rgba(15, 23, 42, 0.3) !important;
        border: 1px solid rgba(255, 255, 255, 0.05) !important;
        border-radius: 12px !important;
        padding: 12px 16px !important;
    }

    /* Pipeline Banner styles */
    .pipeline-container {
        display: flex;
        align-items: center;
        justify-content: space-between;
        background: rgba(15, 23, 42, 0.45);
        backdrop-filter: blur(8px);
        -webkit-backdrop-filter: blur(8px);
        border: 1px solid rgba(255, 255, 255, 0.06);
        border-radius: 16px;
        padding: 12px 24px;
        margin-bottom: 28px;
        width: 100%;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.1);
    }
    .pipeline-item {
        font-family: 'Plus Jakarta Sans', sans-serif;
        font-size: 0.82rem;
        font-weight: 600;
        padding: 6px 14px;
        border-radius: 8px;
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        display: flex;
        align-items: center;
        gap: 6px;
    }
    .pipeline-item-active {
        background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);
        color: #ffffff;
        box-shadow: 0 0 14px rgba(99, 102, 241, 0.45);
        border: 1px solid rgba(255, 255, 255, 0.15);
    }
    .pipeline-item-inactive {
        background: rgba(30, 41, 59, 0.35);
        color: #64748b;
        border: 1px solid rgba(255, 255, 255, 0.02);
    }
    .pipeline-connector {
        flex-grow: 1;
        height: 2px;
        background: rgba(255, 255, 255, 0.06);
        margin: 0 12px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ── Helpers / Component Renderers ────────────────────────────────────
def draw_pipeline_banner(current_stage: str):
    stages = [
        ("📂 Ingestion", "📂 Data Ingestion"),
        ("💬 SME", "💬 Collaboration"),
        ("🔗 Modeling", "🔗 Mapping & Modeling"),
        ("🛡️ Validation", "🛡️ Validation & Compliance"),
        ("📐 Generation", "📐 Report Generation")
    ]
    
    html = '<div class="pipeline-container">'
    for label, stage_name in stages:
        active_class = "pipeline-item-active" if stage_name == current_stage else "pipeline-item-inactive"
        html += f'<div class="pipeline-item {active_class}">{label}</div>'
        if label != stages[-1][0]:
            html += '<div class="pipeline-connector"></div>'
    html += '</div>'
    
    st.markdown(html, unsafe_allow_html=True)


# ── Sidebar ──────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🏥 Healthcare Reporting AI")
    
    stage = st.selectbox(
        "Select Pipeline Stage",
        [
            "📂 Data Ingestion",
            "💬 Collaboration",
            "🔗 Mapping & Modeling",
            "🛡️ Validation & Compliance",
            "📐 Report Generation"
        ]
    )
    
    st.markdown("### 📄 Pages")
    if stage == "📂 Data Ingestion":
        page = st.radio(
            "Go to",
            ["📄 Upload & Extract", "📂 Stored Documents"],
            label_visibility="collapsed"
        )
    elif stage == "💬 Collaboration":
        page = st.radio(
            "Go to",
            ["💬 SME Workspace"],
            label_visibility="collapsed"
        )
    elif stage == "🔗 Mapping & Modeling":
        page = st.radio(
            "Go to",
            ["🔗 FHIR Mapping", "📊 Analytics Model"],
            label_visibility="collapsed"
        )
    elif stage == "🛡️ Validation & Compliance":
        page = st.radio(
            "Go to",
            [
                "🛡️ Model Validator",
                "🎨 Report Layout Validator",
                "✅ PBIP Validation",
                "🔧 Dependency Diagnostics"
            ],
            label_visibility="collapsed"
        )
    else:  # "📐 Report Generation"
        page = st.radio(
            "Go to",
            [
                "🎯 Reporting Intent",
                "📝 Report Definition",
                "📖 Data Dictionary",
                "📐 Measure Generator",
                "🔢 DAX Generator",
                "📦 PBIP Generator"
            ],
            label_visibility="collapsed"
        )
        
    st.divider()
    st.markdown(
        "**Healthcare Reporting AI** v1.0  \n"
        "Upload → Extract → Collaborate → Map → Model → Intent → Report → Dict → Measures → DAX → PBIP."
    )

# Draw the pipeline banner globally at the top of the content area
draw_pipeline_banner(stage)


# ── Helpers ──────────────────────────────────────────────────────────
def _load_requirements() -> dict | None:
    req_path = OUTPUT_DIR / "requirements.json"
    if req_path.exists():
        with open(req_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def _load_decisions() -> list[dict]:
    dec_path = KNOWLEDGE_DIR / "org_decisions.json"
    if dec_path.exists():
        with open(dec_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def _type_badge(decision_type: str) -> str:
    badges = {
        "terminology_clarification": '<span class="badge-terminology">📖 Terminology</span>',
        "business_rule": '<span class="badge-business-rule">⚙️ Business Rule</span>',
        "reporting_preference": '<span class="badge-preference">📊 Preference</span>',
    }
    return badges.get(decision_type, f"🏷️ {decision_type}")


def _confidence_badge(level: str) -> str:
    level_lower = level.lower()
    badges = {
        "high": '<span class="conf-high">✅ High</span>',
        "medium": '<span class="conf-medium">⚠️ Medium</span>',
        "low": '<span class="conf-low">❓ Low</span>',
    }
    return badges.get(level_lower, f"🏷️ {level}")


# =====================================================================
# PAGE: Upload & Extract
# =====================================================================
if page == "📄 Upload & Extract":
    st.markdown('<p class="main-title">Upload & Extract PDF</p>', unsafe_allow_html=True)
    st.caption("Upload a CMS PDF document to extract and display its text content.")

    uploaded_file = st.file_uploader(
        "Choose a PDF file",
        type=["pdf"],
        help="Supported format: PDF (.pdf)",
    )

    if uploaded_file is not None:
        with st.spinner("Saving file…"):
            saved_path = save_uploaded_file(uploaded_file)

        st.success(f"✅ Saved to `{saved_path}`")

        metadata = get_pdf_metadata(saved_path)

        st.markdown("### 📋 Document Metadata")
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Pages", metadata["page_count"])
        col2.metric("Title", metadata["title"][:30] if metadata["title"] != "N/A" else "—")
        col3.metric("Author", metadata["author"][:30] if metadata["author"] != "N/A" else "—")
        col4.metric("Subject", metadata["subject"][:30] if metadata["subject"] != "N/A" else "—")

        st.markdown("### 📝 Extracted Text")
        with st.spinner("Extracting text…"):
            extracted_text = extract_text_from_pdf(saved_path)

        if extracted_text.strip():
            st.session_state["extracted_text"] = extracted_text

            with st.expander("View extracted text", expanded=False):
                st.text_area(
                    "Full document text",
                    value=extracted_text,
                    height=400,
                    label_visibility="collapsed",
                )

            st.markdown("---")
            st.markdown("### 🤖 Requirement Extraction")
            st.caption(
                "Send the extracted text to Gemini to identify structured "
                "reporting requirements from the CMS document."
            )

            if st.button("🚀 Extract Requirements", type="primary", use_container_width=True):
                try:
                    from modules.gemini_client import extract_requirements, save_requirements

                    with st.spinner("Analyzing document with Gemini…"):
                        requirements = extract_requirements(extracted_text)

                    output_path = OUTPUT_DIR / "requirements.json"
                    saved_json_path = save_requirements(requirements, output_path)

                    st.success(f"✅ Requirements extracted and saved to `{saved_json_path}`")
                    st.session_state["requirements_json"] = requirements.model_dump()

                except EnvironmentError as env_err:
                    st.error(f"⚠️ Configuration error: {env_err}")
                except Exception as exc:
                    st.error(f"❌ Gemini extraction failed: {exc}")

            if "requirements_json" in st.session_state:
                req = st.session_state["requirements_json"]

                st.markdown("#### 📊 Extracted Requirements")

                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Metrics", len(req.get("metrics", [])))
                m2.metric("Business Rules", len(req.get("business_rules", [])))
                m3.metric("Dimensions", len(req.get("dimensions", [])))
                m4.metric("Exclusions", len(req.get("exclusions", [])))

                tab_json, tab_details = st.tabs(["📄 Raw JSON", "📋 Details"])

                with tab_json:
                    st.json(req)

                with tab_details:
                    col_left, col_right = st.columns(2)

                    with col_left:
                        st.markdown(f"**Report Name:** {req.get('report_name', '—')}")
                        st.markdown(f"**Report Type:** {req.get('report_type', '—')}")
                        st.markdown(f"**Frequency:** {req.get('reporting_frequency', '—')}")

                        if req.get("reporting_entities"):
                            st.markdown("**Reporting Entities:**")
                            for entity in req["reporting_entities"]:
                                st.markdown(f"  - {entity}")

                        if req.get("metrics"):
                            st.markdown("**Metrics:**")
                            for metric in req["metrics"]:
                                st.markdown(f"  - {metric}")

                        if req.get("dimensions"):
                            st.markdown("**Dimensions:**")
                            for dim in req["dimensions"]:
                                st.markdown(f"  - {dim}")

                    with col_right:
                        if req.get("filters"):
                            st.markdown("**Filters:**")
                            for flt in req["filters"]:
                                st.markdown(f"  - {flt}")

                        if req.get("business_rules"):
                            st.markdown("**Business Rules:**")
                            for rule in req["business_rules"]:
                                st.markdown(f"  - {rule}")

                        if req.get("exclusions"):
                            st.markdown("**Exclusions:**")
                            for exc_item in req["exclusions"]:
                                st.markdown(f"  - {exc_item}")

                        if req.get("notes"):
                            st.markdown("**Notes:**")
                            for note in req["notes"]:
                                st.markdown(f"  - {note}")

                render_download_button(
                    label="⬇️ Download requirements.json",
                    data=json.dumps(req, indent=2),
                    file_name="requirements.json",
                    mime="application/json",
                )

        else:
            st.warning("No text could be extracted. The PDF may be image-based or empty.")


# =====================================================================
# PAGE: SME Workspace
# =====================================================================
elif page == "💬 SME Workspace":
    st.markdown('<p class="main-title">SME Workspace</p>', unsafe_allow_html=True)
    st.caption(
        "Chat with the AI about extracted requirements. "
        "Provide clarifications, define business rules, and set reporting preferences."
    )

    cms_text = st.session_state.get("extracted_text")
    requirements_json = st.session_state.get("requirements_json") or _load_requirements()

    if requirements_json:
        st.session_state["requirements_json"] = requirements_json

    if not requirements_json:
        st.warning(
            "⚠️ No extracted requirements found. Please upload a PDF and "
            "run **Extract Requirements** on the Upload & Extract page first."
        )
        st.stop()

    chat_col, decisions_col = st.columns([3, 2])

    with chat_col:
        st.markdown("### 💬 Chat")

        if "sme_messages" not in st.session_state:
            st.session_state["sme_messages"] = [
                {
                    "role": "assistant",
                    "content": (
                        "👋 I have the extracted requirements loaded. "
                        "You can tell me things like:\n\n"
                        '- *"Disposition means Decision Outcome"*\n'
                        '- *"Telehealth visits should count as encounters"*\n'
                        '- *"Show percentages instead of raw counts"*\n\n'
                        "I'll classify each statement and save it as an "
                        "organizational decision."
                    ),
                }
            ]

        for msg in st.session_state["sme_messages"]:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

        if user_input := st.chat_input("Type your clarification or question…"):
            st.session_state["sme_messages"].append(
                {"role": "user", "content": user_input}
            )
            with st.chat_message("user"):
                st.markdown(user_input)

            try:
                from modules.sme_client import chat_with_sme, build_context
                from modules.decision_store import add_decision, list_decisions

                prior_decisions = [d.model_dump() for d in list_decisions()]
                context = build_context(cms_text, requirements_json, prior_decisions)

                history = []
                for m in st.session_state["sme_messages"][1:-1]:
                    role = "model" if m["role"] == "assistant" else "user"
                    history.append({"role": role, "text": m["content"]})

                with st.spinner("Thinking…"):
                    response = chat_with_sme(user_input, context, history)

                if response.is_decision and response.decision_type:
                    decision = add_decision(
                        decision_type=response.decision_type,
                        source_term=response.source_term,
                        mapped_term=response.mapped_term,
                        description=response.decision_description,
                    )
                    badge = _type_badge(response.decision_type)
                    reply_text = (
                        f"{response.reply}\n\n"
                        f"---\n"
                        f"✅ **Decision saved** ({badge})\n\n"
                        f"**{response.source_term}** → **{response.mapped_term}**"
                    )
                else:
                    reply_text = response.reply

                st.session_state["sme_messages"].append(
                    {"role": "assistant", "content": reply_text}
                )
                with st.chat_message("assistant"):
                    st.markdown(reply_text, unsafe_allow_html=True)

            except EnvironmentError as env_err:
                st.error(f"⚠️ {env_err}")
            except Exception as exc:
                st.error(f"❌ Error: {exc}")

    with decisions_col:
        st.markdown("### 📋 Organizational Decisions")

        from modules.decision_store import list_decisions, delete_decision, update_decision

        decisions = list_decisions()

        if not decisions:
            st.info("No decisions yet. Start chatting to build organizational memory.")
        else:
            st.caption(f"{len(decisions)} decision(s) saved")

            for idx, dec in enumerate(decisions):
                badge_html = _type_badge(dec.type)

                with st.expander(
                    f"{dec.source_term} → {dec.mapped_term}",
                    expanded=False,
                ):
                    st.markdown(badge_html, unsafe_allow_html=True)
                    st.markdown(f"**Description:** {dec.description}")
                    st.caption(f"ID: {dec.decision_id} · {dec.timestamp}")

                    edit_col, del_col = st.columns(2)

                    with del_col:
                        if st.button(
                            "🗑️ Delete",
                            key=f"del_{dec.decision_id}",
                            use_container_width=True,
                        ):
                            delete_decision(dec.decision_id)
                            st.rerun()

                    with edit_col:
                        if st.button(
                            "✏️ Edit",
                            key=f"edit_{dec.decision_id}",
                            use_container_width=True,
                        ):
                            st.session_state[f"editing_{dec.decision_id}"] = True

                    if st.session_state.get(f"editing_{dec.decision_id}"):
                        with st.form(key=f"form_{dec.decision_id}"):
                            new_type = st.selectbox(
                                "Type",
                                ["terminology_clarification", "business_rule", "reporting_preference"],
                                index=["terminology_clarification", "business_rule", "reporting_preference"].index(dec.type)
                                if dec.type in ["terminology_clarification", "business_rule", "reporting_preference"]
                                else 0,
                            )
                            new_source = st.text_input("Source term", value=dec.source_term)
                            new_mapped = st.text_input("Mapped term", value=dec.mapped_term)
                            new_desc = st.text_area("Description", value=dec.description)

                            save_col, cancel_col = st.columns(2)
                            with save_col:
                                submitted = st.form_submit_button("💾 Save", use_container_width=True)
                            with cancel_col:
                                cancelled = st.form_submit_button("Cancel", use_container_width=True)

                            if submitted:
                                update_decision(
                                    dec.decision_id,
                                    type=new_type,
                                    source_term=new_source,
                                    mapped_term=new_mapped,
                                    description=new_desc,
                                )
                                del st.session_state[f"editing_{dec.decision_id}"]
                                st.rerun()

                            if cancelled:
                                del st.session_state[f"editing_{dec.decision_id}"]
                                st.rerun()

            all_decs = [d.model_dump() for d in decisions]
            render_download_button(
                label="⬇️ Download org_decisions.json",
                data=json.dumps(all_decs, indent=2),
                file_name="org_decisions.json",
                mime="application/json",
            )


# =====================================================================
# PAGE: FHIR Mapping
# =====================================================================
elif page == "🔗 FHIR Mapping":
    st.markdown('<p class="main-title">FHIR Mapping</p>', unsafe_allow_html=True)
    st.caption(
        "Map extracted CMS concepts to FHIR US Core R4 resources using AI. "
        "Review, approve, or override each mapping."
    )

    # ── Load prerequisites ────────────────────────────────────────────
    requirements_json = st.session_state.get("requirements_json") or _load_requirements()
    if requirements_json:
        st.session_state["requirements_json"] = requirements_json

    if not requirements_json:
        st.warning(
            "⚠️ No extracted requirements found. Please upload a PDF and "
            "run **Extract Requirements** on the Upload & Extract page first."
        )
        st.stop()

    from modules.fhir_mapper import (
        generate_mappings,
        load_fhir_catalog,
        load_mapping_cache,
        approve_mapping,
        override_mapping,
        remove_from_cache,
        save_mapping_cache,
    )

    decisions = _load_decisions()

    # ── FHIR Catalog preview ──────────────────────────────────────────
    catalog = load_fhir_catalog()
    with st.expander(f"📚 FHIR Catalog — {len(catalog)} resources loaded", expanded=False):
        for entry in catalog:
            st.markdown(
                f"**{entry.resource}** · "
                f"[{entry.profile}]({entry.profile})"
            )
            st.caption(entry.business_meaning)

    # ── Context summary ───────────────────────────────────────────────
    ctx1, ctx2, ctx3 = st.columns(3)
    ctx1.metric("Requirements Fields", sum(
        len(requirements_json.get(k, []))
        for k in ["metrics", "dimensions", "filters", "business_rules", "exclusions", "reporting_entities"]
    ))
    ctx2.metric("Org Decisions", len(decisions))
    cached_mappings = load_mapping_cache()
    ctx3.metric("Cached Mappings", len(cached_mappings))

    # ── Generate mappings button ──────────────────────────────────────
    st.markdown("---")

    if st.button("🧬 Generate FHIR Mappings", type="primary", use_container_width=True):
        try:
            with st.spinner("Mapping CMS concepts to FHIR resources with Gemini…"):
                mappings = generate_mappings(requirements_json, decisions)

            st.session_state["fhir_mappings"] = [m.model_dump() for m in mappings]
            st.success(f"✅ Generated {len(mappings)} mappings")

        except EnvironmentError as env_err:
            st.error(f"⚠️ {env_err}")
        except Exception as exc:
            st.error(f"❌ Mapping failed: {exc}")

    # ── Display mappings ──────────────────────────────────────────────
    if "fhir_mappings" in st.session_state and st.session_state["fhir_mappings"]:
        mappings_data = st.session_state["fhir_mappings"]

        st.markdown("### 📊 Generated Mappings")

        # Summary metrics
        high_count = sum(1 for m in mappings_data if m["confidence"].lower() == "high")
        med_count = sum(1 for m in mappings_data if m["confidence"].lower() == "medium")
        low_count = sum(1 for m in mappings_data if m["confidence"].lower() == "low")

        s1, s2, s3, s4 = st.columns(4)
        s1.metric("Total Mappings", len(mappings_data))
        s2.metric("High Confidence", high_count)
        s3.metric("Medium Confidence", med_count)
        s4.metric("Low Confidence", low_count)

        # Tabs: table view vs. raw JSON
        tab_table, tab_json = st.tabs(["📋 Table View", "📄 Raw JSON"])

        with tab_table:
            for idx, mapping in enumerate(mappings_data):
                conf_badge = _confidence_badge(mapping["confidence"])

                # Check if already in cache
                cached_concepts = {m["concept"] for m in cached_mappings}
                is_cached = mapping["concept"] in cached_concepts

                with st.container():
                    # Header row
                    h1, h2, h3 = st.columns([3, 3, 2])
                    with h1:
                        status_icon = "✅" if is_cached else "🔹"
                        st.markdown(f"**{status_icon} {mapping['concept']}**")
                    with h2:
                        st.markdown(
                            f"`{mapping['fhir_resource']}` → `{mapping['fhir_field']}`"
                        )
                    with h3:
                        st.markdown(conf_badge, unsafe_allow_html=True)

                    # Details expander
                    with st.expander("Details & Actions", expanded=False):
                        st.markdown(f"**Reasoning:** {mapping['reasoning']}")

                        # Action buttons
                        act1, act2, act3 = st.columns(3)

                        with act1:
                            if not is_cached:
                                if st.button(
                                    "✅ Approve",
                                    key=f"approve_{idx}",
                                    use_container_width=True,
                                ):
                                    approve_mapping(mapping)
                                    st.rerun()
                            else:
                                st.success("Approved", icon="✅")

                        with act2:
                            if st.button(
                                "✏️ Override",
                                key=f"override_btn_{idx}",
                                use_container_width=True,
                            ):
                                st.session_state[f"overriding_{idx}"] = True

                        with act3:
                            if is_cached:
                                if st.button(
                                    "🗑️ Remove",
                                    key=f"remove_{idx}",
                                    use_container_width=True,
                                ):
                                    remove_from_cache(mapping["concept"])
                                    st.rerun()

                        # Override form
                        if st.session_state.get(f"overriding_{idx}"):
                            with st.form(key=f"override_form_{idx}"):
                                st.markdown("**Override Mapping**")

                                fhir_resources = [
                                    "Patient", "Encounter", "Condition",
                                    "Observation", "Procedure",
                                    "MedicationRequest", "Practitioner",
                                    "Organization",
                                ]

                                new_res = st.selectbox(
                                    "FHIR Resource",
                                    fhir_resources,
                                    index=fhir_resources.index(mapping["fhir_resource"])
                                    if mapping["fhir_resource"] in fhir_resources
                                    else 0,
                                )
                                new_field = st.text_input(
                                    "FHIR Field",
                                    value=mapping["fhir_field"],
                                )
                                new_reason = st.text_area(
                                    "Reasoning",
                                    value="",
                                    placeholder="Why are you overriding this mapping?",
                                )

                                sub_col, can_col = st.columns(2)
                                with sub_col:
                                    submitted = st.form_submit_button(
                                        "💾 Save Override",
                                        use_container_width=True,
                                    )
                                with can_col:
                                    cancelled = st.form_submit_button(
                                        "Cancel",
                                        use_container_width=True,
                                    )

                                if submitted and new_reason:
                                    overridden = override_mapping(
                                        mapping["concept"],
                                        new_res,
                                        new_field,
                                        new_reason,
                                    )
                                    # Update in session state too
                                    mappings_data[idx] = overridden
                                    st.session_state["fhir_mappings"] = mappings_data
                                    del st.session_state[f"overriding_{idx}"]
                                    st.rerun()

                                if cancelled:
                                    del st.session_state[f"overriding_{idx}"]
                                    st.rerun()

                    st.markdown("---")

        with tab_json:
            st.json(mappings_data)

        # ── Bulk actions ──────────────────────────────────────────────
        st.markdown("### 💾 Save All Mappings")

        bulk1, bulk2 = st.columns(2)

        with bulk1:
            if st.button("✅ Approve All", use_container_width=True):
                for m in mappings_data:
                    approve_mapping(m)
                st.success(f"✅ All {len(mappings_data)} mappings approved and cached!")
                st.rerun()

        with bulk2:
            render_download_button(
                label="⬇️ Download mappings JSON",
                data=json.dumps(mappings_data, indent=2),
                file_name="fhir_mappings.json",
                mime="application/json",
                use_container_width=True,
            )

    # ── Cached mappings view ──────────────────────────────────────────
    if cached_mappings:
        st.markdown("---")
        st.markdown("### 🗂️ Mapping Cache")
        st.caption(
            f"{len(cached_mappings)} approved/overridden mapping(s) in "
            f"`knowledge/mapping_cache.json`"
        )

        # Show as a compact table
        import pandas as pd

        cache_df = pd.DataFrame(cached_mappings)
        display_cols = ["concept", "fhir_resource", "fhir_field", "confidence", "status"]
        available_cols = [c for c in display_cols if c in cache_df.columns]
        st.dataframe(cache_df[available_cols], use_container_width=True, hide_index=True)

        render_download_button(
            label="⬇️ Download mapping_cache.json",
            data=json.dumps(cached_mappings, indent=2),
            file_name="mapping_cache.json",
            mime="application/json",
        )


# =====================================================================
# PAGE: Analytics Model
# =====================================================================
elif page == "📊 Analytics Model":
    st.markdown('<p class="main-title">Analytics Model Generator</p>', unsafe_allow_html=True)
    st.caption(
        "Generate an analytics-ready star schema from approved FHIR mappings. "
        "Identify fact tables, dimensions, metrics, and drill-down attributes."
    )

    # ── Load prerequisites ────────────────────────────────────────────
    requirements_json = st.session_state.get("requirements_json") or _load_requirements()
    if requirements_json:
        st.session_state["requirements_json"] = requirements_json

    if not requirements_json:
        st.warning(
            "⚠️ No extracted requirements found. Please upload a PDF and "
            "run **Extract Requirements** on the Upload & Extract page first."
        )
        st.stop()

    from modules.analytics_generator import (
        generate_analytics_model,
        save_analytics_model,
        load_analytics_model,
        FHIR_TO_STAR,
    )

    decisions = _load_decisions()

    # ── FHIR→Star mapping reference ──────────────────────────────────
    with st.expander("🗺️ FHIR → Star Schema Mapping Rules", expanded=False):
        rule_cols = st.columns(2)
        facts = {k: v for k, v in FHIR_TO_STAR.items() if v.startswith("Fact")}
        dims = {k: v for k, v in FHIR_TO_STAR.items() if v.startswith("Dim")}
        with rule_cols[0]:
            st.markdown("**Fact Tables**")
            for fhir, star in facts.items():
                st.markdown(f"- `{fhir}` → **{star}**")
        with rule_cols[1]:
            st.markdown("**Dimension Tables**")
            for fhir, star in dims.items():
                st.markdown(f"- `{fhir}` → **{star}**")

    # ── Context summary ───────────────────────────────────────────────
    from modules.fhir_mapper import load_mapping_cache as _load_fhir_cache
    cached_mappings = _load_fhir_cache()

    ctx1, ctx2, ctx3 = st.columns(3)
    ctx1.metric("Approved FHIR Mappings", len(cached_mappings))
    ctx2.metric("Org Decisions", len(decisions))
    prev_model = load_analytics_model()
    ctx3.metric("Model Status", "✅ Saved" if prev_model else "⏳ Not Generated")

    if not cached_mappings:
        st.warning(
            "⚠️ No approved FHIR mappings found. Please generate and approve "
            "mappings on the **FHIR Mapping** page first."
        )
        st.stop()

    # ── Generate / Regenerate button ──────────────────────────────────
    st.markdown("---")

    gen_label = "🔄 Regenerate Analytics Model" if prev_model else "🧬 Generate Analytics Model"

    if st.button(gen_label, type="primary", use_container_width=True):
        try:
            with st.spinner("Building star schema with Gemini — identifying metrics, dimensions, and drill-down attributes…"):
                model = generate_analytics_model(requirements_json, decisions)

            st.session_state["analytics_model"] = model.model_dump()
            st.session_state["analytics_model_approved"] = False
            st.success(f"✅ Star schema generated — {len(model.fact_tables)} fact tables, {len(model.dimension_tables)} dimension tables, {len(model.metrics)} metrics")

        except EnvironmentError as env_err:
            st.error(f"⚠️ {env_err}")
        except ValueError as val_err:
            st.error(f"⚠️ {val_err}")
        except Exception as exc:
            st.error(f"❌ Generation failed: {exc}")

    # Load from disk if we don't have one in session
    if "analytics_model" not in st.session_state and prev_model:
        st.session_state["analytics_model"] = prev_model
        st.session_state["analytics_model_approved"] = True

    # ── Display the model ─────────────────────────────────────────────
    if "analytics_model" in st.session_state and st.session_state["analytics_model"]:
        model_data = st.session_state["analytics_model"]
        is_approved = st.session_state.get("analytics_model_approved", False)

        st.markdown("---")

        # Status header
        status_html = (
            '<span class="status-approved">✅ Approved & Saved</span>'
            if is_approved
            else '<span class="status-draft">📝 Draft — Review & Approve</span>'
        )
        st.markdown(
            f'<p class="schema-header">Star Schema Model</p> {status_html}',
            unsafe_allow_html=True,
        )

        # ── Summary metrics ───────────────────────────────────────────
        sm1, sm2, sm3, sm4, sm5 = st.columns(5)
        sm1.metric("Fact Tables", len(model_data.get("fact_tables", [])))
        sm2.metric("Dimensions", len(model_data.get("dimension_tables", [])))
        sm3.metric("Relationships", len(model_data.get("relationships", [])))
        sm4.metric("Metrics", len(model_data.get("metrics", [])))
        sm5.metric("Attributes", len(model_data.get("attributes", [])))

        # ── Tabs for different views ──────────────────────────────────
        tab_visual, tab_validation, tab_tables, tab_metrics, tab_json = st.tabs([
            "🗺️ Visual Schema",
            "🔍 Relationship Validation",
            "📋 Tables & Columns",
            "📈 Metrics & Attributes",
            "📄 Raw JSON",
        ])

        # ── TAB: Visual Schema ────────────────────────────────────────
        with tab_visual:
            st.markdown("#### 🏗️ Star Schema Diagram")

            # Build a visual diagram using columns and HTML
            fact_tables = model_data.get("fact_tables", [])
            dim_tables = model_data.get("dimension_tables", [])
            relationships = model_data.get("relationships", [])

            # Dimension cards at the top
            if dim_tables:
                st.markdown("##### 📐 Dimension Tables")
                dim_cols = st.columns(min(len(dim_tables), 4))
                for idx, dim in enumerate(dim_tables):
                    col = dim_cols[idx % min(len(dim_tables), 4)]
                    with col:
                        cols_html = "".join(
                            f'<span class="col-tag">{c["name"]} <span class="col-type">{c.get("data_type", "")}</span></span>'
                            for c in dim.get("columns", [])[:8]
                        )
                        extra = len(dim.get("columns", [])) - 8
                        if extra > 0:
                            cols_html += f'<span class="col-tag">+{extra} more</span>'

                        st.markdown(
                            f'<div class="dim-card">'
                            f'<h4>📐 {dim["name"]}</h4>'
                            f'<div style="color:#94a3b8;font-size:0.75rem;">'
                            f'Source: {dim.get("source_fhir_resource", "—")}</div>'
                            f'<div class="desc">{dim.get("description", "")}</div>'
                            f'<div style="margin-top:8px">{cols_html}</div>'
                            f'</div>',
                            unsafe_allow_html=True,
                        )

            # Relationships
            if relationships:
                st.markdown("##### 🔗 Relationships")
                for rel in relationships:
                    st.markdown(
                        f'<div class="rel-row">'
                        f'<strong>{rel["fact_table"]}</strong>'
                        f'<span class="arrow"> ──⟨ {rel.get("relationship_type", "M:1")} ⟩── </span>'
                        f'<strong>{rel["dimension_table"]}</strong>'
                        f' &nbsp; ON &nbsp; <span class="key">{rel["join_key"]}</span>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

            # Fact table cards at the bottom
            if fact_tables:
                st.markdown("##### 📊 Fact Tables")
                fact_cols = st.columns(min(len(fact_tables), 3))
                for idx, fact in enumerate(fact_tables):
                    col = fact_cols[idx % min(len(fact_tables), 3)]
                    with col:
                        cols_html = "".join(
                            f'<span class="col-tag">{c["name"]} <span class="col-type">{c.get("data_type", "")}</span></span>'
                            for c in fact.get("columns", [])[:10]
                        )
                        extra = len(fact.get("columns", [])) - 10
                        if extra > 0:
                            cols_html += f'<span class="col-tag">+{extra} more</span>'

                        st.markdown(
                            f'<div class="fact-card">'
                            f'<h4>📊 {fact["name"]}</h4>'
                            f'<div style="color:#94a3b8;font-size:0.75rem;">'
                            f'Source: {fact.get("source_fhir_resource", "—")}</div>'
                            f'<div class="grain">Grain: {fact.get("grain", "—")}</div>'
                            f'<div class="desc">{fact.get("description", "")}</div>'
                            f'<div style="margin-top:8px">{cols_html}</div>'
                            f'</div>',
                            unsafe_allow_html=True,
                        )

        # ── TAB: Relationship Validation ──────────────────────────────
        with tab_validation:
            st.markdown("#### 🔍 Semantic Model Relationship Auditor")
            st.caption(
                "Power BI semantic models require conflict-free directed acyclic schemas. "
                "Below is an audit of your relationship model."
            )

            from modules.relationship_validator import validate_relationships
            issues_list = validate_relationships(model_data)

            # Split issues by category
            dup_issues = [i for i in issues_list if "Duplicate" in i["issue"]]
            ambig_issues = [i for i in issues_list if "Ambiguous" in i["issue"] or "Multiple active" in i["issue"] or "Circular" in i["issue"]]
            card_issues = [i for i in issues_list if "cardinality" in i["issue"] or "Fact-to-fact" in i["issue"]]
            other_issues = [i for i in issues_list if i not in dup_issues and i not in ambig_issues and i not in card_issues]

            # Summary Metrics Row
            err_count = sum(1 for i in issues_list if i["status"] == "Error")
            warn_count = sum(1 for i in issues_list if i["status"] == "Warning")
            
            c_m1, c_m2, c_m3 = st.columns(3)
            c_m1.metric("Validation Status", "Passed ✅" if err_count == 0 else "Failed ❌")
            c_m2.metric("Critical Errors", err_count)
            c_m3.metric("Warnings", warn_count)

            st.markdown("---")

            # 🗺️ Relationship Diagram Section
            st.markdown("##### 🗺️ Relationship Diagram")
            st.caption("Active relationships are solid lines. Inactive paths are dotted lines. Red/orange highlights indicate issues.")
            
            # Generate dynamic Mermaid diagram
            lines = ["graph TD"]
            fact_tables_list = model_data.get("fact_tables", [])
            dim_tables_list = model_data.get("dimension_tables", [])
            relationships_list = model_data.get("relationships", [])
            
            # Nodes
            for f in fact_tables_list:
                lines.append(f'    {f["name"]}["📊 {f["name"]}"]')
            for d in dim_tables_list:
                lines.append(f'    {d["name"]}["📐 {d["name"]}"]')
            
            # Build lookups for links
            seen_pairs = set()
            link_index = 0
            link_styles = []
            
            for rel in relationships_list:
                ft = rel.get("fact_table", "")
                dt = rel.get("dimension_table", "")
                jk = rel.get("join_key", "")
                card = rel.get("relationship_type", "many-to-one")
                
                pair_key = (ft, dt)
                is_active = pair_key not in seen_pairs
                seen_pairs.add(pair_key)
                
                # Check if this specific relationship has an issue
                has_error = False
                has_warning = False
                for issue in issues_list:
                    if ft in issue["relationship"] and dt in issue["relationship"]:
                        if issue["status"] == "Error":
                            has_error = True
                        elif issue["status"] == "Warning":
                            has_warning = True
                            
                arrow = "-->" if is_active else "-.->"
                card_label = f"{card} ({jk})"
                
                lines.append(f'    {ft} {arrow}|"{card_label}"| {dt}')
                
                # Style links
                if has_error:
                    link_styles.append(f"    linkStyle {link_index} stroke:#ef4444,stroke-width:3px;")
                elif has_warning:
                    link_styles.append(f"    linkStyle {link_index} stroke:#f59e0b,stroke-width:3px;")
                elif not is_active:
                    link_styles.append(f"    linkStyle {link_index} stroke:#94a3b8,stroke-width:2px,stroke-dasharray: 5 5;")
                else:
                    link_styles.append(f"    linkStyle {link_index} stroke:#3b82f6,stroke-width:2px;")
                
                link_index += 1
                
            # Class definitions
            lines.append("    classDef fact fill:#0f172a,stroke:#3b82f6,stroke-width:2px,color:#f8fafc;")
            lines.append("    classDef dim fill:#062f17,stroke:#16a34a,stroke-width:2px,color:#f8fafc;")
            
            for f in fact_tables_list:
                lines.append(f'    class {f["name"]} fact;')
            for d in dim_tables_list:
                lines.append(f'    class {d["name"]} dim;')
                
            # Append link styles
            lines.extend(link_styles)
            
            mermaid_code = "\n".join(lines)
            st.markdown(f"```mermaid\n{mermaid_code}\n```")

            st.markdown("---")

            # ── Display Duplicate Relationships
            st.markdown("##### 👯 Duplicate Relationships")
            if not dup_issues:
                st.success("No duplicate relationships found.")
            else:
                for issue in dup_issues:
                    st.error(f"**Relationship:** {issue['relationship']}  \n**Issue:** {issue['issue']}  \n**Recommendation:** {issue['recommendation']}")

            st.markdown("---")

            # ── Display Ambiguous Paths
            st.markdown("##### 🔄 Ambiguous Paths & Loops")
            if not ambig_issues:
                st.success("No circular dependencies or ambiguous loop paths found.")
            else:
                for issue in ambig_issues:
                    if issue["status"] == "Error":
                        st.error(f"**Path:** {issue['relationship']}  \n**Issue:** {issue['issue']}  \n**Recommendation:** {issue['recommendation']}")
                    else:
                        st.warning(f"**Path:** {issue['relationship']}  \n**Issue:** {issue['issue']}  \n**Recommendation:** {issue['recommendation']}")

            st.markdown("---")

            # ── Display Cardinality Issues
            st.markdown("##### 📐 Cardinality & Star Schema Violations")
            if not card_issues:
                st.success("All cardinalities align with star schema standards.")
            else:
                for issue in card_issues:
                    if issue["status"] == "Error":
                        st.error(f"**Relationship:** {issue['relationship']}  \n**Issue:** {issue['issue']}  \n**Recommendation:** {issue['recommendation']}")
                    else:
                        st.warning(f"**Relationship:** {issue['relationship']}  \n**Issue:** {issue['issue']}  \n**Recommendation:** {issue['recommendation']}")

            # ── Display Other Issues (e.g. missing keys)
            if other_issues:
                st.markdown("---")
                st.markdown("##### ⚠️ Other Validation Issues")
                for issue in other_issues:
                    st.error(f"**Target:** {issue['relationship']}  \n**Issue:** {issue['issue']}  \n**Recommendation:** {issue['recommendation']}")

        # ── TAB: Tables & Columns ─────────────────────────────────────
        with tab_tables:
            st.markdown("#### 📊 Fact Tables")
            for fact in model_data.get("fact_tables", []):
                with st.expander(
                    f"📊 {fact['name']} — {fact.get('source_fhir_resource', '')}",
                    expanded=False,
                ):
                    st.markdown(f"**Description:** {fact.get('description', '—')}")
                    st.markdown(f"**Grain:** {fact.get('grain', '—')}")

                    if fact.get("columns"):
                        import pandas as pd
                        col_df = pd.DataFrame(fact["columns"])
                        st.dataframe(col_df, use_container_width=True, hide_index=True)

            st.markdown("---")
            st.markdown("#### 📐 Dimension Tables")
            for dim in model_data.get("dimension_tables", []):
                with st.expander(
                    f"📐 {dim['name']} — {dim.get('source_fhir_resource', '')}",
                    expanded=False,
                ):
                    st.markdown(f"**Description:** {dim.get('description', '—')}")

                    if dim.get("columns"):
                        import pandas as pd
                        col_df = pd.DataFrame(dim["columns"])
                        st.dataframe(col_df, use_container_width=True, hide_index=True)

        # ── TAB: Metrics & Attributes ─────────────────────────────────
        with tab_metrics:
            st.markdown("#### 📈 Business Metrics")
            metrics_list = model_data.get("metrics", [])

            if not metrics_list:
                st.info("No metrics defined in this model.")
            else:
                for metric in metrics_list:
                    with st.expander(
                        f"📈 {metric['name']}",
                        expanded=False,
                    ):
                        st.markdown(f"**Description:** {metric.get('description', '—')}")
                        st.code(metric.get("formula", "—"), language="sql")
                        st.markdown(f"**Fact Table:** `{metric.get('fact_table', '—')}`")

                        dims_for_metric = metric.get("dimensions", [])
                        if dims_for_metric:
                            pills = "".join(
                                f'<span class="metric-pill">{d}</span>'
                                for d in dims_for_metric
                            )
                            st.markdown(
                                f"**Slice by:** {pills}",
                                unsafe_allow_html=True,
                            )

            st.markdown("---")
            st.markdown("#### 🔍 Drill-Down Attributes")
            attrs_list = model_data.get("attributes", [])

            if not attrs_list:
                st.info("No drill-down attributes defined.")
            else:
                for attr in attrs_list:
                    drill = " → ".join(attr.get("drill_path", []))
                    chips = "".join(
                        f'<span class="attr-chip">{step}</span>'
                        for step in attr.get("drill_path", [])
                    )
                    st.markdown(
                        f"**{attr['name']}** "
                        f"(`{attr.get('table', '—')}`) — "
                        f"{attr.get('description', '')}  \n"
                        f"{chips}",
                        unsafe_allow_html=True,
                    )

        # ── TAB: Raw JSON ─────────────────────────────────────────────
        with tab_json:
            st.json(model_data)

        # ── Approval / Save actions ───────────────────────────────────
        st.markdown("---")
        st.markdown("### 💾 Approve & Save")

        action1, action2, action3 = st.columns(3)

        with action1:
            if not is_approved:
                if st.button(
                    "✅ Approve & Save Model",
                    type="primary",
                    use_container_width=True,
                ):
                    try:
                        from modules.schemas import AnalyticsModel
                        validated = AnalyticsModel.model_validate(model_data)
                        saved_path = save_analytics_model(validated)
                        st.session_state["analytics_model_approved"] = True
                        st.success(f"✅ Model approved and saved to `{saved_path}`")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"❌ Save failed: {exc}")
            else:
                st.success("✅ Model is approved and saved", icon="✅")

        with action2:
            render_download_button(
                label="⬇️ Download analytics_model.json",
                data=json.dumps(model_data, indent=2),
                file_name="analytics_model.json",
                mime="application/json",
                use_container_width=True,
            )

        with action3:
            if is_approved:
                if st.button(
                    "🔓 Unlock for Re-generation",
                    use_container_width=True,
                ):
                    st.session_state["analytics_model_approved"] = False
                    st.rerun()


# =====================================================================
# PAGE: Model Validator
# =====================================================================
elif page == "🛡️ Model Validator":
    st.markdown('<p class="main-title">Model Validator</p>', unsafe_allow_html=True)
    st.caption(
        "Audit and enforce Power BI compliance on the generated analytics model schema. "
        "Ensures a valid star schema configuration before project folder compilation."
    )

    from modules.analytics_generator import load_analytics_model
    from modules.relationship_validator import validate_relationships
    from modules.star_schema_enforcer import enforce_and_regenerate

    model_data = st.session_state.get("analytics_model") or load_analytics_model()

    if not model_data:
        st.warning(
            "⚠️ No analytics model found. Please generate the model on the "
            "**📊 Analytics Model** page first."
        )
        st.stop()

    # Run auditor on current model_data
    issues_list = validate_relationships(model_data)
    err_count = sum(1 for i in issues_list if i["status"] == "Error")
    warn_count = sum(1 for i in issues_list if i["status"] == "Warning")

    # Metrics layout
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Validation Status", "Passed ✅" if err_count == 0 else "Violated ❌")
    m2.metric("Critical Errors", err_count)
    m3.metric("Warnings", warn_count)
    m4.metric("Total Relationships", len(model_data.get("relationships", [])))

    st.markdown("---")

    # 🗺️ Relationship Graph Section
    st.markdown("##### 🗺️ Relationship Graph")
    st.caption("Solid lines are active relationships. Dashed lines are inactive. Relationships with errors/warnings are colored.")

    fact_tables_list = model_data.get("fact_tables", [])
    dim_tables_list = model_data.get("dimension_tables", [])
    relationships_list = model_data.get("relationships", [])

    if not relationships_list:
        st.info("No relationships defined in the model to visualize.")
    else:
        # Generate dynamic Mermaid diagram
        lines = ["graph TD"]
        for f in fact_tables_list:
            lines.append(f'    {f["name"]}["📊 {f["name"]}"]')
        for d in dim_tables_list:
            lines.append(f'    {d["name"]}["📐 {d["name"]}"]')

        seen_pairs = set()
        link_index = 0
        link_styles = []

        for rel in relationships_list:
            ft = rel.get("fact_table", "")
            dt = rel.get("dimension_table", "")
            jk = rel.get("join_key", "")
            card = rel.get("relationship_type", "many-to-one")
            is_active = rel.get("is_active", True)
            
            pair_key = (ft, dt)
            
            # Check for issues with this relationship
            has_error = False
            has_warning = False
            for issue in issues_list:
                if ft in issue["relationship"] and dt in issue["relationship"]:
                    if issue["status"] == "Error":
                        has_error = True
                    elif issue["status"] == "Warning":
                        has_warning = True
                        
            arrow = "-->" if is_active else "-.->"
            card_label = f"{card} ({jk})"
            lines.append(f'    {ft} {arrow}|"{card_label}"| {dt}')
            
            if has_error:
                link_styles.append(f"    linkStyle {link_index} stroke:#ef4444,stroke-width:3px;")
            elif has_warning:
                link_styles.append(f"    linkStyle {link_index} stroke:#f59e0b,stroke-width:3px;")
            elif not is_active:
                link_styles.append(f"    linkStyle {link_index} stroke:#94a3b8,stroke-width:2px,stroke-dasharray: 5 5;")
            else:
                link_styles.append(f"    linkStyle {link_index} stroke:#3b82f6,stroke-width:2px;")
            link_index += 1

        lines.append("    classDef fact fill:#0f172a,stroke:#3b82f6,stroke-width:2px,color:#f8fafc;")
        lines.append("    classDef dim fill:#062f17,stroke:#16a34a,stroke-width:2px,color:#f8fafc;")
        for f in fact_tables_list:
            lines.append(f'    class {f["name"]} fact;')
        for d in dim_tables_list:
            lines.append(f'    class {d["name"]} dim;')
        lines.extend(link_styles)

        mermaid_code = "\n".join(lines)
        st.markdown(f"```mermaid\n{mermaid_code}\n```")

    st.markdown("---")

    # Display Fact & Dimension Components
    st.markdown("### 🗂️ Model Components")
    col_facts, col_dims = st.columns(2)
    
    with col_facts:
        st.markdown("#### 📊 Fact Tables")
        for fact in fact_tables_list:
            cols_html = "".join(
                f'<span class="col-tag">{c["name"]} <span class="col-type">{c.get("data_type", "")}</span></span>'
                for c in fact.get("columns", [])
            )
            st.markdown(
                f'<div class="fact-card">'
                f'<h4>📊 {fact["name"]}</h4>'
                f'<div style="color:#94a3b8;font-size:0.75rem;">Source: {fact.get("source_fhir_resource", "—")}</div>'
                f'<div class="grain">Grain: {fact.get("grain", "—")}</div>'
                f'<div class="desc">{fact.get("description", "")}</div>'
                f'<div style="margin-top:8px">{cols_html}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
            
    with col_dims:
        st.markdown("#### 📐 Dimension Tables")
        for dim in dim_tables_list:
            cols_html = "".join(
                f'<span class="col-tag">{c["name"]} <span class="col-type">{c.get("data_type", "")}</span></span>'
                for c in dim.get("columns", [])
            )
            st.markdown(
                f'<div class="dim-card">'
                f'<h4>📐 {dim["name"]}</h4>'
                f'<div style="color:#94a3b8;font-size:0.75rem;">Source: {dim.get("source_fhir_resource", "—")}</div>'
                f'<div class="desc">{dim.get("description", "")}</div>'
                f'<div style="margin-top:8px">{cols_html}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

    st.markdown("---")

    # ── Display Violations & Compliance Findings
    st.markdown("### 🚨 Violations & Compliance Findings")
    if not issues_list:
        st.success("🎉 No violations found! The model is fully compliant with Power BI star schema specifications.")
    else:
        for issue in issues_list:
            if issue["status"] == "Error":
                st.error(
                    f"**Relationship/Path:** {issue['relationship']}  \n"
                    f"**Issue:** {issue['issue']}  \n"
                    f"**Recommendation:** {issue['recommendation']}"
                )
            elif issue["status"] == "Warning":
                st.warning(
                    f"**Relationship/Path:** {issue['relationship']}  \n"
                    f"**Issue:** {issue['issue']}  \n"
                    f"**Recommendation:** {issue['recommendation']}"
                )
            else:
                st.info(
                    f"**Relationship/Path:** {issue['relationship']}  \n"
                    f"**Issue:** {issue['issue']}  \n"
                    f"**Recommendation:** {issue['recommendation']}"
                )

    st.markdown("---")

    # ── Auto-Correction Section
    st.markdown("### 🔧 Auto-Correction Control")
    st.caption(
        "Clicking auto-correct will run the enforcement engine to automatically fix duplicate relationships, "
        "fact-to-fact connections, circular dependencies, multiple active paths, and invalid cardinalities. "
        "It will update the model file, compile PBIP, and re-run validation."
    )

    if st.button("🛠️ Run Star Schema Auto-Correction", type="primary", use_container_width=True):
        with st.spinner("Executing Star Schema Enforcement Engine..."):
            try:
                results = enforce_and_regenerate()
                
                # Update session states and refresh page
                st.session_state["analytics_model"] = load_analytics_model()
                st.session_state["enforcer_applied_fixes"] = results["fixes"]
                
                if "pbip_results" in st.session_state:
                    st.session_state["pbip_results"] = results["compile_result"]
                    
                st.success("✅ Auto-correction ran successfully! Model and PBIP have been updated.")
                st.rerun()
            except Exception as e:
                st.error(f"❌ Auto-correction failed: {e}")

    # Show applied fixes if they exist
    if "enforcer_applied_fixes" in st.session_state:
        st.markdown("#### 🛠️ Auto-fixes Applied (Last Run)")
        fixes = st.session_state["enforcer_applied_fixes"]
        if not fixes:
            st.info("No fixes were needed or applied in the last run.")
        else:
            fixes_table = []
            for f in fixes:
                fixes_table.append({
                    "Issue": f.get("issue", ""),
                    "Severity": f.get("severity", ""),
                    "Auto-Fix": f.get("auto_fix", ""),
                    "Status": f.get("status", "")
                })
            import pandas as pd
            st.dataframe(pd.DataFrame(fixes_table), use_container_width=True, hide_index=True)


# =====================================================================
# PAGE: Report Layout Validator
# =====================================================================
elif page == "🎨 Report Layout Validator":
    st.markdown('<p class="main-title">Report Layout Validator</p>', unsafe_allow_html=True)
    st.caption(
        "Validate the generated report.Report/report.json layout against the compiled semantic model. "
        "Ensures all visuals, fields, and measures are structurally sound to prevent Power BI load errors."
    )

    from modules.report_layout_validator import validate_report_layout_from_files, auto_correct_report_layout
    from modules.analytics_generator import load_analytics_model
    from modules.file_manager import OUTPUT_DIR

    # Load report definition
    report_def_path = OUTPUT_DIR / "report_definition.json"
    if not report_def_path.exists():
        st.warning("⚠️ No report definition found. Please complete the **📝 Report Definition** page first.")
        st.stop()
        
    with open(report_def_path, "r", encoding="utf-8") as f:
        report_def = json.load(f)

    # Run layout validation
    issues_list = validate_report_layout_from_files()
    err_count = sum(1 for i in issues_list if i["status"] == "Error")
    warn_count = sum(1 for i in issues_list if i["status"] == "Warning")

    # Metrics layout
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Validation Status", "Passed ✅" if err_count == 0 else "Violated ❌")
    m2.metric("Critical Errors", err_count)
    m3.metric("Warnings", warn_count)
    
    # Calculate total visuals
    total_visuals = sum(len(p.get("visuals", [])) for p in report_def.get("pages", []))
    m4.metric("Total Visuals", total_visuals)

    st.markdown("---")

    # ── Display Layout Structure
    st.markdown("### 📋 Report Pages & Visual Layout")
    for page_idx, p in enumerate(report_def.get("pages", [])):
        with st.expander(f"📄 Page: {p['page_name']} — {p.get('purpose', '')}", expanded=(page_idx == 0)):
            for v in p.get("visuals", []):
                v_title = v.get("title", "")
                v_type = v.get("visual_type", "")
                dims = v.get("dimensions", [])
                meas = v.get("measures", [])
                
                # Check if this specific visual has issues
                v_issues = [i for i in issues_list if i["visual"] == v_title]
                has_v_error = any(i["status"] == "Error" for i in v_issues)
                
                border_color = "#ef4444" if has_v_error else "#4338ca"
                bg_gradient = "linear-gradient(135deg, #2d1616 0%, #1e0f0f 100%)" if has_v_error else "linear-gradient(135deg, #161a2e 0%, #0f101e 100%)"
                
                # Render visual card
                cols_html = "".join(f'<span class="col-tag">{d}</span>' for d in dims)
                meas_html = "".join(f'<span class="metric-pill">{m}</span>' for m in meas)
                
                st.markdown(
                    f'<div style="border:1px solid {border_color};background:{bg_gradient};border-radius:10px;padding:12px;margin-bottom:10px;">'
                    f'<h5 style="margin:0 0 6px 0;color:#c4b5fd;">📊 {v_title} <span class="visual-rec" style="font-size:0.72rem;margin-left:10px;">{v_type}</span></h5>'
                    f'<div style="font-size:0.8rem;color:#cbd5e1;">'
                    f'<strong>Dimensions:</strong> {cols_html if dims else "None"}  \n'
                    f'<strong>Measures:</strong> {meas_html if meas else "None"}'
                    f'</div>'
                    f'</div>',
                    unsafe_allow_html=True
                )
                
                # Show errors for this visual directly under the card
                for issue in v_issues:
                    if issue["status"] == "Error":
                        st.error(f"❌ {issue['issue']} (Recommendation: {issue['recommendation']})")
                    else:
                        st.warning(f"⚠️ {issue['issue']} (Recommendation: {issue['recommendation']})")

    st.markdown("---")

    # ── Display Overall Violations & Findings
    st.markdown("### 🚨 Layout Violations & Findings")
    if not issues_list:
        st.success("🎉 All layout checks passed! Visual configurations align perfectly with the semantic model.")
    else:
        for issue in issues_list:
            # Exclude page-grouped visuals to avoid duplicate display
            is_visual_specific = any(v.get("title") == issue["visual"] for p in report_def.get("pages", []) for v in p.get("visuals", []))
            if not is_visual_specific:
                if issue["status"] == "Error":
                    st.error(f"**Visual:** {issue['visual']}  \n**Issue:** {issue['issue']}  \n**Recommendation:** {issue['recommendation']}")
                else:
                    st.warning(f"**Visual:** {issue['visual']}  \n**Issue:** {issue['issue']}  \n**Recommendation:** {issue['recommendation']}")

    st.markdown("---")

    # ── Auto-Correction Section
    st.markdown("### 🔧 Layout Auto-Correction Control")
    st.caption(
        "Clicking auto-correct will scan all visual bindings in report_definition.json and synchronize them "
        "with the current model.bim. Missing tables (e.g. FactObservation) will be remapped to valid ones (e.g. FactDetermination), "
        "measure references will be updated to their override versions, and visual type constraints will be enforced. "
        "It will compile the project and re-run validation."
    )

    if st.button("🛠️ Run Report Layout Auto-Correction", type="primary", use_container_width=True):
        with st.spinner("Executing Report Layout Auto-Correction Engine..."):
            try:
                fixes, results = auto_correct_report_layout()
                
                # Update session states and refresh page
                st.session_state["report_layout_applied_fixes"] = fixes
                if "pbip_results" in st.session_state:
                    st.session_state["pbip_results"] = results["compile_result"]
                    
                st.success("✅ Report layout auto-corrected and recompiled successfully!")
                st.rerun()
            except Exception as e:
                st.error(f"❌ Auto-correction failed: {e}")

    # Show applied fixes if they exist
    if "report_layout_applied_fixes" in st.session_state:
        st.markdown("#### 🛠️ Auto-fixes Applied (Last Run)")
        fixes = st.session_state["report_layout_applied_fixes"]
        if not fixes:
            st.info("No fixes were needed or applied in the last run.")
        else:
            fixes_table = []
            for f in fixes:
                fixes_table.append({
                    "Visual": f.get("visual", ""),
                    "Issue": f.get("issue", ""),
                    "Fix Applied": f.get("fix_applied", "")
                })
            import pandas as pd
            st.dataframe(pd.DataFrame(fixes_table), use_container_width=True, hide_index=True)


# =====================================================================
# PAGE: Reporting Intent
# =====================================================================
elif page == "🎯 Reporting Intent":
    st.markdown('<p class="main-title">Reporting Intent Engine</p>', unsafe_allow_html=True)
    st.caption(
        "Classify each CMS requirement by reporting intent before report generation. "
        "Determines whether CMS requires a table, KPI, trend, comparison, or submission dataset."
    )

    # ── Load prerequisites ────────────────────────────────────────────
    requirements_json = st.session_state.get("requirements_json") or _load_requirements()
    if requirements_json:
        st.session_state["requirements_json"] = requirements_json

    if not requirements_json:
        st.warning(
            "⚠️ No extracted requirements found. Please upload a PDF and "
            "run **Extract Requirements** on the Upload & Extract page first."
        )
        st.stop()

    from modules.intent_classifier import (
        generate_reporting_intents,
        save_reporting_intents,
        load_reporting_intents,
        INTENT_VISUAL_MAP,
        VALID_INTENTS,
    )
    from modules.analytics_generator import load_analytics_model as _load_am_intent

    decisions = _load_decisions()
    analytics_model = _load_am_intent()

    # ── Context summary ───────────────────────────────────────────────
    req_count = sum(
        len(requirements_json.get(k, []))
        for k in ["metrics", "dimensions", "filters", "business_rules", "exclusions"]
    )
    ctx1, ctx2, ctx3 = st.columns(3)
    ctx1.metric("CMS Requirements", req_count)
    ctx2.metric("Analytics Model", "✅ Ready" if analytics_model else "❌ Missing")
    prev_intents = load_reporting_intents()
    ctx3.metric("Intent Status", f"✅ {len(prev_intents)} classified" if prev_intents else "⏳ Not Classified")

    if not analytics_model:
        st.warning(
            "⚠️ No analytics model found. Please generate and approve "
            "the model on the **Analytics Model** page first."
        )
        st.stop()

    # ── Intent → Visual reference ────────────────────────────────────
    with st.expander("🗺️ Intent → Visual Recommendation Map", expanded=False):
        ref_cols = st.columns(2)
        items = list(INTENT_VISUAL_MAP.items())
        mid = (len(items) + 1) // 2
        for idx, (intent, visual) in enumerate(items):
            col = ref_cols[0] if idx < mid else ref_cols[1]
            label = intent.replace("_", " ").title()
            with col:
                st.markdown(f"- **{label}** → `{visual}`")

    # ── Generate / Regenerate button ──────────────────────────────────
    st.markdown("---")

    gen_label = (
        "🔄 Re-classify Intents"
        if prev_intents
        else "🎯 Classify Reporting Intents"
    )

    if st.button(gen_label, type="primary", use_container_width=True):
        try:
            with st.spinner(
                "Classifying requirements with Gemini — "
                "determining reporting intent for each CMS data element…"
            ):
                intents = generate_reporting_intents(requirements_json, decisions)

            st.session_state["reporting_intents"] = [i.model_dump() for i in intents]
            st.session_state["intents_approved"] = False
            st.success(f"✅ Classified {len(intents)} requirements into reporting intents")

        except EnvironmentError as env_err:
            st.error(f"⚠️ {env_err}")
        except ValueError as val_err:
            st.error(f"⚠️ {val_err}")
        except Exception as exc:
            st.error(f"❌ Classification failed: {exc}")

    # Load from disk if not in session
    if "reporting_intents" not in st.session_state and prev_intents:
        st.session_state["reporting_intents"] = prev_intents
        st.session_state["intents_approved"] = True

    # ── Display intents ─────────────────────────────────────────────
    if "reporting_intents" in st.session_state and st.session_state["reporting_intents"]:
        intents_data = st.session_state["reporting_intents"]
        is_approved = st.session_state.get("intents_approved", False)

        st.markdown("---")

        # Status header
        status_html = (
            '<span class="status-approved">✅ Approved & Saved</span>'
            if is_approved
            else '<span class="status-draft">📝 Draft — Review & Approve</span>'
        )
        st.markdown(
            f'<p class="schema-header">Reporting Intent Classification</p> {status_html}',
            unsafe_allow_html=True,
        )

        # ── Summary by intent type ─────────────────────────────────
        from collections import Counter
        intent_counts = Counter(i.get("intent", "unknown") for i in intents_data)

        # Show top-level metrics for up to 8 intent types
        sorted_intents = intent_counts.most_common(8)
        if sorted_intents:
            metric_cols = st.columns(min(len(sorted_intents), 4))
            for idx, (intent_name, count) in enumerate(sorted_intents):
                col = metric_cols[idx % min(len(sorted_intents), 4)]
                label = intent_name.replace("_", " ").title()
                col.metric(label, count)

        # ── Tabs ───────────────────────────────────────────────────
        tab_cards, tab_table, tab_json = st.tabs([
            "🎯 Intent Cards",
            "🗏️ Summary Table",
            "📄 Raw JSON",
        ])

        # ── TAB: Intent Cards ─────────────────────────────────────
        with tab_cards:
            # Group by intent type
            intent_groups = {}
            for item in intents_data:
                key = item.get("intent", "unknown")
                intent_groups.setdefault(key, []).append(item)

            for intent_type, items in sorted(intent_groups.items()):
                label = intent_type.replace("_", " ").title()
                visual = INTENT_VISUAL_MAP.get(intent_type, "Unknown")

                with st.expander(
                    f"🎯 {label} — {len(items)} requirements → {visual}",
                    expanded=False,
                ):
                    for idx, item in enumerate(items):
                        intent_cls = item.get("intent", "unknown")
                        cols_html = "".join(
                            f'<span class="col-req">{c}</span>'
                            for c in item.get("required_columns", [])[:10]
                        )
                        extra_cols = len(item.get("required_columns", [])) - 10
                        if extra_cols > 0:
                            cols_html += f'<span class="col-req">+{extra_cols} more</span>'

                        st.markdown(
                            f'<div class="intent-card">'
                            f'<div class="req-text">{item.get("requirement", "")}</div>'
                            f'<span class="intent-badge intent-{intent_cls}">{label}</span>'
                            f'<span class="visual-rec">{item.get("recommended_visual", visual)}</span>'
                            f'<div style="margin-top:6px">{cols_html}</div>'
                            f'<div style="color:#78716c;font-size:0.75rem;margin-top:6px;">'
                            f'{item.get("reasoning", "")}</div>'
                            f'</div>',
                            unsafe_allow_html=True,
                        )

                        # Override button
                        if not is_approved:
                            # Find global index for this item
                            global_idx = intents_data.index(item)
                            if st.button(
                                "✏️ Override Intent",
                                key=f"override_intent_{intent_type}_{idx}",
                            ):
                                st.session_state[f"overriding_intent_{global_idx}"] = True

                            if st.session_state.get(f"overriding_intent_{global_idx}"):
                                with st.form(key=f"intent_override_form_{global_idx}"):
                                    intent_labels = [
                                        i.replace("_", " ").title() for i in VALID_INTENTS
                                    ]
                                    current_idx = (
                                        VALID_INTENTS.index(intent_cls)
                                        if intent_cls in VALID_INTENTS
                                        else 0
                                    )
                                    new_intent_label = st.selectbox(
                                        "New Intent",
                                        intent_labels,
                                        index=current_idx,
                                    )
                                    new_intent = VALID_INTENTS[
                                        intent_labels.index(new_intent_label)
                                    ]
                                    new_visual = INTENT_VISUAL_MAP.get(
                                        new_intent, "Table"
                                    )
                                    st.markdown(
                                        f"Recommended visual: **{new_visual}**"
                                    )

                                    sub_c, can_c = st.columns(2)
                                    with sub_c:
                                        submitted = st.form_submit_button(
                                            "💾 Save Override",
                                            use_container_width=True,
                                        )
                                    with can_c:
                                        cancelled = st.form_submit_button(
                                            "Cancel",
                                            use_container_width=True,
                                        )

                                    if submitted:
                                        intents_data[global_idx]["intent"] = new_intent
                                        intents_data[global_idx]["recommended_visual"] = new_visual
                                        intents_data[global_idx]["reasoning"] = (
                                            f"[SME Override] Changed to {new_intent_label}. "
                                            + intents_data[global_idx].get("reasoning", "")
                                        )
                                        st.session_state["reporting_intents"] = intents_data
                                        del st.session_state[f"overriding_intent_{global_idx}"]
                                        st.rerun()

                                    if cancelled:
                                        del st.session_state[f"overriding_intent_{global_idx}"]
                                        st.rerun()

        # ── TAB: Summary Table ────────────────────────────────────
        with tab_table:
            import pandas as pd
            df = pd.DataFrame(intents_data)
            display_cols = ["requirement", "intent", "recommended_visual", "reasoning"]
            available = [c for c in display_cols if c in df.columns]
            st.dataframe(
                df[available],
                use_container_width=True,
                hide_index=True,
                height=600,
            )

        # ── TAB: Raw JSON ─────────────────────────────────────────
        with tab_json:
            st.json(intents_data)

        # ── Approval / Save actions ─────────────────────────────────
        st.markdown("---")
        st.markdown("### 💾 Approve & Save")

        act1, act2, act3 = st.columns(3)

        with act1:
            if not is_approved:
                if st.button(
                    "✅ Approve & Save Intents",
                    key="approve_intents",
                    type="primary",
                    use_container_width=True,
                ):
                    try:
                        saved_path = save_reporting_intents(intents_data)
                        st.session_state["intents_approved"] = True
                        st.success(f"✅ Intents approved and saved to `{saved_path}`")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"❌ Save failed: {exc}")
            else:
                st.success("✅ Intents are approved and saved", icon="✅")

        with act2:
            render_download_button(
                label="⬇️ Download reporting_intent.json",
                data=json.dumps(intents_data, indent=2),
                file_name="reporting_intent.json",
                mime="application/json",
                use_container_width=True,
            )

        with act3:
            if is_approved:
                if st.button(
                    "🔓 Unlock for Re-classification",
                    key="unlock_intents",
                    use_container_width=True,
                ):
                    st.session_state["intents_approved"] = False
                    st.rerun()


# =====================================================================
# PAGE: Report Definition
# =====================================================================
elif page == "📝 Report Definition":
    st.markdown('<p class="main-title">Report Definition Engine</p>', unsafe_allow_html=True)
    st.caption(
        "Generate a Power BI report specification from the analytics star schema. "
        "Includes pages, visuals, DAX measures, filters, and drillthrough pages."
    )

    # ── Load prerequisites ────────────────────────────────────────────
    requirements_json = st.session_state.get("requirements_json") or _load_requirements()
    if requirements_json:
        st.session_state["requirements_json"] = requirements_json

    if not requirements_json:
        st.warning(
            "⚠️ No extracted requirements found. Please upload a PDF and "
            "run **Extract Requirements** on the Upload & Extract page first."
        )
        st.stop()

    from modules.report_generator import (
        generate_report_definition,
        save_report_definition,
        load_report_definition,
    )
    from modules.analytics_generator import load_analytics_model as _load_am

    decisions = _load_decisions()
    analytics_model = _load_am()

    # ── Context summary ───────────────────────────────────────────────
    ctx1, ctx2, ctx3 = st.columns(3)
    ctx1.metric(
        "Analytics Model",
        f"{len(analytics_model.get('fact_tables', []))} facts / "
        f"{len(analytics_model.get('dimension_tables', []))} dims"
        if analytics_model else "❌ Missing",
    )
    ctx2.metric("Org Decisions", len(decisions))
    prev_report = load_report_definition()
    ctx3.metric("Report Status", "✅ Saved" if prev_report else "⏳ Not Generated")

    if not analytics_model:
        st.warning(
            "⚠️ No analytics model found. Please generate and approve "
            "the model on the **Analytics Model** page first."
        )
        st.stop()

    # ── Generate / Regenerate button ──────────────────────────────────
    st.markdown("---")

    gen_label = (
        "🔄 Regenerate Report Definition"
        if prev_report
        else "📊 Generate Report Definition"
    )

    if st.button(gen_label, type="primary", use_container_width=True):
        try:
            with st.spinner(
                "Designing Power BI report with Gemini — "
                "crafting pages, visuals, DAX measures, and drillthrough pages…"
            ):
                report = generate_report_definition(requirements_json, decisions)

            st.session_state["report_definition"] = report.model_dump()
            st.session_state["report_approved"] = False
            page_count = len(report.pages)
            visual_count = sum(len(p.visuals) for p in report.pages)
            st.success(
                f"✅ Report generated — {page_count} pages, "
                f"{visual_count} visuals, {len(report.measures)} measures"
            )

        except EnvironmentError as env_err:
            st.error(f"⚠️ {env_err}")
        except ValueError as val_err:
            st.error(f"⚠️ {val_err}")
        except Exception as exc:
            st.error(f"❌ Generation failed: {exc}")

    # Load from disk if not in session
    if "report_definition" not in st.session_state and prev_report:
        st.session_state["report_definition"] = prev_report
        st.session_state["report_approved"] = True

    # ── Visual type icon helper ─────────────────────────────────────
    def _vtype_icon(vt: str) -> str:
        icons = {
            "card": "🏷️", "kpi": "🎯", "gauge": "📀",
            "bar_chart": "📊", "stacked_bar": "📊",
            "line_chart": "📈", "donut_chart": "🍩",
            "treemap": "🌳", "table": "🗏️", "matrix": "🗏️",
            "slicer": "🔍", "scatter_chart": "•",
            "waterfall": "🌊", "funnel": "🔻",
        }
        return icons.get(vt.lower(), "📊")

    # ── Display the report ─────────────────────────────────────────
    if "report_definition" in st.session_state and st.session_state["report_definition"]:
        rpt = st.session_state["report_definition"]
        is_approved = st.session_state.get("report_approved", False)

        st.markdown("---")

        # Status header
        status_html = (
            '<span class="status-approved">✅ Approved & Saved</span>'
            if is_approved
            else '<span class="status-draft">📝 Draft — Review & Approve</span>'
        )
        st.markdown(
            f'<p class="schema-header">{rpt.get("report_name", "Report Definition")}</p> '
            f'{status_html}',
            unsafe_allow_html=True,
        )

        # ── Summary metrics ─────────────────────────────────────────
        all_pages = rpt.get("pages", [])
        all_visuals = sum(len(p.get("visuals", [])) for p in all_pages)
        rm1, rm2, rm3, rm4, rm5 = st.columns(5)
        rm1.metric("Pages", len(all_pages))
        rm2.metric("Visuals", all_visuals)
        rm3.metric("DAX Measures", len(rpt.get("measures", [])))
        rm4.metric("Filters", len(rpt.get("filters", [])))
        rm5.metric("Drillthrough", len(rpt.get("drillthrough_pages", [])))

        # ── Tabs ───────────────────────────────────────────────────
        tab_pages, tab_measures, tab_filters, tab_drill, tab_json = st.tabs([
            "📄 Pages & Visuals",
            "🧮 DAX Measures",
            "🔍 Filters & Slicers",
            "🔎 Drillthrough",
            "📄 Raw JSON",
        ])

        # ── TAB: Pages & Visuals ───────────────────────────────────
        with tab_pages:
            for pg_idx, page_data in enumerate(all_pages):
                page_visuals = page_data.get("visuals", [])
                with st.expander(
                    f"📄 {page_data.get('page_name', f'Page {pg_idx+1}')} "
                    f"({len(page_visuals)} visuals)",
                    expanded=(pg_idx == 0),
                ):
                    st.markdown(
                        f'<div class="page-card">'
                        f'<h4>📄 {page_data.get("page_name", "")}</h4>'
                        f'<div class="purpose">{page_data.get("purpose", "")}</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

                    # Visuals grid
                    if page_visuals:
                        vis_cols = st.columns(2)
                        for v_idx, vis in enumerate(page_visuals):
                            with vis_cols[v_idx % 2]:
                                icon = _vtype_icon(vis.get("visual_type", ""))
                                dims_html = "".join(
                                    f'<span class="col-tag">{d}</span>'
                                    for d in vis.get("dimensions", [])
                                )
                                meas_html = "".join(
                                    f'<span class="metric-pill">{m}</span>'
                                    for m in vis.get("measures", [])
                                )
                                st.markdown(
                                    f'<div class="visual-card">'
                                    f'<span class="v-title">{icon} {vis.get("title", "")}</span>'
                                    f'<span class="v-type">{vis.get("visual_type", "")}</span>'
                                    f'<div style="margin-top:6px">{dims_html}</div>'
                                    f'<div style="margin-top:4px">{meas_html}</div>'
                                    f'<div class="v-reason">{vis.get("business_reason", "")}</div>'
                                    f'</div>',
                                    unsafe_allow_html=True,
                                )

        # ── TAB: DAX Measures ─────────────────────────────────────
        with tab_measures:
            measures_list = rpt.get("measures", [])
            if not measures_list:
                st.info("No DAX measures defined.")
            else:
                for meas in measures_list:
                    with st.expander(
                        f"🧮 {meas.get('name', 'Measure')}",
                        expanded=False,
                    ):
                        st.markdown(
                            f'<span class="measure-name">{meas.get("name", "")}</span> '
                            f'<span class="measure-table">[{meas.get("home_table", "")}]</span>',
                            unsafe_allow_html=True,
                        )
                        st.markdown(f"**Description:** {meas.get('description', '—')}")
                        dax = meas.get("dax_expression", "")
                        if dax:
                            st.markdown(
                                f'<div class="dax-block">{dax}</div>',
                                unsafe_allow_html=True,
                            )
                        fmt = meas.get("format_string", "")
                        if fmt:
                            st.markdown(f"**Format:** `{fmt}`")

        # ── TAB: Filters & Slicers ──────────────────────────────────
        with tab_filters:
            filters_list = rpt.get("filters", [])
            if not filters_list:
                st.info("No report-level filters defined.")
            else:
                for flt in filters_list:
                    scope_icon = "🌐" if flt.get("scope") == "report" else "📄"
                    st.markdown(
                        f'{scope_icon} '
                        f'<span class="filter-badge">{flt.get("name", "")}</span> '
                        f'<span style="color:#94a3b8;font-size:0.82rem;">'
                        f'{flt.get("filter_type", "slicer")} • '
                        f'<code>{flt.get("field", "")}</code> • '
                        f'Scope: {flt.get("scope", "report")}'
                        f'</span>',
                        unsafe_allow_html=True,
                    )
                    default = flt.get("default_value", "")
                    if default:
                        st.caption(f"Default: {default}")

        # ── TAB: Drillthrough ─────────────────────────────────────
        with tab_drill:
            drill_pages = rpt.get("drillthrough_pages", [])
            if not drill_pages:
                st.info("No drillthrough pages defined.")
            else:
                for dp in drill_pages:
                    dp_visuals = dp.get("visuals", [])
                    st.markdown(
                        f'<div class="drill-card">'
                        f'<h4>🔎 {dp.get("page_name", "")}</h4>'
                        f'<div style="color:#e9d5ff;font-size:0.82rem;">{dp.get("purpose", "")}</div>'
                        f'<div class="drill-field">Drillthrough on: '
                        f'{dp.get("drillthrough_field", "—")}</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
                    if dp_visuals:
                        with st.expander(
                            f"Visuals on {dp.get('page_name', '')} ({len(dp_visuals)})",
                            expanded=False,
                        ):
                            for vis in dp_visuals:
                                icon = _vtype_icon(vis.get("visual_type", ""))
                                st.markdown(
                                    f"{icon} **{vis.get('title', '')}** "
                                    f"(`{vis.get('visual_type', '')}`)"
                                )
                                if vis.get("business_reason"):
                                    st.caption(vis["business_reason"])

        # ── TAB: Raw JSON ─────────────────────────────────────────
        with tab_json:
            st.json(rpt)

        # ── Approval / Save actions ─────────────────────────────────
        st.markdown("---")
        st.markdown("### 💾 Approve & Save")

        act1, act2, act3 = st.columns(3)

        with act1:
            if not is_approved:
                if st.button(
                    "✅ Approve & Save Report",
                    key="approve_report",
                    type="primary",
                    use_container_width=True,
                ):
                    try:
                        from modules.schemas import ReportDefinition as RD
                        validated = RD.model_validate(rpt)
                        saved_path = save_report_definition(validated)
                        st.session_state["report_approved"] = True
                        st.success(f"✅ Report approved and saved to `{saved_path}`")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"❌ Save failed: {exc}")
            else:
                st.success("✅ Report is approved and saved", icon="✅")

        with act2:
            render_download_button(
                label="⬇️ Download report_definition.json",
                data=json.dumps(rpt, indent=2),
                file_name="report_definition.json",
                mime="application/json",
                use_container_width=True,
            )

        with act3:
            if is_approved:
                if st.button(
                    "🔓 Unlock for Re-generation",
                    key="unlock_report",
                    use_container_width=True,
                ):
                    st.session_state["report_approved"] = False
                    st.rerun()


# =====================================================================
# PAGE: Data Dictionary
# =====================================================================
elif page == "📖 Data Dictionary":
    st.markdown('<p class="main-title">Data Dictionary Generator</p>', unsafe_allow_html=True)
    st.caption(
        "Generate the final source-to-report mapping document. "
        "Traces every report field from its FHIR/source origin through transformations to its report usage."
    )

    # ── Load prerequisites ────────────────────────────────────────────
    requirements_json = st.session_state.get("requirements_json") or _load_requirements()
    if requirements_json:
        st.session_state["requirements_json"] = requirements_json

    if not requirements_json:
        st.warning(
            "⚠️ No extracted requirements found. Please upload a PDF and "
            "run **Extract Requirements** on the Upload & Extract page first."
        )
        st.stop()

    from modules.data_dictionary_generator import (
        generate_data_dictionary,
        save_data_dictionary,
        load_data_dictionary,
        VALID_CLASSIFICATIONS,
        VALID_SOURCE_TYPES,
        VALID_REPORT_USAGES,
    )
    from modules.analytics_generator import load_analytics_model as _load_am_dd
    from modules.intent_classifier import load_reporting_intents as _load_ri_dd
    from modules.fhir_mapper import load_mapping_cache as _load_mc_dd

    decisions = _load_decisions()
    analytics_model = _load_am_dd()
    reporting_intents = _load_ri_dd()
    mapping_cache = _load_mc_dd()

    # ── Context summary ───────────────────────────────────────────────
    ctx1, ctx2, ctx3, ctx4 = st.columns(4)
    ctx1.metric("Analytics Model", "✅ Ready" if analytics_model else "❌ Missing")
    ctx2.metric("FHIR Mappings", f"{len(mapping_cache)} cached" if mapping_cache else "❌ Missing")
    ctx3.metric("Reporting Intents", f"{len(reporting_intents)} classified" if reporting_intents else "❌ Missing")
    prev_dict = load_data_dictionary()
    ctx4.metric("Dictionary Status", f"✅ {len(prev_dict)} entries" if prev_dict else "⏳ Not Generated")

    if not analytics_model:
        st.warning(
            "⚠️ No analytics model found. Please generate and approve "
            "the model on the **Analytics Model** page first."
        )
        st.stop()

    # ── Upstream artifacts preview ────────────────────────────────────
    with st.expander("📦 Upstream Artifacts Summary", expanded=False):
        up1, up2 = st.columns(2)
        with up1:
            st.markdown("**📊 Analytics Model**")
            st.markdown(f"- Fact tables: {len(analytics_model.get('fact_tables', []))}")
            st.markdown(f"- Dimension tables: {len(analytics_model.get('dimension_tables', []))}")
            st.markdown(f"- Metrics: {len(analytics_model.get('metrics', []))}")
            total_cols = sum(
                len(t.get('columns', []))
                for t in analytics_model.get('fact_tables', []) + analytics_model.get('dimension_tables', [])
            )
            st.markdown(f"- Total columns: {total_cols}")
        with up2:
            st.markdown("**🎯 Reporting Intents**")
            if reporting_intents:
                from collections import Counter as _DDCounter
                usage_counts = _DDCounter(i.get('intent', '').replace('_', ' ').title() for i in reporting_intents)
                for usage, count in usage_counts.most_common():
                    st.markdown(f"- {usage}: {count}")
            else:
                st.markdown("- Not yet classified")

    # ── Classification legend ─────────────────────────────────────────
    with st.expander("🗺️ Classification & Source Type Reference", expanded=False):
        leg1, leg2, leg3 = st.columns(3)
        with leg1:
            st.markdown("**Classification**")
            st.markdown('- <span class="cls-fhir">FHIR</span> Direct FHIR resource mapping', unsafe_allow_html=True)
            st.markdown('- <span class="cls-derived">Derived</span> Computed/calculated field', unsafe_allow_html=True)
            st.markdown('- <span class="cls-non-fhir">Non-FHIR</span> External/reference data', unsafe_allow_html=True)
        with leg2:
            st.markdown("**Source Type**")
            st.markdown('- <span class="src-direct">Direct</span> No transformation', unsafe_allow_html=True)
            st.markdown('- <span class="src-derived">Derived</span> Calculated value', unsafe_allow_html=True)
            st.markdown('- <span class="src-sme-rule">SME Rule</span> Business rule', unsafe_allow_html=True)
        with leg3:
            st.markdown("**Report Usage**")
            for usage in VALID_REPORT_USAGES:
                st.markdown(f'- <span class="usage-badge">{usage}</span>', unsafe_allow_html=True)

    # ── Generate / Regenerate button ──────────────────────────────────
    st.markdown("---")

    gen_label = (
        "🔄 Regenerate Data Dictionary"
        if prev_dict
        else "📖 Generate Data Dictionary"
    )

    if st.button(gen_label, type="primary", use_container_width=True):
        try:
            with st.spinner(
                "Building data dictionary with Gemini — "
                "tracing every field from source to report…"
            ):
                entries = generate_data_dictionary(requirements_json, decisions)

            st.session_state["data_dictionary"] = [e.model_dump() for e in entries]
            st.session_state["dd_approved"] = False
            st.success(f"✅ Data dictionary generated — {len(entries)} entries")

        except EnvironmentError as env_err:
            st.error(f"⚠️ {env_err}")
        except ValueError as val_err:
            st.error(f"⚠️ {val_err}")
        except Exception as exc:
            st.error(f"❌ Generation failed: {exc}")

    # Load from disk if not in session
    if "data_dictionary" not in st.session_state and prev_dict:
        st.session_state["data_dictionary"] = prev_dict
        st.session_state["dd_approved"] = True

    # ── Helper: badge HTML ────────────────────────────────────────────
    def _cls_badge(cls_val: str) -> str:
        cls_map = {
            "FHIR": '<span class="cls-fhir">FHIR</span>',
            "Derived": '<span class="cls-derived">Derived</span>',
            "Non-FHIR": '<span class="cls-non-fhir">Non-FHIR</span>',
        }
        return cls_map.get(cls_val, f'<span class="cls-derived">{cls_val}</span>')

    def _src_badge(src_val: str) -> str:
        src_map = {
            "Direct": '<span class="src-direct">Direct</span>',
            "Derived": '<span class="src-derived">Derived</span>',
            "SME Rule": '<span class="src-sme-rule">SME Rule</span>',
        }
        return src_map.get(src_val, f'<span class="src-direct">{src_val}</span>')

    # ── Display dictionary ────────────────────────────────────────────
    if "data_dictionary" in st.session_state and st.session_state["data_dictionary"]:
        dd_data = st.session_state["data_dictionary"]
        is_approved = st.session_state.get("dd_approved", False)

        st.markdown("---")

        # Status header
        status_html = (
            '<span class="status-approved">✅ Approved & Saved</span>'
            if is_approved
            else '<span class="status-draft">📝 Draft — Review & Approve</span>'
        )
        st.markdown(
            f'<p class="schema-header">Data Dictionary</p> {status_html}',
            unsafe_allow_html=True,
        )

        # ── Summary by classification ──────────────────────────────
        from collections import Counter as _DDCounter2
        cls_counts = _DDCounter2(e.get("classification", "Unknown") for e in dd_data)
        src_counts = _DDCounter2(e.get("source_type", "Unknown") for e in dd_data)
        usage_counts = _DDCounter2(e.get("report_usage", "Unknown") for e in dd_data)

        sm1, sm2, sm3, sm4 = st.columns(4)
        sm1.metric("Total Fields", len(dd_data))
        sm2.metric("FHIR Fields", cls_counts.get("FHIR", 0))
        sm3.metric("Derived Fields", cls_counts.get("Derived", 0))
        sm4.metric("Non-FHIR Fields", cls_counts.get("Non-FHIR", 0))

        # ── Tabs ───────────────────────────────────────────────────
        tab_cards, tab_table, tab_json = st.tabs([
            "📖 Field Cards",
            "📋 Summary Table",
            "📄 Raw JSON",
        ])

        # ── TAB: Field Cards ───────────────────────────────────────
        with tab_cards:
            # Group by classification
            cls_groups = {}
            for item in dd_data:
                key = item.get("classification", "Unknown")
                cls_groups.setdefault(key, []).append(item)

            for cls_type, items in sorted(cls_groups.items()):
                with st.expander(
                    f"{_cls_badge(cls_type)} {cls_type} — {len(items)} fields",
                    expanded=False,
                ):
                    for idx, item in enumerate(items):
                        global_idx = dd_data.index(item)

                        st.markdown(
                            f'<div class="dd-card">'
                            f'<div class="dd-field">{item.get("report_field", "")}</div>'
                            f'<div class="dd-def">{item.get("business_definition", "")}</div>'
                            f'{_cls_badge(item.get("classification", ""))}'
                            f'{_src_badge(item.get("source_type", ""))}'
                            f'<span class="usage-badge">{item.get("report_usage", "")}</span>'
                            f'<div class="dd-source-info">'
                            f'{item.get("source_resource", "")} → {item.get("source_field", "")}'
                            f'</div>'
                            f'<div class="dd-transform">'
                            f'Transform: {item.get("transformation_rule", "None")}'
                            f'</div>'
                            f'</div>',
                            unsafe_allow_html=True,
                        )

                        # Override button
                        if not is_approved:
                            if st.button(
                                "✏️ Override",
                                key=f"override_dd_{cls_type}_{idx}",
                            ):
                                st.session_state[f"overriding_dd_{global_idx}"] = True

                            if st.session_state.get(f"overriding_dd_{global_idx}"):
                                with st.form(key=f"dd_override_form_{global_idx}"):
                                    new_cls = st.selectbox(
                                        "Classification",
                                        VALID_CLASSIFICATIONS,
                                        index=VALID_CLASSIFICATIONS.index(item.get("classification", "FHIR"))
                                        if item.get("classification") in VALID_CLASSIFICATIONS
                                        else 0,
                                    )
                                    new_src_type = st.selectbox(
                                        "Source Type",
                                        VALID_SOURCE_TYPES,
                                        index=VALID_SOURCE_TYPES.index(item.get("source_type", "Direct"))
                                        if item.get("source_type") in VALID_SOURCE_TYPES
                                        else 0,
                                    )
                                    new_usage = st.selectbox(
                                        "Report Usage",
                                        VALID_REPORT_USAGES,
                                        index=VALID_REPORT_USAGES.index(item.get("report_usage", "Table"))
                                        if item.get("report_usage") in VALID_REPORT_USAGES
                                        else 0,
                                    )
                                    new_source_resource = st.text_input(
                                        "Source Resource",
                                        value=item.get("source_resource", ""),
                                    )
                                    new_source_field = st.text_input(
                                        "Source Field",
                                        value=item.get("source_field", ""),
                                    )
                                    new_transform = st.text_area(
                                        "Transformation Rule",
                                        value=item.get("transformation_rule", ""),
                                    )
                                    new_definition = st.text_area(
                                        "Business Definition",
                                        value=item.get("business_definition", ""),
                                    )

                                    sub_c, can_c = st.columns(2)
                                    with sub_c:
                                        submitted = st.form_submit_button(
                                            "💾 Save Override",
                                            use_container_width=True,
                                        )
                                    with can_c:
                                        cancelled = st.form_submit_button(
                                            "Cancel",
                                            use_container_width=True,
                                        )

                                    if submitted:
                                        dd_data[global_idx]["classification"] = new_cls
                                        dd_data[global_idx]["source_type"] = new_src_type
                                        dd_data[global_idx]["report_usage"] = new_usage
                                        dd_data[global_idx]["source_resource"] = new_source_resource
                                        dd_data[global_idx]["source_field"] = new_source_field
                                        dd_data[global_idx]["transformation_rule"] = new_transform
                                        dd_data[global_idx]["business_definition"] = new_definition
                                        st.session_state["data_dictionary"] = dd_data
                                        del st.session_state[f"overriding_dd_{global_idx}"]
                                        st.rerun()

                                    if cancelled:
                                        del st.session_state[f"overriding_dd_{global_idx}"]
                                        st.rerun()

        # ── TAB: Summary Table ─────────────────────────────────────
        with tab_table:
            import pandas as pd
            df = pd.DataFrame(dd_data)
            display_cols = [
                "report_field", "business_definition", "classification",
                "source_type", "source_resource", "source_field",
                "transformation_rule", "report_usage",
            ]
            available = [c for c in display_cols if c in df.columns]
            st.dataframe(
                df[available],
                use_container_width=True,
                hide_index=True,
                height=600,
            )

        # ── TAB: Raw JSON ──────────────────────────────────────────
        with tab_json:
            st.json(dd_data)

        # ── Approval / Save actions ────────────────────────────────
        st.markdown("---")
        st.markdown("### 💾 Approve & Save")

        act1, act2, act3 = st.columns(3)

        with act1:
            if not is_approved:
                if st.button(
                    "✅ Approve & Save Dictionary",
                    key="approve_dd",
                    type="primary",
                    use_container_width=True,
                ):
                    try:
                        saved_path = save_data_dictionary(dd_data)
                        st.session_state["dd_approved"] = True
                        st.success(f"✅ Data dictionary approved and saved to `{saved_path}`")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"❌ Save failed: {exc}")
            else:
                st.success("✅ Data dictionary is approved and saved", icon="✅")

        with act2:
            render_download_button(
                label="⬇️ Download data_dictionary.json",
                data=json.dumps(dd_data, indent=2),
                file_name="data_dictionary.json",
                mime="application/json",
                use_container_width=True,
            )

        with act3:
            if is_approved:
                if st.button(
                    "🔓 Unlock for Re-generation",
                    key="unlock_dd",
                    use_container_width=True,
                ):
                    st.session_state["dd_approved"] = False
                    st.rerun()


# =====================================================================
# PAGE: Measure Generator
# =====================================================================
elif page == "📐 Measure Generator":
    st.markdown('<p class="main-title">Measure Generator</p>', unsafe_allow_html=True)
    st.caption(
        "Generate business measures from the approved report definition and data dictionary. "
        "Identifies formulas, source lineage, dependency chains, and measure classifications."
    )

    # ── Load prerequisites ────────────────────────────────────────────
    from modules.measure_generator import (
        generate_measures,
        save_measures,
        load_measures,
        VALID_MEASURE_TYPES,
        VALID_CLASSIFICATIONS as VALID_MEASURE_CLS,
    )
    from modules.analytics_generator import load_analytics_model as _load_am_msr
    from modules.report_generator import load_report_definition as _load_rd_msr
    from modules.data_dictionary_generator import load_data_dictionary as _load_dd_msr
    from modules.intent_classifier import load_reporting_intents as _load_ri_msr

    decisions = _load_decisions()
    analytics_model = _load_am_msr()
    report_def = _load_rd_msr()
    data_dict = _load_dd_msr()
    rep_intents = _load_ri_msr()

    # ── Context summary ───────────────────────────────────────────────
    ctx1, ctx2, ctx3, ctx4 = st.columns(4)
    ctx1.metric("Report Definition", "✅ Ready" if report_def else "❌ Missing")
    ctx2.metric("Data Dictionary", f"{len(data_dict)} fields" if data_dict else "❌ Missing")
    ctx3.metric("Analytics Model", "✅ Ready" if analytics_model else "❌ Missing")
    prev_measures = load_measures()
    ctx4.metric("Measures Status", f"✅ {len(prev_measures)} measures" if prev_measures else "⏳ Not Generated")

    if not report_def:
        st.warning(
            "⚠️ No report definition found. Please generate and approve "
            "the report on the **Report Definition** page first."
        )
        st.stop()

    if not analytics_model:
        st.warning(
            "⚠️ No analytics model found. Please generate and approve "
            "the model on the **Analytics Model** page first."
        )
        st.stop()

    # ── Reference legend ──────────────────────────────────────────────
    with st.expander("🗺️ Measure Types & Classifications", expanded=False):
        leg1, leg2 = st.columns(2)
        with leg1:
            st.markdown("**Measure Types**")
            for mt in VALID_MEASURE_TYPES:
                css_cls = f"mtype-{mt.lower().replace(' ', '-')}"
                st.markdown(
                    f'- <span class="{css_cls}">{mt}</span>',
                    unsafe_allow_html=True,
                )
        with leg2:
            st.markdown("**Classifications**")
            st.markdown('- <span class="mcls-base">Base Measure</span> Foundational — no dependencies', unsafe_allow_html=True)
            st.markdown('- <span class="mcls-derived">Derived Measure</span> Computed from base measures', unsafe_allow_html=True)
            st.markdown('- <span class="mcls-kpi">KPI</span> Key performance indicator', unsafe_allow_html=True)

    # ── Generate / Regenerate button ──────────────────────────────────
    st.markdown("---")

    gen_label = (
        "🔄 Regenerate Measures"
        if prev_measures
        else "📐 Generate Measures"
    )

    if st.button(gen_label, type="primary", use_container_width=True):
        try:
            with st.spinner(
                "Generating business measures with Gemini — "
                "analyzing report visuals, formulas, and dependencies…"
            ):
                measures = generate_measures(decisions)

            st.session_state["measures"] = [m.model_dump() for m in measures]
            st.session_state["measures_approved"] = False
            st.success(f"✅ Generated {len(measures)} business measures")

        except EnvironmentError as env_err:
            st.error(f"⚠️ {env_err}")
        except ValueError as val_err:
            st.error(f"⚠️ {val_err}")
        except Exception as exc:
            st.error(f"❌ Generation failed: {exc}")

    # Load from disk if not in session
    if "measures" not in st.session_state and prev_measures:
        st.session_state["measures"] = prev_measures
        st.session_state["measures_approved"] = True

    # ── Helper: badge HTML ────────────────────────────────────────────
    def _mtype_badge(mt: str) -> str:
        css_cls = f"mtype-{mt.lower().replace(' ', '-')}"
        return f'<span class="{css_cls}">{mt}</span>'

    def _mcls_badge(cls_val: str) -> str:
        cls_map = {
            "Base Measure": '<span class="mcls-base">Base Measure</span>',
            "Derived Measure": '<span class="mcls-derived">Derived Measure</span>',
            "KPI": '<span class="mcls-kpi">KPI</span>',
        }
        return cls_map.get(cls_val, f'<span class="mcls-base">{cls_val}</span>')

    # ── Display measures ──────────────────────────────────────────────
    if "measures" in st.session_state and st.session_state["measures"]:
        msr_data = st.session_state["measures"]
        is_approved = st.session_state.get("measures_approved", False)

        st.markdown("---")

        # Status header
        status_html = (
            '<span class="status-approved">✅ Approved & Saved</span>'
            if is_approved
            else '<span class="status-draft">📝 Draft — Review & Approve</span>'
        )
        st.markdown(
            f'<p class="schema-header">Business Measures</p> {status_html}',
            unsafe_allow_html=True,
        )

        # ── Summary metrics ───────────────────────────────────────────
        from collections import Counter as _MsrCounter
        cls_counts = _MsrCounter(m.get("classification", "Unknown") for m in msr_data)
        type_counts = _MsrCounter(m.get("measure_type", "Unknown") for m in msr_data)

        sm1, sm2, sm3, sm4 = st.columns(4)
        sm1.metric("Total Measures", len(msr_data))
        sm2.metric("Base Measures", cls_counts.get("Base Measure", 0))
        sm3.metric("Derived Measures", cls_counts.get("Derived Measure", 0))
        sm4.metric("KPIs", cls_counts.get("KPI", 0))

        # ── Tabs ──────────────────────────────────────────────────────
        tab_cards, tab_table, tab_deps, tab_json = st.tabs([
            "📐 Measure Cards",
            "📋 Summary Table",
            "🔗 Dependency View",
            "📄 Raw JSON",
        ])

        # ── TAB: Measure Cards ────────────────────────────────────────
        with tab_cards:
            # Group by classification
            cls_groups = {}
            for item in msr_data:
                key = item.get("classification", "Unknown")
                cls_groups.setdefault(key, []).append(item)

            # Display in order: Base → Derived → KPI
            ordered_cls = ["Base Measure", "Derived Measure", "KPI"]
            for cls_type in ordered_cls:
                items = cls_groups.get(cls_type, [])
                if not items:
                    continue

                with st.expander(
                    f"{_mcls_badge(cls_type)} {cls_type} — {len(items)} measures",
                    expanded=False,
                ):
                    for idx, item in enumerate(items):
                        global_idx = msr_data.index(item)

                        # Build source tags HTML
                        fields_html = "".join(
                            f'<span class="msr-src-tag">{f}</span>'
                            for f in item.get("source_fields", [])[:8]
                        )
                        extra_f = len(item.get("source_fields", [])) - 8
                        if extra_f > 0:
                            fields_html += f'<span class="msr-src-tag">+{extra_f} more</span>'

                        tables_html = "".join(
                            f'<span class="msr-tbl-tag">{t}</span>'
                            for t in item.get("source_tables", [])
                        )

                        deps_html = "".join(
                            f'<span class="msr-tbl-tag">{d}</span>'
                            for d in item.get("dependencies", [])
                        ) if item.get("dependencies") else '<span style="color:#64748b;font-size:0.72rem;">None</span>'

                        pages_html = ", ".join(item.get("report_pages", [])) if item.get("report_pages") else "—"
                        visuals_html = ", ".join(item.get("visuals_used_in", [])) if item.get("visuals_used_in") else "—"

                        st.markdown(
                            f'<div class="msr-card">'
                            f'<div class="msr-name">{item.get("measure_name", "")}</div>'
                            f'<div class="msr-def">{item.get("business_definition", "")}</div>'
                            f'{_mtype_badge(item.get("measure_type", ""))}'
                            f'{_mcls_badge(item.get("classification", ""))}'
                            f'<div class="msr-formula">{item.get("formula_description", "")}</div>'
                            f'<div style="margin-top:6px">'
                            f'<span style="color:#64748b;font-size:0.72rem;">Tables: </span>{tables_html}'
                            f'</div>'
                            f'<div style="margin-top:4px">'
                            f'<span style="color:#64748b;font-size:0.72rem;">Fields: </span>{fields_html}'
                            f'</div>'
                            f'<div style="margin-top:4px">'
                            f'<span style="color:#64748b;font-size:0.72rem;">Dependencies: </span>{deps_html}'
                            f'</div>'
                            f'<div style="margin-top:4px">'
                            f'<span style="color:#64748b;font-size:0.72rem;">Report Pages: </span>{pages_html}'
                            f'</div>'
                            f'<div style="margin-top:4px">'
                            f'<span style="color:#64748b;font-size:0.72rem;">Visuals Used In: </span>{visuals_html}'
                            f'</div>'
                            f'</div>',
                            unsafe_allow_html=True,
                        )

                        # Override button
                        if not is_approved:
                            if st.button(
                                "✏️ Override",
                                key=f"override_msr_{cls_type}_{idx}",
                            ):
                                st.session_state[f"overriding_msr_{global_idx}"] = True

                            if st.session_state.get(f"overriding_msr_{global_idx}"):
                                with st.form(key=f"msr_override_form_{global_idx}"):
                                    new_name = st.text_input(
                                        "Measure Name",
                                        value=item.get("measure_name", ""),
                                    )
                                    new_def = st.text_area(
                                        "Business Definition",
                                        value=item.get("business_definition", ""),
                                    )
                                    new_mtype = st.selectbox(
                                        "Measure Type",
                                        VALID_MEASURE_TYPES,
                                        index=VALID_MEASURE_TYPES.index(item.get("measure_type", "Count"))
                                        if item.get("measure_type") in VALID_MEASURE_TYPES
                                        else 0,
                                    )
                                    new_mcls = st.selectbox(
                                        "Classification",
                                        VALID_MEASURE_CLS,
                                        index=VALID_MEASURE_CLS.index(item.get("classification", "Base Measure"))
                                        if item.get("classification") in VALID_MEASURE_CLS
                                        else 0,
                                    )
                                    new_formula = st.text_area(
                                        "Formula Description",
                                        value=item.get("formula_description", ""),
                                    )
                                    new_deps_str = st.text_area(
                                        "Dependencies (comma-separated)",
                                        value=", ".join(item.get("dependencies", [])),
                                    )
                                    new_pages_str = st.text_area(
                                        "Report Pages (comma-separated)",
                                        value=", ".join(item.get("report_pages", [])),
                                    )
                                    new_visuals_str = st.text_area(
                                        "Visuals Used In (comma-separated)",
                                        value=", ".join(item.get("visuals_used_in", [])),
                                    )

                                    sub_c, can_c = st.columns(2)
                                    with sub_c:
                                        submitted = st.form_submit_button(
                                            "💾 Save Override",
                                            use_container_width=True,
                                        )
                                    with can_c:
                                        cancelled = st.form_submit_button(
                                            "Cancel",
                                            use_container_width=True,
                                        )

                                    if submitted:
                                        msr_data[global_idx]["measure_name"] = new_name
                                        msr_data[global_idx]["business_definition"] = new_def
                                        msr_data[global_idx]["measure_type"] = new_mtype
                                        msr_data[global_idx]["classification"] = new_mcls
                                        msr_data[global_idx]["formula_description"] = new_formula
                                        msr_data[global_idx]["dependencies"] = [x.strip() for x in new_deps_str.split(",") if x.strip()]
                                        msr_data[global_idx]["report_pages"] = [x.strip() for x in new_pages_str.split(",") if x.strip()]
                                        msr_data[global_idx]["visuals_used_in"] = [x.strip() for x in new_visuals_str.split(",") if x.strip()]
                                        st.session_state["measures"] = msr_data
                                        del st.session_state[f"overriding_msr_{global_idx}"]
                                        st.rerun()

                                    if cancelled:
                                        del st.session_state[f"overriding_msr_{global_idx}"]
                                        st.rerun()

            # Remaining ungrouped
            remaining = [k for k in cls_groups if k not in ordered_cls]
            for cls_type in remaining:
                items = cls_groups[cls_type]
                with st.expander(f"{cls_type} — {len(items)} measures", expanded=False):
                    for item in items:
                        st.markdown(f"**{item.get('measure_name', '')}** — {item.get('business_definition', '')}")

        # ── TAB: Summary Table ────────────────────────────────────────
        with tab_table:
            import pandas as pd
            df = pd.DataFrame(msr_data)
            display_cols = [
                "measure_name", "business_definition", "measure_type",
                "aggregation", "formula_description", "source_tables",
                "classification",
            ]
            available = [c for c in display_cols if c in df.columns]
            st.dataframe(
                df[available],
                use_container_width=True,
                hide_index=True,
                height=600,
            )

        # ── TAB: Dependency View ──────────────────────────────────────
        with tab_deps:
            st.markdown("#### 🔗 Measure Dependency Chains")
            st.caption(
                "Shows how derived measures and KPIs depend on base measures."
            )

            base_names = {
                m.get("measure_name", "")
                for m in msr_data
                if m.get("classification") == "Base Measure"
            }
            derived_items = [
                m for m in msr_data
                if m.get("classification") in ("Derived Measure", "KPI")
            ]

            if not derived_items:
                st.info("No derived measures or KPIs to show dependencies for.")
            else:
                for m in derived_items:
                    cls_badge = _mcls_badge(m.get("classification", ""))
                    st.markdown(
                        f"{cls_badge} **{m.get('measure_name', '')}**",
                        unsafe_allow_html=True,
                    )
                    # Show formula
                    st.markdown(
                        f'<div class="msr-formula">{m.get("formula_description", "")}</div>',
                        unsafe_allow_html=True,
                    )
                    # Show source fields as potential dependencies
                    deps = m.get("source_fields", [])
                    if deps:
                        dep_tags = "".join(
                            f'<span class="msr-src-tag">{d}</span>' for d in deps
                        )
                        st.markdown(
                            f'<span style="color:#64748b;font-size:0.75rem;">Depends on: </span>{dep_tags}',
                            unsafe_allow_html=True,
                        )
                    st.markdown("---")

        # ── TAB: Raw JSON ─────────────────────────────────────────────
        with tab_json:
            st.json(msr_data)

        # ── Approval / Save actions ───────────────────────────────────
        st.markdown("---")
        st.markdown("### 💾 Approve & Save")

        act1, act2, act3 = st.columns(3)

        with act1:
            if not is_approved:
                if st.button(
                    "✅ Approve & Save Measures",
                    key="approve_measures",
                    type="primary",
                    use_container_width=True,
                ):
                    try:
                        saved_path = save_measures(msr_data)
                        st.session_state["measures_approved"] = True
                        st.success(f"✅ Measures approved and saved to `{saved_path}`")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"❌ Save failed: {exc}")
            else:
                st.success("✅ Measures are approved and saved", icon="✅")

        with act2:
            render_download_button(
                label="⬇️ Download measures.json",
                data=json.dumps(msr_data, indent=2),
                file_name="measures.json",
                mime="application/json",
                use_container_width=True,
            )

        with act3:
            if is_approved:
                if st.button(
                    "🔓 Unlock for Re-generation",
                    key="unlock_measures",
                    use_container_width=True,
                ):
                    st.session_state["measures_approved"] = False
                    st.rerun()





# =====================================================================
# PAGE: DAX Generator
# =====================================================================
elif page == "🔢 DAX Generator":
    st.markdown('<p class="main-title">DAX Generator</p>', unsafe_allow_html=True)
    st.caption("Translate approved business measures into Power BI DAX formulas using Gemini.")

    from modules.dax_generator import (
        generate_dax_measures,
        save_dax_artifacts,
        load_dax_artifacts,
        check_cycles,
        validate_dax_measure,
    )

    # Check inputs
    import os as _dax_os
    if not (OUTPUT_DIR / "measures.json").exists():
        st.warning("⚠️ **Measures missing:** Please generate and approve measures on the **Measure Generator** page first.")
        st.stop()
    if not (OUTPUT_DIR / "analytics_model.json").exists():
        st.warning("⚠️ **Analytics Model missing:** Please generate and approve the model on the **Analytics Model** page first.")
        st.stop()

    # Load existing approved DAX or session DAX
    if "dax_measures" not in st.session_state:
        saved_dax = load_dax_artifacts()
        if saved_dax:
            st.session_state["dax_measures"] = saved_dax
            st.session_state["dax_approved"] = True
        else:
            st.session_state["dax_measures"] = []
            st.session_state["dax_approved"] = False

    dax_data = st.session_state["dax_measures"]
    is_approved = st.session_state.get("dax_approved", False)

    # Validation & Cycle Detection
    cycle_nodes = check_cycles(dax_data) if dax_data else set()
    all_names = {m.get("measure_name", "") for m in dax_data} if dax_data else set()
    
    validation_results = {}
    valid_count = 0
    warning_count = 0
    error_count = 0
    for m in dax_data:
        v_res = validate_dax_measure(m, all_names, cycle_nodes)
        validation_results[m.get("measure_name", "")] = v_res
        if v_res["status"] == "✅ Valid":
            valid_count += 1
        elif v_res["status"] == "⚠️ Warning":
            warning_count += 1
        else:
            error_count += 1

    # Action bar
    st.markdown("### ⚙️ Generation Control")
    col_gen, col_status = st.columns([1, 2])
    with col_gen:
        if is_approved:
            st.info("🔓 Unlock below to regenerate.")
        else:
            if st.button("🚀 Generate DAX Measures", type="primary", use_container_width=True):
                with st.spinner("Generating DAX formulas with Gemini..."):
                    try:
                        generated = generate_dax_measures()
                        dax_data = [g.model_dump() for g in generated]
                        st.session_state["dax_measures"] = dax_data
                        st.session_state["dax_approved"] = False
                        st.success("✅ DAX measures generated successfully!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Generation failed: {e}")

    with col_status:
        if dax_data:
            st.markdown(
                f"**Catalog Status:** "
                f'<span class="badge-dax-valid">✅ {valid_count} Valid</span> '
                f'<span class="badge-dax-warning">⚠️ {warning_count} Warnings</span> '
                f'<span class="badge-dax-error">❌ {error_count} Errors</span>',
                unsafe_allow_html=True
            )
        else:
            st.info("No DAX measures loaded. Click Generate to start.")

    if dax_data:
        # Layout in tabs
        tab_cards, tab_table, tab_json = st.tabs(["📇 DAX Cards", "📋 Summary Table", "📄 Raw JSON"])

        with tab_cards:
            st.markdown("### 🏷️ DAX Catalog")
            for idx, item in enumerate(dax_data):
                name = item.get("measure_name", "")
                dax_expr = item.get("dax_expression", "")
                deps = item.get("dependencies", [])
                v_info = validation_results.get(name, {"status": "❓ Unknown", "messages": []})
                
                if v_info["status"] == "✅ Valid":
                    badge_class = "badge-dax-valid"
                elif v_info["status"] == "⚠️ Warning":
                    badge_class = "badge-dax-warning"
                else:
                    badge_class = "badge-dax-error"

                deps_html = "".join(f'<span class="msr-tbl-tag">{d}</span>' for d in deps) if deps else '<span style="color:#64748b;font-size:0.72rem;">None</span>'
                
                st.markdown(
                    f'<div class="dax-card">'
                    f'<div class="dax-name">{name}</div>'
                    f'<div class="dax-def">{item.get("business_definition", "")}</div>'
                    f'<div class="dax-expr-block">{dax_expr}</div>'
                    f'<div style="margin-top:6px">'
                    f'<span style="color:#64748b;font-size:0.72rem;">Dependencies: </span>{deps_html}'
                    f'</div>'
                    f'<div style="margin-top:6px">'
                    f'<span style="color:#64748b;font-size:0.72rem;">Status: </span><span class="{badge_class}">{v_info["status"]}</span>'
                    f'</div>'
                    f'</div>',
                    unsafe_allow_html=True
                )

                # Show validation error/warning messages if any
                if v_info["messages"]:
                    for msg in v_info["messages"]:
                        if "Missing" in msg or "Circular" in msg:
                            st.error(f"  - {msg}")
                        else:
                            st.warning(f"  - {msg}")

                # Override button
                if not is_approved:
                    if st.button("✏️ Override", key=f"override_dax_{idx}"):
                        st.session_state[f"overriding_dax_{idx}"] = True

                    if st.session_state.get(f"overriding_dax_{idx}"):
                        with st.form(key=f"dax_override_form_{idx}"):
                            new_name = st.text_input("Measure Name", value=name)
                            new_def = st.text_area("Business Definition", value=item.get("business_definition", ""))
                            new_dax = st.text_area("DAX Expression", value=dax_expr)
                            new_deps_str = st.text_area("Dependencies (comma-separated)", value=", ".join(deps))
                            
                            sub_c, can_c = st.columns(2)
                            with sub_c:
                                submitted = st.form_submit_button("💾 Save Override", use_container_width=True)
                            with can_c:
                                cancelled = st.form_submit_button("Cancel", use_container_width=True)

                            if submitted:
                                dax_data[idx]["measure_name"] = new_name
                                dax_data[idx]["business_definition"] = new_def
                                dax_data[idx]["dax_expression"] = new_dax
                                dax_data[idx]["dependencies"] = [x.strip() for x in new_deps_str.split(",") if x.strip()]
                                st.session_state["dax_measures"] = dax_data
                                del st.session_state[f"overriding_dax_{idx}"]
                                st.rerun()

                            if cancelled:
                                del st.session_state[f"overriding_dax_{idx}"]
                                st.rerun()

        with tab_table:
            import pandas as pd
            table_rows = []
            for item in dax_data:
                name = item.get("measure_name", "")
                v_info = validation_results.get(name, {"status": "❓ Unknown", "messages": []})
                table_rows.append({
                    "Measure Name": name,
                    "DAX Expression": item.get("dax_expression", ""),
                    "Dependencies": ", ".join(item.get("dependencies", [])),
                    "Validation Status": v_info["status"]
                })
            st.dataframe(pd.DataFrame(table_rows), use_container_width=True, hide_index=True)

        with tab_json:
            st.json(dax_data)

        # Approve and Save Action
        st.markdown("---")
        st.markdown("### 💾 Approve & Save")
        act1, act2, act3 = st.columns(3)
        with act1:
            if not is_approved:
                if st.button("✅ Approve & Save DAX", key="approve_dax", type="primary", use_container_width=True):
                    try:
                        saved_path = save_dax_artifacts(dax_data)
                        st.session_state["dax_approved"] = True
                        st.success(f"✅ DAX measures approved and saved to `{saved_path}`")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"❌ Save failed: {exc}")
            else:
                st.success("✅ DAX measures are approved and saved", icon="✅")

        with act2:
            render_download_button(
                label="⬇️ Download dax_artifacts.json",
                data=json.dumps(dax_data, indent=2),
                file_name="dax_artifacts.json",
                mime="application/json",
                use_container_width=True
            )

        with act3:
            if is_approved:
                if st.button("🔓 Unlock for Re-generation", key="unlock_dax", use_container_width=True):
                    st.session_state["dax_approved"] = False
                    st.rerun()





# =====================================================================
# PAGE: PBIP Generator
# =====================================================================
elif page == "📦 PBIP Generator":
    st.markdown('<p class="main-title">PBIP Generator</p>', unsafe_allow_html=True)
    st.caption("Generate a complete Power BI Project (PBIP) archive from approved upstream artifacts.")

    import importlib
    import modules.pbip_generator
    importlib.reload(modules.pbip_generator)
    from modules.pbip_generator import compile_pbip_project, validate_pbip_project

    # Check inputs
    required_inputs = [
        ("analytics_model.json", "Analytics Model"),
        ("report_definition.json", "Report Definition"),
        ("dax_artifacts.json", "DAX Artifacts"),
        ("measures.json", "Measures"),
        ("data_dictionary.json", "Data Dictionary"),
        ("reporting_intent.json", "Reporting Intent")
    ]
    missing = []
    for fname, label in required_inputs:
        if not (OUTPUT_DIR / fname).exists():
            missing.append(label)

    if missing:
        st.warning(f"⚠️ **Upstream inputs missing:** Please complete and approve: {', '.join(f'**{m}**' for m in missing)} first.")
        st.stop()

    # Load PBIP stats or trigger compilation
    if "pbip_results" not in st.session_state:
        if (OUTPUT_DIR / "pbip_project.zip").exists() and (OUTPUT_DIR / "pbip").exists():
            try:
                st.session_state["pbip_results"] = compile_pbip_project()
            except Exception:
                st.session_state["pbip_results"] = None
        else:
            st.session_state["pbip_results"] = None

    results = st.session_state["pbip_results"]

    st.markdown("### ⚙️ Compilation Control")
    c1, c2 = st.columns([1, 2])
    with c1:
        if st.button("🚀 Compile PBIP Project", type="primary", use_container_width=True):
            with st.spinner("Compiling Power BI Project layout & TMDL files..."):
                try:
                    res = compile_pbip_project()
                    st.session_state["pbip_results"] = res
                    st.success("✅ PBIP project compiled successfully!")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Compilation failed: {e}")

    with c2:
        if results:
            if results.get("is_valid"):
                st.success("✅ Project Compiled & Validated – Spec Compliant", icon="✅")
            else:
                st.warning("⚠️ Project compiled but has validation issues.", icon="⚠️")
        else:
            st.info("Click Compile to build the Power BI Project.")

    if results:
        col_left, col_right = st.columns([1, 1])

        with col_left:
            st.markdown("### 📂 PBIP Folder Structure (Official Spec)")
            tree_md = """
```
📂 pbip_project.zip/
├── 📄 report.pbip
├── 📄 metadata.json
├── 📂 report.Report/
│   ├── 📄 definition.pbir
│   ├── 📂 definition/
│   │   ├── 📄 report.json
│   │   └── 📂 pages/
│   │       └── 📂 <PageName>/
│   │           ├── 📄 page.json
│   │           └── 📂 visuals/
│   │               └── 📄 <visual_id>.json
│   └── 📂 .pbi/
│       └── 📄 localSettings.json
└── 📂 report.SemanticModel/
    ├── 📄 definition.pbism
    ├── 📂 definition/
    │   ├── 📄 model.tmdl
    │   └── 📂 tables/
    │       └── 📄 _Measures.tmdl
    └── 📂 .pbi/
        └── 📄 localSettings.json
```
            """
            st.markdown(tree_md)

            st.markdown("### 📋 Generated Files Detail")
            files_table = []
            for fname, info in results["files"].items():
                files_table.append({
                    "File": fname,
                    "Size": f"{info['size_bytes'] / 1024:.2f} KB"
                })
            import pandas as pd
            st.dataframe(pd.DataFrame(files_table), use_container_width=True, hide_index=True)

        with col_right:
            st.markdown("### 🧪 Validation Results")
            for log in results["validation_logs"]:
                if log.startswith("MISSING:") or log.startswith("EMPTY:") or log.startswith("ERROR:") or log.startswith("ZIP MISSING:"):
                    st.error(log)
                elif log.startswith("WARNING:"):
                    st.warning(log)
                else:
                    st.success(log)

        # Download ZIP section
        st.markdown("---")
        st.markdown("### 📦 Download PBIP Package")

        from pathlib import Path as _PbipPath
        zip_path = _PbipPath(results["zip_path"])
        if zip_path.exists():
            with open(zip_path, "rb") as zf:
                zip_bytes = zf.read()

            d1, d2 = st.columns(2)
            with d1:
                render_download_button(
                    label="⬇️ Download pbip_project.zip",
                    data=zip_bytes,
                    file_name="pbip_project.zip",
                    mime="application/zip",
                    use_container_width=True,
                    type="primary"
                )
            with d2:
                st.info("💡 **Unzip instructions:** Extract this archive and open `report.pbip` in Power BI Desktop.")


# =====================================================================
# PAGE: PBIP Validation
# =====================================================================
elif page == "✅ PBIP Validation":
    st.markdown('<p class="main-title">PBIP Validation</p>', unsafe_allow_html=True)
    st.caption("Validate the generated PBIP package against the official Power BI Desktop PBIP specification.")

    import importlib
    import modules.pbip_generator as _pbip_val_mod
    importlib.reload(_pbip_val_mod)
    from modules.pbip_generator import validate_pbip_project as _validate_pbip, PBIP_REQUIRED_FILES as _PBIP_REQ

    pbip_dir_exists = (OUTPUT_DIR / "pbip").exists()

    if not pbip_dir_exists:
        st.warning("⚠️ No PBIP project found. Please compile the project on the **📦 PBIP Generator** page first.")
        st.stop()

    # Run validation
    val_result = _validate_pbip()

    # ── Summary Banner ───────────────────────────────────────────
    status = val_result["validation_status"]
    is_compatible = val_result["power_bi_compatible"]

    if status == "Success":
        st.markdown(
            f'<div class="pbip-summary-pass">'
            f'<span style="font-size:1.8rem;">✅</span><br>'
            f'<span style="color:#86efac;font-size:1.1rem;font-weight:700;">'
            f'Power BI Compatible: Success</span><br>'
            f'<span style="color:#94a3b8;font-size:0.85rem;">'
            f'All compatibility checks passed! Package is ready to open in Power BI Desktop.</span></div>',
            unsafe_allow_html=True
        )
    elif status == "Warning":
        st.markdown(
            f'<div class="pbip-summary-empty">'
            f'<span style="font-size:1.8rem;">⚠️</span><br>'
            f'<span style="color:#fcd34d;font-size:1.1rem;font-weight:700;">'
            f'Power BI Compatible: Warning</span><br>'
            f'<span style="color:#94a3b8;font-size:0.85rem;">'
            f'Compatible, but some non-blocking warnings exist. Check details below.</span></div>',
            unsafe_allow_html=True
        )
    else: # Failed
        st.markdown(
            f'<div class="pbip-summary-fail">'
            f'<span style="font-size:1.8rem;">❌</span><br>'
            f'<span style="color:#fca5a5;font-size:1.1rem;font-weight:700;">'
            f'Power BI Incompatible: Failed</span><br>'
            f'<span style="color:#94a3b8;font-size:0.85rem;">'
            f'Critical checks failed. Power BI Desktop will fail to open this package.</span></div>',
            unsafe_allow_html=True
        )

    # ── Metrics Row ──────────────────────────────────────────────
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Compatibility Status", status)
    m2.metric("Critical Errors", len(val_result["errors"]))
    m3.metric("Warnings", len(val_result["warnings"]))
    m4.metric("Power BI Compatible?", "Yes ✅" if is_compatible else "No ❌")

    st.markdown("---")

    # ── Critical Validation Findings ──────────────────────────────
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("### 🚨 Critical Errors")
        if val_result["errors"]:
            for err in val_result["errors"]:
                st.error(err)
        else:
            st.success("No critical errors detected.")

    with c2:
        st.markdown("### ⚠️ Warnings")
        if val_result["warnings"]:
            for wrn in val_result["warnings"]:
                st.warning(wrn)
        else:
            st.info("No warnings detected.")

    st.markdown("---")

    # ── Missing Artifacts & Invalid References ────────────────────
    c3, c4 = st.columns(2)
    with c3:
        st.markdown("### 📂 Missing Artifacts")
        if val_result["missing_artifacts"]:
            for ma in val_result["missing_artifacts"]:
                st.markdown(f"- ❌ `{ma}`")
        else:
            st.success("All required folders and files exist.")

    with c4:
        st.markdown("### 🔗 Invalid References")
        if val_result["invalid_references"]:
            for ir in val_result["invalid_references"]:
                st.markdown(f"- ⚠️ `{ir}`")
        else:
            st.success("All references and relative paths resolve correctly.")

    st.markdown("---")

    # ── Recommended Fixes ────────────────────────────────────────
    st.markdown("### 💡 Recommended Fixes")
    if val_result["recommended_fixes"]:
        for fix in val_result["recommended_fixes"]:
            st.markdown(f"- **Fix:** {fix}")
    else:
        st.success("No fixes needed! The package is fully compatible.")

    st.markdown("---")

    # ── Per-file Validation Table ────────────────────────────────
    st.markdown("### 📋 File-by-File Audit Table")

    table_rows = []
    for detail in val_result["details"]:
        status = detail["status"]
        file_path = detail["file"]
        desc = detail["description"]

        if status == "valid":
            generated = "Yes ✅"
            missing = "No"
            val_res = f"Passed ({detail['size_bytes'] / 1024:.1f} KB)"
        elif status == "missing":
            generated = "No ❌"
            missing = "Yes ❌"
            val_res = "Failed (File is missing)"
        else:  # empty
            generated = "Yes ✅"
            missing = "No"
            val_res = "Failed (File is empty ⚠️)"

        table_rows.append(
            f"| **`{file_path}`** <br><small style='color: #94a3b8;'>{desc}</small> | {generated} | {missing} | {val_res} |"
        )

    table_header = (
        "| Required File & Purpose | Generated File? | Missing File? | Validation Result |\n"
        "| :--- | :---: | :---: | :--- |\n"
    )
    table_markdown = table_header + "\n".join(table_rows)
    st.markdown(table_markdown, unsafe_allow_html=True)

    # ── Validation Logs ──────────────────────────────────────────
    st.markdown("---")
    st.markdown("### 🧪 Detailed Validation Log")
    for log in val_result["logs"]:
        if log.startswith("MISSING:") or log.startswith("EMPTY:") or log.startswith("ERROR:") or log.startswith("ZIP MISSING:"):
            st.error(log)
        elif log.startswith("WARNING:"):
            st.warning(log)
        else:
            st.success(log)

    # ── Expected Folder Structure Reference ──────────────────────
    with st.expander("📖 Official PBIP Specification Reference", expanded=False):
        st.markdown("""
**Power BI Project (PBIP)** with **Legacy Report Layout & TMDL Semantic Model Format** – optimized for compatibility and performance.

```
<ProjectName>.pbip                       ← Project entry point
<ProjectName>.Report/                    ← Report artifact folder
    definition.pbir                      ← Report config (version 1.0, links to semantic model)
    report.json                          ← Monolithic report layout metadata
<ProjectName>.SemanticModel/             ← Semantic model folder
    definition.pbism                     ← Semantic model configuration
    model.bim                            ← TMSL representation of the model
    definition/                          ← TMDL files folder
        model.tmdl                       ← Tables, columns, relationships
        tables/                          ← Individual table TMDL files
            _Measures.tmdl               ← DAX measures
    .pbi/                                ← Power BI internal settings
        localSettings.json
        version.json
```

Key files:
- **`definition.pbir`**: Links the report to its semantic model via a relative path. Uses version `1.0`.
- **`report.json`**: Holds the entire report definition (pages, visuals, positions) in monolithic JSON format.
- **`definition.pbism`**: Declares the semantic model configuration.
- **`model.tmdl`**: Defines tables, columns, and relationships in TMDL syntax.
- **`model.bim`**: Legacy TMSL model representation.
- **`.pbi/localSettings.json`**: Environment-specific settings.
        """)


# =====================================================================
# PAGE: Dependency Diagnostics
# =====================================================================
elif page == "🔧 Dependency Diagnostics":
    st.markdown('<p class="main-title">Dependency Diagnostics</p>', unsafe_allow_html=True)
    st.caption(
        "Audit all artifact dependencies across the pipeline. "
        "Identifies missing files that block downstream stages."
    )

    import os as _diag_os
    import pandas as pd
    from pathlib import Path as _DiagPath

    # ── Define all artifacts and their dependencies ──────────────────
    _artifacts = [
        {
            "name": "requirements.json",
            "expected_path": str(OUTPUT_DIR / "requirements.json"),
            "stage": "Upload & Extract",
            "produced_by": "📄 Upload & Extract",
            "consumed_by": ["💬 SME Workspace", "🔗 FHIR Mapping", "📊 Analytics Model", "🎯 Reporting Intent", "📝 Report Definition", "📖 Data Dictionary"],
        },
        {
            "name": "org_decisions.json",
            "expected_path": str(KNOWLEDGE_DIR / "org_decisions.json"),
            "stage": "SME Workspace",
            "produced_by": "💬 SME Workspace",
            "consumed_by": ["🔗 FHIR Mapping", "📊 Analytics Model", "🎯 Reporting Intent", "📝 Report Definition", "📖 Data Dictionary", "📐 Measure Generator"],
        },
        {
            "name": "mapping_cache.json",
            "expected_path": str(KNOWLEDGE_DIR / "mapping_cache.json"),
            "stage": "FHIR Mapping",
            "produced_by": "🔗 FHIR Mapping",
            "consumed_by": ["📊 Analytics Model", "📖 Data Dictionary"],
        },
        {
            "name": "analytics_model.json",
            "expected_path": str(OUTPUT_DIR / "analytics_model.json"),
            "stage": "Analytics Model",
            "produced_by": "📊 Analytics Model",
            "consumed_by": ["🎯 Reporting Intent", "📝 Report Definition", "📖 Data Dictionary", "📐 Measure Generator", "🔢 DAX Generator", "📦 PBIP Generator"],
        },
        {
            "name": "reporting_intent.json",
            "expected_path": str(OUTPUT_DIR / "reporting_intent.json"),
            "stage": "Reporting Intent",
            "produced_by": "🎯 Reporting Intent",
            "consumed_by": ["📖 Data Dictionary", "📐 Measure Generator", "📦 PBIP Generator"],
        },
        {
            "name": "report_definition.json",
            "expected_path": str(OUTPUT_DIR / "report_definition.json"),
            "stage": "Report Definition",
            "produced_by": "📝 Report Definition",
            "consumed_by": ["📐 Measure Generator", "📦 PBIP Generator"],
        },
        {
            "name": "data_dictionary.json",
            "expected_path": str(OUTPUT_DIR / "data_dictionary.json"),
            "stage": "Data Dictionary",
            "produced_by": "📖 Data Dictionary",
            "consumed_by": ["📐 Measure Generator", "🔢 DAX Generator", "📦 PBIP Generator"],
        },
        {
            "name": "measures.json",
            "expected_path": str(OUTPUT_DIR / "measures.json"),
            "stage": "Measure Generator",
            "produced_by": "📐 Measure Generator",
            "consumed_by": ["🔢 DAX Generator", "📦 PBIP Generator"],
        },
        {
            "name": "dax_artifacts.json",
            "expected_path": str(OUTPUT_DIR / "dax_artifacts.json"),
            "stage": "DAX Generator",
            "produced_by": "🔢 DAX Generator",
            "consumed_by": ["📦 PBIP Generator"],
        },
        {
            "name": "pbip_project.zip",
            "expected_path": str(OUTPUT_DIR / "pbip_project.zip"),
            "stage": "PBIP Generator",
            "produced_by": "📦 PBIP Generator",
            "consumed_by": [],
        },
    ]

    # ── Check each artifact ───────────────────────────────────────────
    diagnostics = []
    for art in _artifacts:
        path = _DiagPath(art["expected_path"])
        exists = path.exists()
        size = path.stat().st_size if exists else 0
        diagnostics.append({
            **art,
            "exists": exists,
            "actual_path": str(path.resolve()) if exists else "— NOT FOUND —",
            "size_bytes": size,
            "size_display": f"{size / 1024:.1f} KB" if exists else "—",
        })

    found_count = sum(1 for d in diagnostics if d["exists"])
    missing_count = sum(1 for d in diagnostics if not d["exists"])

    # ── Summary metrics ──────────────────────────────────────────────
    sm1, sm2, sm3 = st.columns(3)
    sm1.metric("Total Artifacts", len(diagnostics))
    sm2.metric("✅ Found", found_count)
    sm3.metric("❌ Missing", missing_count)

    # ── Target Artifact Validation Table (Show: Artifact Name, Expected Path, Actual Path, Status) ──
    st.markdown("### 📋 Target Artifact Status Table")
    st.caption("Validating all core artifacts required across the pipeline.")
    
    target_names = [
        "requirements.json",
        "org_decisions.json",
        "mapping_cache.json",
        "analytics_model.json",
        "reporting_intent.json",
        "report_definition.json",
        "data_dictionary.json",
        "measures.json",
        "dax_artifacts.json",
        "pbip_project.zip"
    ]
    master_table = []
    for name in target_names:
        art_info = next((d for d in diagnostics if d["name"] == name), None)
        if art_info:
            master_table.append({
                "Artifact Name": art_info["name"],
                "Expected Path": art_info["expected_path"],
                "Actual Path": art_info["actual_path"],
                "Status": "✅ Found" if art_info["exists"] else "❌ Missing"
            })
    st.dataframe(pd.DataFrame(master_table), use_container_width=True, hide_index=True)

    # ── Root Cause Analysis (Goal resolution) ───────────────────────
    st.markdown("---")
    st.markdown("### 🔍 Root Cause Analysis: Why Measure Generator Cannot Find Report Definition & Data Dictionary")
    st.warning(
        "**Root Cause:** "
        "The **Report Definition Engine** and **Data Dictionary Generator** produce local drafts stored only "
        "in-memory within the Streamlit session state (`st.session_state`). They are not automatically written to the filesystem. "
        "The **Measure Generator** reads directly from files on disk: `output/report_definition.json` and `output/data_dictionary.json` "
        "and has no session state fallback. If the user does not explicitly click **Approve & Save** on those pages, "
        "the files remain missing on disk, blocking the Measure Generator."
    )
    st.info(
        "👉 **Action Plan to Resolve:**\n"
        "1. Go to the **📝 Report Definition** page, generate the report spec, and click the **Approve & Save Report** button.\n"
        "2. Go to the **📖 Data Dictionary** page, generate the dictionary, and click the **Approve & Save Dictionary** button.\n"
        "3. Once both files are approved and saved, navigate back to the **📐 Measure Generator** page to generate measures."
    )

    # ── Pipeline Flow Diagram ────────────────────────────────────────
    st.markdown("---")
    st.markdown("### 📡 Pipeline Flow")
    st.caption("Green = artifact exists. Red = missing and blocking downstream stages.")

    pipeline_stages = [
        ("requirements.json", "📄 Extract"),
        ("org_decisions.json", "💬 SME"),
        ("mapping_cache.json", "🔗 FHIR"),
        ("analytics_model.json", "📊 Model"),
        ("reporting_intent.json", "🎯 Intent"),
        ("report_definition.json", "📝 Report"),
        ("data_dictionary.json", "📖 Dict"),
        ("measures.json", "📐 Measures"),
        ("dax_artifacts.json", "🔢 DAX"),
        ("pbip_project.zip", "📦 PBIP"),
    ]
    diag_lookup = {d["name"]: d["exists"] for d in diagnostics}

    flow_html = ""
    for i, (fname, label) in enumerate(pipeline_stages):
        ok = diag_lookup.get(fname, False)
        cls = "pipeline-ok" if ok else "pipeline-blocked"
        icon = "✅" if ok else "❌"
        flow_html += f'<span class="pipeline-stage {cls}">{icon} {label}</span>'
        if i < len(pipeline_stages) - 1:
            flow_html += '<span class="pipeline-arrow">→</span>'
    st.markdown(flow_html, unsafe_allow_html=True)

    # ── Per-Stage Input Dependencies ─────────────────────────────────
    st.markdown("---")
    st.markdown("### 🔗 Per-Stage Input Dependencies")
    st.caption("Audit of inputs, expected/actual paths, and missing artifacts for each stage of the pipeline.")

    _stages = [
        {
            "name": "📄 Upload & Extract",
            "inputs": [],
            "output": "requirements.json",
        },
        {
            "name": "💬 SME Workspace",
            "inputs": ["requirements.json"],
            "output": "org_decisions.json",
        },
        {
            "name": "🔗 FHIR Mapping",
            "inputs": ["requirements.json", "org_decisions.json"],
            "output": "mapping_cache.json",
        },
        {
            "name": "📊 Analytics Model",
            "inputs": ["requirements.json", "org_decisions.json", "mapping_cache.json"],
            "output": "analytics_model.json",
        },
        {
            "name": "🎯 Reporting Intent",
            "inputs": ["requirements.json", "org_decisions.json", "analytics_model.json"],
            "output": "reporting_intent.json",
        },
        {
            "name": "📝 Report Definition",
            "inputs": ["requirements.json", "org_decisions.json", "analytics_model.json"],
            "output": "report_definition.json",
        },
        {
            "name": "📖 Data Dictionary",
            "inputs": ["requirements.json", "org_decisions.json", "mapping_cache.json", "analytics_model.json", "reporting_intent.json"],
            "output": "data_dictionary.json",
        },
        {
            "name": "📐 Measure Generator",
            "inputs": ["report_definition.json", "data_dictionary.json", "analytics_model.json", "reporting_intent.json"],
            "output": "measures.json",
        },
        {
            "name": "🔢 DAX Generator",
            "inputs": ["measures.json", "analytics_model.json", "data_dictionary.json"],
            "output": "dax_artifacts.json",
        },
        {
            "name": "📦 PBIP Generator",
            "inputs": ["analytics_model.json", "report_definition.json", "reporting_intent.json", "data_dictionary.json", "measures.json", "dax_artifacts.json"],
            "output": "pbip_project.zip",
        },
    ]

    for stage_info in _stages:
        stage_name = stage_info["name"]
        inputs = stage_info["inputs"]
        output = stage_info["output"]
        output_exists = diag_lookup.get(output, False)

        all_inputs_ok = all(diag_lookup.get(inp, False) for inp in inputs)
        stage_status = "✅" if all_inputs_ok else "❌"

        with st.expander(
            f"{stage_status} {stage_name} (Output: `{output}`)",
            expanded=not all_inputs_ok,
        ):
            st.markdown(f"**Output file:** `{output}` — {'<span class="diag-found">✅ Exists</span>' if output_exists else '<span class="diag-missing">❌ Not yet generated</span>'}", unsafe_allow_html=True)
            
            if not inputs:
                st.markdown("*Inputs: Manual upload of PDF source file.*")
            else:
                st.markdown("**Required inputs and paths:**")
                stage_table = []
                missing_inputs = []
                
                for inp in inputs:
                    art_info = next((a for a in diagnostics if a["name"] == inp), None)
                    if art_info:
                        expected = art_info["expected_path"]
                        actual = art_info["actual_path"]
                        status = "✅ Found" if art_info["exists"] else "❌ Missing"
                        if not art_info["exists"]:
                            missing_inputs.append(inp)
                    else:
                        expected = "Unknown"
                        actual = "—"
                        status = "❌ Missing"
                        missing_inputs.append(inp)
                    
                    stage_table.append({
                        "Required Input File": inp,
                        "Expected File Path": expected,
                        "Actual File Path Found": actual,
                        "Status": status
                    })
                
                st.dataframe(pd.DataFrame(stage_table), use_container_width=True, hide_index=True)
                
                if missing_inputs:
                    st.error(f"⚠️ **Missing Artifacts for Stage:** {', '.join(f'`{m}`' for m in missing_inputs)}")
                else:
                    st.success("✅ All required input files found for this stage.")


# =====================================================================
# PAGE: Stored Documents
# =====================================================================
elif page == "📂 Stored Documents":
    st.markdown('<p class="main-title">Stored Documents</p>', unsafe_allow_html=True)
    st.caption("Previously uploaded PDF files stored in the knowledge directory.")

    files = list_stored_files()

    if files:
        for fname in files:
            st.markdown(f"- 📄 `{fname}`")
    else:
        st.info("No documents uploaded yet. Use the **Upload & Extract** page to get started.")
