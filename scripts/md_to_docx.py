# -*- coding: utf-8 -*-
"""把项目 Markdown 文档转换为排版好的 Word 文档。

用法：
    python scripts/md_to_docx.py docs/05-开发过程分析与评价报告.md docs/05-开发过程分析与评价报告.docx

支持：标题、段落、粗体/行内代码/链接、无序与有序列表、管道表格、代码块、
引用、图片、水平分隔线、封面信息表与自动目录域。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

BODY_FONT = "宋体"
HEADING_FONT = "黑体"
CODE_FONT = "Consolas"
PRIMARY = RGBColor(0x4F, 0x46, 0xE5)
MUTED = RGBColor(0x66, 0x66, 0x66)
CODE_COLOR = RGBColor(0xB0, 0x30, 0x60)

HEADING_RE = re.compile(r"^(#{1,4})\s+(.*)$")
IMAGE_RE = re.compile(r"^!\[(.*?)\]\((.+?)\)\s*$")
BULLET_RE = re.compile(r"^[-*]\s+(.*)$")
NUMBER_RE = re.compile(r"^\d+\.\s+(.*)$")
QUOTE_RE = re.compile(r"^>\s?(.*)$")
INLINE_RE = re.compile(r"(\*\*.+?\*\*|`[^`]+`|\[[^\]]+\]\([^)]+\))")


def set_run_font(run, name=BODY_FONT, size=11, bold=None, italics=None, color=None):
    run.font.name = name
    rpr = run._element.get_or_add_rPr()
    rfonts = rpr.get_or_add_rFonts()
    rfonts.set(qn("w:eastAsia"), name)
    run.font.size = Pt(size)
    if bold is not None:
        run.font.bold = bold
    if italics is not None:
        run.font.italic = italics
    if color is not None:
        run.font.color.rgb = color


def add_inline(paragraph, text, size=11, base_bold=False):
    parts = INLINE_RE.split(text)
    for part in parts:
        if not part:
            continue
        if part.startswith("**") and part.endswith("**") and len(part) > 4:
            run = paragraph.add_run(part[2:-2])
            set_run_font(run, BODY_FONT, size, bold=True)
        elif part.startswith("`") and part.endswith("`") and len(part) > 2:
            run = paragraph.add_run(part[1:-1])
            set_run_font(run, CODE_FONT, size - 0.5, color=CODE_COLOR)
        elif part.startswith("[") and "](" in part and part.endswith(")"):
            match = re.match(r"\[([^\]]+)\]\(([^)]+)\)", part)
            label, url = match.group(1), match.group(2)
            run = paragraph.add_run(label)
            set_run_font(run, BODY_FONT, size, bold=base_bold, color=PRIMARY)
            if url and url not in label:
                run = paragraph.add_run(f"（{url}）")
                set_run_font(run, BODY_FONT, size - 1, color=MUTED)
        else:
            run = paragraph.add_run(part)
            set_run_font(run, BODY_FONT, size, bold=base_bold)


def shade_cell(cell, hex_color="F2F2F2"):
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_color)
    tc_pr.append(shd)


def add_table(doc, rows):
    if not rows:
        return
    columns = max(len(row) for row in rows)
    table = doc.add_table(rows=len(rows), cols=columns)
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = True
    for row_index, row in enumerate(rows):
        for col_index in range(columns):
            cell = table.rows[row_index].cells[col_index]
            text = row[col_index] if col_index < len(row) else ""
            paragraph = cell.paragraphs[0]
            paragraph.paragraph_format.space_before = Pt(1)
            paragraph.paragraph_format.space_after = Pt(1)
            add_inline(paragraph, text.replace("<br>", "\n"), size=9.5, base_bold=(row_index == 0))
            if row_index == 0:
                shade_cell(cell, "EEF2FF")
    doc.add_paragraph()


def add_code_block(doc, lines, language=""):
    paragraph = doc.add_paragraph()
    paragraph.paragraph_format.left_indent = Cm(0.5)
    paragraph.paragraph_format.space_before = Pt(4)
    paragraph.paragraph_format.space_after = Pt(8)
    paragraph.paragraph_format.line_spacing = 1.1
    p_pr = paragraph._p.get_or_add_pPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), "F7F7F9")
    p_pr.append(shd)
    text = "\n".join(lines)
    run = paragraph.add_run(text)
    set_run_font(run, CODE_FONT, 9, color=RGBColor(0x33, 0x33, 0x33))
    if language == "mermaid":
        caption = doc.add_paragraph()
        caption.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = caption.add_run("（图中关系以 Mermaid 源码表示，可用支持 Mermaid 的 Markdown 工具渲染）")
        set_run_font(run, BODY_FONT, 8.5, color=MUTED)


def add_picture(doc, path: Path, alt=""):
    if not path.exists():
        paragraph = doc.add_paragraph()
        run = paragraph.add_run(f"[图片缺失：{alt or path.name}]")
        set_run_font(run, BODY_FONT, 9, color=RGBColor(0xCC, 0x00, 0x00))
        return
    paragraph = doc.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = paragraph.add_run()
    run.add_picture(str(path), width=Cm(15.5))
    if alt:
        caption = doc.add_paragraph()
        caption.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = caption.add_run(f"图：{alt}")
        set_run_font(run, BODY_FONT, 9, color=MUTED)


def add_horizontal_rule(doc):
    paragraph = doc.add_paragraph()
    p_pr = paragraph._p.get_or_add_pPr()
    p_bdr = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), "6")
    bottom.set(qn("w:space"), "1")
    bottom.set(qn("w:color"), "DDDDDD")
    p_bdr.append(bottom)
    p_pr.append(p_bdr)


def add_field(paragraph, instruction: str, placeholder: str = ""):
    run = paragraph.add_run()
    fld_begin = OxmlElement("w:fldChar")
    fld_begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = instruction
    fld_sep = OxmlElement("w:fldChar")
    fld_sep.set(qn("w:fldCharType"), "separate")
    text = OxmlElement("w:t")
    text.text = placeholder
    fld_end = OxmlElement("w:fldChar")
    fld_end.set(qn("w:fldCharType"), "end")
    run._r.append(fld_begin)
    run._r.append(instr)
    run._r.append(fld_sep)
    run._r.append(text)
    run._r.append(fld_end)
    return run


def setup_document() -> Document:
    doc = Document()
    section = doc.sections[0]
    section.page_width = Cm(21)
    section.page_height = Cm(29.7)
    section.top_margin = Cm(2.4)
    section.bottom_margin = Cm(2.2)
    section.left_margin = Cm(2.5)
    section.right_margin = Cm(2.3)

    normal = doc.styles["Normal"]
    normal.font.name = BODY_FONT
    normal.font.size = Pt(11)
    normal.element.get_or_add_rPr().get_or_add_rFonts().set(qn("w:eastAsia"), BODY_FONT)
    normal.paragraph_format.line_spacing = 1.5

    for style_name, size in (("Heading 1", 16), ("Heading 2", 14), ("Heading 3", 12), ("Heading 4", 11)):
        style = doc.styles[style_name]
        style.font.name = HEADING_FONT
        style.font.size = Pt(size)
        style.font.bold = True
        style.font.color.rgb = RGBColor(0x1F, 0x24, 0x30)
        style.element.get_or_add_rPr().get_or_add_rFonts().set(qn("w:eastAsia"), HEADING_FONT)
        style.paragraph_format.space_before = Pt(12)
        style.paragraph_format.space_after = Pt(6)

    # 页脚页码
    footer = section.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = footer.add_run("第 ")
    set_run_font(run, BODY_FONT, 9, color=MUTED)
    run = add_field(footer, "PAGE", "1")
    set_run_font(run, BODY_FONT, 9, color=MUTED)
    run = footer.add_run(" 页")
    set_run_font(run, BODY_FONT, 9, color=MUTED)

    # 打开时自动更新目录
    settings = doc.settings.element
    update = OxmlElement("w:updateFields")
    update.set(qn("w:val"), "true")
    settings.append(update)
    return doc


def parse_metadata(lines):
    metadata = {}
    in_table = False
    for line in lines:
        if line.strip().startswith("| 项目 | 内容 |"):
            in_table = True
            continue
        if in_table:
            if not line.strip().startswith("|"):
                break
            if re.match(r"^\|[\s:|-]+\|$", line.strip()):
                continue
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            if len(cells) >= 2:
                metadata[cells[0]] = cells[1]
    return metadata


def add_cover(doc, title, metadata):
    for _ in range(4):
        doc.add_paragraph()
    paragraph = doc.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = paragraph.add_run("课程设计报告")
    set_run_font(run, HEADING_FONT, 16, bold=True, color=MUTED)

    paragraph = doc.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    paragraph.paragraph_format.space_before = Pt(18)
    run = paragraph.add_run(title)
    set_run_font(run, HEADING_FONT, 24, bold=True)

    paragraph = doc.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    paragraph.paragraph_format.space_before = Pt(10)
    run = paragraph.add_run("——以「会记 · AI 会议纪要助手」为例")
    set_run_font(run, BODY_FONT, 14, color=MUTED)

    for _ in range(3):
        doc.add_paragraph()

    info_rows = [
        ("课程名称", metadata.get("课程名称", "")),
        ("姓　　名", metadata.get("姓名", "")),
        ("学　　号", metadata.get("学号", "")),
        ("班　　级", metadata.get("班级", "")),
        ("指导教师", metadata.get("指导教师", "")),
        ("完成日期", metadata.get("完成日期", "")),
    ]
    table = doc.add_table(rows=len(info_rows), cols=2)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    for index, (label, value) in enumerate(info_rows):
        cells = table.rows[index].cells
        cells[0].width = Cm(4.0)
        cells[1].width = Cm(9.0)
        paragraph = cells[0].paragraphs[0]
        paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        run = paragraph.add_run(label + "：")
        set_run_font(run, BODY_FONT, 12)
        paragraph = cells[1].paragraphs[0]
        run = paragraph.add_run(value)
        set_run_font(run, BODY_FONT, 12)

    doc.add_paragraph()
    paragraph = doc.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = paragraph.add_run(metadata.get("项目仓库", ""))
    set_run_font(run, BODY_FONT, 10, color=MUTED)
    doc.add_page_break()


def add_toc(doc):
    paragraph = doc.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = paragraph.add_run("目　录")
    set_run_font(run, HEADING_FONT, 18, bold=True)
    paragraph = doc.add_paragraph()
    add_field(paragraph, 'TOC \\o "1-3" \\h \\z \\u', "请在 Word 中右键选择「更新域」生成目录")
    note = doc.add_paragraph()
    run = note.add_run("提示：如目录未自动生成，请全选后按 F9，或右键目录选择「更新域」。")
    set_run_font(run, BODY_FONT, 9, color=MUTED)
    doc.add_page_break()


def convert(md_path: Path, docx_path: Path):
    lines = md_path.read_text(encoding="utf-8").splitlines()
    metadata = parse_metadata(lines)
    title = next((m.group(2).strip() for line in lines if (m := HEADING_RE.match(line)) and len(m.group(1)) == 1), md_path.stem)

    doc = setup_document()
    add_cover(doc, title, metadata)
    add_toc(doc)

    index = 0
    first_h1_skipped = False
    metadata_table_skipped = False
    total = len(lines)

    while index < total:
        line = lines[index]
        stripped = line.strip()

        if not stripped:
            index += 1
            continue

        # 代码块
        if stripped.startswith("```"):
            language = stripped[3:].strip()
            code_lines = []
            index += 1
            while index < total and not lines[index].strip().startswith("```"):
                code_lines.append(lines[index])
                index += 1
            index += 1
            add_code_block(doc, code_lines, language)
            continue

        # 封面信息表（第一张表）不重复渲染
        if stripped.startswith("| 项目 | 内容 |"):
            while index < total and lines[index].strip().startswith("|"):
                index += 1
            metadata_table_skipped = True
            continue

        # 图片
        match = IMAGE_RE.match(stripped)
        if match:
            add_picture(doc, (md_path.parent / match.group(2)).resolve(), match.group(1))
            index += 1
            continue

        # 标题
        match = HEADING_RE.match(stripped)
        if match:
            level = len(match.group(1))
            text = match.group(2).strip()
            if level == 1 and not first_h1_skipped:
                first_h1_skipped = True
                index += 1
                continue
            word_level = min(max(level - 1, 1), 4)
            paragraph = doc.add_heading(level=word_level)
            run = paragraph.add_run(text)
            set_run_font(run, HEADING_FONT, {1: 16, 2: 14, 3: 12, 4: 11}[word_level], bold=True)
            index += 1
            continue

        # 水平线
        if re.fullmatch(r"-{3,}", stripped):
            add_horizontal_rule(doc)
            index += 1
            continue

        # 表格
        if stripped.startswith("|") and index + 1 < total and re.match(r"^\|[\s:|-]+\|$", lines[index + 1].strip()):
            rows = []
            header = [cell.strip() for cell in stripped.strip("|").split("|")]
            rows.append(header)
            index += 2
            while index < total and lines[index].strip().startswith("|"):
                row = [cell.strip() for cell in lines[index].strip().strip("|").split("|")]
                rows.append(row)
                index += 1
            add_table(doc, rows)
            continue

        # 引用
        match = QUOTE_RE.match(stripped)
        if match:
            paragraph = doc.add_paragraph()
            paragraph.paragraph_format.left_indent = Cm(0.8)
            paragraph.paragraph_format.space_before = Pt(4)
            paragraph.paragraph_format.space_after = Pt(4)
            add_inline(paragraph, match.group(1), size=10.5)
            for run in paragraph.runs:
                run.font.italic = True
                run.font.color.rgb = MUTED
            index += 1
            continue

        # 列表
        match = BULLET_RE.match(stripped)
        if match:
            paragraph = doc.add_paragraph(style="List Bullet")
            add_inline(paragraph, match.group(1))
            index += 1
            continue
        match = NUMBER_RE.match(stripped)
        if match:
            paragraph = doc.add_paragraph(style="List Number")
            add_inline(paragraph, match.group(1))
            index += 1
            continue

        # 普通段落（合并连续文本行）
        paragraph_lines = [stripped]
        index += 1
        while index < total:
            candidate = lines[index].strip()
            if (not candidate or candidate.startswith(("```", "|", "#", ">", "![", "---"))
                    or BULLET_RE.match(candidate) or NUMBER_RE.match(candidate)):
                break
            paragraph_lines.append(candidate)
            index += 1

        text = ""
        for part in paragraph_lines:
            if text and re.search(r"[A-Za-z0-9]$", text) and re.match(r"[A-Za-z0-9]", part):
                text += " "
            text += part
        paragraph = doc.add_paragraph()
        paragraph.paragraph_format.first_line_indent = Pt(22)
        add_inline(paragraph, text)

    doc.core_properties.title = title
    doc.core_properties.author = metadata.get("姓名") or "241310322"
    doc.core_properties.comments = "由脚本从 Markdown 生成"
    doc.save(docx_path)
    return docx_path


def main():
    if len(sys.argv) != 3:
        print("用法：python scripts/md_to_docx.py <input.md> <output.docx>")
        raise SystemExit(1)
    source = Path(sys.argv[1])
    target = Path(sys.argv[2])
    if not source.is_absolute():
        source = (Path.cwd() / source).resolve()
    if not target.is_absolute():
        target = (Path.cwd() / target).resolve()
    convert(source, target)
    print(f"已生成：{target}")


if __name__ == "__main__":
    main()
