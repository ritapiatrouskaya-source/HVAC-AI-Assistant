import streamlit as st
import fitz
import json
import base64

from pathlib import Path

from src.loader import load_document
from src.chunking import splitting
from src.vector_store import load_or_create_vector_store
from src.llm import create_llm
from src.retriever import create_retriever
from src.rag import ask_question
from src.config import DATA_PATH
from search.search_equipment import find_model

PROJECT_ROOT = Path(__file__).resolve().parent
BACKGROUND_PATH = PROJECT_ROOT / "assets" / "back.png"

with open(BACKGROUND_PATH, "rb") as f:
    bg_image = base64.b64encode(f.read()).decode()


st.set_page_config(
    page_title="HVAC Technical AI Assistant",
    layout="wide"
)

@st.dialog("Daikin General Catalog")
def show_pdf_dialog(pdf_path, page_number):

    pdf = fitz.open(pdf_path)

    try:
        page = pdf.load_page(page_number)
        pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5))
        image_bytes = pix.tobytes("png")

        st.image(image_bytes, use_container_width=True)

    finally:
        pdf.close()

@st.dialog("About — HVAC Technical AI Assistant")
def show_about_dialog():
    st.markdown("""
    ## HVAC Technical AI Assistant

    AI-powered assistant for HVAC technical documentation.

    The application uses Retrieval-Augmented Generation (RAG)
    to answer technical questions based on manufacturer documentation.

    ---

    ### Documentation

    The current knowledge base includes:

    - Daikin General Catalog
    - Engineering Data
    - Installation Manual
    - Service Manual

    ### Current Scope

    - Daikin Single-Split / Single-Zone systems
    - Technical specifications
    - Installation requirements
    - Piping
    - Refrigerants
    - Error codes and troubleshooting

    ### Technology

    - Python
    - Streamlit
    - LangChain
    - Chroma
    - HuggingFace Embeddings
    - Ollama
    - Llama 3.1
    - Retrieval-Augmented Generation (RAG)

    ### Project

    Source code and project documentation:
    """)

    st.link_button(
        "GitHub",
        "https://github.com/ritapiatrouskaya-source/HVAC-AI-Assistant"
    )

if st.query_params.get("about") == "1":
    show_about_dialog()
    st.query_params.clear()

st.markdown(f"""
<style>
    /* =========================================
       GLOBAL
       ========================================= */
    .stApp {{
        background: #f5f8fc;
    }}

    .block-container {{
        max-width: 1500px;
        padding-top: 1rem;
        padding-bottom: 2rem;
    }}

    /* =========================================
       HEADER
       ========================================= */

    .app-header {{
        background: rgba(255, 255, 255, 0.96);
        border-radius: 18px;
        padding: 18px 28px;
        margin-bottom: 18px;

        display: flex;
        align-items: center;
        justify-content: space-between;

        box-shadow: 0 4px 20px rgba(30, 60, 90, 0.08);
    }}
    
    .header-nav {{
        display: flex;
        align-items: center;
        gap: 24px;
    }}
    
    .header-nav a {{
        color: #66758c;
        text-decoration: none;
        font-size: 16px;
        font-weight: 500;
    }}
    
    .header-nav a:hover {{
        color: #10234a;
    }}

    .app-title {{
        font-size: 26px;
        font-weight: 700;
        color: #10234a;
    }}

    .app-subtitle {{
        font-size: 13px;
        color: #71809a;
        margin-top: 3px;
    }}

    /* =========================================
       LEFT PANEL
       ========================================= */
       
    .left-panel-anchor {{
    display: none;
    }}

    div[data-testid="stColumn"]:has(.left-panel-anchor) {{
        background:
            linear-gradient(
                rgba(255, 255, 255, 0.25),
                rgba(255, 255, 255, 0.35)
            ),
            url("data:image/png;base64,{bg_image}");
    
        background-size: cover;
        background-position: center;
    
        border-radius: 22px;
        padding: 26px;
    
        box-shadow: 0 8px 30px rgba(30, 60, 90, 0.10);
    }}
    .panel-title {{
        font-size: 23px;
        font-weight: 700;
        color: #10234a;
        margin-bottom: 5px;
    }}

    .panel-description {{
        color: #2E3743;
        font-size: 14px;
        line-height: 1.5;
        margin-bottom: 25px;
    }}

    /* =========================================
       EQUIPMENT CARD
       ========================================= */

    .equipment-card {{
        background: rgba(255,255,255,0.94);
        border-radius: 18px;
        padding: 20px;
        margin-top: 20px;

        box-shadow: 0 5px 20px rgba(30, 60, 90, 0.08);
    }}

    .equipment-model {{
        font-size: 20px;
        font-weight: 700;
        color: #10234a;
    }}

    .equipment-family {{
        font-size: 13px;
        color: #71809a;
        margin-bottom: 15px;
    }}

    .spec-row {{
        display: flex;
        justify-content: space-between;
        padding: 9px 0;
        border-bottom: 1px solid #edf1f7;
    }}

    .spec-name {{
        color: #66758c;
        font-size: 14px;
    }}

    .spec-value {{
        color: #172b4d;
        font-weight: 600;
        font-size: 14px;
    }}

    /* =========================================
       CHAT
       ========================================= */

    .chat-panel {{
        background: rgba(255,255,255,0.96);
        border-radius: 22px;
        min-height: 760px;
        padding: 30px;

        box-shadow: 0 8px 30px rgba(30, 60, 90, 0.08);
    }}

    .welcome-title {{
        font-size: 25px;
        font-weight: 700;
        color: #10234a;
    }}

    .welcome-text {{
        color: #64748b;
        line-height: 1.6;
    }}

    .example-box {{
        background: #eef6ff;
        border-radius: 16px;
        padding: 18px;
        margin: 20px 0;
    }}

    .example-title {{
        font-weight: 600;
        color: #1769aa;
        margin-bottom: 10px;
    }}

    .source-box {{
        background: #f5f8fc;
        border-left: 4px solid #2d8cff;
        padding: 12px 16px;
        border-radius: 8px;
        color: #56657a;
        font-size: 14px;
    }}

    /* =========================================
       FOOTER
       ========================================= */

    .disclaimer {{
        text-align: center;
        color: #8a97aa;
        font-size: 11px;
        margin-top: 10px;
    }}

</style>
""", unsafe_allow_html=True)

