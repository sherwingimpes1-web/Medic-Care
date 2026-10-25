"""MEDIC CARE - database layer.

Currently SQLite (temporary). Lahat ng database access ay nandito lang, kaya kapag
dumating na yung actual database, ito lang ang papalitan - hindi na ang app.py.

Same structure ito ng dating localStorage:
    users      -> id, password hash, profile (name/email/phone/code/photo)
    user_data  -> per-account key/value (appointments, profileExtra, ...)
"""
import json
import os
import sqlite3

DB_PATH = os.environ.get(
    "DATABASE_PATH",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "medic_care.db"),
)

PROFILE_FIELDS = ("name", "email", "phone", "code", "photo")


def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    with _conn() as c:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id         TEXT PRIMARY KEY,          -- normalized email or phone
                pw_hash    TEXT NOT NULL,
                name       TEXT NOT NULL DEFAULT '',
                email      TEXT NOT NULL DEFAULT '',
                phone      TEXT NOT NULL DEFAULT '',
                code       TEXT NOT NULL DEFAULT '+63',
                photo      TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS user_data (
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                key     TEXT NOT NULL,
                value   TEXT NOT NULL,                -- JSON
                PRIMARY KEY (user_id, key)
            );
            """
        )


def get_user(uid):
    with _conn() as c:
        row = c.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
    return dict(row) if row else None


def create_user(uid, pw_hash, profile):
    """Returns False if the account already exists."""
    try:
        with _conn() as c:
            c.execute(
                "INSERT INTO users (id, pw_hash, name, email, phone, code, photo) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (uid, pw_hash, profile["name"], profile["email"], profile["phone"],
                 profile["code"], profile["photo"]),
            )
        return True
    except sqlite3.IntegrityError:
        return False


def update_profile(uid, patch):
    fields = {k: str(v) for k, v in patch.items() if k in PROFILE_FIELDS}
    if not fields:
        return
    sets = ", ".join(f"{k} = ?" for k in fields)
    with _conn() as c:
        c.execute(f"UPDATE users SET {sets} WHERE id = ?", (*fields.values(), uid))


def set_password_hash(uid, pw_hash):
    with _conn() as c:
        c.execute("UPDATE users SET pw_hash = ? WHERE id = ?", (pw_hash, uid))


def delete_user(uid):
    with _conn() as c:
        c.execute("DELETE FROM users WHERE id = ?", (uid,))   # user_data goes with it (CASCADE)


def get_all_data(uid):
    with _conn() as c:
        rows = c.execute("SELECT key, value FROM user_data WHERE user_id = ?", (uid,)).fetchall()
    return {r["key"]: json.loads(r["value"]) for r in rows}


def set_data(uid, key, value):
    with _conn() as c:
        c.execute(
            "INSERT INTO user_data (user_id, key, value) VALUES (?, ?, ?) "
            "ON CONFLICT(user_id, key) DO UPDATE SET value = excluded.value",
            (uid, key, json.dumps(value)),
        )
