"""
Transcript Intelligence Dashboard — Main Flask Application
"""
import json
import os
import sys
from datetime import date, datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(__file__))

from flask import Flask, request, jsonify, render_template, redirect, url_for, session
from lib.db import query, execute, get_db
from lib.engine.mastery import update_mastery, update_confidence
from lib.engine.mental_blocks import compute_severity
from lib.auth import (
    google_login, passwordless_parent_login,
    dev_register_tutor, dev_authenticate_tutor,
    login_user, logout_user, get_current_user, login_required,
    GOOGLE_CLIENT_ID
)

app = Flask(__name__, static_folder="static", template_folder="templates")
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")

# ──────────────────────────────────────────────
# PROCESSOR INIT: Gemini AI with rule-based fallback
# ──────────────────────────────────────────────

def get_processor():
    """Initialize the best available transcript processor."""
    try:
        from lib.engine.gemini_processor import GeminiProcessor
        gp = GeminiProcessor()
        if gp.is_available:
            print("✅ Using Gemini AI for transcript processing")
            return gp
    except Exception as e:
        print(f"⚠️ Gemini unavailable: {e}")

    from lib.engine.rule_based import RuleBasedProcessor
    print("📝 Using rule-based transcript processing (set GEMINI_API_KEY for AI)")
    return RuleBasedProcessor()

processor = get_processor()

# Import RuleBasedProcessor for fallback use
from lib.engine.rule_based import RuleBasedProcessor
fallback_processor = RuleBasedProcessor()


# ──────────────────────────────────────────────
# AUTH PAGES & API
# ──────────────────────────────────────────────

@app.route("/login")
def login_page():
    if get_current_user():
        return redirect(url_for("index"))
    return render_template("login.html", google_client_id=GOOGLE_CLIENT_ID)


@app.route("/api/login/google", methods=["POST"])
def api_login_google():
    """Tutor sign-in via Google ID token."""
    data = request.json
    id_token = data.get("id_token", "")
    if not id_token:
        return jsonify({"error": "Missing ID token"}), 400

    user = google_login(id_token)
    if user:
        login_user(user)
        return jsonify({"ok": True, "role": user["role"], "name": user["name"]})
    return jsonify({"error": "Google sign-in failed. Please try again."}), 401


@app.route("/api/login/parent", methods=["POST"])
def api_login_parent():
    """Parent passwordless login by email or phone."""
    data = request.json
    contact = data.get("contact", "").strip()
    if not contact:
        return jsonify({"error": "Please enter your email or phone number"}), 400

    user = passwordless_parent_login(contact)
    if user:
        login_user(user)
        return jsonify({"ok": True, "role": user["role"], "name": user["name"]})
    return jsonify({
        "error": "No matching student found. Please check with your child's tutor that they have your correct email or phone number on file."
    }), 404


# Dev fallback: email+password login (when GOOGLE_CLIENT_ID is not set)
@app.route("/api/login", methods=["POST"])
def api_login_dev():
    """Dev-mode tutor login with email+password."""
    data = request.json
    user = dev_authenticate_tutor(data.get("email", ""), data.get("password", ""))
    if user:
        login_user(user)
        return jsonify({"ok": True, "role": user["role"], "name": user["name"]})
    return jsonify({"error": "Invalid email or password"}), 401


@app.route("/api/register", methods=["POST"])
def api_register_dev():
    """Dev-mode tutor registration."""
    data = request.json
    try:
        uid = dev_register_tutor(
            email=data.get("email", ""),
            password=data.get("password", ""),
            name=data.get("name", ""),
        )
        user = query("SELECT * FROM users WHERE id = ?", (uid,), one=True)
        login_user(user)
        return jsonify({"ok": True, "id": uid}), 201
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/logout", methods=["POST"])
def api_logout():
    logout_user()
    return jsonify({"ok": True})


@app.route("/logout")
def logout_redirect():
    logout_user()
    return redirect(url_for("login_page"))


