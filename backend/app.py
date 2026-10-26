"""MEDIC CARE - Python Flask backend.

Handles:
- Patient registration and login
- Supabase-backed patient profiles
- Password verification and changes
- Session management
- Account deletion
- Patient-specific data and appointments

Run:
    pip install -r requirements.txt
    python app.py
"""

import os
import re
import secrets
import time
from datetime import timedelta
from functools import wraps

from flask import (
    Flask,
    jsonify,
    request,
    send_from_directory,
    session,
)
from werkzeug.security import (
    check_password_hash,
    generate_password_hash,
)

import db


# ---------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------

BASE = os.path.dirname(os.path.abspath(__file__))

FRONTEND = os.path.abspath(
    os.path.join(BASE, "..", "frontend")
)


def _secret_key():
    """Get the persistent Flask session secret."""

    env = os.environ.get("SECRET_KEY")

    if env:
        return env

    path = os.path.join(BASE, ".secret_key")

    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            f.write(secrets.token_hex(32))

    with open(path, encoding="utf-8") as f:
        return f.read().strip()


app = Flask(
    __name__,
    static_folder=FRONTEND,
    static_url_path=""
)

app.config.update(
    SECRET_KEY=_secret_key(),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=(
        os.environ.get("COOKIE_SECURE") == "1"
    ),
    PERMANENT_SESSION_LIFETIME=timedelta(days=30),
    MAX_CONTENT_LENGTH=5 * 1024 * 1024,
)

PW_VERIFIED_WINDOW = 300

DATA_KEY = re.compile(r"^[A-Za-z0-9_.\-]{1,64}$")


# ---------------------------------------------------------
# HELPERS
# ---------------------------------------------------------

def normalize(raw):
    """Normalize an email address or phone number."""

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
    return bool(
        re.fullmatch(
            r"[^\s@]+@[^\s@]+\.[^\s@]{2,}",
            value
        )
    )


def is_phone(value):
    return bool(
        re.fullmatch(r"\+?\d{7,15}", value)
    )


def valid_id(raw):
    value = normalize(raw)

    return is_email(value) or is_phone(value)


def name_from_id(value):
    """Generate a fallback name for existing account formats."""

    if not is_email(value):
        return "Patient"

    words = [
        word
        for word in re.split(
            r"[._\-+0-9]+",
            value.split("@")[0]
        )
        if word
    ]

    return (
        " ".join(
            word[0].upper() + word[1:]
            for word in words
        )
        or "Patient"
    )


def default_profile(value):
    """Build the default profile from the account identifier."""

    email_account = is_email(value)

    return {
        "name": name_from_id(value),
        "email": value if email_account else "",
        "phone": "" if email_account else value,
        "code": "+63",
        "photo": "",
    }


def password_error(password):
    """Return a validation error or None."""

    if not isinstance(password, str) or len(password) < 8:
        return "len"

    if (
        not re.search(r"[A-Za-z]", password)
        or not re.search(r"\d", password)
    ):
        return "mix"

    return None


def body():
    """Read a JSON request body safely."""

    data = request.get_json(silent=True)

    return data if isinstance(data, dict) else {}


def current():
    """Return the signed-in account ID if it exists in session or token."""

    # 1. Subukan muna i-tsek sa Flask Session Cookie
    uid = session.get("uid")
    if uid and db.get_user(uid):
        return uid

    # 2. Kung wala sa session, i-tsek kung may Bearer Token mula sa auth.js
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        parts = auth_header.split(" ")
        if len(parts) == 2:
            token = parts[1]
            try:
                # Tinatawag ang verify_supabase_token function sa iyong db.py
                supabase_user = db.verify_supabase_token(token)
                if supabase_user:
                    # I-return ang identifier (karaniwang email o id)
                    # Siguraduhing tugma ito sa ginagamit mong format ng 'uid'
                    user_id = supabase_user.email if hasattr(supabase_user, 'email') else supabase_user.id
                    return normalize(user_id)
            except Exception as e:
                app.logger.error(f"Supabase token validation failed: {e}")

    return None


