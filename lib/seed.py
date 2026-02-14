"""Seed script — populate database with sample data for development."""
from lib.db import execute, query
from datetime import date


def seed():
    """Insert sample student, goals, and topics if DB is empty."""
    existing = query("SELECT COUNT(*) as c FROM students")
    if existing and existing[0]["c"] > 0:
        print("Database already seeded.")
        return

    # --- Student ---
    student_id = execute(
        "INSERT INTO students (name, grade, curriculum, target_exam, long_term_goal_summary) "
        "VALUES (?, ?, ?, ?, ?)",
        ("Arjun Mehta", "8th Grade", "Common Core + AMC Prep",
         "AMC 8", "Score in top 5% on AMC 8 and build strong algebra foundation")
    )

    # --- Goals ---
    goals = [
        ("Master algebraic expressions and equations", "Score 90%+ on algebra unit test", "2026-06-01", "in progress"),
        ("Build mental math speed", "Complete 20-problem set in under 10 minutes", "2026-04-01", "in progress"),
        ("Prepare for AMC 8 competition", "Score 20+ on practice AMC 8", "2026-11-01", "not started"),
        ("Overcome fraction/decimal confusion", "Zero errors on mixed operations quiz", "2026-05-01", "in progress"),
    ]
    for desc, outcome, deadline, status in goals:
        execute(
            "INSERT INTO goals (student_id, description, measurable_outcome, deadline, status) "
            "VALUES (?, ?, ?, ?, ?)",
            (student_id, desc, outcome, deadline, status)
        )

    # --- Topics (hierarchical) ---
    # Parent topics
    algebra_id = execute(
        "INSERT INTO topics (student_id, topic_name, mastery_score, confidence_score) VALUES (?, ?, ?, ?)",
        (student_id, "Algebra", 45, 40)
    )
    number_sense_id = execute(
        "INSERT INTO topics (student_id, topic_name, mastery_score, confidence_score) VALUES (?, ?, ?, ?)",
        (student_id, "Number Sense", 60, 55)
    )
    geometry_id = execute(
        "INSERT INTO topics (student_id, topic_name, mastery_score, confidence_score) VALUES (?, ?, ?, ?)",
        (student_id, "Geometry", 35, 30)
    )
    word_problems_id = execute(
        "INSERT INTO topics (student_id, topic_name, mastery_score, confidence_score) VALUES (?, ?, ?, ?)",
        (student_id, "Word Problems", 50, 45)
    )

    # Sub-topics
    subtopics = [
        (student_id, "Linear Equations", algebra_id, 50, 45),
        (student_id, "Expressions & Simplification", algebra_id, 55, 50),
        (student_id, "Inequalities", algebra_id, 30, 25),
        (student_id, "Fractions", number_sense_id, 40, 35),
        (student_id, "Decimals", number_sense_id, 65, 60),
        (student_id, "Ratios & Proportions", number_sense_id, 70, 65),
        (student_id, "Angles & Triangles", geometry_id, 40, 35),
        (student_id, "Area & Perimeter", geometry_id, 30, 25),
        (student_id, "Rate Problems", word_problems_id, 55, 50),
        (student_id, "Age Problems", word_problems_id, 45, 40),
    ]
    for sid, name, parent, mastery, confidence in subtopics:
        execute(
            "INSERT INTO topics (student_id, topic_name, parent_topic_id, mastery_score, confidence_score) "
            "VALUES (?, ?, ?, ?, ?)",
            (sid, name, parent, mastery, confidence)
        )

    print(f"Seeded student '{student_id}' with goals and topics.")


if __name__ == "__main__":
    seed()