# ──────────────────────────────────────────────
# PAGES
# ──────────────────────────────────────────────

@app.route("/")
@login_required
def index():
    """Landing page — student list."""
    user = get_current_user()
    return render_template("index.html", user=user)


@app.route("/student/<int:student_id>")
@login_required
def student_dashboard(student_id):
    """Student dashboard page."""
    user = get_current_user()
    # Verify access
    student = query("SELECT * FROM students WHERE id = ?", (student_id,), one=True)
    if not student:
        return redirect(url_for("index"))
    if user["role"] == "tutor" and student.get("tutor_id") and student["tutor_id"] != user["id"]:
        return redirect(url_for("index"))
    if user["role"] == "parent" and student.get("parent_email", "").lower() != user["email"].lower():
        return redirect(url_for("index"))
    return render_template("dashboard.html", student_id=student_id, user=user)


@app.route("/session/<int:session_id>/report")
@login_required
def session_report(session_id):
    """Printable session report page."""
    user = get_current_user()
    sess = query("SELECT * FROM sessions WHERE id = ?", (session_id,), one=True)
    if not sess:
        return "Session not found", 404

    student = query("SELECT * FROM students WHERE id = ?", (sess["student_id"],), one=True)

    # Parse JSON fields
    topics = []
    strengths = []
    misconceptions = []
    if sess["detected_topics"]:
        try:
            raw = json.loads(sess["detected_topics"])
            topics = [t if isinstance(t, str) else t.get("name", str(t)) for t in raw]
        except:
            topics = []
    if sess["detected_strengths"]:
        try:
            strengths = json.loads(sess["detected_strengths"])
        except:
            strengths = []
    if sess["detected_misconceptions"]:
        try:
            misconceptions = json.loads(sess["detected_misconceptions"])
        except:
            misconceptions = []

    return render_template("report.html",
        session=sess,
        student=student,
        topics=topics,
        topics_count=len(topics),
        strengths=strengths,
        strengths_count=len(strengths),
        misconceptions=misconceptions,
        misconceptions_count=len(misconceptions),
        generated_at=datetime.now().strftime("%B %d, %Y at %I:%M %p"),
    )


# ──────────────────────────────────────────────
# API: STUDENTS
# ──────────────────────────────────────────────

@app.route("/api/students", methods=["GET"])
@login_required
def list_students():
    user = get_current_user()
    if user["role"] == "tutor":
        students = query(
            "SELECT * FROM students WHERE tutor_id = ? OR tutor_id IS NULL ORDER BY name",
            (user["id"],)
        )
    else:
        # Parent — see students linked to their email or phone
        user_email = user.get("email", "")
        user_phone = session.get("user_phone", "")
        # Fetch parent user to get phone
        parent_user = query("SELECT * FROM users WHERE id = ?", (user["id"],), one=True)
        if parent_user:
            user_phone = parent_user.get("phone", "") or ""
            user_email = parent_user.get("email", "") or ""

        students = []
        if user_email:
            students += query(
                "SELECT * FROM students WHERE LOWER(parent_email) = LOWER(?)",
                (user_email,)
            )
        if user_phone:
            # Also check by phone (normalized)
            from lib.auth import _normalize_phone
            all_with_phone = query(
                "SELECT * FROM students WHERE parent_phone IS NOT NULL AND parent_phone != ''"
            )
            seen_ids = {s["id"] for s in students}
            for s in all_with_phone:
                if s["id"] not in seen_ids and _normalize_phone(s["parent_phone"]) == _normalize_phone(user_phone):
                    students.append(s)
    return jsonify(students)


@app.route("/api/students", methods=["POST"])
@login_required
def create_student():
    user = get_current_user()
    if user["role"] != "tutor":
        return jsonify({"error": "Only tutors can add students"}), 403
    data = request.json
    sid = execute(
        "INSERT INTO students (name, grade, curriculum, target_exam, long_term_goal_summary, tutor_id, parent_email, parent_phone) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (data["name"], data["grade"], data.get("curriculum", ""),
         data.get("target_exam", ""), data.get("long_term_goal_summary", ""),
         user["id"], data.get("parent_email", ""), data.get("parent_phone", ""))
    )
    return jsonify({"id": sid}), 201


