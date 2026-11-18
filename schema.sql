PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS meetings (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT    NOT NULL,
    meeting_date TEXT   NOT NULL,
    attendees   TEXT    NOT NULL DEFAULT '',
    location    TEXT    NOT NULL DEFAULT '',
    transcript  TEXT    NOT NULL DEFAULT '',
    summary     TEXT    NOT NULL DEFAULT '',
    status      TEXT    NOT NULL DEFAULT 'draft',
    created_at  TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
    updated_at  TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS decisions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    meeting_id  INTEGER NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
    content     TEXT    NOT NULL,
    position    INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS todos (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    meeting_id  INTEGER NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
    content     TEXT    NOT NULL,
    assignee    TEXT    NOT NULL DEFAULT '',
    due_date    TEXT    NOT NULL DEFAULT '',
    done        INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS qa_logs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    question    TEXT    NOT NULL,
    answer      TEXT    NOT NULL,
    sources     TEXT    NOT NULL DEFAULT '',
    created_at  TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE INDEX IF NOT EXISTS idx_meetings_date ON meetings(meeting_date DESC);
CREATE INDEX IF NOT EXISTS idx_decisions_meeting ON decisions(meeting_id);
CREATE INDEX IF NOT EXISTS idx_todos_meeting ON todos(meeting_id);
CREATE INDEX IF NOT EXISTS idx_todos_done ON todos(done, due_date);
