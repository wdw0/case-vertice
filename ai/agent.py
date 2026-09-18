from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from .context import ContextStore
from .llm import build_eloagents_llm
from .prompts import SYSTEM_PROMPT
from .tools import ToolRegistry, build_langchain_tools


class VerticeAgent:
    """Decision Copilot using the EloAgents-compatible ChatLiteLLM + LangChain tool-calling pattern."""

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
        """Ask a question and let the LLM call deterministic tools as needed."""
        if not question.strip():
            raise ValueError("A pergunta não pode ser vazia.")

        try:
            from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
        except ImportError as exc:
            raise RuntimeError(
                "Dependências LangChain ausentes. Execute: pip install -r requirements.txt"
            ) from exc

        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=question),
        ]

        for round_idx in range(1, self.max_tool_rounds + 1):
            response = self.llm_with_tools.invoke(messages)
            messages.append(response)

            tool_calls = getattr(response, "tool_calls", None) or []
            if not tool_calls:
                answer = self._message_text(response)
                self._log(
                    question=question,
                    round_idx=round_idx,
                    tool_name=None,
                    arguments={},
                    payload={"final_answer": answer},
                )
                return answer

            for call in tool_calls:
                name = call.get("name")
                arguments = call.get("args") or {}
                tool_id = call.get("id")

                if not name:
                    raise RuntimeError(f"Tool call sem nome: {call}")

                # O provedor EloAgents/modelo pode, em alguns cenários, devolver
                # um nome de tool que não faz parte das tools registradas localmente.
                # Isso não deve derrubar o agente: devolvemos uma mensagem de erro
                # estruturada ao modelo para que ele tente novamente usando somente
                # as tools oficiais do Vértice Intelligence.
                if name not in self.registry.names():
                    tool_output = json.dumps(
                        {
                            "error": "unknown_tool",
                            "message": (
                                f"A tool '{name}' não está disponível neste agente. "
                                "Use exclusivamente as tools oficiais listadas no prompt. "
                                f"Tools disponíveis: {self.registry.names()}"
                            ),
                            "available_tools": self.registry.names(),
                        },
                        ensure_ascii=False,
                    )

                    messages.append(
                        ToolMessage(
                            content=tool_output,
                            tool_call_id=tool_id,
                            name=name,
                        )
                    )

                    self._log(
                        question=question,
                        round_idx=round_idx,
                        tool_name=name,
                        arguments=arguments,
                        payload=json.loads(tool_output),
                    )
                    continue

                execution = self.registry.execute(name, arguments)
                tool_output = json.dumps(execution.result, ensure_ascii=False)

                messages.append(
                    ToolMessage(
                        content=tool_output,
                        tool_call_id=tool_id,
                        name=name,
                    )
                )

                self._log(
                    question=question,
                    round_idx=round_idx,
                    tool_name=name,
                    arguments=arguments,
                    payload=execution.result,
                )

        raise RuntimeError(
            f"O agente excedeu o limite de {self.max_tool_rounds} rodadas de Tool Calling."
        )

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
    ) -> None:
        self.audit_log.append(
            {
                "question": question,
                "round": round_idx,
                "tool": tool_name,
                "arguments": arguments,
                "payload": payload,
            }
        )

    def save_audit(self, path: str | Path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            json.dumps(self.audit_log, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
