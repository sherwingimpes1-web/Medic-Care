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

BASE = os.path.dirname(os.path.abspath(_file_))

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
    _name_,
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
    """Return the signed-in account ID if it still exists."""

    uid = session.get("uid")

    if not uid:
        return None

    if db.get_user(uid):
        return uid

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
    """Require an authenticated patient session."""

    @wraps(fn)
    def wrapper(*args, **kwargs):
        uid = current()

        if not uid:
            return jsonify(
                ok=False,
                error="unauthorized"
            ), 401

        return fn(uid, *args, **kwargs)

    return wrapper


# ---------------------------------------------------------
# SIGN UP
# ---------------------------------------------------------

@app.post("/api/signup")
def signup():
    """Register a patient and save their actual name."""

    data = body()

    uid = normalize(data.get("id"))
    password = data.get("password")
    profile = data.get("profile")

    # Validate email or phone
    if not valid_id(uid):
        return jsonify(
            ok=False,
            error="invalid_id"
        ), 400

    # Validate password
    password_issue = password_error(password)

    if password_issue:
        return jsonify(
            ok=False,
            error="weak_password"
        ), 400

    # Require the profile sent by signup.js
    if not isinstance(profile, dict):
        return jsonify(
            ok=False,
            error="missing_profile"
        ), 400

    # Get the patient's actual name
    name = str(
        profile.get("name") or ""
    ).strip()

    if not name or len(name) > 200:
        return jsonify(
            ok=False,
            error="invalid_name"
        ), 400

    # Check whether this account already exists
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

    # Build the profile using the actual name.
    # Email or phone is derived from the account identifier.
    patient_profile = default_profile(uid)
    patient_profile["name"] = name

    # Hash the password before saving it.
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
        # db.create_user() may return False for a duplicate
        # or a database insertion failure.
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


# ---------------------------------------------------------
# VERIFY LOGIN CREDENTIALS
# ---------------------------------------------------------

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
            reason="bad"
        )

    # The login endpoint must complete the sign-in.
    session["pending"] = uid

    return jsonify(
        ok=True,
        id=uid
    )


# ---------------------------------------------------------
# LOGIN
# ---------------------------------------------------------

@app.post("/api/login")
def login():
    """Create a signed-in patient session."""

    uid = normalize(body().get("id"))

    if (
        not uid
        or session.get("pending") != uid
    ):
        return jsonify(
            ok=False,
            error="verify_first"
        ), 403

    try:
        user = db.get_user(uid)

    except Exception:
        app.logger.exception(
            "Unable to retrieve account during login"
        )

        return jsonify(
            ok=False,
            error="database_error"
        ), 500

    if not user:
        session.clear()

        return jsonify(
            ok=False,
            error="account_not_found"
        ), 403

    session.clear()
    session["uid"] = uid
    session.permanent = True

    return jsonify(ok=True)


# ---------------------------------------------------------
# LOGOUT
# ---------------------------------------------------------

@app.post("/api/logout")
def logout():
    """End the current session."""

    session.clear()

    return jsonify(ok=True)


# ---------------------------------------------------------
# CURRENT PATIENT
# ---------------------------------------------------------

@app.get("/api/me")
def me():
    """Return the signed-in patient and their saved data."""

    uid = current()

    if not uid:
        return jsonify(user=None)

    try:
        user = db.get_user(uid)

        if not user:
            session.clear()
            return jsonify(user=None)

        return jsonify(
            user={
                "id": uid,
                "profile": profile_of(user),
                "data": db.get_all_data(uid),
            }
        )

    except Exception:
        app.logger.exception(
            "Unable to load current patient"
        )

        return jsonify(
            ok=False,
            error="database_error"
        ), 500


# ---------------------------------------------------------
# SAVE PATIENT PROFILE
# ---------------------------------------------------------

