"""
基础智能体类
所有专门智能体的基类。

统一在这里注入：
1. GlobalShop 跨境电商人设（persona.py）
2. 语言策略：根据用户提问自动中/英回复（i18n.py）
3. 知识库片段：按 query 向量召回 knowledge/ 的相关章节（vector_store.py，失败回退 knowledge_base.py）
4. 多轮对话上下文要求
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from i18n import detect_language, language_instruction
from knowledge_base import default_knowledge_base
from persona import build_agent_prompt
from session_manager import LangChainSessionManager


class BaseAgent(ABC):
    # 子类可覆盖：限定只召回某些知识库章节
    kb_categories: Optional[List[str]] = None

    def __init__(self, name: str, role: str, expertise: List[str],
                 session_manager: LangChainSessionManager = None,
                 kb_categories: Optional[List[str]] = None):
        self.name = name
        self.role = role
        self.expertise = expertise
        self.llm = None  # 将在运行时注入
        self.session_manager = session_manager or LangChainSessionManager()
        if kb_categories is not None:
            self.kb_categories = kb_categories

    def set_llm(self, llm):
        """设置LLM客户端"""
        self.llm = llm

    def set_session_manager(self, session_manager: LangChainSessionManager):
        """设置会话管理器"""
        self.session_manager = session_manager

    @abstractmethod
    def process(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """处理客户查询的抽象方法"""
        pass

    # ---------- 提示词组装 ----------

    def _knowledge_context(self, query: str) -> str:
        """优先向量检索（knowledge/ + bge-m3）；索引不可用时回退关键词检索。"""
        try:
            from vector_store import has_index, search as vector_search

            if has_index():
                hits = vector_search(query, top_k=3)
                if hits:
                    return "\n\n".join(f"### {h['title']}\n{h['content']}" for h in hits)
        except Exception as e:
            print(f"向量检索失败，回退关键词检索: {e}")

        try:
            return default_knowledge_base.as_prompt_block(
                query, limit=2, categories=self.kb_categories
            )
        except Exception as e:  # 知识库异常不应阻断回复
            print(f"知识库检索失败: {e}")
            return ""

    def _enhance_system_prompt_with_context(self, base_prompt: str, query: str = "",
                                            use_kb: bool = True) -> str:
        """拼接最终系统提示：人设 + 职责 + 语言 + 知识库 + 多轮上下文。"""
        lang = detect_language(query)
        context_rule = """重要：请结合对话历史上下文，理解客户之前的问题和需求，提供连贯、个性化的回答。
如果这是多轮对话，请参考之前的对话内容，避免重复信息，并基于客户的新问题提供补充信息。"""
        return build_agent_prompt(
            role_prompt=base_prompt,
            language_rule=language_instruction(lang),
            knowledge_block=self._knowledge_context(query) if use_kb else "",
            context_rule=context_rule,
        )

    def _fallback_reply(self, query: str, topic_zh: str, topic_en: str) -> str:
        """LLM 调用失败时的兜底文案（跟随提问语言）。"""
        if detect_language(query) == "zh":
            return f"抱歉，处理您的{topic_zh}时遇到系统错误，请稍后重试。"
        return f"Sorry, we hit a temporary issue while handling your {topic_en} request. Please try again shortly."

    # ---------- 会话上下文 ----------

    def _get_conversation_context(
        self,
        session_id: str,
        state: Optional[Dict[str, Any]] = None,
        max_messages: int = 12,
    ) -> str:
        """优先使用图状态中持久化的对话（跨 LangGraph 进程/工作有效），否则回退到 session_manager。"""
        if state is not None:
            records = state.get("persisted_dialogue")
            if records:
                tail = records[-max_messages:]
                context_lines = []
                for msg in tail:
                    role = "用户" if msg.get("is_user", True) else "AI"
                    content = msg.get("content", "")
                    timestamp = msg.get("timestamp", "")
                    context_lines.append(f"[{timestamp}] {role}: {content}")
                return "\n".join(context_lines)
        try:
            conversation_context = self.session_manager.get_conversation_context(session_id, max_messages)
            if not conversation_context:
                return ""

            context_lines = []
            for msg in conversation_context:
                role = "用户" if msg.get("is_user", True) else "AI"
                content = msg.get("content", "")
                timestamp = msg.get("timestamp", "")
                context_lines.append(f"[{timestamp}] {role}: {content}")
            return "\n".join(context_lines)
        except Exception as e:
            print(f"获取对话上下文时出错: {e}")
            return ""

    def _add_message_to_session(self, session_id: str, message: str, is_user: bool = True):
        """添加消息到会话历史"""
        try:
            self.session_manager.add_message(session_id, message, is_user)
        except Exception as e:
            print(f"添加消息到会话时出错: {e}")

    def get_info(self) -> Dict[str, Any]:
        """获取智能体信息"""
        return {
            "name": self.name,
            "role": self.role,
            "expertise": self.expertise
        }
