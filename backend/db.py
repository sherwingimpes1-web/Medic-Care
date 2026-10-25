"""MEDIC CARE - Supabase database layer."""

import json
import os

from supabase import create_client, Client


# ---------------------------------------------------------
# SUPABASE CONNECTION
# ---------------------------------------------------------

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SECRET_KEY")

if not SUPABASE_URL:
    raise RuntimeError("SUPABASE_URL environment variable is missing.")

if not SUPABASE_KEY:
    raise RuntimeError("SUPABASE_SECRET_KEY environment variable is missing.")

supabase: Client = create_client(
    SUPABASE_URL,
    SUPABASE_KEY
)


# ---------------------------------------------------------
# PROFILE FIELDS
# ---------------------------------------------------------

PROFILE_FIELDS = (
    "name",
    "email",
    "phone",
    "code",
    "photo",
)


# ---------------------------------------------------------
# DATABASE INITIALIZATION
# ---------------------------------------------------------

def init_db():
    """
    Supabase tables are created in the Supabase dashboard,
    so there is no local database initialization here.
    """
    return True


# ---------------------------------------------------------
# USERS
# ---------------------------------------------------------

def get_user(uid):
    """Get one user by ID."""

    response = (
        supabase
        .table("users")
        .select("*")
        .eq("id", uid)
        .limit(1)
        .execute()
    )

    if not response.data:
        return None

    return response.data[0]


def create_user(uid, pw_hash, profile):
    """Create a user. Returns False if the account already exists."""

    existing = get_user(uid)

    if existing:
        return False

    data = {
        "id": uid,
        "pw_hash": pw_hash,
        "name": profile.get("name", ""),
        "email": profile.get("email", ""),
        "phone": profile.get("phone", ""),
        "code": profile.get("code", "+63"),
        "photo": profile.get("photo", ""),
    }

    try:
        (
            supabase
            .table("users")
            .insert(data)
            .execute()
        )

        return True

    except Exception as e:
        print("Supabase create_user error:", e)
        return False


def update_profile(uid, patch):
    """Update the user's profile."""

    fields = {
        key: str(value)
        for key, value in patch.items()
        if key in PROFILE_FIELDS
    }

    if not fields:
        return

    try:
        (
            supabase
            .table("users")
            .update(fields)
            .eq("id", uid)
            .execute()
        )

    except Exception as e:
        print("Supabase update_profile error:", e)
        raise


def set_password_hash(uid, pw_hash):
    """Update the user's password hash."""

    try:
        (
            supabase
            .table("users")
            .update({
                "pw_hash": pw_hash
            })
            .eq("id", uid)
            .execute()
        )

    except Exception as e:
        print("Supabase set_password_hash error:", e)
        raise


def delete_user(uid):
    """Delete a user and their associated user data."""

    try:
        (
            supabase
            .table("user_data")
            .delete()
            .eq("user_id", uid)
            .execute()
        )

        (
            supabase
            .table("users")
            .delete()
            .eq("id", uid)
            .execute()
        )

    except Exception as e:
        print("Supabase delete_user error:", e)
        raise


# ---------------------------------------------------------
# USER DATA
# ---------------------------------------------------------

def get_all_data(uid):
    """Return all key/value data belonging to a user."""

    response = (
        supabase
        .table("user_data")
        .select("key,value")
        .eq("user_id", uid)
        .execute()
    )

    result = {}

    for row in response.data or []:
        value = row.get("value")

        # If value was stored as JSON text
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except (json.JSONDecodeError, TypeError):
                pass

        result[row["key"]] = value

    return result


def set_data(uid, key, value):
    """Create or update a user's data."""

    # Store JSON-compatible data.
    #
    # If the Supabase 'value' column is JSONB,
    # storing the Python object directly is preferred.

    data = {
        "user_id": uid,
        "key": key,
        "value": value,
    }

    try:
        (
            supabase
            .table("user_data")
            .upsert(
                data,
                on_conflict="user_id,key"
            )
            .execute()
        )

except Exception as e:
    print("Supabase create_user error:", repr(e))
    raise
