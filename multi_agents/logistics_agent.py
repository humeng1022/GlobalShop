"""
物流追踪智能体。

三种情况分开处理，避免"问时效却回答清关"的误答：
1. 有运单号            → 返回模拟轨迹（已到达目的国海关，正在清关中）
2. 没单号但问时效/运费 → 直接引用知识库的时效政策回答
3. 没单号也没问时效   → 请用户提供单号，并说明可查询的内容

物流状态查询走确定性逻辑，不调用大模型，既稳定又不烧额度。
"""

from typing import Any, Dict

from vector_store import search

from .base_agent import BaseAgent
from tools.logistics import extract_tracking_number, format_record_reply, format_tracking_reply

# 问"多久能到"而不是"我的包裹在哪"
_DURATION_HINTS = [
    "多久", "几天", "多长时间", "时效", "多久能到", "什么时候到", "几天能到",
    "how long", "how many days", "delivery time", "shipping time", "when will",
]


class LogisticsAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="Logistics Tracking",
            role="国际物流追踪与清关答疑",
            expertise=["运单追踪", "清关状态", "国际时效", "异常件处理"],
        )
        self.kb_categories = ["shipping", "customs", "tracking"]

    def _shipping_time_answer(self, query: str, lang: str) -> str:
        """引用知识库的时效/关税政策回答。"""
        hits = search(query, top_k=1) if self._has_index() else []
        body = hits[0]["content"] if hits else ""

        if lang == "zh":
            head = "关于配送时效，我们的政策如下："
            tail = "\n\n如果您想查询**某个具体包裹**的当前位置，请把运单号发给我（例如 YT123456789CN）。"
            return head + "\n" + body + tail if body else (
                "美国 3–7 个工作日，欧洲 5–10 个工作日，其他地区 10–15 个工作日，"
                "另需 1–2 个工作日处理时间。\n\n要查询具体包裹，请提供运单号。"
            )

        head = "Here is our shipping timeline:"
        tail = "\n\nTo check a specific parcel, send me the tracking number (e.g. YT123456789CN)."
        return head + "\n" + body + tail if body else (
            "US 3-7 business days, EU 5-10, other regions 10-15, plus 1-2 business days processing."
            + tail
        )

    @staticmethod
    def _has_index() -> bool:
        try:
            from vector_store import has_index
            return has_index()
        except Exception:
            return False

    @staticmethod
    def _tracking_record(number: str):
        try:
            from db import tracking_get
            return tracking_get(number)
        except Exception:
            return None

    @staticmethod
    def _match_stored_number(query: str):
        """后台录入的单号可能不是标准格式，直接在查询文本里找已知单号。"""
        try:
            from db import tracking_list
            q = (query or "").upper()
            for row in tracking_list():
                number = (row.get("number") or "").upper()
                if number and number in q:
                    return row
        except Exception:
            pass
        return None

    def process(self, state: Dict[str, Any]) -> Dict[str, Any]:
        customer_query = state.get("customer_query", "")
        lang = state.get("language") or "en"

        tracking_number = extract_tracking_number(customer_query)
        record = self._tracking_record(tracking_number) if tracking_number else None

        # 标准格式没提出来时，再匹配后台已录入的单号（支持任意格式）
        if not tracking_number:
            record = self._match_stored_number(customer_query)
            if record:
                tracking_number = record.get("number")

        if tracking_number:
            response = (format_record_reply(record, lang=lang)
                        if record else format_tracking_reply(tracking_number, lang=lang))
        elif any(hint in customer_query.lower() for hint in _DURATION_HINTS):
            response = self._shipping_time_answer(customer_query, lang)
        else:
            response = (
                "请把运单号发给我（例如 YT123456789CN），我帮您查询当前清关/派送状态。"
                if lang == "zh"
                else "Please share your tracking number (e.g. YT123456789CN) and I'll check the current status for you."
            )

        state["response"] = response
        state["current_agent"] = self.name
        state["tracking_number"] = tracking_number or ""
        state["tools_used"].append("logistics_tracking")
        return state
