# -*- coding: utf-8 -*-
"""Flask 路由。"""
from __future__ import annotations

import json
from datetime import date

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)

import db
from ai_service import AIServiceError
from docx_export import build_filename, build_meeting_docx

main = Blueprint("main", __name__)


def _get_meeting_or_404(meeting_id: int):
    meeting = db.query_one("SELECT * FROM meetings WHERE id = ?", (meeting_id,))
    if meeting is None:
        abort(404)
    return meeting


def _fetch_decisions(meeting_id: int) -> list[dict]:
    rows = db.query(
        "SELECT * FROM decisions WHERE meeting_id = ? ORDER BY position, id",
        (meeting_id,),
    )
    return [dict(row) for row in rows]


def _fetch_todos(meeting_id: int) -> list[dict]:
    rows = db.query(
        """SELECT * FROM todos WHERE meeting_id = ?
           ORDER BY done ASC,
                    CASE WHEN due_date = '' THEN 1 ELSE 0 END,
                    due_date ASC, id ASC""",
        (meeting_id,),
    )
    return [dict(row) for row in rows]


def _load_all_meetings_with_details() -> list[dict]:
    meetings = [dict(row) for row in db.query(
        "SELECT * FROM meetings ORDER BY meeting_date DESC, id DESC"
    )]
    for meeting in meetings:
        meeting["decisions"] = [d["content"] for d in _fetch_decisions(meeting["id"])]
        meeting["todos"] = _fetch_todos(meeting["id"])
    return meetings


def _read_meeting_form() -> dict:
    return {
        "title": request.form.get("title", "").strip(),
        "meeting_date": request.form.get("meeting_date", "").strip(),
        "attendees": request.form.get("attendees", "").strip(),
        "location": request.form.get("location", "").strip(),
        "transcript": request.form.get("transcript", "").strip(),
    }


def _validate_meeting_form(data: dict) -> list[str]:
    errors: list[str] = []
    if not data["title"]:
        errors.append("请填写会议主题")
    if not data["meeting_date"]:
        errors.append("请选择会议日期")
    else:
        try:
            date.fromisoformat(data["meeting_date"])
        except ValueError:
            errors.append("会议日期格式不正确")
    return errors


@main.get("/")
def index():
    q = request.args.get("q", "").strip()
    pending_sql = "(SELECT COUNT(*) FROM todos t WHERE t.meeting_id = m.id AND t.done = 0)"
    if q:
        like = f"%{q}%"
        meetings = db.query(
            f"""SELECT m.*, {pending_sql} AS pending_todos FROM meetings m
                WHERE m.title LIKE ? OR m.attendees LIKE ? OR m.transcript LIKE ? OR m.summary LIKE ?
                ORDER BY m.meeting_date DESC, m.id DESC""",
            (like, like, like, like),
        )
    else:
        meetings = db.query(
            f"""SELECT m.*, {pending_sql} AS pending_todos FROM meetings m
                ORDER BY m.meeting_date DESC, m.id DESC"""
        )

    today = date.today().isoformat()
    stats = {
        "meetings": db.query_one("SELECT COUNT(*) AS c FROM meetings")["c"],
        "open_todos": db.query_one("SELECT COUNT(*) AS c FROM todos WHERE done = 0")["c"],
        "done_todos": db.query_one("SELECT COUNT(*) AS c FROM todos WHERE done = 1")["c"],
        "overdue": db.query_one(
            "SELECT COUNT(*) AS c FROM todos WHERE done = 0 AND due_date <> '' AND due_date < ?",
            (today,),
        )["c"],
    }
    return render_template("index.html", meetings=meetings, q=q, stats=stats, today=today)


