"""MEDIC CARE - Python Flask backend."""

import os
import re
import secrets
import time
from datetime import timedelta
from functools import wraps

from flask import Flask, jsonify, request, send_from_directory, session
from werkzeug.security import check_password_hash, generate_password_hash

import db

BASE = os.path.dirname(os.path.abspath(__file__))
FRONTEND = os.path.abspath(os.path.join(BASE, "..", "frontend"))


def _secret_key():
    env = os.environ.get("SECRET_KEY")
    if env:
        return env
    path = os.path.join(BASE, ".secret_key")
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            f.write(secrets.token_hex(32))
    with open(path, encoding="utf-8") as f:
        return f.read().strip()


app = Flask(__name__, static_folder=FRONTEND, static_url_path="")

app.config.update(
    SECRET_KEY=_secret_key(),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=(os.environ.get("COOKIE_SECURE") == "1"),
    PERMANENT_SESSION_LIFETIME=timedelta(days=30),
    MAX_CONTENT_LENGTH=5 * 1024 * 1024,
)

PW_VERIFIED_WINDOW = 300      # seconds
LOGIN_WINDOW = 120            # seconds between verify/signup and login
DATA_KEY = re.compile(r"^[A-Za-z0-9_.\-]{1,64}$")


# ---------------- HELPERS ----------------

def normalize(raw):
    value = str(raw or "").strip()
    if "@" in value:
        return value.lower()
    value = re.sub(r"[\s\-().]", "", value)
    if re.fullmatch(r"\+63\d{10}", value):
        value = "0" + value[3:]
    elif re.fullmatch(r"63\d{10}", value):
        value = "0" + value[2:]
    return value


def is_email(value):
    return bool(re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]{2,}", value))


def is_phone(value):
    return bool(re.fullmatch(r"\+?\d{7,15}", value))


def valid_id(raw):
    value = normalize(raw)
    return is_email(value) or is_phone(value)


def name_from_id(value):
    if not is_email(value):
        return "Patient"
    words = [w for w in re.split(r"[._\-+0-9]+", value.split("@")[0]) if w]
    return " ".join(w[0].upper() + w[1:] for w in words) or "Patient"


def default_profile(value):
    email_account = is_email(value)
    return {
        "name": name_from_id(value),
        "email": value if email_account else "",
        "phone": "" if email_account else value,
        "code": "+63",
        "photo": "",
    }


def password_error(password):
    if not isinstance(password, str) or len(password) < 8:
        return "len"
    if not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        return "mix"
    return None


def body():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def profile_of(user):
    if not user:
        return {}
    return {key: user.get(key, "") for key in db.PROFILE_FIELDS}


def current():
    """Signed-in account ID from the session, or None."""
    uid = session.get("uid")
    if not uid:
        return None
    try:
        if db.get_user(uid):
            return uid
    except Exception:
        app.logger.exception("Session lookup failed")
    session.pop("uid", None)
    return None


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        uid = current()
        if not uid:
            return jsonify(ok=False, error="unauthorized"), 401
        return fn(uid, *args, **kwargs)
    return wrapper


def error(code, status):
    return jsonify(ok=False, error=code), status


def mark_pending(uid):
    """Allows /api/login for this uid shortly after a password check or signup."""
    session["pending_uid"] = uid
    session["pending_at"] = time.time()


# ---------------- FRONTEND ----------------

@app.get("/")
def index():
    return send_from_directory(FRONTEND, "index.html")


# ---------------- AUTH ----------------

@app.get("/api/me")
def get_me():
    uid = current()
    if not uid:
        return jsonify(ok=True, user=None)
    try:
        user = db.get_user(uid)
        return jsonify(
            ok=True,
            user={
                "id": uid,
                "profile": profile_of(user),
                "data": db.get_all_data(uid),
            },
        )
    except Exception:
        app.logger.exception("Error loading current user")
        return error("database_error", 500)


