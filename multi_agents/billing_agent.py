"""
账单与支付专家：退款、支付失败、关税与币种问题。

数据来自 knowledge/（payment / refund / customs 章节）。
"""

from typing import Any, Dict

from langchain_core.messages import HumanMessage, SystemMessage

from .base_agent import BaseAgent


class BillingAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="Billing & Payments",
            role="refunds, payment failures, duties and currency questions",
            expertise=["refund timelines", "payment methods", "duties & VAT", "currency & invoicing"],
            kb_categories=["payment", "refund", "customs"],
        )

    def process(self, state: Dict[str, Any]) -> Dict[str, Any]:
        customer_query = state.get("customer_query", "")
        session_id = state.get("session_id", "default")
        conversation_context = self._get_conversation_context(session_id, state)

        role_prompt = """You are GlobalShop's Billing & Payments Specialist.

Your job:
1. Explain where the money is: authorization vs capture vs refund, and the exact timeline.
2. For refunds, state the return-window eligibility and the 5–10 business day refund window.
3. For payment failures, list the 3 most common causes (3-D Secure, bank block, currency) and the retry path.
4. For duties/VAT, explain who pays, the de minimis thresholds, and that we never collect duty by unofficial link.
5. Never ask for full card numbers, CVV or passwords. Mask order IDs when echoing them.

Always give amounts in USD and include the next action for the customer."""

        system_prompt = self._enhance_system_prompt_with_context(
            role_prompt, customer_query, use_kb=state.get("use_kb", True))

        messages = []
        if conversation_context:
            messages.append(SystemMessage(
                content=f"对话历史上下文：\n{conversation_context}\n\n请基于以上对话历史，延续之前的退款/支付进度回答。"
            ))
        messages.append(SystemMessage(content=system_prompt))
        messages.append(HumanMessage(content=customer_query))

        try:
            response = self.llm.invoke(messages)
            response_content = response.content
            state["reasoning"] = getattr(response, "reasoning", "") or ""
        except Exception as e:
            print(f"{self.name} 调用LLM时出错: {e}")
            response_content = self._fallback_reply(customer_query, "账单问题", "billing")

        state["response"] = response_content
        state["current_agent"] = self.name
        state["tools_used"].append(f"{self.name}_processing")
        return state
