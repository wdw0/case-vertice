from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from .context import ContextStore
from .llm import build_eloagents_llm
from .prompts import SYNTHESIS_PROMPT
from .routing import AUTHORIZED_TOOLS, infer_tool_arguments, infer_tool_for_followup, infer_tool_for_question
from .tools import ToolRegistry


class VerticeAgent:
    """
    Router determinístico → Tool determinística → ChatLiteLLM/EloAgents → síntese.

    O LLM nunca escolhe a ferramenta. Ele recebe somente a evidência produzida pela
    camada determinística e transforma essa evidência em uma resposta executiva.
    """

    def __init__(self, context_path: str | Path, *, llm: Optional[Any] = None, model: Optional[str] = None, max_tool_rounds: int = 1):
        self.context = ContextStore(context_path)
        self.registry = ToolRegistry(self.context)
        self.llm = llm or build_eloagents_llm(model=model)
        self.max_tool_rounds = max(1, max_tool_rounds)
        self.audit_log: List[Dict[str, Any]] = []

    def _log(self, *, question: str, round_idx: int, tool_name: Optional[str], arguments: Dict[str, Any], payload: Any, status: str) -> None:
        self.audit_log.append({
            "question": question,
            "round": round_idx,
            "tool": tool_name,
            "arguments": arguments,
            "payload": payload,
            "status": status,
        })

    def _route(self, question: str, conversation: List[Dict[str, Any]]) -> Optional[str]:
        explicit = infer_tool_for_question(question)
        if explicit:
            return explicit

        # Nomes de produtos não precisam conter uma palavra-chave de domínio.
        # A existência do nome/SKU no catálogo auditado é suficiente para classificar
        # a pergunta como consulta de produto.
        if self.context.find_products(question, limit=1):
            return "get_product_details"

        return infer_tool_for_followup(question, conversation)

    def _infer_followup_tool(self, question: str, conversation: List[Dict[str, Any]]) -> Optional[str]:
        """Compatibilidade com a API das versões anteriores."""
        return infer_tool_for_followup(question, conversation)

    def _execute_tool(self, tool_name: str, arguments: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Compatibilidade e ponto único de execução determinística."""
        execution = self.registry.execute(tool_name, arguments or {})
        self._log(
            question=getattr(self, "_current_question", ""),
            round_idx=1,
            tool_name=tool_name,
            arguments=execution.arguments,
            payload=execution.result,
            status="tool_executed",
        )
        return {
            "tool": execution.name,
            "arguments": execution.arguments,
            "result": execution.result,
            "execution_mode": "deterministic_router",
        }

    def ask(self, question: str, conversation: Optional[List[Dict[str, Any]]] = None) -> str:
        if not question.strip():
            raise ValueError("A pergunta não pode ser vazia.")

        conversation = conversation or []
        self._current_question = question
        selected_tool = self._route(question, conversation)
        arguments = infer_tool_arguments(question, selected_tool)

        if not selected_tool:
            answer = self._scope_answer(question)
            self._log(
                question=question,
                round_idx=1,
                tool_name=None,
                arguments={},
                payload={"final_answer": answer},
                status="unrouted_final",
            )
            return answer

        try:
            executed_item = self._execute_tool(selected_tool, arguments)
            execution_result = executed_item["result"]
        except Exception as exc:
            self._log(
                question=question,
                round_idx=1,
                tool_name=selected_tool,
                arguments=arguments,
                payload={"error": type(exc).__name__, "message": str(exc)},
                status="tool_error",
            )
            raise RuntimeError(f"Falha ao executar a ferramenta {selected_tool}: {exc}") from exc

        executed_results = [executed_item]

        answer = self._synthesize(question, conversation, selected_tool, executed_results, retry=False)
        if self._needs_retry(answer):
            retry_answer = self._synthesize(question, conversation, selected_tool, executed_results, retry=True)
            if retry_answer.strip():
                answer = retry_answer

        if not answer.strip() or self._needs_retry(answer):
            answer = self._deterministic_fallback_answer(
                question=question,
                selected_tool=selected_tool,
                executed_results=executed_results,
                conversation=conversation,
            )

        self._log(
            question=question,
            round_idx=3,
            tool_name=selected_tool,
            arguments={},
            payload={
                "final_answer": answer,
                "tools_used": [selected_tool],
                "execution_modes": ["deterministic_router"],
            },
            status="final",
        )
        return answer

    def _synthesize(self, question: str, conversation: List[Dict[str, Any]], selected_tool: str, executed_results: List[Dict[str, Any]], retry: bool) -> str:
        try:
            from langchain_core.messages import HumanMessage, SystemMessage
        except ImportError as exc:
            raise RuntimeError("Dependências LangChain ausentes. Execute: pip install -r requirements.txt") from exc

        packet = {
            "question": question,
            "selected_tool": selected_tool,
            "conversation_context": self._compact_conversation_context(conversation),
            "executed_tools": executed_results,
            "authorized_modules": list(AUTHORIZED_TOOLS),
        }
        instructions = (
            "Responda diretamente ao pedido atual. Use somente os dados estruturados. "
            "Não introduza nenhum número que não esteja no pacote de evidências. "
            "Não faça perguntas de continuidade ao final."
        )
        if retry:
            instructions += (
                "\n\nESTA É UMA SEGUNDA TENTATIVA. A resposta anterior foi considerada genérica ou vazia. "
                "Entregue uma resposta concreta em 2–5 bullets, citando os IDs de oportunidade ou SKUs "
                "presentes nos dados quando isso atender ao pedido."
            )

        try:
            synthesis = self.llm.invoke([
                SystemMessage(content=SYNTHESIS_PROMPT),
                HumanMessage(
                    content=(
                        "DADOS ESTRUTURADOS — FONTE FACTUAL ÚNICA:\n"
                        + json.dumps(packet, ensure_ascii=False, indent=2)
                        + "\n\nINSTRUÇÃO DE SÍNTESE:\n"
                        + instructions
                    )
                ),
            ])
            answer = self._message_text(synthesis)
            self._log(
                question=question,
                round_idx=3 if retry else 2,
                tool_name=None,
                arguments={},
                payload={"answer_preview": answer[:2000], "retry": retry},
                status="llm_synthesis_retry" if retry else "llm_synthesis",
            )
            return answer
        except Exception as exc:
            self._log(
                question=question,
                round_idx=3 if retry else 2,
                tool_name=None,
                arguments={},
                payload={"error": type(exc).__name__, "message": str(exc), "retry": retry},
                status="llm_synthesis_error",
            )
            return ""

    @staticmethod
    def _needs_retry(answer: str) -> bool:
        normalized = " ".join((answer or "").lower().split())
        if not normalized:
            return True
        generic_markers = (
            "resposta baseada nos resultados determinísticos disponíveis",
            "resposta baseada nos resultados determinísticos das ferramentas autorizadas",
            "módulo consultado: nenhum",
            "pergunta: sim, gostaria",
        )
        return any(marker in normalized for marker in generic_markers)

    @staticmethod
    def _compact_conversation_context(conversation: List[Dict[str, Any]], max_turns: int = 4, max_answer_chars: int = 6000) -> List[Dict[str, Any]]:
        compact: List[Dict[str, Any]] = []
        for turn in conversation[-max_turns:]:
            answer = str(turn.get("answer", turn.get("content", "")))
            if len(answer) > max_answer_chars:
                answer = answer[:max_answer_chars] + "\n[resposta anterior truncada]"
            compact.append({
                "question": str(turn.get("question", "")),
                "answer": answer,
                "tools_used": list(turn.get("tools_used") or []),
            })
        return compact

    @staticmethod
    def _scope_answer(question: str) -> str:
        return (
            "Essa pergunta está fora do escopo factual do Vértice Intelligence. "
            "O Copilot atual responde sobre margem, devoluções, marketing e aquisição, "
            "estoque, atendimento, produtos e priorização de oportunidades com base nos dados do case."
        )

    @staticmethod
    def _deterministic_fallback_answer(
        question: str,
        executed_results: List[Dict[str, Any]],
        selected_tool: Optional[str] = None,
        conversation: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        result = executed_results[0].get("result") or {}
        lines = ["Resposta baseada nos resultados determinísticos disponíveis.", ""]

        if selected_tool == "get_marketing_efficiency":
            channels = result.get("channels") or []
            if channels:
                lines += ["**Eficiência de aquisição**", ""]
                for c in channels[:5]:
                    lines.append(f"- {c.get('canal')}: ROAS {c.get('roas', 0):.2f}x | CAC R$ {c.get('cac', 0):.2f}")
                lines.append("")
                lines.append("A decisão de verba deve ser validada por testes incrementais e retorno marginal; os valores são da base de marketing.")
                return "\n".join(lines)

        if selected_tool == "get_inventory_opportunities":
            stockouts = result.get("stockouts_high_demand") or []
            coverage = result.get("high_coverage") or []
            q_lower = question.lower()
            inventory_query = any(marker in q_lower for marker in (
                "ruptura", "sku", "item", "itens", "produto", "produtos",
                "beleza", "moda", "lifestyle", "acessórios", "acessorios"
            ))
            if stockouts and inventory_query:
                order_by = (result.get("query_parameters") or {}).get("stockout_order_by")
                if order_by == "receita_potencial_bloqueada_estimada":
                    lines += ["**Rupturas com maior receita potencial bloqueada estimada**", ""]
                    for item in stockouts[:5]:
                        lines.append(
                            f"- {item.get('sku_id')} — {item.get('nome_produto')}: "
                            f"receita potencial bloqueada estimada R$ {item.get('receita_potencial_bloqueada_estimada', 0):,.2f}; "
                            f"lead time {item.get('lead_time_reposicao')} dias"
                        )
                    lines.append("\nA base não mede prejuízo realizado por SKU; este valor é uma estimativa baseada na demanda histórica e no lead time.")
                    return "\n".join(lines)
                lines += ["**SKUs de ruptura em maior volume de vendas histórico**", ""]
                for item in stockouts[:5]:
                    lines.append(f"- {item.get('sku_id')} — {item.get('nome_produto')}: {item.get('unidades_vendidas')} un.; receita histórica R$ {item.get('receita_historica', 0):,.2f}")
                return "\n".join(lines)
            if coverage:
                lines += ["**Exposição de estoque**", ""]
                for item in coverage[:5]:
                    lines.append(f"- {item.get('sku_id')} — {item.get('nome_produto')}: {item.get('cobertura_teorica_dias', 0):,.0f} dias teóricos; exposição potencial R$ {item.get('capital_exposicao', 0):,.2f}")
                lines.append("")
                lines.append("Ação sugerida: congelar novas compras e testar estratégias de escoamento, respeitando a natureza teórica da cobertura.")
                return "\n".join(lines)

        if not selected_tool and executed_results:
            selected_tool = str(executed_results[0].get("tool") or "") or None

        if selected_tool == "get_product_details":
            if not result.get("found"):
                return (
                    "Não encontrei esse produto ou SKU no contexto estruturado de produtos. "
                    "A consulta aceita o nome do produto ou um SKU presente na base do case."
                )
            product = result.get("product") or {}
            rankings = result.get("rankings") or {}
            lines += [f"**{product.get('produto')} ({product.get('sku_id')})**", ""]
            lines.append(f"- Rentabilidade: {float(product.get('rentabilidade', 0)) * 100:.2f}%")
            lines.append(f"- Faturamento: R$ {float(product.get('faturamento', 0)):,.2f}")
            lines.append(f"- Margem de contribuição: R$ {float(product.get('margem', 0)):,.2f}")
            lines.append(f"- Unidades vendidas: {product.get('unidades')}")
            if rankings.get("rentabilidade") is not None:
                lines.append(f"- Posição por rentabilidade: {rankings.get('rentabilidade')}º")
            if product.get("estoque_disponivel") is not None:
                lines.append(f"- Estoque disponível no snapshot: {product.get('estoque_disponivel')}")
            lines.append("")
            lines.append("A rentabilidade e os rankings são históricos e descritivos; o estoque é um snapshot separado da janela de vendas.")
            return "\n".join(lines)

        if selected_tool == "get_product_ranking":
            ranking = result.get("ranking") or []
            params = result.get("query_parameters") or {}
            if not ranking:
                return "Não há produtos disponíveis para o ranking no contexto estruturado."
            metric_labels = {
                "rentabilidade": "rentabilidade",
                "faturamento": "faturamento",
                "margem": "margem de contribuição",
                "unidades": "unidades vendidas",
            }
            metric = metric_labels.get(params.get("order_by"), params.get("order_by"))
            lines += [f"**Ranking de produtos por {metric}**", ""]
            for item in ranking:
                if params.get("order_by") == "rentabilidade":
                    value = f"{float(item.get('rentabilidade', 0)) * 100:.2f}%"
                elif params.get("order_by") in {"faturamento", "margem"}:
                    key = params.get("order_by")
                    value = f"R$ {float(item.get(key, 0)):,.2f}"
                else:
                    value = f"{item.get('unidades')} un."
                lines.append(f"- {item.get('posicao_consulta')}º — {item.get('produto')} ({item.get('sku_id')}): {value}")
            return "\n".join(lines)

        if selected_tool == "get_prioritized_opportunities":
            portfolio = result.get("portfolio") or []
            lines += ["**Portfólio priorizado**", ""]
            for item in portfolio[:7]:
                lines.append(
                    f"- #{item.get('rank')} — **{item.get('id')} — {item.get('oportunidade') or item.get('title')}** "
                    f"({item.get('area')}, score {item.get('score')})"
                )
            return "\n".join(lines)

        opportunities = result.get("opportunities") if isinstance(result, dict) else None
        if isinstance(opportunities, list):
            lines.append(f"**Módulo consultado:** {selected_tool}")
            for opportunity in opportunities[:5]:
                title = opportunity.get("title") or opportunity.get("id") or "Oportunidade"
                opp_id = opportunity.get("id")
                note = opportunity.get("notes")
                impact_type = opportunity.get("impact_type")
                suffix = f" — {impact_type}" if impact_type else ""
                lines.append(f"- **{opp_id} — {title}**{suffix}")
                if note:
                    lines.append(f"  Ação sugerida: {note}")
            return "\n".join(lines)

        lines.append(f"**Módulo consultado:** {selected_tool}")
        return "\n".join(lines)

    @staticmethod
    def _message_text(message: Any) -> str:
        content = getattr(message, "content", None)
        if content is None:
            content = getattr(message, "text", "")
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, dict):
            for key in ("text", "content", "value", "output"):
                value = content.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
            return str(content)
        if isinstance(content, list):
            parts: List[str] = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict):
                    for key in ("text", "content", "value"):
                        value = item.get(key)
                        if isinstance(value, str) and value.strip():
                            parts.append(value)
                            break
                else:
                    value = getattr(item, "text", None)
                    if isinstance(value, str) and value.strip():
                        parts.append(value)
            return "\n".join(parts).strip()
        return str(content or "").strip()
