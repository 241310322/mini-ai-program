# -*- coding: utf-8 -*-
"""DeepSeek AI 服务封装。

包含两类能力：
1. extract_minutes：从会议记录原文中提炼摘要、决议与待办（结构化 JSON）。
2. answer_question：跨会议检索并回答自然语言问题（带来源标注）。
"""
from __future__ import annotations

import json
import re
from datetime import date
from typing import Any

from openai import OpenAI


class AIServiceError(RuntimeError):
    """AI 调用失败或返回内容无法解析。"""


EXTRACT_SYSTEM_PROMPT = """你是一名严谨的会议纪要助理。请从会议记录原文中提炼结构化纪要。
必须遵守以下规则：
1. 只依据原文，不得编造原文没有的信息；原文没有的内容宁可不写。
2. 只输出合法 JSON，不要输出 Markdown 代码块、解释或多余文字。
3. JSON 结构固定为：
{
  "summary": "会议摘要，120 字以内，客观概括议题与结论",
  "decisions": ["决议事项1", "决议事项2"],
  "todos": [
    {"content": "待办事项", "assignee": "负责人（未提及则为空字符串）", "due_date": "YYYY-MM-DD（未提及则为空字符串）"}
  ]
}
4. decisions 与 todos 可以为空数组；普通讨论不得写成决议。
5. 截止日期若为相对表述（如“下周三”），按会议日期换算为具体日期。
6. 待办事项应具体可执行，避免“继续跟进”这类空泛表述。"""

QA_SYSTEM_PROMPT = """你是一名会议知识库问答助手。请依据提供的会议资料回答用户问题。
要求：
1. 只使用资料中的信息，不得编造；资料不足时明确说明“现有会议记录无法回答”，并指出缺少什么信息。
2. 用中文回答，条理清晰，必要时用「1. 2. 3.」分点；使用纯文本，不要使用 Markdown 标记（如 **、#、反引号、表格等）。
3. 每个关键结论后用【会议：标题（日期）】标注来源。
4. 不要提及“资料片段”“上下文”等系统措辞。"""

# 检索时忽略的高频词，降低通用词的干扰
_STOP_TOKENS = {
    "会议", "什么", "哪些", "怎么", "怎样", "我们", "他们", "你们", "这个", "那个",
    "一下", "请问", "问题", "事情", "时候", "上周", "本周", "下周", "今天", "昨天",
    "明天", "关于", "以及", "还有", "是否", "可以", "需要", "多少", "哪个",
}


def _tokens(text: str) -> set[str]:
    """轻量分词：英文/数字按词，中文按二元字组，用于关键词检索。"""
    text = (text or "").lower()
    tokens: set[str] = set()
    for word in re.findall(r"[a-z0-9_]{2,}", text):
        tokens.add(word)
    for segment in re.findall(r"[一-鿿]+", text):
        if len(segment) == 1:
            tokens.add(segment)
        for i in range(len(segment) - 1):
            tokens.add(segment[i:i + 2])
    return tokens - _STOP_TOKENS


