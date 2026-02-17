"""Seed the database with demo data for development/testing."""
from werkzeug.security import generate_password_hash
from lib.db import execute


def seed():
    """Insert demo users and sample student data."""

    # ─── Demo Users ───

    # Tutor (dev-mode email+password fallback)
    tutor_id = execute(
        "INSERT INTO users (email, password_hash, role, name) VALUES (?, ?, 'tutor', ?)",
        ("tutor@example.com", generate_password_hash("demo123", method='pbkdf2:sha256'), "Dr. Sharma")
    )

    # Parent (linked by email AND phone)
    parent_id = execute(
        "INSERT INTO users (email, phone, role, name) VALUES (?, ?, 'parent', ?)",
        ("parent@example.com", "+919876543210", "Mrs. Mehta")
    )
    print("Created demo users:")
    print("  Tutor: tutor@example.com / demo123")
    print("  Parent: parent@example.com OR +91-9876543210 (no password needed)")

    # ─── Demo Student ───
    student_id = execute(
        "INSERT INTO students (name, grade, curriculum, target_exam, long_term_goal_summary, tutor_id, parent_email, parent_phone) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("Arjun Mehta", "8th Grade", "Common Core + AMC Prep", "AMC 8",
         "Score in top 5% on AMC 8 and build strong algebra + geometry foundation.",
         tutor_id, "parent@example.com", "+91-9876543210")
    )
    print(f"Created demo student: Arjun Mehta (id={student_id})")

    # ─── Demo Goals ───
    goals = [
        ("Master linear equations and inequalities", "Solve 90%+ of linear equation problems correctly", "in progress"),
        ("Build strong number sense for AMC", "Complete AMC 8 practice test with score >= 20/25", "not started"),
        ("Develop problem-solving strategies", "Apply at least 3 different strategies independently", "not started"),
    ]
    for desc, outcome, status in goals:
        execute(
            "INSERT INTO goals (student_id, description, measurable_outcome, status) VALUES (?, ?, ?, ?)",
            (student_id, desc, outcome, status)
        )
    print(f"Created {len(goals)} demo goals")

    # ─── Demo Topics ───
    topics = [
        ("Algebra", None, 45, 50),
        ("Linear Equations", "Algebra", 60, 65),
        ("Inequalities", "Algebra", 30, 35),
        ("Geometry", None, 35, 40),
        ("Triangles", "Geometry", 40, 45),
        ("Number Theory", None, 25, 30),
    ]
    topic_ids = {}
    for name, parent, mastery, conf in topics:
        parent_id_val = topic_ids.get(parent)
        tid = execute(
            "INSERT INTO topics (student_id, topic_name, parent_topic_id, mastery_score, confidence_score) "
            "VALUES (?, ?, ?, ?, ?)",
            (student_id, name, parent_id_val, mastery, conf)
        )
        topic_ids[name] = tid
    print(f"Created {len(topics)} demo topics")