@app.route("/api/students/<int:sid>", methods=["GET"])
@login_required
def get_student(sid):
    student = query("SELECT * FROM students WHERE id = ?", (sid,), one=True)
    if not student:
        return jsonify({"error": "Student not found"}), 404
    return jsonify(student)


@app.route("/api/students/<int:sid>", methods=["PUT"])
@login_required
def update_student(sid):
    data = request.json
    execute(
        "UPDATE students SET name=?, grade=?, curriculum=?, target_exam=?, long_term_goal_summary=? WHERE id=?",
        (data["name"], data["grade"], data.get("curriculum", ""),
         data.get("target_exam", ""), data.get("long_term_goal_summary", ""), sid)
    )
    return jsonify({"ok": True})


# ──────────────────────────────────────────────
# API: GOALS
# ──────────────────────────────────────────────

@app.route("/api/students/<int:sid>/goals", methods=["GET"])
@login_required
def list_goals(sid):
    goals = query("SELECT * FROM goals WHERE student_id = ? ORDER BY created_at", (sid,))
    return jsonify(goals)


@app.route("/api/students/<int:sid>/goals", methods=["POST"])
@login_required
def create_goal(sid):
    data = request.json
    gid = execute(
        "INSERT INTO goals (student_id, description, measurable_outcome, deadline, status) "
        "VALUES (?, ?, ?, ?, ?)",
        (sid, data["description"], data.get("measurable_outcome", ""),
         data.get("deadline"), data.get("status", "not started"))
    )
    return jsonify({"id": gid}), 201


@app.route("/api/goals/<int:gid>", methods=["PUT"])
@login_required
def update_goal(gid):
    data = request.json
    execute(
        "UPDATE goals SET description=?, measurable_outcome=?, deadline=?, status=? WHERE id=?",
        (data["description"], data.get("measurable_outcome", ""),
         data.get("deadline"), data.get("status", "not started"), gid)
    )
    return jsonify({"ok": True})


# ──────────────────────────────────────────────
# API: TOPICS
# ──────────────────────────────────────────────

@app.route("/api/students/<int:sid>/topics", methods=["GET"])
@login_required
def list_topics(sid):
    topics = query("SELECT * FROM topics WHERE student_id = ? ORDER BY topic_name", (sid,))
    return jsonify(topics)


# ──────────────────────────────────────────────
# API: SESSIONS
# ──────────────────────────────────────────────

@app.route("/api/students/<int:sid>/sessions", methods=["GET"])
@login_required
def list_sessions(sid):
    sessions = query(
        "SELECT id, student_id, session_type, session_date, extracted_summary, "
        "detected_topics, detected_misconceptions, detected_strengths, "
        "engagement_score, parent_summary, tutor_insight, recommended_next "
        "FROM sessions WHERE student_id = ? ORDER BY session_date DESC", (sid,)
    )
    return jsonify(sessions)


# ──────────────────────────────────────────────
# API: MENTAL BLOCKS
# ──────────────────────────────────────────────

@app.route("/api/students/<int:sid>/mental-blocks", methods=["GET"])
@login_required
def list_mental_blocks(sid):
    blocks = query(
        "SELECT * FROM mental_blocks WHERE student_id = ? ORDER BY severity_score DESC", (sid,)
    )
    return jsonify(blocks)


# ──────────────────────────────────────────────
# API: DASHBOARD AGGREGATE
# ──────────────────────────────────────────────

