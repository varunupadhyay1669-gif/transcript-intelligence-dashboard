"""Authentication helpers — Google OAuth for tutors, passwordless for parents."""
import functools
import os
import re
from typing import Optional
from flask import session, request, jsonify, redirect, url_for
from werkzeug.security import generate_password_hash, check_password_hash
from lib.db import query, execute


# ──────────────────────────────────────────────
# GOOGLE OAUTH (TUTOR)
# ──────────────────────────────────────────────

GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")


def verify_google_token(id_token_str: str) -> Optional[dict]:
    """Verify a Google ID token and return user info dict, or None."""
    try:
        from google.oauth2 import id_token as gid_token
        from google.auth.transport import requests as google_requests
        info = gid_token.verify_oauth2_token(
            id_token_str,
            google_requests.Request(),
            GOOGLE_CLIENT_ID
        )
        # info contains: sub, email, name, picture, etc.
        return {
            "google_id": info["sub"],
            "email": info.get("email", ""),
            "name": info.get("name", ""),
        }
    except Exception as e:
        print(f"Google token verification failed: {e}")
        return None


def google_login(id_token_str: str) -> Optional[dict]:
    """Login or auto-register a tutor via Google. Returns user dict or None."""
    info = verify_google_token(id_token_str)
    if not info:
        return None

    # Check if user exists by google_id
    user = query("SELECT * FROM users WHERE google_id = ?", (info["google_id"],), one=True)
    if user:
        return user

    # Check if user exists by email (might have been created as dev fallback)
    user = query("SELECT * FROM users WHERE email = ? AND role = 'tutor'",
                 (info["email"].lower(),), one=True)
    if user:
        # Link Google ID to existing account
        execute("UPDATE users SET google_id = ? WHERE id = ?", (info["google_id"], user["id"]))
        return query("SELECT * FROM users WHERE id = ?", (user["id"],), one=True)

    # Auto-register new tutor
    uid = execute(
        "INSERT INTO users (email, google_id, role, name) VALUES (?, ?, 'tutor', ?)",
        (info["email"].lower(), info["google_id"], info["name"])
    )
    return query("SELECT * FROM users WHERE id = ?", (uid,), one=True)


# ──────────────────────────────────────────────
# DEV FALLBACK: Email+Password login for tutor
# (used when GOOGLE_CLIENT_ID is not set)
# ──────────────────────────────────────────────

def dev_register_tutor(email: str, password: str, name: str):
    """Register a tutor with email+password (dev mode only)."""
    email = email.strip().lower()
    existing = query("SELECT id FROM users WHERE email = ?", (email,), one=True)
    if existing:
        raise ValueError("Email already registered")
    if len(password) < 4:
        raise ValueError("Password must be at least 4 characters")
    pw_hash = generate_password_hash(password, method='pbkdf2:sha256')
    uid = execute(
        "INSERT INTO users (email, password_hash, role, name) VALUES (?, ?, 'tutor', ?)",
        (email, pw_hash, name)
    )
    return uid


def dev_authenticate_tutor(email: str, password: str):
    """Verify tutor credentials (dev mode). Returns user dict or None."""
    email = email.strip().lower()
    user = query("SELECT * FROM users WHERE email = ? AND role = 'tutor'", (email,), one=True)
    if user and user["password_hash"] and check_password_hash(user["password_hash"], password):
        return user
    return None


# ──────────────────────────────────────────────
# PARENT PASSWORDLESS LOGIN
# ──────────────────────────────────────────────

def _normalize_phone(phone: str) -> str:
    """Strip spaces, dashes, parentheses — keep digits and leading +."""
    phone = phone.strip()
    if not phone:
        return ""
    # Keep leading + and all digits
    cleaned = re.sub(r'[^\d+]', '', phone)
    return cleaned


def passwordless_parent_login(contact: str) -> Optional[dict]:
    """
    Login a parent by email or phone (no password needed).
    If a matching parent user exists, return it.
    If not but a student has this as parent_email or parent_phone,
    auto-create the parent user account.
    """
    contact = contact.strip()
    if not contact:
        return None

    is_email = "@" in contact
    is_phone = bool(re.search(r'\d{7,}', contact))

    if is_email:
        contact_lower = contact.lower()
        # Check existing parent user by email
        user = query("SELECT * FROM users WHERE LOWER(email) = ? AND role = 'parent'",
                      (contact_lower,), one=True)
        if user:
            return user

        # Check if any student has this parent_email
        student = query("SELECT * FROM students WHERE LOWER(parent_email) = ?",
                         (contact_lower,), one=True)
        if student:
            # Auto-create parent user
            uid = execute(
                "INSERT INTO users (email, role, name) VALUES (?, 'parent', ?)",
                (contact_lower, f"Parent of {student['name']}")
            )
            return query("SELECT * FROM users WHERE id = ?", (uid,), one=True)

    elif is_phone:
        normalized = _normalize_phone(contact)
        # Check existing parent user by phone
        user = query("SELECT * FROM users WHERE phone = ? AND role = 'parent'",
                      (normalized,), one=True)
        if user:
            return user

        # Check if any student has this parent_phone
        # We need to compare normalized versions
        all_students = query("SELECT * FROM students WHERE parent_phone IS NOT NULL AND parent_phone != ''")
        for student in all_students:
            if _normalize_phone(student["parent_phone"]) == normalized:
                uid = execute(
                    "INSERT INTO users (phone, role, name) VALUES (?, 'parent', ?)",
                    (normalized, f"Parent of {student['name']}")
                )
                return query("SELECT * FROM users WHERE id = ?", (uid,), one=True)

    return None


# ──────────────────────────────────────────────
# SESSION MANAGEMENT
# ──────────────────────────────────────────────

def login_user(user: dict):
    """Store user info in Flask session."""
    session["user_id"] = user["id"]
    session["user_email"] = user.get("email", "")
    session["user_name"] = user["name"]
    session["user_role"] = user["role"]


def logout_user():
    """Clear session."""
    session.clear()


def get_current_user():
    """Return current user dict from session, or None."""
    uid = session.get("user_id")
    if uid is None:
        return None
    return {
        "id": uid,
        "email": session.get("user_email", ""),
        "name": session.get("user_name"),
        "role": session.get("user_role"),
    }


# ──────────────────────────────────────────────
# DECORATORS
# ──────────────────────────────────────────────

def login_required(f):
    """Redirect to login page if not authenticated."""
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if get_current_user() is None:
            if request.path.startswith("/api/"):
                return jsonify({"error": "Authentication required"}), 401
            return redirect(url_for("login_page"))
        return f(*args, **kwargs)
    return decorated


def role_required(role):
    """Restrict access to a specific role."""
    def decorator(f):
        @functools.wraps(f)
        def decorated(*args, **kwargs):
            user = get_current_user()
            if user is None:
                if request.path.startswith("/api/"):
                    return jsonify({"error": "Authentication required"}), 401
                return redirect(url_for("login_page"))
            if user["role"] != role:
                if request.path.startswith("/api/"):
                    return jsonify({"error": "Access denied"}), 403
                return redirect(url_for("index"))
            return f(*args, **kwargs)
        return decorated
    return decorator
