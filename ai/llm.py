from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Optional


DEFAULT_ELOAGENTS_API_BASE = "https://chat.eloagents.click/api"
DEFAULT_ELOAGENTS_MODEL = "openai/gemini-3-flash-preview"


@dataclass(frozen=True)
class EloAgentsConfig:
    api_key: str
    api_base: str = DEFAULT_ELOAGENTS_API_BASE
    model: str = DEFAULT_ELOAGENTS_MODEL
    temperature: float = 0.1


def load_eloagents_config(
    *,
    api_key: Optional[str] = None,
    api_base: Optional[str] = None,
    model: Optional[str] = None,
    temperature: float = 0.1,
) -> EloAgentsConfig:
    """Load EloAgents settings and expose them through the OpenAI-compatible env vars used by LiteLLM."""
    key = api_key or os.getenv("ELOAGENTS_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not key:
        raise ValueError(
            "Defina ELOAGENTS_API_KEY no ambiente (ou passe api_key explicitamente)."
        )

    base = api_base or os.getenv("ELOAGENTS_API_BASE") or DEFAULT_ELOAGENTS_API_BASE
    chosen_model = model or os.getenv("VERTICE_MODEL") or DEFAULT_ELOAGENTS_MODEL

    # O notebook oficial do bootcamp configura a Sandbox do EloAgents por meio
    # das variáveis OPENAI_* porque o ChatLiteLLM/LiteLLM usa esse padrão.
    os.environ["OPENAI_API_KEY"] = key
    os.environ["OPENAI_API_BASE"] = base

    return EloAgentsConfig(
        api_key=key,
        api_base=base,
        model=chosen_model,
        temperature=temperature,
    )


def build_eloagents_llm(
    *,
    api_key: Optional[str] = None,
    api_base: Optional[str] = None,
    model: Optional[str] = None,
    temperature: float = 0.1,
) -> Any:
    """Create the ChatLiteLLM client using the same EloAgents pattern as the bootcamp notebook."""
    try:
        from langchain_litellm import ChatLiteLLM
    except ImportError as exc:
        raise RuntimeError(
            "Pacote 'langchain-litellm' não instalado. Execute: pip install -r requirements.txt"
        ) from exc

    cfg = load_eloagents_config(
        api_key=api_key,
        api_base=api_base,
        model=model,
        temperature=temperature,
    )

    return ChatLiteLLM(
        model=cfg.model,
        temperature=cfg.temperature,
        api_base=cfg.api_base,
    )
