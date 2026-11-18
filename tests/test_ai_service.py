# -*- coding: utf-8 -*-
import json

import pytest

from ai_service import (
    AIService,
    AIServiceError,
    parse_minutes_json,
    select_relevant_meetings,
)


def test_parse_plain_json():
    raw = json.dumps({
        "summary": "摘要",
        "decisions": ["决议一"],
        "todos": [{"content": "任务", "assignee": "张三", "due_date": "2026-11-25"}],
    }, ensure_ascii=False)
    result = parse_minutes_json(raw)
    assert result["summary"] == "摘要"
    assert result["decisions"] == ["决议一"]
    assert result["todos"] == [
        {"content": "任务", "assignee": "张三", "due_date": "2026-11-25"}
    ]


def test_parse_code_fenced_json():
    raw = """```json
{"summary": "摘要", "decisions": [], "todos": []}
```"""
    assert parse_minutes_json(raw)["summary"] == "摘要"


def test_parse_json_with_noise_around():
    raw = '好的，以下是纪要：\n{"summary": "摘要", "decisions": [], "todos": []}\n请核对。'
    assert parse_minutes_json(raw)["summary"] == "摘要"


def test_parse_normalizes_fields_and_dates():
    raw = json.dumps({
        "summary": " 摘要 ",
        "decisions": ["决议", "决议", "", "  "],
        "todos": [
            "字符串形式的任务",
            {"content": "任务二", "assignee": None, "due_date": "2026/1/2"},
            {"content": "", "assignee": "无人"},
            {"task": "任务三", "owner": "李四", "deadline": "2026年12月1日"},
        ],
    }, ensure_ascii=False)
    result = parse_minutes_json(raw)
    assert result["summary"] == "摘要"
    assert result["decisions"] == ["决议"]
    assert [todo["content"] for todo in result["todos"]] == ["字符串形式的任务", "任务二", "任务三"]
    assert result["todos"][1]["due_date"] == "2026-01-02"
    assert result["todos"][2]["assignee"] == "李四"
    assert result["todos"][2]["due_date"] == "2026-12-01"


def test_parse_relative_date_is_left_empty():
    result = parse_minutes_json(json.dumps({
        "summary": "摘要",
        "decisions": [],
        "todos": [{"content": "任务", "assignee": "", "due_date": "下周三"}],
    }, ensure_ascii=False))
    assert result["todos"][0]["due_date"] == ""


def test_parse_invalid_json_raises():
    with pytest.raises(AIServiceError):
        parse_minutes_json("这不是 JSON")


def test_parse_empty_content_raises():
    with pytest.raises(AIServiceError):
        parse_minutes_json('{"summary": "", "decisions": [], "todos": []}')


def _meeting(meeting_id, title, summary="", transcript=""):
    return {
        "id": meeting_id,
        "title": title,
        "meeting_date": "2026-11-18",
        "summary": summary,
        "transcript": transcript,
        "decisions": [],
        "todos": [],
    }


def test_select_relevant_meetings_ranks_by_keywords():
    meetings = [
        _meeting(1, "智慧工地需求评审", "讨论二期需求与上线时间"),
        _meeting(2, "食堂满意度调查", "讨论菜品口味"),
    ]
    selected = select_relevant_meetings("智慧工地什么时候上线？", meetings)
    assert [m["id"] for m in selected] == [1]


def test_select_relevant_meetings_falls_back_to_recent():
    meetings = [
        _meeting(1, "周会一"),
        _meeting(2, "周会二"),
        _meeting(3, "周会三"),
        _meeting(4, "周会四"),
    ]
    selected = select_relevant_meetings("火星移民计划", meetings, limit=3)
    assert [m["id"] for m in selected] == [1, 2, 3]


def test_extract_minutes_calls_model_in_json_mode():
    service = AIService({"DEEPSEEK_API_KEY": "test-key", "DEEPSEEK_MODEL": "test-model"})
    captured = {}

    def fake_chat(messages, json_mode=False):
        captured["messages"] = messages
        captured["json_mode"] = json_mode
        return json.dumps({
            "summary": "摘要",
            "decisions": ["决议"],
            "todos": [{"content": "任务", "assignee": "张三", "due_date": "2026-12-01"}],
        }, ensure_ascii=False)

    service._chat = fake_chat
    result = service.extract_minutes(
        "张三：下周三前完成任务。",
        title="项目周会",
        attendees="张三",
        meeting_date="2026-11-18",
    )
    assert captured["json_mode"] is True
    assert "项目周会" in captured["messages"][1]["content"]
    assert result["summary"] == "摘要"
    assert result["todos"][0]["assignee"] == "张三"


def test_extract_minutes_rejects_empty_transcript():
    service = AIService({"DEEPSEEK_API_KEY": "test-key"})
    service._chat = lambda *args, **kwargs: pytest.fail("不应调用模型")
    with pytest.raises(AIServiceError, match="记录为空"):
        service.extract_minutes("   ")


def test_extract_minutes_requires_api_key():
    service = AIService({"DEEPSEEK_API_KEY": ""})
    with pytest.raises(AIServiceError, match="DEEPSEEK_API_KEY"):
        service.extract_minutes("会议记录")
    assert service.available is False


def test_extract_minutes_truncates_long_transcript():
    service = AIService({
        "DEEPSEEK_API_KEY": "test-key",
        "AI_MAX_TRANSCRIPT_CHARS": 10,
    })
    captured = {}

    def fake_chat(messages, json_mode=False):
        captured["content"] = messages[1]["content"]
        return '{"summary": "摘要", "decisions": [], "todos": []}'

    service._chat = fake_chat
    service.extract_minutes("一二三四五六七八九十十一十二")
    assert "内容过长已截断" in captured["content"]


def test_answer_question_without_meetings_returns_hint():
    service = AIService({"DEEPSEEK_API_KEY": "test-key"})
    service._chat = lambda *args, **kwargs: pytest.fail("不应调用模型")
    result = service.answer_question("有什么决定？", [])
    assert result["sources"] == []
    assert "还没有" in result["answer"]


def test_answer_question_returns_sources():
    service = AIService({"DEEPSEEK_API_KEY": "test-key"})
    captured = {}

    def fake_chat(messages, json_mode=False):
        captured["prompt"] = messages[1]["content"]
        return "二期计划 12 月上线。【会议：智慧工地需求评审（2026-11-18）】"

    service._chat = fake_chat
    meetings = [
        _meeting(1, "智慧工地需求评审", "讨论二期需求与上线时间"),
        _meeting(2, "食堂满意度调查", "讨论菜品口味"),
    ]
    result = service.answer_question("智慧工地什么时候上线？", meetings)
    assert "12 月上线" in result["answer"]
    assert result["sources"] == [
        {"id": 1, "title": "智慧工地需求评审", "meeting_date": "2026-11-18"}
    ]
    assert "会议资料" in captured["prompt"]
    assert "用户问题" in captured["prompt"]


def test_friendly_error_messages():
    assert "API Key" in AIService._friendly_error(Exception("Error code: 401 - invalid"))
    assert "超时" in AIService._friendly_error(Exception("Request timed out"))
