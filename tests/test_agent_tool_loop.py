from pathlib import Path

import pytest

from ai.agent import VerticeAgent

CONTEXT = Path(__file__).resolve().parents[1] / "data" / "vertice_ai_context.json"


class FakeLLM:
    """Stand-in for ChatLiteLLM used to test the tool-calling orchestration."""

    def __init__(self):
        self.calls = []
        self.bound = False

    def bind_tools(self, tools):
        self.bound = True
        self.tools = tools
        return self

    def invoke(self, messages):
        self.calls.append(messages)
        tool_messages = [m for m in messages if getattr(m, "type", None) == "tool"]
        if not tool_messages:
            class ToolCallingMessage:
                content = ""
                tool_calls = [{"name": "get_margin_opportunities", "args": {}, "id": "call-1"}]
            return ToolCallingMessage()

        class FinalMessage:
            content = "Resposta baseada na Tool de margem."
            tool_calls = []
        return FinalMessage()


def test_agent_tool_loop_routes_and_returns_final_answer():
    pytest.importorskip("langchain_core")
    agent = VerticeAgent(CONTEXT, llm=FakeLLM(), max_tool_rounds=2)
    answer = agent.ask("Onde estamos perdendo margem?")
    assert "Resposta baseada" in answer
    assert any(item["tool"] == "get_margin_opportunities" for item in agent.audit_log)
