"""
Local, file-backed auth. Two JSON files under data/:

  data/users.json     {user_id: {username, salt, password_hash,
                                  semester, created_at}}
  data/sessions.json   {token: {user_id, created_at, expires_at}}

No external database, no server round-trip --- this is the local
equivalent of an auth table, same spirit as tree_store.py being the
local equivalent of the nodes/links tables.

Password storage: PBKDF2-HMAC-SHA256, 260,000 iterations (OWASP's 2023
minimum recommendation for PBKDF2-SHA256), random 16-byte salt per user.
The raw password is never written to disk or logged --- only the salt
and the derived hash. This is a genuine hash+salt, not the plaintext
storage that was explicitly asked against; see the salt/hash fields
below for what actually persists.

Session persistence: a session token (not the password) is what
survives across browser reloads, carried the same way device_token
already was --- as a value in st.query_params, which Streamlit keeps
in the URL and therefore across a closed-and-reopened tab on the same
device. The token maps to a user_id via sessions.json with a 3-day
expiry (SESSION_TTL_SECONDS below); app.py checks this on every load
and only falls through to the sign-up/login gate when the token is
missing, unknown, or expired. Signing out deletes the session's file
entry, not just the client-side param, so the emptied token can't be
replayed by editing the URL back.

Concurrency note, stated plainly rather than implied: writes here use
write-to-temp-then-os.replace, which is atomic on POSIX --- a crash or
concurrent read mid-write can never leave users.json/sessions.json
truncated or corrupted, and a reader never sees a half-written file.
It does NOT serialize two concurrent signups of the exact same
username into a clean "second one fails" outcome; the check-then-write
for username uniqueness has a race window. For a local single-user or
small-class-of-users prototype (which is what this is) that's an
acceptable, explicitly-known limitation --- it would not be acceptable
as-is for a multi-server production deployment.
"""
import hashlib
import json
import os
import secrets
import time
from pathlib import Path
from typing import Optional

import streamlit as st

USERS_PATH = Path(__file__).parent / "data" / "users.json"
SESSIONS_PATH = Path(__file__).parent / "data" / "sessions.json"

PBKDF2_ITERATIONS = 260_000
SESSION_TTL_SECONDS = 3 * 24 * 60 * 60  # 3 days, per the "up to three days without logging" ask


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        # A corrupted file is treated as empty rather than crashing the
        # app --- losing accumulated users/sessions is bad, but it's
        # strictly better than the platform becoming totally unusable
        # for everyone because one file got mangled.
        return {}


def _write_json_atomic(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + f".tmp{os.getpid()}")
    tmp_path.write_text(json.dumps(data, indent=2))
    os.replace(tmp_path, path)  # atomic on POSIX


def _hash_password(password: str, salt: Optional[bytes] = None) -> tuple[str, str]:
    """Returns (salt_hex, hash_hex). Generates a new random salt when
    none is given (signup); reuses a stored salt when one is given
    (login verification)."""
    if salt is None:
        salt = secrets.token_bytes(16)
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return salt.hex(), derived.hex()


# ---------------------------------------------------------------------------
# User accounts
# ---------------------------------------------------------------------------

def username_exists(username: str) -> bool:
    users = _read_json(USERS_PATH)
    key = username.strip().lower()
    return key in users


def create_user(username: str, password: str, semester: str) -> tuple[bool, str]:
    """Returns (success, message). Fails if the username is taken (see
    module docstring's concurrency note for the one known race here) or
    inputs are empty."""
    username = username.strip()
    if not username or not password:
        return False, "Username and password are required."
    key = username.lower()

    users = _read_json(USERS_PATH)
    if key in users:
        return False, "That username is already taken."

    salt_hex, hash_hex = _hash_password(password)
    user_id = secrets.token_hex(8)
    users[key] = {
        "user_id": user_id,
        "username": username,
        "salt": salt_hex,
        "password_hash": hash_hex,
        "semester": semester,
        "created_at": time.time(),
    }
    _write_json_atomic(USERS_PATH, users)
    return True, user_id


def verify_login(username: str, password: str) -> tuple[bool, str]:
    """Returns (success, user_id_or_message)."""
    users = _read_json(USERS_PATH)
    record = users.get(username.strip().lower())
    if not record:
        return False, "No account with that username."

    salt = bytes.fromhex(record["salt"])
    _, computed_hash = _hash_password(password, salt=salt)
    # Constant-time comparison so a timing side-channel can't be used to
    # guess the stored hash one byte at a time.
    if not secrets.compare_digest(computed_hash, record["password_hash"]):
        return False, "Incorrect password."
    return True, record["user_id"]


def get_user_by_id(user_id: str) -> Optional[dict]:
    users = _read_json(USERS_PATH)
    for record in users.values():
        if record["user_id"] == user_id:
            return record
    return None


def update_user_semester(user_id: str, semester: str) -> None:
    users = _read_json(USERS_PATH)
    for record in users.values():
        if record["user_id"] == user_id:
            record["semester"] = semester
            _write_json_atomic(USERS_PATH, users)
            return


# ---------------------------------------------------------------------------
# Sessions (the "up to 3 days without logging in" mechanism)
# ---------------------------------------------------------------------------

def create_session(user_id: str) -> str:
    token = secrets.token_urlsafe(24)
    sessions = _read_json(SESSIONS_PATH)
    now = time.time()
    sessions[token] = {
        "user_id": user_id,
        "created_at": now,
        "expires_at": now + SESSION_TTL_SECONDS,
    }
    _write_json_atomic(SESSIONS_PATH, sessions)
    return token


def resolve_session(token: Optional[str]) -> Optional[str]:
    """Returns the user_id for a valid, non-expired token, or None. A
    None return means the caller should fall through to the sign-up/
    login gate --- it does not distinguish "no token", "unknown token",
    and "expired token" because app.py treats all three identically."""
    if not token:
        return None
    sessions = _read_json(SESSIONS_PATH)
    record = sessions.get(token)
    if not record:
        return None
    if time.time() > record["expires_at"]:
        return None
    return record["user_id"]


def destroy_session(token: Optional[str]) -> None:
    if not token:
        return
    sessions = _read_json(SESSIONS_PATH)
    if token in sessions:
        del sessions[token]
        _write_json_atomic(SESSIONS_PATH, sessions)


def current_user() -> Optional[dict]:
    """The single call pages need: resolves the session token in
    st.query_params to a full user record, or None if not logged in.
    Caches the lookup in session_state for the rest of this rerun so
    pages calling this more than once don't re-read both files
    repeatedly within the same request."""
    if "_resolved_user" in st.session_state:
        return st.session_state["_resolved_user"]

    token = st.query_params.get("session")
    user_id = resolve_session(token)
    user = get_user_by_id(user_id) if user_id else None
    st.session_state["_resolved_user"] = user
    return user
