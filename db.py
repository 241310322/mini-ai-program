# -*- coding: utf-8 -*-
"""SQLite 数据访问层。"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import click
from flask import current_app, g

SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = sqlite3.connect(
            current_app.config["DATABASE"],
            detect_types=sqlite3.PARSE_DECLTYPES,
        )
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(_exc=None) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


def query(sql: str, params: tuple = ()) -> list[sqlite3.Row]:
    return get_db().execute(sql, params).fetchall()


def query_one(sql: str, params: tuple = ()):
    return get_db().execute(sql, params).fetchone()


def execute(sql: str, params: tuple = ()) -> sqlite3.Cursor:
    db = get_db()
    cursor = db.execute(sql, params)
    db.commit()
    return cursor


def init_db() -> None:
    db = get_db()
    with SCHEMA_PATH.open(encoding="utf-8") as f:
        db.executescript(f.read())
    db.commit()


def init_app(app) -> None:
    app.teardown_appcontext(close_db)

    @app.cli.command("init-db")
    def init_db_command() -> None:
        """初始化数据库表结构。"""
        init_db()
        click.echo("数据库已初始化。")

    # 启动时自动建表（IF NOT EXISTS，可重复执行）
    with app.app_context():
        Path(app.config["DATABASE"]).parent.mkdir(parents=True, exist_ok=True)
        init_db()
