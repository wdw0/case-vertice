from __future__ import annotations

import argparse
import json
from pathlib import Path

from ai.agent import VerticeAgent
from ai.context import ContextStore
from ai.tools import ToolRegistry

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def demo(question: str, context_path: Path) -> None:
    """Deterministic routing smoke test; no LLM/network call."""
    context = ContextStore(context_path)
    tools = ToolRegistry(context)

    q = question.lower()
    if "margem" in q:
        result = tools.execute("get_margin_opportunities").result
    elif any(term in q for term in ("marketing", "canal", "canais", "roas", "cac")):
        result = tools.execute(
            "get_marketing_efficiency",
            {"order_by": "roas", "descending": True},
        ).result
    elif any(term in q for term in ("estoque", "ruptura", "sku")):
        result = tools.execute("get_inventory_opportunities", {"limit": 10}).result
    elif any(term in q for term in ("atendimento", "wismo", "ticket")):
        result = tools.execute("get_support_opportunities", {"limit": 10}).result
    elif any(term in q for term in ("prior", "30 dias", "60 dias", "90 dias")):
        result = tools.execute("get_prioritized_opportunities").result
    else:
        result = {
            "message": "Pergunta não roteada no modo demo determinístico. Configure o agente com EloAgents para tool calling.",
        }
    print(json.dumps(result, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="Vértice Intelligence — Etapa 2 / EloAgents")
    parser.add_argument("question", nargs="?", help="Pergunta executiva")
    parser.add_argument("--context", default="data/vertice_ai_context.json")
    parser.add_argument("--demo", action="store_true", help="Executa Tools sem LLM")
    parser.add_argument("--audit", default="logs/tool_calls.json")
    parser.add_argument("--model", default=None, help="Modelo habilitado no EloAgents")
    args = parser.parse_args()

    context_path = Path(args.context)
    if args.demo:
        if not args.question:
            parser.error("Passe uma pergunta no modo --demo.")
        demo(args.question, context_path)
        return

    if not args.question:
        parser.error("Passe uma pergunta ou use --demo.")

    agent = VerticeAgent(context_path, model=args.model)
    answer = agent.ask(args.question)
    print(answer)
    agent.save_audit(args.audit)


if __name__ == "__main__":
    main()
