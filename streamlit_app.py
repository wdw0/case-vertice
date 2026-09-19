from __future__ import annotations

import html
import os
import re
from pathlib import Path
from typing import Any, Dict, List

import streamlit as st
from dotenv import load_dotenv

from ai.agent import VerticeAgent
from ai.context import ContextStore

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
CONTEXT_PATH = BASE_DIR / "data" / "vertice_ai_context.json"

st.set_page_config(
    page_title="Vértice Intelligence",
    page_icon="◈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------
# CSS: v4 intentionally does NOT rely on Streamlit chat bubbles for the
# response content. The previous versions inherited theme colors inside
# st.chat_message, causing white text on a light background.
# We render the conversation as explicit HTML cards instead.
# ---------------------------------------------------------------------
st.markdown(
    """
    <style>
    .stApp,
    [data-testid="stAppViewContainer"],
    [data-testid="stMain"] {
        background: #f4f5f9 !important;
        color: #172033 !important;
    }

    .main .block-container {
        max-width: 1180px;
        padding: 1.45rem 2rem 4rem;
    }

    /* Sidebar */
    [data-testid="stSidebar"] {
        background: #171824 !important;
        border-right: 1px solid #292b39 !important;
    }

    [data-testid="stSidebar"] *,
    [data-testid="stSidebar"] [data-testid="stMarkdownContainer"],
    [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p,
    [data-testid="stSidebar"] label {
        color: #f5f7fb !important;
    }

    [data-testid="stSidebar"] small,
    [data-testid="stSidebar"] .stCaption {
        color: #aeb5c4 !important;
    }

    /* Generic main text */
    .main [data-testid="stMarkdownContainer"],
    .main [data-testid="stMarkdownContainer"] p,
    .main [data-testid="stMarkdownContainer"] li,
    .main [data-testid="stMarkdownContainer"] strong,
    .main [data-testid="stMarkdownContainer"] em {
        color: #172033 !important;
    }

    .main h1, .main h2, .main h3, .main h4 {
        color: #111827 !important;
    }

    /* Header */
    .hero {
        background: linear-gradient(135deg, #171825 0%, #30246e 100%);
        border-radius: 18px;
        padding: 28px 30px;
        margin-bottom: 18px;
        box-shadow: 0 14px 35px rgba(48, 36, 110, .14);
    }

    .hero-title {
        color: #ffffff !important;
        font-size: 2rem;
        font-weight: 800;
        letter-spacing: -.035em;
        line-height: 1.05;
    }

    .hero-subtitle {
        color: rgba(255,255,255,.78) !important;
        font-size: .95rem;
        margin-top: 7px;
    }

    .section-label {
        color: #667085 !important;
        font-size: .72rem;
        letter-spacing: .1em;
        text-transform: uppercase;
        font-weight: 800;
        margin: 17px 0 8px;
    }

    /* Quick prompts */
    .stButton > button {
        min-height: 46px;
        border-radius: 11px !important;
        border: 1px solid #dfe3ec !important;
        background: #ffffff !important;
        color: #202637 !important;
        font-weight: 650 !important;
        box-shadow: 0 2px 8px rgba(17, 24, 39, .035) !important;
    }

    .stButton > button:hover {
        border-color: #6d5dfc !important;
        color: #4f46e5 !important;
        box-shadow: 0 6px 18px rgba(79,70,229,.10) !important;
    }

    /* Conversation cards */
    .user-card,
    .assistant-card {
        border-radius: 15px;
        padding: 16px 18px;
        margin: 10px 0;
    }

    .user-card {
        background: #e7e9ee;
        border: 1px solid #d5d9e1;
        color: #172033 !important;
        margin-left: 9%;
    }

    .assistant-card {
        background: #ffffff;
        border: 1px solid #dde1e8;
        color: #172033 !important;
        box-shadow: 0 7px 20px rgba(17, 24, 39, .045);
        margin-right: 4%;
    }

    .card-label {
        color: #6b7280 !important;
        font-size: .72rem;
        text-transform: uppercase;
        letter-spacing: .08em;
        font-weight: 800;
        margin-bottom: 7px;
    }

    .user-card .card-label {
        color: #5a6475 !important;
    }

    .assistant-card .answer-content,
    .assistant-card .answer-content p,
    .assistant-card .answer-content li,
    .assistant-card .answer-content strong,
    .assistant-card .answer-content em,
    .assistant-card .answer-content h1,
    .assistant-card .answer-content h2,
    .assistant-card .answer-content h3,
    .assistant-card .answer-content h4,
    .assistant-card .answer-content td,
    .assistant-card .answer-content th {
        color: #172033 !important;
    }

    .assistant-card .answer-content h1,
    .assistant-card .answer-content h2,
    .assistant-card .answer-content h3 {
        margin-top: 1rem;
        margin-bottom: .45rem;
        color: #111827 !important;
    }

    .assistant-card .answer-content table {
        border-collapse: collapse;
        width: 100%;
        margin: 12px 0;
    }

    .assistant-card .answer-content th,
    .assistant-card .answer-content td {
        border: 1px solid #e2e5ea;
        padding: 7px 9px;
        text-align: left;
    }

    .assistant-card .answer-content th {
        background: #f5f6f8;
        font-weight: 750;
    }

    .assistant-card .answer-content blockquote {
        margin: 12px 0;
        padding: 10px 13px;
        border-left: 4px solid #6d5dfc;
        background: #f6f5ff;
        color: #344054 !important;
    }

    .assistant-card .answer-content code {
        color: #4f46e5 !important;
        background: #f1f2f8;
        padding: 1px 4px;
        border-radius: 4px;
    }

    /* Trace pills */
    .trace-row {
        display: flex;
        flex-wrap: wrap;
        gap: 7px;
        margin: 10px 0 2px;
    }

    .trace-pill {
        display: inline-block;
        border-radius: 999px;
        padding: 5px 9px;
        font-size: .72rem;
        font-weight: 750;
        line-height: 1;
    }

    .trace-used {
        background: #ecfdf3;
        color: #067647 !important;
    }

    .trace-fallback {
        background: #fff4e8;
        color: #b54708 !important;
    }

    /* Welcome */
    .welcome {
        background: #ffffff;
        border: 1px solid #e3e6ee;
        border-radius: 16px;
        padding: 22px;
        box-shadow: 0 6px 18px rgba(17,24,39,.04);
        margin: 8px 0 16px;
    }

    .welcome-title {
        color: #111827 !important;
        font-size: 1.12rem;
        font-weight: 780;
    }

    .welcome-text {
        color: #667085 !important;
        font-size: .9rem;
        margin-top: 4px;
    }

    /* Opportunities */
    .opportunity-card {
        background: #ffffff;
        border: 1px solid #e3e6ee;
        border-radius: 15px;
        padding: 18px;
        margin-bottom: 10px;
        box-shadow: 0 5px 16px rgba(17,24,39,.035);
    }

    .opportunity-card * {
        color: #172033 !important;
    }

    .muted {
        color: #667085 !important;
        font-size: .84rem;
    }

    [data-testid="stChatInput"] {
        border-radius: 14px !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# Optional dependency is intentionally small and only used to turn the
# LLM's markdown answer into HTML before placing it in a guaranteed-light
# card. If unavailable, a safe plain-text fallback is used.
try:
    import markdown as md
except Exception:
    md = None


def get_context() -> ContextStore:
    if "context_store" not in st.session_state:
        st.session_state.context_store = ContextStore(CONTEXT_PATH)
    return st.session_state.context_store


def get_agent() -> VerticeAgent:
    if "agent" not in st.session_state:
        st.session_state.agent = VerticeAgent(CONTEXT_PATH)
    return st.session_state.agent


def markdown_to_html(text: str) -> str:
    if md is not None:
        return md.markdown(
            text,
            extensions=["tables", "fenced_code"],
        )

    # Safe fallback if the markdown package is absent.
    escaped = html.escape(text).replace("\n", "<br>")
    return f"<p>{escaped}</p>"


def render_header(page: str) -> None:
    st.markdown(
        f"""
        <div class="hero">
            <div class="hero-title">Vértice Intelligence</div>
            <div class="hero-subtitle">Decision Copilot · {page}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_trace(audit_entries: List[Dict[str, Any]]) -> None:
    if not audit_entries:
        return

    final_entry = next(
        (entry for entry in reversed(audit_entries) if entry.get("status") == "final"),
        None,
    )

    if not final_entry:
        return

    payload = final_entry.get("payload") or {}
    tools_used: List[str] = payload.get("tools_used") or []
    execution_modes: List[str] = payload.get("execution_modes") or []

    # The user requested only modules actually used. Blocked/unknown tools
    # are deliberately NOT displayed in the UI.
    if not tools_used:
        return

    pills: List[str] = []
    for idx, tool in enumerate(tools_used):
        mode = execution_modes[idx] if idx < len(execution_modes) else ""
        cls = "trace-fallback" if mode == "deterministic_fallback" else "trace-used"
        suffix = " · fallback" if mode == "deterministic_fallback" else " · LLM"
        pills.append(
            f'<span class="trace-pill {cls}">{html.escape(tool)}{suffix}</span>'
        )

    st.markdown(
        '<div class="trace-row">' + "".join(pills) + "</div>",
        unsafe_allow_html=True,
    )


def ask_agent(question: str) -> None:
    agent = get_agent()
    history: List[Dict[str, Any]] = st.session_state.setdefault("history", [])
    before = len(agent.audit_log)

    try:
        conversation = []
        for item in history[-4:]:
            tools_used = list(item.get("tools_used") or [])
            if not tools_used:
                for audit in reversed(item.get("audit") or []):
                    if audit.get("status") == "final":
                        tools_used = list((audit.get("payload") or {}).get("tools_used") or [])
                        break
            conversation.append(
                {
                    "question": item.get("question", ""),
                    "answer": item.get("answer", ""),
                    "tools_used": tools_used,
                    "audit": item.get("audit", []),
                }
            )

        with st.spinner("Analisando dados e preparando resposta..."):
            answer = agent.ask(question, conversation=conversation)
    except Exception as exc:
        st.error(
            "Não foi possível concluir a pergunta. "
            "Verifique o EloAgents e o terminal para os detalhes."
        )
        st.exception(exc)
        return

    audit_entries = agent.audit_log[before:]
    final_entry = next(
        (entry for entry in reversed(audit_entries) if entry.get("status") == "final"),
        None,
    )
    tools_used = list((final_entry.get("payload") or {}).get("tools_used") or []) if final_entry else []

    history.append(
        {
            "question": question,
            "answer": answer,
            "tools_used": tools_used,
            "audit": audit_entries,
        }
    )


def render_welcome() -> None:
    st.markdown(
        """
        <div class="welcome">
            <div class="welcome-title">Pergunte à inteligência da Vértice</div>
            <div class="welcome-text">
                Consulte margem, marketing, estoque e atendimento em linguagem natural.
                As respostas usam a camada analítica e mostram as ferramentas realmente utilizadas.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_quick_questions() -> None:
    questions = [
        "Onde estamos perdendo margem?",
        "Quais canais têm maior eficiência de aquisição?",
        "Quais problemas de estoque deveriam ser analisados?",
        "Quais oportunidades existem em atendimento?",
        "Quais oportunidades deveriam ser priorizadas nos próximos 30 dias?",
    ]

    st.markdown(
        '<div class="section-label">Perguntas rápidas</div>',
        unsafe_allow_html=True,
    )

    cols = st.columns(2)
    for idx, question in enumerate(questions):
        if cols[idx % 2].button(
            question,
            key=f"quick_{idx}",
            use_container_width=True,
        ):
            ask_agent(question)
            st.rerun()


def render_chat() -> None:
    history: List[Dict[str, Any]] = st.session_state.get("history", [])

    if not history:
        render_welcome()

    for item in history:
        user_text = html.escape(item["question"])
        answer_html = markdown_to_html(item["answer"])

        st.markdown(
            f"""
            <div class="user-card">
                <div class="card-label">Você</div>
                <div>{user_text}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown(
            f"""
            <div class="assistant-card">
                <div class="card-label">Vértice Intelligence</div>
                <div class="answer-content">{answer_html}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        render_trace(item["audit"])

    prompt = st.chat_input(
        "Pergunte algo sobre margem, marketing, estoque ou atendimento..."
    )

    if prompt:
        ask_agent(prompt)
        st.rerun()


def render_copilot() -> None:
    render_header("Copilot")
    st.markdown(
        '<div class="muted">Faça uma pergunta em linguagem natural sobre o negócio.</div>',
        unsafe_allow_html=True,
    )
    render_quick_questions()
    render_chat()


def render_opportunities() -> None:
    ctx = get_context()
    portfolio = ctx.prioritized()

    render_header("Oportunidades")

    if not portfolio:
        st.info("Nenhuma oportunidade priorizada encontrada.")
        return

    st.markdown(
        '<div class="muted">Portfólio produzido pelo Opportunity Engine da Etapa 1.</div>',
        unsafe_allow_html=True,
    )

    areas = sorted({item.get("area", "") for item in portfolio})
    confidence_values = sorted(
        {str(item.get("confiança", "")) for item in portfolio}
    )

    c1, c2 = st.columns(2)
    area = c1.selectbox("Área", ["Todas"] + areas)
    confidence = c2.selectbox("Confiança", ["Todas"] + confidence_values)

    filtered = portfolio

    if area != "Todas":
        filtered = [x for x in filtered if x.get("area") == area]

    if confidence != "Todas":
        filtered = [
            x for x in filtered
            if str(x.get("confiança", "")) == confidence
        ]

    for item in filtered:
        st.markdown(
            f"""
            <div class="opportunity-card">
                <div class="muted">
                    #{html.escape(str(item.get("rank", "")))} ·
                    {html.escape(str(item.get("id", "")))} ·
                    {html.escape(str(item.get("area", "")))}
                </div>
                <h3>{html.escape(str(item.get("oportunidade", item.get("title", ""))))}</h3>
                <p>
                    <strong>Score:</strong> {html.escape(str(item.get("score", "")))}
                    &nbsp;&nbsp;
                    <strong>Impacto:</strong> {html.escape(str(item.get("impact", "")))}
                    &nbsp;&nbsp;
                    <strong>Esforço:</strong> {html.escape(str(item.get("effort", "")))}
                    &nbsp;&nbsp;
                    <strong>Velocidade:</strong> {html.escape(str(item.get("speed", "")))}
                </p>
                <p class="muted">
                    Confiança: {html.escape(str(item.get("confiança", "")))}
                    · Status: {html.escape(str(item.get("status", "")))}
                    · Tipo de impacto: {html.escape(str(item.get("impact_type", "")))}
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    if filtered:
        st.markdown(
            '<div class="section-label">Detalhes</div>',
            unsafe_allow_html=True,
        )

        selected_id = st.selectbox(
            "Oportunidade",
            [x.get("id") for x in filtered],
            format_func=lambda value: (
                f"{value} — "
                f"{next((o.get('oportunidade') for o in filtered if o.get('id') == value), '')}"
            ),
        )

        opportunity = ctx.opportunity_by_id(selected_id)

        if opportunity:
            with st.container(border=True):
                st.markdown(
                    f"### {html.escape(str(opportunity.get('title', '')))}"
                )
                st.markdown(opportunity.get("evidence", ""))

                col1, col2, col3 = st.columns(3)
                col1.metric(
                    "Confiança",
                    str(opportunity.get("confidence", "")).upper(),
                )
                col2.metric(
                    "Status",
                    str(opportunity.get("status", "")).upper(),
                )
                col3.metric(
                    "Tipo de impacto",
                    str(opportunity.get("impact_type", "")).upper(),
                )

                limitations = opportunity.get("limitations") or []
                if limitations:
                    st.markdown("**Limitações**")
                    for limitation in limitations:
                        st.markdown(f"- {limitation}")


def main() -> None:
    st.sidebar.markdown(
        """
        <div style="font-size:1.2rem;font-weight:800;color:#f5f7fb;">
            Vértice Intelligence
        </div>
        <div style="color:#aeb5c4;font-size:.84rem;margin-top:4px;">
            Decision Copilot · Case Vértice
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.sidebar.markdown("<br>", unsafe_allow_html=True)

    page = st.sidebar.radio(
        "Navegação",
        ["Copilot", "Oportunidades"],
    )

    st.sidebar.divider()

    if os.getenv("ELOAGENTS_API_KEY"):
        st.sidebar.success("EloAgents configurado")
    else:
        st.sidebar.warning("EloAgents não configurado")

    if st.sidebar.button("Limpar conversa", use_container_width=True):
        st.session_state.history = []
        st.rerun()

    if page == "Copilot":
        render_copilot()
    else:
        render_opportunities()


if __name__ == "__main__":
    main()
