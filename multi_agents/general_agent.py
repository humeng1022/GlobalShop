"""
综合客服：售前售后通用问题、政策与联系方式。

数据来自 knowledge/（contact / shipping / customs / refund 章节）。
"""

from typing import Any, Dict

from langchain_core.messages import HumanMessage, SystemMessage

from .base_agent import BaseAgent


class GeneralAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="General Support",
            role="general enquiries, policies and hand-off",
            expertise=["shipping times", "customs basics", "store policies", "contact & hours"],
            kb_categories=["contact", "shipping", "customs", "refund"],
        )

    def process(self, state: Dict[str, Any]) -> Dict[str, Any]:
        customer_query = state.get("customer_query", "")
        session_id = state.get("session_id", "default")
        conversation_context = self._get_conversation_context(session_id, state)

        role_prompt = """You are GlobalShop's General Support Specialist — the friendly first line for international shoppers.

Your job:
1. Answer with concrete policy facts (windows, fees, hours) from the knowledge base rather than vague reassurance.
2. If the question needs a specialist, say exactly which team handles it and hand off in the same message:
   logistics tracking, product advice, billing/refunds, or technical support.
3. For country-specific questions, give the relevant destination band (US/EU/AU/JP-KR-SG) and note customs variance.
4. If the customer asks something out of scope, politely redirect to shopping support.
5. Keep replies under ~150 words unless the customer asks for a checklist.

Always close with a next step: a link path in "My Orders", an email address, or a question."""

        system_prompt = self._enhance_system_prompt_with_context(
            role_prompt, customer_query, use_kb=state.get("use_kb", True))

        messages = []
        if conversation_context:
            messages.append(SystemMessage(
                content=f"对话历史上下文：\n{conversation_context}\n\n请基于以上对话历史，提供连贯、不重复的回答。"
            ))
        messages.append(SystemMessage(content=system_prompt))
        messages.append(HumanMessage(content=customer_query))

        try:
            response = self.llm.invoke(messages)
            response_content = response.content
            state["reasoning"] = getattr(response, "reasoning", "") or ""
        except Exception as e:
            print(f"{self.name} 调用LLM时出错: {e}")
            response_content = self._fallback_reply(customer_query, "咨询", "enquiry")

        state["response"] = response_content
        state["current_agent"] = self.name
        state["tools_used"].append(f"{self.name}_processing")
        return state
