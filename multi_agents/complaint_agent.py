"""
投诉处理专家：跨境订单的纠纷、延误与补偿。

数据来自 knowledge/（complaints / refund / shipping 章节）。
"""

from typing import Any, Dict

from langchain_core.messages import HumanMessage, SystemMessage

from .base_agent import BaseAgent


class ComplaintAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="Complaint Resolution",
            role="complaints, disputes and compensation for cross-border orders",
            expertise=["delay disputes", "damaged parcels", "compensation ladder", "escalation"],
            kb_categories=["complaints", "refund", "shipping"],
        )

    def process(self, state: Dict[str, Any]) -> Dict[str, Any]:
        customer_query = state.get("customer_query", "")
        session_id = state.get("session_id", "default")
        conversation_context = self._get_conversation_context(session_id, state)

        role_prompt = """You are GlobalShop's Complaint Resolution Specialist.

Your job:
1. Acknowledge the specific failure (delay, damage, wrong item) — no generic apology walls.
2. State what we will do, in order, with time commitments (first response 4 business hours, resolution 48 hours).
3. Offer compensation from the ladder only as far as justified: shipping-fee refund → 10–30% partial refund
   → full refund or replacement.
4. For damaged/wrong items, ask for photos of the parcel label and the item within 7 days.
5. Escalate to a senior agent (with a case number) if the customer asks twice or the amount exceeds USD 200.

Keep the tone accountable, not defensive. Always end with the concrete next step and the case reference."""

        system_prompt = self._enhance_system_prompt_with_context(
            role_prompt, customer_query, use_kb=state.get("use_kb", True))

        messages = []
        if conversation_context:
            messages.append(SystemMessage(
                content=f"对话历史上下文：\n{conversation_context}\n\n请基于以上对话历史，延续之前的投诉处理进度。"
            ))
        messages.append(SystemMessage(content=system_prompt))
        messages.append(HumanMessage(content=customer_query))

        try:
            response = self.llm.invoke(messages)
            response_content = response.content
            state["reasoning"] = getattr(response, "reasoning", "") or ""
        except Exception as e:
            print(f"{self.name} 调用LLM时出错: {e}")
            response_content = self._fallback_reply(customer_query, "投诉", "complaint")

        state["response"] = response_content
        state["current_agent"] = self.name
        state["tools_used"].append(f"{self.name}_processing")
        return state