@app.route("/api/students/<int:sid>/dashboard", methods=["GET"])
@login_required
def dashboard_data(sid):
    student = query("SELECT * FROM students WHERE id = ?", (sid,), one=True)
    if not student:
        return jsonify({"error": "Student not found"}), 404

    goals = query("SELECT * FROM goals WHERE student_id = ? ORDER BY created_at", (sid,))
    topics = query("SELECT * FROM topics WHERE student_id = ? ORDER BY topic_name", (sid,))
    sessions = query(
        "SELECT id, session_type, session_date, extracted_summary, detected_topics, "
        "engagement_score, parent_summary, tutor_insight, recommended_next "
        "FROM sessions WHERE student_id = ? ORDER BY session_date DESC LIMIT 20", (sid,)
    )
    mental_blocks = query(
        "SELECT * FROM mental_blocks WHERE student_id = ? AND resolved = 0 "
        "ORDER BY severity_score DESC", (sid,)
    )

    # Compute confidence trend from sessions
    confidence_trend = []
    for s in reversed(sessions):
        confidence_trend.append({
            "date": s["session_date"],
            "engagement": s["engagement_score"],
        })

    # Identify improving / struggling topics
    improving = [t for t in topics if t["mastery_score"] >= 60]
    needs_support = [t for t in topics if t["mastery_score"] < 40]

    # Next recommended target
    recommended_next = None
    if sessions:
        recommended_next = sessions[0].get("recommended_next")

    return jsonify({
        "student": student,
        "goals": goals,
        "topics": topics,
        "sessions": sessions,
        "mental_blocks": mental_blocks,
        "confidence_trend": confidence_trend,
        "improving_topics": improving,
        "needs_support": needs_support,
        "recommended_next": recommended_next,
    })


# ──────────────────────────────────────────────
# API: TRANSCRIPT PROCESSING
# ──────────────────────────────────────────────

@app.route("/api/process/trial", methods=["POST"])
@login_required
def process_trial():
    """Process a trial transcript → create goals + topics."""
    data = request.json
    student_id = data["student_id"]
    transcript = data["transcript"]
    session_date = data.get("session_date", date.today().isoformat())

    # Process transcript (try AI, fall back to rule-based)
    try:
        result = processor.process_trial(transcript, student_id)
    except Exception:
        result = fallback_processor.process_trial(transcript, student_id)

    # Store session
    session_id = execute(
        "INSERT INTO sessions (student_id, transcript_text, session_type, session_date, "
        "extracted_summary, detected_topics) VALUES (?, ?, ?, ?, ?, ?)",
        (student_id, transcript, "trial", session_date,
         result["summary"], json.dumps(result["topics"]))
    )

    # Create goals
    for goal in result["goals"]:
        execute(
            "INSERT INTO goals (student_id, description, measurable_outcome, deadline, status) "
            "VALUES (?, ?, ?, ?, ?)",
            (student_id, goal["description"], goal["measurable_outcome"],
             goal.get("deadline"), "not started")
        )

    # Create topics (avoid duplicates)
    existing_topics = query("SELECT topic_name FROM topics WHERE student_id = ?", (student_id,))
    existing_names = {t["topic_name"].lower() for t in existing_topics}

    for topic_data in result["topics"]:
        if topic_data["name"].lower() not in existing_names:
            parent_id = None
            if topic_data.get("parent"):
                parent = query(
                    "SELECT id FROM topics WHERE student_id = ? AND topic_name = ?",
                    (student_id, topic_data["parent"]), one=True
                )
                if parent:
                    parent_id = parent["id"]
                else:
                    # Create parent topic first
                    parent_id = execute(
                        "INSERT INTO topics (student_id, topic_name, mastery_score, confidence_score) "
                        "VALUES (?, ?, ?, ?)",
                        (student_id, topic_data["parent"], 0, 0)
                    )
                    existing_names.add(topic_data["parent"].lower())

            execute(
                "INSERT INTO topics (student_id, topic_name, parent_topic_id, mastery_score, confidence_score) "
                "VALUES (?, ?, ?, ?, ?)",
                (student_id, topic_data["name"], parent_id, 0, 0)
            )
            existing_names.add(topic_data["name"].lower())

    # Update student curriculum if inferred
    if result.get("curriculum_recommendation"):
        execute(
            "UPDATE students SET curriculum = ? WHERE id = ?",
            (result["curriculum_recommendation"], student_id)
        )

    return jsonify({
        "session_id": session_id,
        "result": result,
    }), 201


