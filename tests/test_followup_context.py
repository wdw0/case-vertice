from ai.agent import VerticeAgent


class DummyRegistry:
    def names(self):
        return {
            "get_margin_opportunities",
            "get_marketing_efficiency",
            "get_inventory_opportunities",
            "get_support_opportunities",
            "get_prioritized_opportunities",
            "get_opportunity_by_id",
        }


def make_agent():
    agent = object.__new__(VerticeAgent)
    agent.registry = DummyRegistry()
    return agent


def test_followup_reuses_last_authorized_tool():
    agent = make_agent()

    conversation = [
        {
            "question": "Quais problemas de estoque deveriam ser analisados?",
            "answer": "Há ruptura e cobertura teórica elevada.",
            "tools_used": ["get_inventory_opportunities"],
        }
    ]

    assert agent._infer_followup_tool(
        "Sim, eu quero que você detalhe esse plano de ação que comentou",
        conversation,
    ) == "get_inventory_opportunities"


def test_followup_can_use_audit_history():
    agent = make_agent()

    conversation = [
        {
            "question": "Onde estamos perdendo margem?",
            "answer": "Há erosão por devoluções.",
            "audit": [
                {
                    "status": "final",
                    "payload": {
                        "tools_used": ["get_margin_opportunities"],
                    },
                }
            ],
        }
    ]

    assert agent._infer_followup_tool(
        "Explique melhor isso",
        conversation,
    ) == "get_margin_opportunities"


def test_new_explicit_domain_question_does_not_reuse_previous_tool():
    agent = make_agent()

    conversation = [
        {
            "question": "Onde estamos perdendo margem?",
            "answer": "Há erosão por devoluções.",
            "tools_used": ["get_margin_opportunities"],
        }
    ]

    assert agent._infer_followup_tool(
        "Quais canais têm maior eficiência de aquisição?",
        conversation,
    ) is None


def test_empty_synthesis_has_nonempty_fallback():
    agent = object.__new__(VerticeAgent)

    answer = agent._deterministic_fallback_answer(
        question="Onde estamos perdendo margem?",
        executed_results=[
            {
                "tool": "get_margin_opportunities",
                "result": {
                    "summary": "Foram encontradas oportunidades de margem.",
                },
            }
        ],
    )

    assert "Resposta baseada" in answer
    assert "get_margin_opportunities" in answer