@main.route("/meetings/new", methods=["GET", "POST"])
def new_meeting():
    if request.method == "POST":
        data = _read_meeting_form()
        errors = _validate_meeting_form(data)
        if errors:
            for error in errors:
                flash(error, "error")
            return render_template("meeting_form.html", form=data, meeting=None), 400
        cursor = db.execute(
            """INSERT INTO meetings (title, meeting_date, attendees, location, transcript)
               VALUES (?, ?, ?, ?, ?)""",
            (data["title"], data["meeting_date"], data["attendees"],
             data["location"], data["transcript"]),
        )
        flash("会议已创建，可以点击「AI 提炼纪要」生成摘要与待办。", "success")
        return redirect(url_for("main.meeting_detail", meeting_id=cursor.lastrowid))

    form = {
        "title": "",
        "meeting_date": date.today().isoformat(),
        "attendees": "",
        "location": "",
        "transcript": "",
    }
    return render_template("meeting_form.html", form=form, meeting=None)


@main.get("/meetings/<int:meeting_id>")
def meeting_detail(meeting_id: int):
    meeting = _get_meeting_or_404(meeting_id)
    decisions = _fetch_decisions(meeting_id)
    todos = _fetch_todos(meeting_id)
    today = date.today().isoformat()
    for todo in todos:
        todo["overdue"] = bool(
            not todo["done"] and todo["due_date"] and todo["due_date"] < today
        )
    service = current_app.extensions["ai_service"]
    return render_template(
        "meeting_detail.html",
        meeting=meeting,
        decisions=decisions,
        todos=todos,
        ai_available=service.available,
        ai_model=service.model,
    )


@main.route("/meetings/<int:meeting_id>/edit", methods=["GET", "POST"])
def edit_meeting(meeting_id: int):
    meeting = _get_meeting_or_404(meeting_id)
    if request.method == "POST":
        data = _read_meeting_form()
        errors = _validate_meeting_form(data)
        if errors:
            for error in errors:
                flash(error, "error")
            return render_template("meeting_form.html", form=data, meeting=meeting), 400
        db.execute(
            """UPDATE meetings
               SET title = ?, meeting_date = ?, attendees = ?, location = ?, transcript = ?,
                   updated_at = datetime('now', 'localtime')
               WHERE id = ?""",
            (data["title"], data["meeting_date"], data["attendees"], data["location"],
             data["transcript"], meeting_id),
        )
        flash("会议信息已更新。", "success")
        return redirect(url_for("main.meeting_detail", meeting_id=meeting_id))

    return render_template("meeting_form.html", form=dict(meeting), meeting=meeting)


@main.post("/meetings/<int:meeting_id>/delete")
def delete_meeting(meeting_id: int):
    _get_meeting_or_404(meeting_id)
    db.execute("DELETE FROM meetings WHERE id = ?", (meeting_id,))
    flash("会议及其纪要、待办已删除。", "success")
    return redirect(url_for("main.index"))


@main.post("/meetings/<int:meeting_id>/extract")
def extract_meeting(meeting_id: int):
    """调用 AI 提炼纪要（JSON 接口，供前端异步调用）。"""
    meeting = _get_meeting_or_404(meeting_id)
    service = current_app.extensions["ai_service"]
    try:
        result = service.extract_minutes(
            transcript=meeting["transcript"],
            title=meeting["title"],
            attendees=meeting["attendees"],
            meeting_date=meeting["meeting_date"],
        )
    except AIServiceError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 502

    connection = db.get_db()
    existing = {
        row["content"]: row["done"]
        for row in connection.execute(
            "SELECT content, done FROM todos WHERE meeting_id = ?", (meeting_id,)
        )
    }
    with connection:
        connection.execute("DELETE FROM decisions WHERE meeting_id = ?", (meeting_id,))
        connection.execute("DELETE FROM todos WHERE meeting_id = ?", (meeting_id,))
        for position, content in enumerate(result["decisions"]):
            connection.execute(
                "INSERT INTO decisions (meeting_id, content, position) VALUES (?, ?, ?)",
                (meeting_id, content, position),
            )
        for todo in result["todos"]:
            connection.execute(
                """INSERT INTO todos (meeting_id, content, assignee, due_date, done)
                   VALUES (?, ?, ?, ?, ?)""",
                (meeting_id, todo["content"], todo["assignee"], todo["due_date"],
                 1 if existing.get(todo["content"]) else 0),
            )
        connection.execute(
            """UPDATE meetings SET summary = ?, status = 'processed',
                                  updated_at = datetime('now', 'localtime')
               WHERE id = ?""",
            (result["summary"], meeting_id),
        )

    return jsonify({
        "ok": True,
        "summary": result["summary"],
        "decisions": result["decisions"],
        "todos": result["todos"],
    })