def profile_of(user):
    """Return only public profile fields."""

    if not user:
        return {}

    return {
        key: user.get(key, "")
        for key in db.PROFILE_FIELDS
    }


def login_required(fn):
    """Require an authenticated patient session or token."""

    @wraps(fn)
    def wrapper(*args, **kwargs):
        uid = current()

        if not uid:
            # 401 Unauthorized ang magpapatigil sa loop ng auth.js mo
            return jsonify(
                ok=False,
                error="unauthorized"
            ), 401

        return fn(uid, *args, **kwargs)

    return wrapper


# ---------------------------------------------------------
# ROUTES / API ENDPOINTS
# ---------------------------------------------------------

@app.route("/api/me", methods=["GET"])
@login_required
def get_me(uid):
    """Fetch current user profile for auth.js."""
    try:
        user = db.get_user(uid)
        if not user:
            return jsonify(
                ok=False, 
                error="user_not_found"
            ), 404
            
        return jsonify(
            ok=True,
            id=uid,
            profile=profile_of(user)
        )
    except Exception:
        app.logger.exception("Error loading current user context")
        return jsonify(
            ok=False,
            error="database_error"
        ), 500


@app.post("/api/signup")
def signup():
    """Register a patient and save their actual name."""

    data = body()

    uid = normalize(data.get("id"))
    password = data.get("password")
    profile = data.get("profile")

    if not valid_id(uid):
        return jsonify(
            ok=False,
            error="invalid_id"
        ), 400

    password_issue = password_error(password)

    if password_issue:
        return jsonify(
            ok=False,
            error="weak_password"
        ), 400

    if not isinstance(profile, dict):
        return jsonify(
            ok=False,
            error="missing_profile"
        ), 400

    name = str(
        profile.get("name") or ""
    ).strip()

    if not name or len(name) > 200:
        return jsonify(
            ok=False,
            error="invalid_name"
        ), 400

    try:
        existing_user = db.get_user(uid)
    except Exception:
        app.logger.exception(
            "Unable to check existing patient account"
        )
        return jsonify(
            ok=False,
            error="database_error"
        ), 500

    if existing_user:
        return jsonify(
            ok=False,
            error="exists"
        ), 409

    patient_profile = default_profile(uid)
    patient_profile["name"] = name

    password_hash = generate_password_hash(password)

    try:
        created = db.create_user(
            uid,
            password_hash,
            patient_profile
        )
    except Exception:
        app.logger.exception(
            "Unable to create patient account"
        )
        return jsonify(
            ok=False,
            error="database_error"
        ), 500

    if not created:
        try:
            if db.get_user(uid):
                return jsonify(
                    ok=False,
                    error="exists"
                ), 409
        except Exception:
            app.logger.exception(
                "Unable to verify patient account creation"
            )
        return jsonify(
            ok=False,
            error="database_error"
        ), 500

    return jsonify(
        ok=True,
        id=uid,
        profile=patient_profile
    ), 201


@app.post("/api/verify")
def verify():
    """Verify the patient's account ID and password."""

    data = body()

    uid = normalize(data.get("id"))
    password = data.get("password") or ""

    if not valid_id(uid):
        return jsonify(
            ok=False,
            reason="none"
        )

    try:
        user = db.get_user(uid)
    except Exception:
        app.logger.exception(
            "Unable to retrieve patient account"
        )
        return jsonify(
            ok=False,
            reason="server_error"
        ), 500

    if not user:
        return jsonify(
            ok=False,
            reason="none"
        )

    if not check_password_hash(
        user["pw_hash"],
        password
    ):
        return jsonify(
            ok=False,
            reason="none"
        )
        
    # Mag-save sa session para sa local cookie tracking
    session["uid"] = uid
    return jsonify(
        ok=True,
        id=uid,
        profile=profile_of(user)
    )


# ---------------------------------------------------------
# SERVER INITIALIZATION
# ---------------------------------------------------------

if __name__ == "__main__":
    # Naka-on ang debug=True para makita ang error details sa console
    app.run(debug=True, port=5000)