@app.post("/api/signup")
def signup():
    data = body()
    uid = normalize(data.get("id"))
    password = data.get("password")
    profile = data.get("profile")

    if not valid_id(uid):
        return error("invalid_id", 400)
    if password_error(password):
        return error("weak_password", 400)
    if not isinstance(profile, dict):
        return error("missing_profile", 400)

    name = str(profile.get("name") or "").strip()
    if not name or len(name) > 200:
        return error("invalid_name", 400)

    try:
        if db.get_user(uid):
            return error("exists", 409)

        patient_profile = default_profile(uid)
        patient_profile["name"] = name

        created = db.create_user(
            uid, generate_password_hash(password), patient_profile
        )
    except Exception:
        app.logger.exception("Unable to create patient account")
        return error("database_error", 500)

    if not created:
        return error("exists", 409)

    mark_pending(uid)
    return jsonify(ok=True, id=uid, profile=patient_profile), 201


@app.post("/api/verify")
def verify():
    data = body()
    uid = normalize(data.get("id"))
    password = data.get("password") or ""

    if not valid_id(uid):
        return jsonify(ok=False, reason="none")

    try:
        user = db.get_user(uid)
    except Exception:
        app.logger.exception("Unable to retrieve patient account")
        return jsonify(ok=False, reason="server_error"), 500

    if not user or not check_password_hash(user["pw_hash"], password):
        return jsonify(ok=False, reason="none")

    mark_pending(uid)
    return jsonify(ok=True, id=uid)


@app.post("/api/login")
def login():
    uid = normalize(body().get("id"))
    pending = session.get("pending_uid")
    at = session.get("pending_at", 0)

    if not uid or pending != uid or time.time() - at > LOGIN_WINDOW:
        return error("unauthorized", 401)

    session.pop("pending_uid", None)
    session.pop("pending_at", None)
    session.permanent = True
    session["uid"] = uid
    return jsonify(ok=True, id=uid)


@app.post("/api/logout")
def logout():
    session.clear()
    return jsonify(ok=True)


# ---------------- PROFILE ----------------

@app.put("/api/profile")
@login_required
def save_profile(uid):
    patch = body()
    if "name" in patch:
        name = str(patch["name"] or "").strip()
        if not name or len(name) > 200:
            return error("invalid_name", 400)
        patch["name"] = name
    try:
        db.update_profile(uid, patch)
        return jsonify(ok=True, profile=profile_of(db.get_user(uid)))
    except Exception:
        app.logger.exception("Unable to update profile")
        return error("database_error", 500)


# ---------------- PASSWORD ----------------

@app.post("/api/password/check")
@login_required
def password_check(uid):
    password = body().get("password") or ""
    try:
        user = db.get_user(uid)
    except Exception:
        app.logger.exception("Password check failed")
        return error("database_error", 500)

    if not user or not check_password_hash(user["pw_hash"], password):
        return error("bad_password", 400)

    session["pw_ok_at"] = time.time()
    return jsonify(ok=True)


@app.put("/api/password")
@login_required
def change_password(uid):
    if time.time() - session.get("pw_ok_at", 0) > PW_VERIFIED_WINDOW:
        return error("reverify", 403)

    password = body().get("password")
    if password_error(password):
        return error("weak_password", 400)

    try:
        db.set_password_hash(uid, generate_password_hash(password))
    except Exception:
        app.logger.exception("Unable to change password")
        return error("database_error", 500)

    session.pop("pw_ok_at", None)
    return jsonify(ok=True)


# ---------------- ACCOUNT ----------------

@app.delete("/api/account")
@login_required
def delete_account(uid):
    try:
        db.delete_user(uid)
    except Exception:
        app.logger.exception("Unable to delete account")
        return error("database_error", 500)
    session.clear()
    return jsonify(ok=True)


# ---------------- USER DATA ----------------

@app.put("/api/data/<key>")
@login_required
def put_data(uid, key):
    if not DATA_KEY.match(key):
        return error("invalid_key", 400)
    data = body()
    if "value" not in data:
        return error("missing_value", 400)
    try:
        db.set_data(uid, key, data["value"])
    except Exception:
        app.logger.exception("Unable to save data")
        return error("database_error", 500)
    return jsonify(ok=True)


if __name__ == "__main__":
    app.run(debug=True, port=5000)
