"""
技术支持专家：跨境购买电子产品的使用与故障排查。

数据来自 knowledge/（warranty / products / refund 章节）。
"""

from typing import Any, Dict

from langchain_core.messages import HumanMessage, SystemMessage

from .base_agent import BaseAgent


class TechAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="Technical Support",
            role="troubleshooting for products bought across borders",
            expertise=["setup & pairing", "charging issues", "firmware/app problems", "warranty claims"],
            kb_categories=["warranty", "products", "refund"],
        )

    def process(self, state: Dict[str, Any]) -> Dict[str, Any]:
        customer_query = state.get("customer_query", "")
        session_id = state.get("session_id", "default")
        conversation_context = self._get_conversation_context(session_id, state)

        role_prompt = """You are GlobalShop's Technical Support Specialist. Customers bought electronics abroad
and may face voltage, plug, region, firmware or pairing problems.

Your job:
1. Ask for the exact model/SKU and the symptom before giving steps (one question max per reply).
2. Give 3–5 ordered troubleshooting steps, each one action, no jargon dumps.
3. Call out cross-border specifics: 110V/220V compatibility, plug adapters, region-locked apps, firmware region.
4. If the unit is defective, explain the 12-month warranty path and what evidence is needed (photo/video).
5. Never suggest opening the device or bypassing local regulations.

End with what to send next (photo, error code, order number)."""

        system_prompt = self._enhance_system_prompt_with_context(
            role_prompt, customer_query, use_kb=state.get("use_kb", True))

        messages = []
        if conversation_context:
            messages.append(SystemMessage(
                content=f"对话历史上下文：\n{conversation_context}\n\n请结合历史排查进度，避免重复之前的步骤。"
            ))
        messages.append(SystemMessage(content=system_prompt))
        messages.append(HumanMessage(content=customer_query))

        try:
            response = self.llm.invoke(messages)
            response_content = response.content
            state["reasoning"] = getattr(response, "reasoning", "") or ""
        except Exception as e:
            print(f"{self.name} 调用LLM时出错: {e}")
            response_content = self._fallback_reply(customer_query, "技术问题", "technical")

        state["response"] = response_content
        state["current_agent"] = self.name
        state["tools_used"].append(f"{self.name}_processing")
        return state
