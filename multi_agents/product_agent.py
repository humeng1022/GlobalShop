"""
产品专家：跨境电商商品咨询与推荐。

数据来自 knowledge/（products / shipping / warranty 章节），不再维护本地硬编码字典。
"""

from typing import Any, Dict

from langchain_core.messages import HumanMessage, SystemMessage

from .base_agent import BaseAgent


class ProductAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="Product Specialist",
            role="product selection and pre-sales advice",
            expertise=["product specs", "pricing (USD)", "stock & variants", "cross-border availability"],
            kb_categories=["products", "shipping", "warranty"],
        )

    def process(self, state: Dict[str, Any]) -> Dict[str, Any]:
        customer_query = state.get("customer_query", "")
        session_id = state.get("session_id", "default")
        conversation_context = self._get_conversation_context(session_id, state)

        role_prompt = """You are the Product Specialist for GlobalShop's international storefront.

Your job:
1. Recommend products by use case (commute, travel, gaming, gifting), not by pushing the priciest item.
2. Always state the price in USD and mention whether the SKU ships to the customer's country.
3. Flag cross-border constraints early: plug type/voltage, size chart, battery shipping restrictions.
4. If a SKU is out of stock, offer the closest alternative or the "Notify me" option.
5. Never promise a delivery date; quote the shipping ranges from the knowledge base instead.

Answer structure: short recommendation → key specs → price → shipping note → one follow-up question."""

        system_prompt = self._enhance_system_prompt_with_context(
            role_prompt, customer_query, use_kb=state.get("use_kb", True))

        messages = []
        if conversation_context:
            messages.append(SystemMessage(
                content=f"对话历史上下文：\n{conversation_context}\n\n请基于以上对话历史和当前查询，提供连贯的回答。"
            ))
        messages.append(SystemMessage(content=system_prompt))
        messages.append(HumanMessage(content=customer_query))

        try:
            response = self.llm.invoke(messages)
            response_content = response.content
            state["reasoning"] = getattr(response, "reasoning", "") or ""
        except Exception as e:
            print(f"{self.name} 调用LLM时出错: {e}")
            response_content = self._fallback_reply(customer_query, "产品咨询", "product")

        state["response"] = response_content
        state["current_agent"] = self.name
        state["tools_used"].append(f"{self.name}_processing")
        return state
