"""
物流追踪（模拟实现）。

真实接入时，把 `track_package` 换成承运商 API 调用即可，函数签名和返回结构不用改。
"""

import hashlib
import re
from typing import Dict, List, Optional

# 中英文触发词：命中任意一个就走物流链路
LOGISTICS_KEYWORDS_ZH = [
    "物流", "快递", "单号", "运单", "包裹", "到哪了", "到哪", "发货", "签收", "清关", "海关", "派送", "转运",
]
LOGISTICS_KEYWORDS_EN = [
    "tracking", "track", "parcel", "package", "shipment", "courier", "delivery", "deliver",
    "customs", "clearance", "where is my order", "where's my order", "awb",
]

_TRACKING_PATTERNS = [
    re.compile(r"\b[A-Z]{2}\d{9}[A-Z]{2}\b"),        # UPU S10: YT123456789CN
    re.compile(r"\b[A-Z]{3}\d{9,12}\b"),             # 部分专线: GS12345678901
    re.compile(r"\b\d{12,22}\b"),                    # 纯数字运单
]


def normalize_text(text: str) -> str:
    return (text or "").lower()


def is_logistics_query(text: str) -> bool:
    """判断是否为物流类提问（先于 LLM 分类执行，省一次模型调用）。"""
    q = normalize_text(text)
    if any(k in q for k in LOGISTICS_KEYWORDS_ZH):
        return True
    return any(k in q for k in LOGISTICS_KEYWORDS_EN)


def extract_tracking_number(text: str) -> Optional[str]:
    """从查询中提取运单号，支持 S10 / 专线 / 纯数字。"""
    if not text:
        return None
    upper = text.upper()
    for pattern in _TRACKING_PATTERNS:
        match = pattern.search(upper)
        if match:
            return match.group(0)
    return None


def _pick_stage(tracking_number: str) -> str:
    """按运单号稳定地挑选一个模拟节点（同一单号每次结果一致）。"""
    digest = hashlib.md5(tracking_number.encode("utf-8")).hexdigest()
    return ["picked_up", "in_transit", "customs", "customs"][int(digest[:2], 16) % 4]


STAGES: Dict[str, Dict[str, str]] = {
    "picked_up": {
        "zh": "已揽收",
        "en": "Picked up by carrier",
        "zh_note": "包裹已被承运商揽收，等待航班/干线运输。",
        "en_note": "The parcel has been collected and is waiting for the next flight.",
        "eta_zh": "预计 6–10 个工作日送达",
        "eta_en": "Estimated delivery in 6–10 business days",
    },
    "in_transit": {
        "zh": "国际干线运输中",
        "en": "In international transit",
        "zh_note": "包裹已离开发货国，正在前往目的国。",
        "en_note": "The parcel has left the origin country and is on its way to the destination.",
        "eta_zh": "预计 5–9 个工作日送达",
        "eta_en": "Estimated delivery in 5–9 business days",
    },
    "customs": {
        "zh": "已到达目的国海关，正在清关中",
        "en": "Arrived at destination customs, under clearance",
        "zh_note": "包裹已抵达目的国并进入清关环节，海关可能要求补交身份或 invoice 信息。",
        "en_note": "The parcel has arrived in the destination country and entered customs clearance. "
                   "Customs may request ID or invoice details.",
        "eta_zh": "清关通常 1–3 个工作日，查验时最长约 7 天",
        "eta_en": "Clearance usually takes 1–3 business days, up to 7 days if inspected",
    },
}


def track_package(tracking_number: Optional[str] = None, stage: str = "customs") -> Dict[str, object]:
    """返回模拟轨迹。tracking_number 为空时也返回可展示的默认轨迹。"""
    number = (tracking_number or "GS000000000000").upper()
    stage_key = stage if stage in STAGES else _pick_stage(number) if tracking_number else "customs"
    info = STAGES[stage_key]
    return {
        "tracking_number": number,
        "stage": stage_key,
        "carrier": "GlobalShop Express (demo)",
        "events": [
            {"time": "Day 0", "zh": "订单已出库", "en": "Order dispatched"},
            {"time": "Day 2", "zh": "离开分拨中心", "en": "Departed sorting hub"},
            {"time": "Day 5", "zh": "到达目的国", "en": "Arrived in destination country"},
            {"time": "Day 6", "zh": info["zh"], "en": info["en"]},
        ],
        **info,
    }


def format_record_reply(record: Dict[str, object], lang: str = "en") -> str:
    """用后台录入的模拟运单记录生成回复。"""
    number = record.get("number", "")
    status_zh = record.get("status_zh") or "运输中"
    status_en = record.get("status_en") or "In transit"
    location = record.get("location") or ""
    eta = record.get("eta") or ""
    note = record.get("note") or ""

    if lang == "zh":
        lines = [f"您的包裹（运单号 **{number}**）当前状态：**{status_zh}**。"]
        if location:
            lines.append(f"**当前位置**：{location}")
        if eta:
            lines.append(f"**预计时效**：{eta}")
        if note:
            lines.append(f"**备注**：{note}")
        lines.append("\n如需进一步协助清关或改派，请直接回复我。")
        return "\n".join(lines)

    lines = [f"Your parcel (**{number}**) is currently **{status_en}**."]
    if location:
        lines.append(f"**Location**: {location}")
    if eta:
        lines.append(f"**ETA**: {eta}")
    if note:
        lines.append(f"**Note**: {note}")
    lines.append("\nLet me know if you need help with clearance or redelivery.")
    return "\n".join(lines)


def format_tracking_reply(tracking_number: Optional[str], lang: str = "en") -> str:
    """把轨迹格式化成客服口吻的回复（中英双语模板）。"""
    result = track_package(tracking_number, stage="customs")

    if lang == "zh":
        lines: List[str] = []
        if tracking_number:
            lines.append(f"您的包裹（运单号 **{result['tracking_number']}**）已到达目的国海关，正在清关中。")
        else:
            lines.append("您的包裹已到达目的国海关，正在清关中。")
        lines += [
            f"**当前状态**：{result['zh']}",
            f"**清关说明**：{result['zh_note']}",
            f"**时效参考**：{result['eta_zh']}",
            "",
            "**需要您留意**：",
            "1. 海关可能短信/邮件通知补交身份或发票信息，请在 48 小时内提交；",
            "2. 只通过承运商官方渠道缴费，不要点击陌生链接；",
            "3. 提供运单号后我可帮您继续跟进清关进度。",
        ]
        return "\n".join(lines)

    lines = []
    if tracking_number:
        lines.append(f"Your parcel (**{result['tracking_number']}**) has arrived at destination customs and is under clearance.")
    else:
        lines.append("Your parcel has arrived at destination customs and is under clearance.")
    lines += [
        f"**Current status**: {result['en']}",
        f"**What is happening**: {result['en_note']}",
        f"**Timeline**: {result['eta_en']}",
        "",
        "**What you may need to do**:",
        "1. If customs asks for ID or an invoice, reply within 48 hours;",
        "2. Pay duties only through the carrier's official link, never a third-party message;",
        "3. Share your tracking number and I can keep following the clearance for you.",
    ]
    return "\n".join(lines)
