# -*- coding: utf-8 -*-
import io

from docx import Document

import db
from ai_service import AIServiceError


def test_index_empty(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "还没有会议记录" in response.get_data(as_text=True)


def test_create_meeting(client, app):
    response = client.post(
        "/meetings/new",
        data={
            "title": "智慧工地需求评审",
            "meeting_date": "2026-11-18",
            "attendees": "张三、李四",
            "location": "会议室 A",
            "transcript": "讨论二期需求。",
        },
        follow_redirects=False,
    )
    assert response.status_code == 302

    page = client.get(response.headers["Location"])
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    assert "智慧工地需求评审" in html
    assert "AI 提炼纪要" in html

    with app.app_context():
        row = db.query_one("SELECT * FROM meetings")
        assert row["title"] == "智慧工地需求评审"
        assert row["status"] == "draft"


def test_create_meeting_validation(client, app):
    response = client.post(
        "/meetings/new",
        data={"title": "", "meeting_date": "", "transcript": ""},
    )
    assert response.status_code == 400
    html = response.get_data(as_text=True)
    assert "请填写会议主题" in html
    assert "请选择会议日期" in html
    with app.app_context():
        assert db.query_one("SELECT COUNT(*) AS c FROM meetings")["c"] == 0


def test_edit_meeting(client, make_meeting):
    meeting_id = make_meeting(title="旧主题")
    response = client.post(
        f"/meetings/{meeting_id}/edit",
        data={
            "title": "新主题",
            "meeting_date": "2026-11-19",
            "attendees": "王五",
            "location": "线上",
            "transcript": "更新后的记录。",
        },
    )
    assert response.status_code == 302
    page = client.get(response.headers["Location"]).get_data(as_text=True)
    assert "新主题" in page
    assert "王五" in page


def test_search_meetings(client, make_meeting):
    make_meeting(title="智慧工地需求评审")
    make_meeting(title="食堂满意度调查", transcript="讨论菜单。")
    assert "智慧工地需求评审" in client.get("/?q=智慧").get_data(as_text=True)
    assert "食堂满意度调查" not in client.get("/?q=智慧").get_data(as_text=True)


def test_extract_meeting_success(client, app, make_meeting):
    meeting_id = make_meeting()
    response = client.post(f"/meetings/{meeting_id}/extract")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["summary"] == "会议确定了二期需求范围和上线时间。"
    assert len(payload["todos"]) == 2

    with app.app_context():
        meeting = db.query_one("SELECT * FROM meetings WHERE id = ?", (meeting_id,))
        assert meeting["status"] == "processed"
        assert meeting["summary"]
        assert db.query_one(
            "SELECT COUNT(*) AS c FROM decisions WHERE meeting_id = ?", (meeting_id,)
        )["c"] == 2
        assert db.query_one(
            "SELECT COUNT(*) AS c FROM todos WHERE meeting_id = ?", (meeting_id,)
        )["c"] == 2

    page = client.get(f"/meetings/{meeting_id}").get_data(as_text=True)
    assert "会议确定了二期需求范围和上线时间。" in page
    assert "完成用户访谈" in page
    assert "二期于 12 月上线" in page


def test_extract_preserves_done_status(client, app, make_meeting):
    meeting_id = make_meeting()
    client.post(f"/meetings/{meeting_id}/extract")

    with app.app_context():
        todo = db.query_one(
            "SELECT * FROM todos WHERE meeting_id = ? AND content = ?",
            (meeting_id, "完成用户访谈"),
        )
    client.post(f"/todos/{todo['id']}/toggle")

    app.fake_ai.extract_result = {
        "summary": "更新后的摘要",
        "decisions": ["保持 12 月上线"],
        "todos": [
            {"content": "完成用户访谈", "assignee": "张三", "due_date": "2026-11-26"},
            {"content": "新增任务", "assignee": "李四", "due_date": ""},
        ],
    }
    response = client.post(f"/meetings/{meeting_id}/extract")
    assert response.status_code == 200

    with app.app_context():
        kept = db.query_one(
            "SELECT * FROM todos WHERE meeting_id = ? AND content = ?",
            (meeting_id, "完成用户访谈"),
        )
        added = db.query_one(
            "SELECT * FROM todos WHERE meeting_id = ? AND content = ?",
            (meeting_id, "新增任务"),
        )
        assert kept["done"] == 1
        assert added["done"] == 0


def test_extract_ai_error_returns_502(client, app, make_meeting):
    meeting_id = make_meeting()
    app.fake_ai.extract_error = AIServiceError("模型服务繁忙")
    response = client.post(f"/meetings/{meeting_id}/extract")
    assert response.status_code == 502
    payload = response.get_json()
    assert payload["ok"] is False
    assert "模型服务繁忙" in payload["error"]


def test_toggle_and_edit_todo(client, app, make_meeting):
    meeting_id = make_meeting()
    client.post(f"/meetings/{meeting_id}/extract")

    with app.app_context():
        todo = db.query_one(
            "SELECT * FROM todos WHERE meeting_id = ? AND content = ?",
            (meeting_id, "输出接口文档"),
        )

    response = client.post(f"/todos/{todo['id']}/toggle")
    assert response.status_code == 200
    assert response.get_json() == {"ok": True, "done": True}

    response = client.post(
        f"/todos/{todo['id']}/edit",
        data={"content": "输出接口文档 V2", "assignee": "王五", "due_date": "2026-12-01"},
    )
    assert response.status_code == 302

    with app.app_context():
        updated = db.query_one("SELECT * FROM todos WHERE id = ?", (todo["id"],))
        assert updated["content"] == "输出接口文档 V2"
        assert updated["assignee"] == "王五"
        assert updated["due_date"] == "2026-12-01"
        assert updated["done"] == 1

    page = client.get(f"/meetings/{meeting_id}").get_data(as_text=True)
    assert "输出接口文档 V2" in page


def test_edit_todo_rejects_invalid_date(client, app, make_meeting):
    meeting_id = make_meeting()
    client.post(f"/meetings/{meeting_id}/extract")
    with app.app_context():
        todo = db.query_one("SELECT * FROM todos WHERE meeting_id = ?", (meeting_id,))
    response = client.post(
        f"/todos/{todo['id']}/edit",
        data={"content": "仍然有效", "assignee": "", "due_date": "不是日期"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "截止日期格式不正确" in response.get_data(as_text=True)


def test_delete_meeting_cascades(client, app, make_meeting):
    meeting_id = make_meeting()
    client.post(f"/meetings/{meeting_id}/extract")
    response = client.post(f"/meetings/{meeting_id}/delete")
    assert response.status_code == 302
    with app.app_context():
        assert db.query_one("SELECT COUNT(*) AS c FROM meetings")["c"] == 0
        assert db.query_one("SELECT COUNT(*) AS c FROM decisions")["c"] == 0
        assert db.query_one("SELECT COUNT(*) AS c FROM todos")["c"] == 0


def test_export_docx(client, make_meeting):
    meeting_id = make_meeting(title="导出测试会议")
    client.post(f"/meetings/{meeting_id}/extract")
    response = client.get(f"/meetings/{meeting_id}/export")
    assert response.status_code == 200
    assert response.mimetype == (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )

    document = Document(io.BytesIO(response.data))
    paragraphs = "\n".join(p.text for p in document.paragraphs)
    table_text = "\n".join(
        cell.text for table in document.tables for row in table.rows for cell in row.cells
    )
    combined = paragraphs + "\n" + table_text
    assert "导出测试会议" in combined
    assert "会议确定了二期需求范围和上线时间。" in combined
    assert "完成用户访谈" in combined
    assert "张三" in combined


def test_ask_question(client, app, make_meeting):
    meeting_id = make_meeting()
    app.fake_ai.qa_result = {
        "answer": "二期计划 12 月上线。【会议：项目周会（2026-11-18）】",
        "sources": [{"id": meeting_id, "title": "项目周会", "meeting_date": "2026-11-18"}],
    }
    response = client.post("/ask", data={"question": "二期什么时候上线？"})
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "二期计划 12 月上线" in html
    assert f"/meetings/{meeting_id}" in html
    assert app.fake_ai.qa_calls[0]["question"] == "二期什么时候上线？"
    with app.app_context():
        assert db.query_one("SELECT COUNT(*) AS c FROM qa_logs")["c"] == 1


def test_ask_requires_question(client):
    response = client.post("/ask", data={"question": "  "})
    assert response.status_code == 200
    assert "请输入问题" in response.get_data(as_text=True)


def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["ai_configured"] is True
    assert payload["meetings"] == 0


def test_404(client):
    response = client.get("/meetings/999")
    assert response.status_code == 404
    assert "页面不存在" in response.get_data(as_text=True)
