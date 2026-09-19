from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from .context import ContextStore
from .llm import build_eloagents_llm
from .prompts import SYSTEM_PROMPT, SYNTHESIS_PROMPT
from .routing import infer_tool_for_question
from .tools import ToolRegistry, build_langchain_tools


class VerticeAgent:
    """Decision Copilot usando ChatLiteLLM/EloAgents e tools determinísticas."""

    def __init__(
        self,
        context_path: str | Path,
        *,
        llm: Optional[Any] = None,
        model: Optional[str] = None,
        max_tool_rounds: int = 5,
    ):
        self.context = ContextStore(context_path)
        self.registry = ToolRegistry(self.context)
        self.tools = build_langchain_tools(self.registry)
        self.llm = llm or build_eloagents_llm(model=model)
        self.llm_with_tools = self.llm.bind_tools(self.tools)
        self.max_tool_rounds = max(1, max_tool_rounds)
        self.audit_log: List[Dict[str, Any]] = []

    def ask(self, question: str) -> str:
        """Executa uma pergunta e mantém a síntese desacoplada do protocolo de tools.

        O EloAgents/Gemini pode retornar chamadas de tools externas ao contrato local
        ou múltiplos function calls. Nunca reenviamos esse AIMessage para a etapa de
        síntese com ToolMessages parciais, pois isso quebra o contrato de Chat
        Completions (o número de function responses deve corresponder aos calls).
        Em vez disso, a síntese recebe um pacote textual estruturado com os resultados
        determinísticos efetivamente executados.
        """
        if not question.strip():
            raise ValueError("A pergunta não pode ser vazia.")

        try:
            from langchain_core.messages import HumanMessage, SystemMessage
        except ImportError as exc:
            raise RuntimeError(
                "Dependências LangChain ausentes. Execute: pip install -r requirements.txt"
            ) from exc

        available_tools = self.registry.names()
        forced_tool = infer_tool_for_question(question)

        if forced_tool:
            tool_obj = next(t for t in self.tools if t.name == forced_tool)
            first_llm = self._bind_forced_tool(tool_obj, forced_tool)
        else:
            first_llm = self.llm_with_tools

        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=question),
        ]

        executed_results: List[Dict[str, Any]] = []
        tool_calls = []

        try:
            response = first_llm.invoke(messages)
        except Exception as exc:
            self._log(
                question=question,
                round_idx=1,
                tool_name=None,
                arguments={},
                payload={"error": type(exc).__name__, "message": str(exc)},
                status="llm_error",
            )
            raise RuntimeError(
                "Falha ao consultar o EloAgents. Verifique a chave, o modelo e o endpoint. "
                f"Detalhe: {exc}"
            ) from exc

        tool_calls = getattr(response, "tool_calls", None) or []

        for call in tool_calls:
            name = call.get("name")
            arguments = call.get("args") or {}

            if not name:
                self._log(
                    question=question,
                    round_idx=1,
                    tool_name=None,
                    arguments=arguments,
                    payload={"raw_call": call},
                    status="invalid_tool_call",
                )
                continue

            if name not in available_tools:
                payload = {
                    "error": f"Tool '{name}' não está disponível neste agente.",
                    "available_tools": available_tools,
                    "required_tool": forced_tool,
                }
                self._log(
                    question=question,
                    round_idx=1,
                    tool_name=name,
                    arguments=arguments,
                    payload=payload,
                    status="unknown_tool",
                )
                continue

            if forced_tool and name != forced_tool:
                payload = {
                    "error": f"Tool '{name}' foi rejeitada pela guarda de intenção.",
                    "required_tool": forced_tool,
                }
                self._log(
                    question=question,
                    round_idx=1,
                    tool_name=name,
                    arguments=arguments,
                    payload=payload,
                    status="guardrail_rejected_tool",
                )
                continue

            try:
                execution = self.registry.execute(name, arguments)
            except Exception as exc:
                payload = {"error": type(exc).__name__, "message": str(exc)}
                self._log(
                    question=question,
                    round_idx=1,
                    tool_name=name,
                    arguments=arguments,
                    payload=payload,
                    status="tool_error",
                )
                continue

            executed_results.append(
                {
                    "tool": execution.name,
                    "arguments": execution.arguments,
                    "result": execution.result,
                    "execution_mode": "llm_tool_call",
                }
            )
            self._log(
                question=question,
                round_idx=1,
                tool_name=name,
                arguments=arguments,
                payload=execution.result,
                status="tool_executed",
            )

        # Fallback determinístico para intents canônicos quando o proxy/modelo
        # não produziu o Tool Call autorizado. O resultado é enviado à síntese
        # como contexto estruturado, não como ToolMessage, evitando o erro 400
        # de function-response/function-call mismatch do endpoint Gemini.
        if forced_tool and not any(item["tool"] == forced_tool for item in executed_results):
            execution = self.registry.execute(forced_tool, {})
            executed_results.append(
                {
                    "tool": execution.name,
                    "arguments": execution.arguments,
                    "result": execution.result,
                    "execution_mode": "deterministic_fallback",
                }
            )
            self._log(
                question=question,
                round_idx=1,
                tool_name=forced_tool,
                arguments={},
                payload=execution.result,
                status="tool_executed_fallback",
            )

        if not executed_results:
            # Pergunta realmente ambígua e sem Tool Call.
            answer = self._message_text(response)
            self._log(
                question=question,
                round_idx=1,
                tool_name=None,
                arguments={},
                payload={"final_answer": answer},
                status="final",
            )
            return answer

        # Síntese independente do protocolo de function calling.
        # Não reutilizamos o AIMessage que pode conter calls externos/ignorado(s).
        evidence_packet = json.dumps(
            {
                "question": question,
                "authorized_tools": available_tools,
                "required_tool": forced_tool,
                "executed_tools": executed_results,
            },
            ensure_ascii=False,
            indent=2,
        )

        try:
            synthesis = self.llm.invoke([
                SystemMessage(content=SYNTHESIS_PROMPT),
                HumanMessage(
                    content=(
                        "PERGUNTA DA DIRETORIA:\n"
                        f"{question}\n\n"
                        "RESULTADOS DETERMINÍSTICOS DAS TOOLS AUTORIZADAS:\n"
                        f"{evidence_packet}"
                    )
                ),
            ])
        except Exception as exc:
            self._log(
                question=question,
                round_idx=2,
                tool_name=None,
                arguments={},
                payload={"error": type(exc).__name__, "message": str(exc)},
                status="llm_synthesis_error",
            )
            raise RuntimeError(f"Falha ao sintetizar resposta: {exc}") from exc

        answer = self._message_text(synthesis)
        self._log(
            question=question,
            round_idx=2,
            tool_name=None,
            arguments={},
            payload={
                "final_answer": answer,
                "tools_used": [item["tool"] for item in executed_results],
                "execution_modes": [item["execution_mode"] for item in executed_results],
            },
            status="final",
        )
        return answer

    def _bind_forced_tool(self, tool_obj: Any, tool_name: str) -> Any:
        """Try the most specific tool_choice forms supported by the installed stack."""
        attempts = [
            {"tool_choice": tool_name},
            {"tool_choice": "required"},
        ]
        for kwargs in attempts:
            try:
                return self.llm.bind_tools([tool_obj], **kwargs)
            except Exception:
                continue
        return self.llm.bind_tools([tool_obj])

    @staticmethod
    def _message_text(message: Any) -> str:
        content = getattr(message, "content", "")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: List[str] = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    parts.append(str(item.get("text", "")))
                elif isinstance(item, str):
                    parts.append(item)
            return "\n".join(part for part in parts if part).strip()
        return str(content)

    def _log(
        self,
        *,
        question: str,
        round_idx: int,
        tool_name: Optional[str],
        arguments: Dict[str, Any],
        payload: Any,
        status: str,
    ) -> None:
        self.audit_log.append(
            {
                "question": question,
                "round": round_idx,
                "tool": tool_name,
                "arguments": arguments,
                "payload": payload,
                "status": status,
            }
        )

    def save_audit(self, path: str | Path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            json.dumps(self.audit_log, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