@main.post("/todos/<int:todo_id>/toggle")
def toggle_todo(todo_id: int):
    todo = db.query_one("SELECT * FROM todos WHERE id = ?", (todo_id,))
    if todo is None:
        return jsonify({"ok": False, "error": "待办不存在"}), 404
    done = 0 if todo["done"] else 1
    db.execute("UPDATE todos SET done = ? WHERE id = ?", (done, todo_id))
    return jsonify({"ok": True, "done": bool(done)})


@main.post("/todos/<int:todo_id>/edit")
def edit_todo(todo_id: int):
    todo = db.query_one("SELECT * FROM todos WHERE id = ?", (todo_id,))
    if todo is None:
        abort(404)
    content = request.form.get("content", "").strip()
    assignee = request.form.get("assignee", "").strip()
    due_date = request.form.get("due_date", "").strip()
    if not content:
        flash("待办内容不能为空。", "error")
        return redirect(url_for("main.meeting_detail", meeting_id=todo["meeting_id"]))
    if due_date:
        try:
            due_date = date.fromisoformat(due_date).isoformat()
        except ValueError:
            flash("截止日期格式不正确。", "error")
            return redirect(url_for("main.meeting_detail", meeting_id=todo["meeting_id"]))
    db.execute(
        "UPDATE todos SET content = ?, assignee = ?, due_date = ? WHERE id = ?",
        (content, assignee, due_date, todo_id),
    )
    flash("待办已更新。", "success")
    return redirect(url_for("main.meeting_detail", meeting_id=todo["meeting_id"]))


@main.post("/todos/<int:todo_id>/delete")
def delete_todo(todo_id: int):
    todo = db.query_one("SELECT * FROM todos WHERE id = ?", (todo_id,))
    if todo is None:
        abort(404)
    meeting_id = todo["meeting_id"]
    db.execute("DELETE FROM todos WHERE id = ?", (todo_id,))
    flash("待办已删除。", "success")
    return redirect(url_for("main.meeting_detail", meeting_id=meeting_id))


@main.get("/meetings/<int:meeting_id>/export")
def export_meeting(meeting_id: int):
    meeting = dict(_get_meeting_or_404(meeting_id))
    decisions = [row["content"] for row in _fetch_decisions(meeting_id)]
    todos = _fetch_todos(meeting_id)
    buffer = build_meeting_docx(meeting, decisions, todos)
    return send_file(
        buffer,
        as_attachment=True,
        download_name=build_filename(meeting),
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


@main.route("/ask", methods=["GET", "POST"])
def ask():
    question = ""
    answer = None
    sources: list[dict] = []
    error = None

    if request.method == "POST":
        question = request.form.get("question", "").strip()
        if not question:
            error = "请输入问题"
        else:
            meetings = _load_all_meetings_with_details()
            service = current_app.extensions["ai_service"]
            try:
                result = service.answer_question(question, meetings)
                answer = result["answer"]
                sources = result["sources"]
                db.execute(
                    "INSERT INTO qa_logs (question, answer, sources) VALUES (?, ?, ?)",
                    (question, answer, json.dumps(sources, ensure_ascii=False)),
                )
            except AIServiceError as exc:
                error = str(exc)

    history = [dict(row) for row in db.query(
        "SELECT * FROM qa_logs ORDER BY id DESC LIMIT 8"
    )]
    service = current_app.extensions["ai_service"]
    return render_template(
        "ask.html",
        question=question,
        answer=answer,
        sources=sources,
        error=error,
        history=history,
        ai_available=service.available,
    )


@main.get("/api/health")
def health():
    service = current_app.extensions["ai_service"]
    counted = db.query_one("SELECT COUNT(*) AS c FROM meetings")["c"]
    return jsonify({
        "ok": True,
        "meetings": counted,
        "ai_configured": service.available,
        "model": service.model,
    })
