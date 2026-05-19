# auth/user_store.py
# JSON-based user store — no external dependencies.
# users.json lives in data/ next to the project root.

import json
import hashlib
import os
import datetime


# ── Path helpers ──────────────────────────────────────────────────────────────
def _root():
    """Return the project root directory."""
    import sys
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _db_path():
    return os.path.join(_root(), "data", "users.json")


# ── Hashing ───────────────────────────────────────────────────────────────────
def _hash(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


# ── Persistence ───────────────────────────────────────────────────────────────
def _load() -> dict:
    path = _db_path()
    if not os.path.exists(path):
        db = _default_db()
        _save(db)
        return db
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _save(db: dict):
    path = _db_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=2)


def _default_db() -> dict:
    return {
        "admin": {
            "password":    _hash("admin123"),
            "role":        "admin",
            "full_name":   "System Administrator",
            "email":       "admin@solarpv.gh",
            "created_at":  "2026-01-01",
            "last_login":  None,
            "designs_run": 0,
        }
    }


# ── Public API ────────────────────────────────────────────────────────────────
def authenticate(username: str, password: str):
    """Return user dict on success, else None."""
    db = _load()
    key = username.strip().lower()
    rec = db.get(key)
    if rec and rec["password"] == _hash(password):
        return {"username": key, **rec}
    return None


def create_user(username: str, password: str, full_name: str, email: str):
    """Returns (True, msg) on success, (False, msg) on failure."""
    key = username.strip().lower()
    if len(key) < 3:
        return False, "Username must be at least 3 characters."
    if not key.replace("_", "").replace("-", "").isalnum():
        return False, "Username may only contain letters, numbers, _ and -."
    if len(password) < 6:
        return False, "Password must be at least 6 characters."

    db = _load()
    if key in db:
        return False, "Username already taken."

    db[key] = {
        "password":    _hash(password),
        "role":        "user",
        "full_name":   (full_name.strip() or key).title(),
        "email":       email.strip(),
        "created_at":  datetime.date.today().isoformat(),
        "last_login":  None,
        "designs_run": 0,
    }
    _save(db)
    return True, "Account created successfully."


def update_last_login(username: str):
    db = _load()
    if username in db:
        db[username]["last_login"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        _save(db)


def increment_designs(username: str):
    db = _load()
    if username in db:
        db[username]["designs_run"] = db[username].get("designs_run", 0) + 1
        _save(db)


def get_all_users() -> list:
    db = _load()
    return [{"username": k, **v} for k, v in db.items()]


def delete_user(username: str):
    db = _load()
    rec = db.get(username)
    if rec is None:
        return False, "User not found."
    if rec["role"] == "admin":
        return False, "Cannot delete an admin account."
    del db[username]
    _save(db)
    return True, f"User '{username}' deleted."


def change_role(username: str, new_role: str):
    db = _load()
    if username not in db:
        return False
    db[username]["role"] = new_role
    _save(db)
    return True


def update_password(username: str, new_password: str):
    if len(new_password) < 6:
        return False, "Password must be at least 6 characters."
    db = _load()
    if username not in db:
        return False, "User not found."
    db[username]["password"] = _hash(new_password)
    _save(db)
    return True, "Password updated."