st.markdown("""
    <div class="app-header">
    <div>
    <div class="app-title">
    ❄ HVAC Technical AI Assistant
    </div>
    <div class="app-subtitle">
    AI assistant for HVAC technical documentation
    </div>
    </div>
    <div class="header-nav">
    <a href="?about=1">ℹ About</a>
    <a href="https://github.com/ritapiatrouskaya-source/HVAC-AI-Assistant" target="_blank">GitHub</a>
    </div>
    </div>
""", unsafe_allow_html=True)

CATALOG_PATH = (PROJECT_ROOT / "data" / "catalog" / "GeneralCatalog.pdf")

EQUIPMENT_PATH = (PROJECT_ROOT / "data" / "indexes" / "equipment_database.json")

with open(EQUIPMENT_PATH, encoding="utf-8") as f:
    equipment = json.load(f)

@st.cache_resource
def load_backend():

    documents = load_document(str(DATA_PATH))
    chunks = splitting(documents)
    vector_db = load_or_create_vector_store(chunks)
    retriever = create_retriever(vector_db)
    llm = create_llm()
    return vector_db, retriever, llm, documents

vector_db, retriever, llm, documents = load_backend()

left, right = st.columns([0.75, 1.65], gap="large")

with left:
    st.markdown(
        '<div class="left-panel-anchor"></div>',
        unsafe_allow_html=True
    )
        
    st.markdown("""
    <div class="panel-title">
        Select Your Model
    </div>

    <div class="panel-description">
        Choose the indoor unit to get accurate answers
        from Daikin technical documentation.
    </div>
    """, unsafe_allow_html=True)

    families = sorted(set(item["family"] for item in equipment))

    selected_family = st.selectbox("Product Series", families)

    family_models = [
        item["model"]
        for item in equipment
        if item["family"] == selected_family
    ]

    selected_model = st.selectbox("Indoor Unit Model", family_models)
    selected_equipment = find_model(equipment, selected_model)

    if selected_equipment:
        manufacturer = selected_equipment["manufacturer"]

        st.markdown(
            f"""
        <div class="equipment-card">
            <div class="equipment-model">
                {selected_equipment['model']}
            </div>
            <div class="equipment-family">
                {selected_equipment['family']}
            </div>
            <div class="spec-row">
                <span class="spec-name">Cooling capacity</span>
                <span class="spec-value">
                    {selected_equipment['cooling_capacity']}
                </span>
            </div>
            <div class="spec-row">
                <span class="spec-name">Heating capacity</span>
                <span class="spec-value">
                    {selected_equipment['heating_capacity']}
                </span>
            </div>
            <div class="spec-row">
                <span class="spec-name">Liquid pipe</span>
                <span class="spec-value">
                    {selected_equipment['liquid_pipe']}
                </span>
            </div>
            <div class="spec-row">
                <span class="spec-name">Gas pipe</span>
                <span class="spec-value">
                    {selected_equipment['gas_pipe']}
                </span>
            </div>
            <div class="spec-row">
                <span class="spec-name">Sound level</span>
                <span class="spec-value">
                    {selected_equipment['sound_level']}
                </span>
            </div>
        </div>
        """,
            unsafe_allow_html=True
        )

    if st.button("📄 Show PDF Page", use_container_width=True):
        show_pdf_dialog( CATALOG_PATH, selected_equipment["pdf_page"] )

indoor_unit = selected_model

with right:

    st.markdown("""
    <div class="welcome-title">
        Welcome to the HVAC Technical AI Assistant
    </div>

    <p class="welcome-text">
        Ask questions about technical specifications,
        installation requirements, troubleshooting,
        piping, refrigerants and more.
    </p>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div class="example-box">
        <div class="example-title">
            💡 You can ask, for example:
        </div>
    </div>
    """, unsafe_allow_html=True)

    example1, example2 = st.columns(2)

    with example1:

        if st.button(
            "What is the maximum piping length?",
            use_container_width=True
        ):
            st.session_state.question = (
                "What is the maximum piping length?"
            )

        if st.button(
            "What does error U4 mean?",
            use_container_width=True
        ):
            st.session_state.question = (
                "What does error U4 mean?"
            )

    with example2:

        if st.button(
            "What are the dimensions?",
            use_container_width=True
        ):
            st.session_state.question = (
                "What are the dimensions?"
            )

        if st.button(
            "What type of refrigerant is used?",
            use_container_width=True
        ):
            st.session_state.question = (
                "What type of refrigerant is used?"
            )

    question = st.text_input(
        "Ask your question",
        value=st.session_state.get(
            "question",
            ""
        ),
        placeholder="Ask a technical question..."
    )

    if st.button("➤ Ask", type="primary"):

        answer = ask_question(
            vector_db,
            retriever,
            llm,
            question=question,
            manufacturer=manufacturer,
            outdoor_unit=None,
            indoor_unit=selected_model,
        )

        st.markdown(
            '<div class="source-box">',
            unsafe_allow_html=True
        )

        st.write(answer)

        st.markdown(
            '</div>',
            unsafe_allow_html=True
        )