@app.put("/api/profile")
@login_required
def save_profile(uid):
    """Update the signed-in patient's profile."""

    patch = body()

    allowed_fields = (
        "name",
        "email",
        "phone",
        "code",
        "photo",
    )

    # Reject oversized text fields
    for key in ("name", "email", "phone", "code"):
        if key in patch and len(str(patch[key])) > 200:
            return jsonify(
                ok=False,
                error="too_long"
            ), 400

    # Only update permitted profile fields.
    safe_patch = {
        key: patch[key]
        for key in allowed_fields
        if key in patch
    }

    if "name" in safe_patch:
        name = str(safe_patch["name"]).strip()

        if not name:
            return jsonify(
                ok=False,
                error="invalid_name"
            ), 400

        safe_patch["name"] = name

    try:
        db.update_profile(uid, safe_patch)

        updated_user = db.get_user(uid)

        if not updated_user:
            return jsonify(
                ok=False,
                error="account_not_found"
            ), 404

        return jsonify(
            ok=True,
            profile=profile_of(updated_user)
        )

    except Exception:
        app.logger.exception(
            "Unable to update patient profile"
        )

        return jsonify(
            ok=False,
            error="database_error"
        ), 500


# ---------------------------------------------------------
# CHECK CURRENT PASSWORD
# ---------------------------------------------------------

@app.post("/api/password/check")
@login_required
def password_check(uid):
    """Verify the current password before changing it."""

    password = body().get("password") or ""

    try:
        user = db.get_user(uid)

        if not user:
            return jsonify(
                ok=False,
                error="account_not_found"
            ), 404

        valid = check_password_hash(
            user["pw_hash"],
            password
        )

        if valid:
            session["pw_verified_at"] = time.time()

        return jsonify(ok=valid)

    except Exception:
        app.logger.exception(
            "Unable to verify patient password"
        )

        return jsonify(
            ok=False,
            error="database_error"
        ), 500


# ---------------------------------------------------------
# CHANGE PASSWORD
# ---------------------------------------------------------

@app.put("/api/password")
@login_required
def password_set(uid):
    """Change the password after current-password verification."""

    verified_at = session.get("pw_verified_at", 0)

    if (
        not isinstance(verified_at, (int, float))
        or time.time() - verified_at > PW_VERIFIED_WINDOW
    ):
        return jsonify(
            ok=False,
            error="verify_current_password"
        ), 403

    password = body().get("password")

    if password_error(password):
        return jsonify(
            ok=False,
            error="weak_password"
        ), 400

    try:
        db.set_password_hash(
            uid,
            generate_password_hash(password)
        )

        session.pop("pw_verified_at", None)

        return jsonify(ok=True)

    except Exception:
        app.logger.exception(
            "Unable to change patient password"
        )

        return jsonify(
            ok=False,
            error="database_error"
        ), 500


# ---------------------------------------------------------
# DELETE ACCOUNT
# ---------------------------------------------------------

@app.delete("/api/account")
@login_required
def delete_account(uid):
    """Delete the patient's account and associated data."""

    try:
        db.delete_user(uid)
        session.clear()

        return jsonify(ok=True)

    except Exception:
        app.logger.exception(
            "Unable to delete patient account"
        )

        return jsonify(
            ok=False,
            error="database_error"
        ), 500


# ---------------------------------------------------------
# PATIENT-SPECIFIC DATA
# ---------------------------------------------------------

@app.put("/api/data/<key>")
@login_required
def set_data(uid, key):
    """Save patient-specific data, including appointments."""

    if not DATA_KEY.fullmatch(key):
        return jsonify(
            ok=False,
            error="bad_key"
        ), 400

    data = body()

    if "value" not in data:
        return jsonify(
            ok=False,
            error="missing_value"
        ), 400

    try:
        db.set_data(
            uid,
            key,
            data["value"]
        )

        return jsonify(ok=True)

    except Exception:
        app.logger.exception(
            "Unable to save patient data"
        )

        return jsonify(
            ok=False,
            error="database_error"
        ), 500


# ---------------------------------------------------------
# WEBSITE
# ---------------------------------------------------------

@app.get("/")
def root():
    """Serve the login page."""

    return send_from_directory(
        FRONTEND,
        "index.html"
    )


# ---------------------------------------------------------
# STARTUP
# ---------------------------------------------------------

db.init_db()


if _name_ == "_main_":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        debug=os.environ.get("DEBUG") == "1"
    )
