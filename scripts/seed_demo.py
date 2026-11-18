# -*- coding: utf-8 -*-
"""写入一条演示会议数据，便于不调用 AI 也能查看界面与导出效果。

用法：
    python scripts/seed_demo.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import db  # noqa: E402
from app import create_app  # noqa: E402

DEMO_TITLE = "智慧工地平台二期需求评审会"
DEMO_TRANSCRIPT = """主持人（王强）：今天召开智慧工地平台二期需求评审会，主要确认二期范围、里程碑和风险。
产品（李敏）：二期范围包括劳务实名制、安全巡检、塔吊监控三个模块。劳务实名制需要对接省平台；安全巡检支持移动端拍照；塔吊监控本期只做数据接入。
项目经理（赵磊）：工期方面，开发 6 周，联调 2 周，计划 12 月 28 日上线。
王强：同意。李敏下周三前输出详细需求文档；赵磊本周五前给出排期和资源计划。
测试（周婷）：需要提前准备测试环境，建议 12 月 5 日开始系统测试。
赵磊：可以，测试环境由运维张伟负责，12 月 3 日前准备好。
王强：风险方面，省平台接口文档还没拿到，可能影响对接。
李敏：我本周内联系省平台，拿到接口文档后同步给开发。
王强：另外，本周五下午开一次进度同步会。没有其他问题，散会。"""

DEMO_SUMMARY = (
    "会议评审智慧工地平台二期需求，确认二期范围为劳务实名制、安全巡检、塔吊监控三个模块，"
    "其中塔吊监控本期只做数据接入。会议确认开发 6 周、联调 2 周，12 月 28 日上线，"
    "并同意 12 月 5 日开始系统测试。主要风险是省平台接口文档尚未取得，可能影响对接。"
)
DEMO_DECISIONS = [
    "二期范围确定为劳务实名制、安全巡检、塔吊监控三个模块；劳务实名制需对接省平台，"
    "安全巡检支持移动端拍照，塔吊监控本期只做数据接入",
    "工期为开发 6 周、联调 2 周，计划 2026 年 12 月 28 日上线",
    "同意 2026 年 12 月 5 日开始系统测试",
]
DEMO_TODOS = [
    ("输出二期详细需求文档", "李敏", "2026-11-25"),
    ("给出二期排期和资源计划", "赵磊", "2026-11-20"),
    ("准备好系统测试环境", "张伟", "2026-12-03"),
    ("联系省平台获取接口文档，并同步给开发", "李敏", "2026-11-20"),
    ("组织召开进度同步会", "王强", "2026-11-20"),
]


def main() -> None:
    app = create_app()
    with app.app_context():
        existing = db.query_one("SELECT id FROM meetings WHERE title = ?", (DEMO_TITLE,))
        if existing:
            print(f"演示数据已存在，会议 ID：{existing['id']}")
            return

        cursor = db.execute(
            """INSERT INTO meetings
               (title, meeting_date, attendees, location, transcript, summary, status)
               VALUES (?, ?, ?, ?, ?, ?, 'processed')""",
            (
                DEMO_TITLE,
                "2026-11-18",
                "王强、李敏、赵磊、周婷、张伟",
                "总部 3 楼会议室",
                DEMO_TRANSCRIPT,
                DEMO_SUMMARY,
            ),
        )
        meeting_id = cursor.lastrowid
        for position, content in enumerate(DEMO_DECISIONS):
            db.execute(
                "INSERT INTO decisions (meeting_id, content, position) VALUES (?, ?, ?)",
                (meeting_id, content, position),
            )
        for content, assignee, due_date in DEMO_TODOS:
            db.execute(
                "INSERT INTO todos (meeting_id, content, assignee, due_date) VALUES (?, ?, ?, ?)",
                (meeting_id, content, assignee, due_date),
            )
        print(f"演示数据已写入，会议 ID：{meeting_id}")


if __name__ == "__main__":
    main()
