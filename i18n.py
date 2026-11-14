"""
多语言支持：语言识别 + 回复语言指令。

规则：
- 查询里出现汉字，且汉字数量足够（默认即视为中文提问）→ 中文回复
- 纯英文 / 其他拉丁字母 / 数字单号 → 英文回复
- 空查询 → 英文（默认语言）
"""

import re
from typing import Literal

Language = Literal["zh", "en"]

_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_ASCII_LETTER_RE = re.compile(r"[A-Za-z]")


def detect_language(text: str) -> Language:
    """判断用户提问语言：含中文走中文，否则默认英文。"""
    if not text:
        return "en"

    cjk_count = len(_CJK_RE.findall(text))
    if cjk_count == 0:
        return "en"

    latin_count = len(_ASCII_LETTER_RE.findall(text))

    # 中英混排时，汉字数量明显占多数才判为中文
    if cjk_count >= 2 and cjk_count * 2 >= latin_count:
        return "zh"

    # 只有一两个汉字（例如单号上下文里的“吗”）仍按英文处理
    return "zh" if cjk_count >= 2 else "en"


def language_instruction(lang: Language) -> str:
    """生成系统提示中的语言约束。"""
    if lang == "zh":
        return (
            "【回复语言】用户本轮使用中文提问，请全程使用简体中文回复。"
            "专业术语（如 HS code、tracking number）可保留英文原文并附中文解释。"
        )
    return (
        "[Reply language] The user wrote in English (or a non-Chinese language). "
        "Reply in English only. Keep product names and policy terms consistent; "
        "if the user later switches to Chinese, switch to Chinese as well."
    )
