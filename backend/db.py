"""MEDIC CARE - Supabase database layer."""

import json
import os

from supabase import create_client, Client

# ---------------------------------------------------------
# CONNECTION SETTINGS
# ---------------------------------------------------------
# Set these in Render -> your service -> Environment:
#   SUPABASE_URL                = https://xxxx.supabase.co
#   SUPABASE_SERVICE_ROLE_KEY   = your secret / service key
#
# Do NOT paste the keys into this file. This file goes to GitHub.

SUPABASE_URL = os.environ.get("https://reilluhyetzmxgczratk.supabase.co", "").strip()
SUPABASE_KEY = (
    os.environ.get("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InJlaWxsdWh5ZXR6bXhnY3pyYXRrIiwicm9sZSI6ImFub24iLCJpYXQiOjE3OTI1MDA4MDIsImV4cCI6MjEwODA3NjgwMn0._xMkzw7PsnxnlntShpfGBztrQ0TqtmD-OVVpYINdPSI")
    or os.environ.get("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InJlaWxsdWh5ZXR6bXhnY3pyYXRrIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc5MjUwMDgwMiwiZXhwIjoyMTA4MDc2ODAyfQ.bB6NdPz_i2DVSooDoYfT0IrHqPmRL0xcuRiWIPx6Q8c")
    or ""
).strip()

if not SUPABASE_URL:
    raise RuntimeError("SUPABASE_URL is not set in the environment.")
if not SUPABASE_KEY:
    raise RuntimeError("SUPABASE_SERVICE_ROLE_KEY is not set in the environment.")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Table names. Change these if your tables are named differently.
USERS_TABLE = os.environ.get("USERS_TABLE", "mc_users")
DATA_TABLE = os.environ.get("DATA_TABLE", "mc_user_data")

PROFILE_FIELDS = ("name", "email", "phone", "code", "photo")


def init_db():
    return True


# ---------------- USERS ----------------

def get_user(uid):
    res = (
        supabase.table(USERS_TABLE)
        .select("*")
        .eq("id", uid)
        .limit(1)
        .execute()
    )
    return res.data[0] if res.data else None


def create_user(uid, pw_hash, profile):
    """Returns False if the user already exists. Other errors propagate."""
    if get_user(uid):
        return False

    supabase.table(USERS_TABLE).insert({
        "id": uid,
        "pw_hash": pw_hash,
        "name": profile.get("name", ""),
        "email": profile.get("email", ""),
        "phone": profile.get("phone", ""),
        "code": profile.get("code", "+63"),
        "photo": profile.get("photo", ""),
    }).execute()
    return True


def update_profile(uid, patch):
    fields = {k: str(v) for k, v in patch.items() if k in PROFILE_FIELDS}
    if fields:
        supabase.table(USERS_TABLE).update(fields).eq("id", uid).execute()


def set_password_hash(uid, pw_hash):
    supabase.table(USERS_TABLE).update({"pw_hash": pw_hash}).eq("id", uid).execute()


def delete_user(uid):
    supabase.table(DATA_TABLE).delete().eq("user_id", uid).execute()
    supabase.table(USERS_TABLE).delete().eq("id", uid).execute()


# ---------------- USER DATA ----------------

def get_all_data(uid):
    res = (
        supabase.table(DATA_TABLE)
        .select("key,value")
        .eq("user_id", uid)
        .execute()
    )
    out = {}
    for row in res.data or []:
        value = row.get("value")
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except (json.JSONDecodeError, TypeError):
                pass
        out[row["key"]] = value
    return out


def set_data(uid, key, value):
    supabase.table(DATA_TABLE).upsert(
        {"user_id": uid, "key": key, "value": value},
        on_conflict="user_id,key",
    ).execute()
