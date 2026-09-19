from __future__ import annotations

import argparse
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from ai.agent import VerticeAgent

DEFAULT_QUESTIONS = [
    "Onde estamos perdendo margem?",
    "Quais canais têm maior eficiência de aquisição?",
    "Quais problemas de estoque deveriam ser analisados?",
    "Quais oportunidades existem em atendimento?",
    "Quais oportunidades deveriam ser priorizadas nos próximos 30 dias?",
]

EXPECTED_TOOLS = {
    DEFAULT_QUESTIONS[0]: "get_margin_opportunities",
    DEFAULT_QUESTIONS[1]: "get_marketing_efficiency",
    DEFAULT_QUESTIONS[2]: "get_inventory_opportunities",
    DEFAULT_QUESTIONS[3]: "get_support_opportunities",
    DEFAULT_QUESTIONS[4]: "get_prioritized_opportunities",
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Smoke test da integração real Vértice + EloAgents")
    parser.add_argument("--context", default="data/vertice_ai_context.json")
    parser.add_argument("--model", default=None)
    parser.add_argument("--limit", type=int, default=5)
    args = parser.parse_args()

    questions = DEFAULT_QUESTIONS[: max(1, min(args.limit, len(DEFAULT_QUESTIONS)))]
    agent = VerticeAgent(Path(args.context), model=args.model)

    print("=" * 72)
    print("VÉRTICE INTELLIGENCE — FASE A / SMOKE TEST REAL")
    print("EloAgents + ChatLiteLLM + Tool Calling")
    print("=" * 72)

    failures = 0

    for idx, question in enumerate(questions, start=1):
        print(f"\n[{idx}/{len(questions)}] {question}")
        before = len(agent.audit_log)
        try:
            answer = agent.ask(question)
            new_events = agent.audit_log[before:]

            tool_events = [
                event for event in new_events
                if event.get("status") in {"tool_executed", "tool_executed_fallback"}
                and event.get("tool")
            ]
            tools_used = list(dict.fromkeys(event["tool"] for event in tool_events))
            execution_modes = list(
                dict.fromkeys(
                    "LLM tool call" if event["status"] == "tool_executed" else "fallback determinístico"
                    for event in tool_events
                )
            )
            unknown_tools = list(dict.fromkeys(
                event["tool"]
                for event in new_events
                if event.get("status") == "unknown_tool" and event.get("tool")
            ))

            expected = EXPECTED_TOOLS[question]

            if expected not in tools_used:
                failures += 1
                print("STATUS: ERRO")
                print(f"Tool esperada não executada: {expected}")
                print("TOOLS:", ", ".join(tools_used) or "nenhuma")
            else:
                print("STATUS: OK")
                print("TOOLS:", ", ".join(tools_used))
                print("EXECUÇÃO:", ", ".join(execution_modes))

            if unknown_tools:
                print("TOOLS DESCONHECIDAS TENTADAS:", ", ".join(unknown_tools))
                print("AVISO: bloqueadas pelo contrato de tools; não foram executadas.")

            print("RESPOSTA:")
            print(answer.strip())
        except Exception as exc:
            failures += 1
            print("STATUS: ERRO")
            print(f"{type(exc).__name__}: {exc}")

    audit_path = Path("logs/phase_a_smoke_test.json")
    agent.save_audit(audit_path)
    print("\n" + "=" * 72)
    print(f"Perguntas com erro: {failures}/{len(questions)}")
    print(f"Auditoria: {audit_path}")
    print("=" * 72)

    raise SystemExit(1 if failures else 0)


if __name__ == "__main__":
    main()
