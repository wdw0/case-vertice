from ai.agent import VerticeAgent
from ai.routing import infer_tool_arguments, infer_tool_for_question


class FakeLLM:
    def __init__(self, responses=None):
        self.responses = list(responses or ["Resposta ok."])
        self.prompts = []

    def invoke(self, messages):
        self.prompts.append(messages)
        value = self.responses.pop(0) if self.responses else "Resposta ok."
        return type("Msg", (), {"content": value})()


def test_marketing_router_is_deterministic():
    assert infer_tool_for_question("Quais canais têm maior eficiência de aquisição?") == "get_marketing_efficiency"
    assert infer_tool_arguments("Qual canal tem o menor CAC?", "get_marketing_efficiency") == {"order_by": "cac", "descending": False}


def test_inventory_query_gets_numeric_limit_and_relevant_sort():
    args = infer_tool_arguments("Quero saber quais são os 3 SKUs em ruptura que mais causam prejuízo", "get_inventory_opportunities")
    assert args["limit"] == 3
    assert args["stockout_order_by"] == "receita_potencial_bloqueada_estimada"


def test_out_of_scope_does_not_call_llm():
    llm = FakeLLM(["não deveria ser chamado"])
    agent = VerticeAgent("data/vertice_ai_context.json", llm=llm)
    answer = agent.ask("Qual filme tem a maior bilheteria de 2026?")
    assert "fora do escopo" in answer.lower()
    assert not llm.prompts


def test_followup_reuses_previous_module_and_context():
    llm = FakeLLM(["Plano contextualizado para a oportunidade atual."])
    agent = VerticeAgent("data/vertice_ai_context.json", llm=llm)
    conversation = [
        {
            "question": "Onde estamos perdendo margem?",
            "answer": "OPP-MAR-02 é a maior oportunidade de impacto.",
            "tools_used": ["get_margin_opportunities"],
        }
    ]
    answer = agent.ask("Detalhe o plano de ação dessa oportunidade.", conversation=conversation)
    assert "contextualizado" in answer
    prompt_text = "\n".join(
        str(getattr(msg, "content", msg))
        for batch in llm.prompts
        for msg in batch
    )
    assert "OPP-MAR-02" in prompt_text


def test_generic_llm_response_triggers_retry():
    llm = FakeLLM([
        "Resposta baseada nos resultados determinísticos disponíveis.",
        "O principal ponto é a erosão por devoluções (OPP-MAR-02).",
    ])
    agent = VerticeAgent("data/vertice_ai_context.json", llm=llm)
    answer = agent.ask("Onde estamos perdendo margem?")
    assert "OPP-MAR-02" in answer
    assert len(llm.prompts) == 2


def test_marketing_output_contains_source_contract():
    llm = FakeLLM(["ROAS de marketing: 4,18x."])
    agent = VerticeAgent("data/vertice_ai_context.json", llm=llm)
    agent.ask("Quais canais têm maior eficiência de aquisição?")
    prompt_text = "\n".join(str(getattr(msg, "content", msg)) for msg in llm.prompts[0])
    assert "marketing.csv / camada analítica determinística" in prompt_text
    assert "ROAS agregado geral" in prompt_text or "roas" in prompt_text.lower()


def test_inventory_category_loss_query_routes_to_potential_blocked_revenue():
    question = "Quais são os 5 itens de Beleza com maior perda?"
    tool = infer_tool_for_question(question)
    assert tool == "get_inventory_opportunities"
    args = infer_tool_arguments(question, tool)
    assert args["limit"] == 5
    assert args["categoria"] == "Beleza"
    assert args["stockout_order_by"] == "receita_potencial_bloqueada_estimada"



def test_product_router_resolves_named_product():
    question = "O que vc tem a dizer sobre o item Calça Jeans Moderno Nude"
    tool = infer_tool_for_question(question)
    # A função pura não conhece o catálogo; a detecção por entidade ocorre no Agent.
    assert tool is None


def test_product_ranking_router_is_deterministic():
    question = "qual é o 1º lugar na lista de produtos ordenados por rentabilidade"
    assert infer_tool_for_question(question) == "get_product_ranking"
    assert infer_tool_arguments(question, "get_product_ranking") == {
        "order_by": "rentabilidade",
        "descending": True,
        "limit": 1,
    }


def test_product_query_agent_routes_by_catalog_entity():
    class NoopLLM:
        def invoke(self, messages):
            return type("Msg", (), {"content": "produto consultado"})()

    agent = VerticeAgent("data/vertice_ai_context.json", llm=NoopLLM())
    assert agent._route("O que vc tem a dizer sobre o item Calça Jeans Moderno Nude", []) == "get_product_details"