@app.route("/api/process/session", methods=["POST"])
@login_required
def process_session():
    """Process a session transcript → update mastery + detect blocks."""
    data = request.json
    student_id = data["student_id"]
    transcript = data["transcript"]
    session_date = data.get("session_date", date.today().isoformat())

    # Process transcript (try AI, fall back to rule-based)
    try:
        result = processor.process_session(transcript, student_id)
    except Exception:
        result = fallback_processor.process_session(transcript, student_id)

    # Store session
    session_id = execute(
        "INSERT INTO sessions (student_id, transcript_text, session_type, session_date, "
        "extracted_summary, detected_topics, detected_misconceptions, detected_strengths, "
        "engagement_score, parent_summary, tutor_insight, recommended_next) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (student_id, transcript, "session", session_date,
         result["tutor_insight"],
         json.dumps(result["topics_discussed"]),
         json.dumps(result["misconceptions"]),
         json.dumps(result["strengths"]),
         result["engagement_score"],
         result["parent_summary"],
         result["tutor_insight"],
         result["recommended_next"])
    )

    # Update mastery scores
    for update in result["mastery_updates"]:
        topic = query(
            "SELECT * FROM topics WHERE student_id = ? AND topic_name = ?",
            (student_id, update["topic"]), one=True
        )
        if topic:
            new_mastery = update_mastery(
                topic["mastery_score"], update["improvement"],
                update["errors"], update["independent_solves"]
            )
            new_confidence = update_confidence(
                topic["confidence_score"],
                hesitation_count=update["errors"],
                positive_signals=update["independent_solves"]
            )
            execute(
                "UPDATE topics SET mastery_score = ?, confidence_score = ? WHERE id = ?",
                (new_mastery, new_confidence, topic["id"])
            )

    # Process mental block signals
    for signal in result["mental_block_signals"]:
        # Check if similar block already exists
        existing = query(
            "SELECT * FROM mental_blocks WHERE student_id = ? AND description LIKE ? AND resolved = 0",
            (student_id, f"%{signal.get('type', signal.get('description', ''))}%"), one=True
        )
        if existing:
            new_freq = existing["frequency_count"] + 1
            has_avoidance = signal.get("type") == "avoidance"
            has_emotional = signal.get("type") == "emotional"
            new_severity = compute_severity(new_freq, has_avoidance, has_emotional)
            execute(
                "UPDATE mental_blocks SET frequency_count = ?, severity_score = ? WHERE id = ?",
                (new_freq, new_severity, existing["id"])
            )
        else:
            execute(
                "INSERT INTO mental_blocks (student_id, description, first_detected, "
                "frequency_count, severity_score) VALUES (?, ?, ?, ?, ?)",
                (student_id, signal.get("description", "Unknown signal"), session_date,
                 1, signal.get("severity", 1))
            )

    return jsonify({
        "session_id": session_id,
        "result": {
            "topics_discussed": result["topics_discussed"],
            "misconceptions": result["misconceptions"],
            "strengths": result["strengths"],
            "engagement_score": result["engagement_score"],
            "parent_summary": result["parent_summary"],
            "tutor_insight": result["tutor_insight"],
            "recommended_next": result["recommended_next"],
            "mental_block_signals": len(result["mental_block_signals"]),
        }
    }), 201


# ──────────────────────────────────────────────
# SEED ENDPOINT (dev only)
# ──────────────────────────────────────────────

@app.route("/api/seed", methods=["POST"])
def seed_db():
    """Seed the database with sample data."""
    from lib.seed import seed
    seed()
    return jsonify({"ok": True}), 201


# ──────────────────────────────────────────────
# RUN
# ──────────────────────────────────────────────

# Initialize schema (works for both direct run and gunicorn import)
get_db()

if __name__ == "__main__":
    app.run(debug=True, port=5001)
