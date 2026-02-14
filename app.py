"""
Transcript Intelligence Dashboard — Main Flask Application
"""
import json
import sys
import os
from datetime import date, datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(__file__))

from flask import Flask, request, jsonify, render_template, send_from_directory
from lib.db import query, execute, get_db
from lib.engine.rule_based import RuleBasedProcessor
from lib.engine.mastery import update_mastery, update_confidence
from lib.engine.mental_blocks import compute_severity

app = Flask(__name__, static_folder="static", template_folder="templates")
processor = RuleBasedProcessor()


# ──────────────────────────────────────────────
# PAGES
# ──────────────────────────────────────────────

@app.route("/")
def index():
    """Landing page — student list."""
    return render_template("index.html")


@app.route("/student/<int:student_id>")
def student_dashboard(student_id):
    """Student dashboard page."""
    return render_template("dashboard.html", student_id=student_id)


# ──────────────────────────────────────────────
# API: STUDENTS
# ──────────────────────────────────────────────

@app.route("/api/students", methods=["GET"])
def list_students():
    students = query("SELECT * FROM students ORDER BY name")
    return jsonify(students)


@app.route("/api/students", methods=["POST"])
def create_student():
    data = request.json
    sid = execute(
        "INSERT INTO students (name, grade, curriculum, target_exam, long_term_goal_summary) "
        "VALUES (?, ?, ?, ?, ?)",
        (data["name"], data["grade"], data.get("curriculum", ""),
         data.get("target_exam", ""), data.get("long_term_goal_summary", ""))
    )
    return jsonify({"id": sid}), 201


@app.route("/api/students/<int:sid>", methods=["GET"])
def get_student(sid):
    student = query("SELECT * FROM students WHERE id = ?", (sid,), one=True)
    if not student:
        return jsonify({"error": "Student not found"}), 404
    return jsonify(student)


@app.route("/api/students/<int:sid>", methods=["PUT"])
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
def list_goals(sid):
    goals = query("SELECT * FROM goals WHERE student_id = ? ORDER BY created_at", (sid,))
    return jsonify(goals)


@app.route("/api/students/<int:sid>/goals", methods=["POST"])
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
def list_topics(sid):
    topics = query("SELECT * FROM topics WHERE student_id = ? ORDER BY topic_name", (sid,))
    return jsonify(topics)


# ──────────────────────────────────────────────
# API: SESSIONS
# ──────────────────────────────────────────────

@app.route("/api/students/<int:sid>/sessions", methods=["GET"])
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
def list_mental_blocks(sid):
    blocks = query(
        "SELECT * FROM mental_blocks WHERE student_id = ? ORDER BY severity_score DESC", (sid,)
    )
    return jsonify(blocks)


# ──────────────────────────────────────────────
# API: DASHBOARD AGGREGATE
# ──────────────────────────────────────────────

@app.route("/api/students/<int:sid>/dashboard", methods=["GET"])
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
def process_trial():
    """Process a trial transcript → create goals + topics."""
    data = request.json
    student_id = data["student_id"]
    transcript = data["transcript"]
    session_date = data.get("session_date", date.today().isoformat())

    # Process transcript
    result = processor.process_trial(transcript, student_id)

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
def process_session():
    """Process a session transcript → update mastery + detect blocks."""
    data = request.json
    student_id = data["student_id"]
    transcript = data["transcript"]
    session_date = data.get("session_date", date.today().isoformat())

    # Process transcript
    result = processor.process_session(transcript, student_id)

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
            (student_id, f"%{signal['type']}%"), one=True
        )
        if existing:
            new_freq = existing["frequency_count"] + 1
            has_avoidance = signal["type"] == "avoidance"
            has_emotional = signal["type"] == "emotional"
            new_severity = compute_severity(new_freq, has_avoidance, has_emotional)
            execute(
                "UPDATE mental_blocks SET frequency_count = ?, severity_score = ? WHERE id = ?",
                (new_freq, new_severity, existing["id"])
            )
        else:
            execute(
                "INSERT INTO mental_blocks (student_id, description, first_detected, "
                "frequency_count, severity_score) VALUES (?, ?, ?, ?, ?)",
                (student_id, signal["description"], session_date, 1, signal["severity"])
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
