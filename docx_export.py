# -*- coding: utf-8 -*-
"""把会议纪要导出为 Word 文档（python-docx）。"""
from __future__ import annotations

import re
from datetime import datetime
from io import BytesIO

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

BODY_FONT = "宋体"
TITLE_FONT = "黑体"


def _set_run_font(run, name: str = BODY_FONT, size: int | None = None,
                  bold: bool | None = None, color: RGBColor | None = None) -> None:
    run.font.name = name
    rpr = run._element.get_or_add_rPr()
    rfonts = rpr.get_or_add_rFonts()
    rfonts.set(qn("w:eastAsia"), name)
    if size is not None:
        run.font.size = Pt(size)
    if bold is not None:
        run.font.bold = bold
    if color is not None:
        run.font.color.rgb = color


def _set_style_font(style, name: str, size: int) -> None:
    style.font.name = name
    style.font.size = Pt(size)
    rpr = style.element.get_or_add_rPr()
    rfonts = rpr.get_or_add_rFonts()
    rfonts.set(qn("w:eastAsia"), name)


def _add_heading(doc: Document, text: str) -> None:
    paragraph = doc.add_paragraph()
    paragraph.paragraph_format.space_before = Pt(12)
    paragraph.paragraph_format.space_after = Pt(6)
    run = paragraph.add_run(text)
    _set_run_font(run, TITLE_FONT, size=14, bold=True)


def _add_body(doc: Document, text: str, *, size: int = 11, indent: bool = True) -> None:
    paragraph = doc.add_paragraph()
    paragraph.paragraph_format.line_spacing = 1.4
    if indent:
        paragraph.paragraph_format.first_line_indent = Pt(22)
    run = paragraph.add_run(text)
    _set_run_font(run, BODY_FONT, size=size)


def _add_numbered(doc: Document, items: list[str]) -> None:
    for index, item in enumerate(items, start=1):
        paragraph = doc.add_paragraph()
        paragraph.paragraph_format.line_spacing = 1.4
        paragraph.paragraph_format.left_indent = Cm(0.75)
        paragraph.paragraph_format.first_line_indent = Cm(-0.75)
        run = paragraph.add_run(f"{index}. {item}")
        _set_run_font(run, BODY_FONT, size=11)


def build_meeting_docx(meeting: dict, decisions: list[str], todos: list[dict]) -> BytesIO:
    """生成 Word 文档并返回内存文件对象。"""
    doc = Document()
    _set_style_font(doc.styles["Normal"], BODY_FONT, 11)

    section = doc.sections[0]
    section.top_margin = Cm(2.2)
    section.bottom_margin = Cm(2.2)
    section.left_margin = Cm(2.5)
    section.right_margin = Cm(2.5)

    # 标题
    title_paragraph = doc.add_paragraph()
    title_paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title_run = title_paragraph.add_run("会议纪要")
    _set_run_font(title_run, TITLE_FONT, size=22, bold=True)

    subtitle_paragraph = doc.add_paragraph()
    subtitle_paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    subtitle_run = subtitle_paragraph.add_run(meeting.get("title", ""))
    _set_run_font(subtitle_run, BODY_FONT, size=12, color=RGBColor(0x55, 0x55, 0x55))

    # 元信息表
    meta_rows = [
        ("会议主题", meeting.get("title", "")),
        ("会议日期", meeting.get("meeting_date", "")),
        ("参会人员", meeting.get("attendees") or "—"),
        ("会议地点", meeting.get("location") or "—"),
    ]
    table = doc.add_table(rows=len(meta_rows), cols=2)
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    for row_index, (label, value) in enumerate(meta_rows):
        cells = table.rows[row_index].cells
        cells[0].width = Cm(3.0)
        cells[1].width = Cm(12.5)
        label_run = cells[0].paragraphs[0].add_run(label)
        _set_run_font(label_run, BODY_FONT, size=10, bold=True)
        value_run = cells[1].paragraphs[0].add_run(str(value))
        _set_run_font(value_run, BODY_FONT, size=10)

    # 摘要
    _add_heading(doc, "一、会议摘要")
    summary = meeting.get("summary") or ""
    if summary:
        _add_body(doc, summary)
    else:
        _add_body(doc, "（尚未生成摘要）", indent=True)

    # 决议
    _add_heading(doc, "二、会议决议")
    if decisions:
        _add_numbered(doc, decisions)
    else:
        _add_body(doc, "本次会议无明确决议。", indent=True)

    # 待办
    _add_heading(doc, "三、待办事项")
    if todos:
        todo_table = doc.add_table(rows=1, cols=5)
        todo_table.style = "Table Grid"
        todo_table.alignment = WD_TABLE_ALIGNMENT.CENTER
        headers = ["序号", "事项", "负责人", "截止日期", "状态"]
        widths = [Cm(1.2), Cm(7.5), Cm(2.2), Cm(2.6), Cm(1.6)]
        for col_index, (header, width) in enumerate(zip(headers, widths)):
            cell = todo_table.rows[0].cells[col_index]
            cell.width = width
            run = cell.paragraphs[0].add_run(header)
            _set_run_font(run, BODY_FONT, size=10, bold=True)
        for index, todo in enumerate(todos, start=1):
            row = todo_table.add_row().cells
            values = [
                str(index),
                todo.get("content", ""),
                todo.get("assignee") or "—",
                todo.get("due_date") or "—",
                "已完成" if todo.get("done") else "未完成",
            ]
            for col_index, (value, width) in enumerate(zip(values, widths)):
                row[col_index].width = width
                run = row[col_index].paragraphs[0].add_run(value)
                _set_run_font(run, BODY_FONT, size=10)
    else:
        _add_body(doc, "本次会议未提取出待办事项。", indent=True)

    # 原文附录
    transcript = (meeting.get("transcript") or "").strip()
    if transcript:
        _add_heading(doc, "四、会议记录原文")
        _add_body(doc, transcript, size=9)

    # 结尾说明
    footer_paragraph = doc.add_paragraph()
    footer_paragraph.paragraph_format.space_before = Pt(18)
    footer_run = footer_paragraph.add_run(
        f"本纪要由 AI 会议纪要助手辅助生成（{datetime.now():%Y-%m-%d %H:%M}），请人工核对后使用。"
    )
    _set_run_font(footer_run, BODY_FONT, size=9, color=RGBColor(0x88, 0x88, 0x88))

    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer


def build_filename(meeting: dict) -> str:
    title = (meeting.get("title") or "未命名会议").strip()
    title = re.sub(r'[\\/:*?"<>|\r\n\t]', "_", title)[:40] or "未命名会议"
    meeting_date = meeting.get("meeting_date") or datetime.now().strftime("%Y-%m-%d")
    return f"{meeting_date}_会议纪要_{title}.docx"