def _strip_code_fence(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _normalize_due_date(value: str) -> str:
    """把常见日期写法归一化为 YYYY-MM-DD；无法识别则返回空串。"""
    if not value:
        return ""
    value = value.strip()
    if value in {"无", "未提及", "暂无", "待定", "null", "None"}:
        return ""
    match = re.search(r"(\d{4})[-/年.](\d{1,2})[-/月.](\d{1,2})", value)
    if match:
        year, month, day = (int(part) for part in match.groups())
        try:
            return date(year, month, day).isoformat()
        except ValueError:
            return ""
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return value
    return ""


def _normalize_minutes(data: Any) -> dict:
    if not isinstance(data, dict):
        raise AIServiceError("AI 返回的纪要格式不正确（不是 JSON 对象）")

    summary = str(data.get("summary") or "").strip()

    decisions: list[str] = []
    raw_decisions = data.get("decisions") or []
    if isinstance(raw_decisions, str):
        raw_decisions = [raw_decisions]
    for item in raw_decisions:
        if isinstance(item, dict):
            item = item.get("content") or item.get("decision") or ""
        text = str(item).strip()
        if text and text not in decisions:
            decisions.append(text)

    todos: list[dict] = []
    raw_todos = data.get("todos") or []
    if isinstance(raw_todos, dict):
        raw_todos = [raw_todos]
    for item in raw_todos:
        if isinstance(item, str):
            item = {"content": item}
        if not isinstance(item, dict):
            continue
        content = str(item.get("content") or item.get("task") or "").strip()
        if not content:
            continue
        due = _normalize_due_date(str(item.get("due_date") or item.get("deadline") or ""))
        todos.append({
            "content": content,
            "assignee": str(item.get("assignee") or item.get("owner") or "").strip(),
            "due_date": due,
        })

    if not summary and not decisions and not todos:
        raise AIServiceError("AI 未能从会议记录中提炼出有效内容，请补充记录后重试")

    return {"summary": summary, "decisions": decisions, "todos": todos}


def parse_minutes_json(raw: str) -> dict:
    """解析模型输出，兼容代码块、前后说明文字等常见噪声。"""
    text = _strip_code_fence(raw or "")
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            raise AIServiceError("AI 返回内容不是有效 JSON，请重试") from None
        try:
            data = json.loads(text[start:end + 1])
        except json.JSONDecodeError as exc:
            raise AIServiceError("AI 返回内容不是有效 JSON，请重试") from exc
    return _normalize_minutes(data)


def select_relevant_meetings(question: str, meetings: list[dict], limit: int = 3) -> list[dict]:
    """基于关键词重合度挑选与问题最相关的会议；无命中时回退到最近的会议。"""
    if not meetings:
        return []
    question_tokens = _tokens(question)
    scored: list[tuple[float, int, dict]] = []
    for index, meeting in enumerate(meetings):
        title = _tokens(meeting.get("title", ""))
        summary = _tokens(meeting.get("summary", ""))
        decisions = _tokens(" ".join(meeting.get("decisions") or []))
        todos = _tokens(" ".join(
            f"{t.get('content', '')} {t.get('assignee', '')}" for t in meeting.get("todos") or []
        ))
        transcript = _tokens((meeting.get("transcript") or "")[:8000])
        score = (
            len(question_tokens & title) * 4
            + len(question_tokens & summary) * 3
            + len(question_tokens & decisions) * 2
            + len(question_tokens & todos) * 2
            + len(question_tokens & transcript) * 1
        )
        scored.append((score, -index, meeting))
    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
    selected = [item[2] for item in scored if item[0] > 0][:limit]
    if not selected:
        selected = meetings[:limit]
    return selected


def _format_context(meeting: dict) -> str:
    lines = [
        f"会议 ID：{meeting.get('id')}",
        f"标题：{meeting.get('title')}",
        f"日期：{meeting.get('meeting_date')}",
    ]
    if meeting.get("attendees"):
        lines.append(f"参会人：{meeting['attendees']}")
    if meeting.get("summary"):
        lines.append(f"摘要：{meeting['summary']}")
    if meeting.get("decisions"):
        lines.append("决议：" + "；".join(meeting["decisions"]))
    if meeting.get("todos"):
        todo_texts = []
        for todo in meeting["todos"]:
            parts = [todo.get("content", "")]
            if todo.get("assignee"):
                parts.append(f"负责人 {todo['assignee']}")
            if todo.get("due_date"):
                parts.append(f"截止 {todo['due_date']}")
            parts.append("已完成" if todo.get("done") else "未完成")
            todo_texts.append("（" + "，".join(parts) + "）")
        lines.append("待办：" + "".join(todo_texts))
    transcript = (meeting.get("transcript") or "").strip()
    if transcript:
        excerpt = transcript[:3000]
        if len(transcript) > 3000:
            excerpt += "……（记录已截断）"
        lines.append(f"记录摘录：{excerpt}")
    return "\n".join(lines)


class AIService:
    def __init__(self, config):
        self.api_key = (config.get("DEEPSEEK_API_KEY") or "").strip()
        self.base_url = (config.get("DEEPSEEK_BASE_URL") or "https://api.deepseek.com").strip()
        self.model = (config.get("DEEPSEEK_MODEL") or "deepseek-flash").strip()
        self.timeout = float(config.get("AI_TIMEOUT") or 60)
        self.max_transcript_chars = int(config.get("AI_MAX_TRANSCRIPT_CHARS") or 60000)
        self._client: OpenAI | None = None

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    def _get_client(self) -> OpenAI:
        if not self.api_key:
            raise AIServiceError("未配置 DEEPSEEK_API_KEY，请先在 .env 中设置后再使用 AI 功能")
        if self._client is None:
            self._client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=self.timeout,
                max_retries=1,
            )
        return self._client

    def _chat(self, messages: list[dict], json_mode: bool = False) -> str:
        client = self._get_client()
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.2,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        try:
            response = client.chat.completions.create(**kwargs)
        except Exception as exc:  # openai SDK 的异常类型较杂，统一转换
            if json_mode and "response_format" in str(exc).lower():
                kwargs.pop("response_format", None)
                try:
                    response = client.chat.completions.create(**kwargs)
                except Exception as retry_exc:
                    raise AIServiceError(self._friendly_error(retry_exc)) from retry_exc
            else:
                raise AIServiceError(self._friendly_error(exc)) from exc

        if not response.choices:
            raise AIServiceError("AI 服务返回了空响应，请稍后重试")
        content = response.choices[0].message.content or ""
        if not content.strip():
            raise AIServiceError("AI 服务返回了空内容，请稍后重试")
        return content

    @staticmethod
    def _friendly_error(exc: Exception) -> str:
        text = str(exc)
        lowered = text.lower()
        if "401" in text or "authentication" in lowered or "invalid api key" in lowered:
            return "DeepSeek API Key 无效或已过期，请检查 .env 配置"
        if "timeout" in lowered or "timed out" in lowered:
            return "AI 服务响应超时，请稍后重试或缩短会议记录"
        if "429" in text or "rate limit" in lowered:
            return "AI 服务请求过于频繁，请稍后重试"
        if "insufficient" in lowered or "balance" in lowered:
            return "DeepSeek 账户余额不足"
        return f"调用 AI 服务失败：{text[:300]}"

    def extract_minutes(
        self,
        transcript: str,
        title: str = "",
        attendees: str = "",
        meeting_date: str = "",
    ) -> dict:
        transcript = (transcript or "").strip()
        if not transcript:
            raise AIServiceError("会议记录为空，无法提炼纪要")
        if len(transcript) > self.max_transcript_chars:
            transcript = transcript[: self.max_transcript_chars] + "\n……（内容过长已截断）"

        user_prompt = (
            f"会议标题：{title or '未命名会议'}\n"
            f"会议日期：{meeting_date or '未提供'}\n"
            f"参会人：{attendees or '未提供'}\n\n"
            f"会议记录原文：\n{transcript}\n\n"
            "请按要求输出 JSON 纪要。"
        )
        raw = self._chat(
            [
                {"role": "system", "content": EXTRACT_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            json_mode=True,
        )
        return parse_minutes_json(raw)

    def answer_question(self, question: str, meetings: list[dict]) -> dict:
        question = (question or "").strip()
        if not question:
            raise AIServiceError("问题不能为空")
        if not meetings:
            return {
                "answer": "知识库里还没有可检索的会议记录，请先录入会议。",
                "sources": [],
            }

        selected = select_relevant_meetings(question, meetings, limit=3)
        context = "\n\n".join(_format_context(meeting) for meeting in selected)
        answer = self._chat(
            [
                {"role": "system", "content": QA_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": f"会议资料：\n{context}\n\n用户问题：{question}",
                },
            ]
        ).strip()
        sources = [
            {
                "id": meeting.get("id"),
                "title": meeting.get("title"),
                "meeting_date": meeting.get("meeting_date"),
            }
            for meeting in selected
        ]
        return {"answer": answer, "sources": sources}
