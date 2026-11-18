# -*- coding: utf-8 -*-
"""AI 会议纪要助手 —— 应用入口。

开发运行：
    python app.py
或：
    flask --app app run --debug
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

from flask import Flask, render_template

import db
from ai_service import AIService
from config import Config
from routes import main


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)

    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    Path(app.config["DATABASE"]).parent.mkdir(parents=True, exist_ok=True)

    db.init_app(app)
    app.extensions["ai_service"] = AIService(app.config)
    app.register_blueprint(main)

    @app.context_processor
    def inject_globals():
        return {"today": date.today().isoformat()}

    @app.errorhandler(404)
    def not_found(_error):
        return render_template("404.html"), 404

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
