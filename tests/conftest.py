# -*- coding: utf-8 -*-
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import create_app  # noqa: E402


class FakeAIService:
    """测试用假 AI 服务，不发起任何网络请求。"""

    def __init__(self):
        self.available = True
        self.model = "fake-model"
        self.extract_result = {
            "summary": "会议确定了二期需求范围和上线时间。",
            "decisions": ["二期于 12 月上线", "采用分阶段发布"],
            "todos": [
                {"content": "完成用户访谈", "assignee": "张三", "due_date": "2026-11-25"},
                {"content": "输出接口文档", "assignee": "", "due_date": ""},
            ],
        }
        self.extract_error = None
        self.qa_result = {"answer": "默认回答", "sources": []}
        self.qa_error = None
        self.extract_calls = []
        self.qa_calls = []

    def extract_minutes(self, transcript, title="", attendees="", meeting_date=""):
        self.extract_calls.append({
            "transcript": transcript,
            "title": title,
            "attendees": attendees,
            "meeting_date": meeting_date,
        })
        if self.extract_error:
            raise self.extract_error
        return self.extract_result

    def answer_question(self, question, meetings):
        self.qa_calls.append({"question": question, "meetings": meetings})
        if self.qa_error:
            raise self.qa_error
        return self.qa_result


@pytest.fixture()
def app(tmp_path):
    application = create_app({
        "TESTING": True,
        "SECRET_KEY": "test-secret",
        "DATABASE": str(tmp_path / "test.db"),
        "DEEPSEEK_API_KEY": "test-key",
        "AI_TIMEOUT": 5,
    })
    fake_ai = FakeAIService()
    application.extensions["ai_service"] = fake_ai
    application.fake_ai = fake_ai
    yield application


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def make_meeting(client):
    def _make(
        title="项目周会",
        meeting_date="2026-11-18",
        attendees="张三、李四",
        location="会议室 A",
        transcript="张三：二期需求已经确认。李四：下周三前完成用户访谈。",
    ):
        response = client.post(
            "/meetings/new",
            data={
                "title": title,
                "meeting_date": meeting_date,
                "attendees": attendees,
                "location": location,
                "transcript": transcript,
            },
        )
        assert response.status_code == 302
        location_header = response.headers["Location"]
        return int(location_header.rstrip("/").split("/")[-1])

    return _make
