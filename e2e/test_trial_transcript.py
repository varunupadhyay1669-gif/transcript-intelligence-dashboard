"""
Test 1: Upload trial transcript → goal tree created.
"""
import pytest
from playwright.sync_api import sync_playwright, expect


TRIAL_TRANSCRIPT = """Parent: Hi, we are looking for math tutoring for our daughter Maya. She is in 7th grade.
Tutor: Welcome! What are your main goals for Maya?
Parent: She needs to improve her algebra skills. She struggles with equations and variables.
Tutor: I see. Any specific exams or targets?
Parent: Yes, we want her to prepare for the AMC 8 competition next year.
Student: I also find fractions really hard. I don't understand how to multiply fractions.
Tutor: That's very common. We'll build a solid foundation.
Parent: We also want her to get better at word problems. She freezes when she sees them.
Tutor: Understood. We'll create a structured plan covering algebra, fractions, and word problems.
Parent: Her goal is to score above 80% on her school math tests consistently.
Tutor: That's a great measurable goal. Let's get started."""


def test_trial_transcript_creates_goals(reset_db, base_url):
    """Upload a trial transcript and verify goals and topics are created."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # Navigate to dashboard for student 1
        page.goto(f"{base_url}/student/1")
        page.wait_for_load_state("networkidle")

        # Click "Upload Transcript" button
        page.click("text=Upload Transcript")

        # Select "Trial" type
        page.select_option("#transcript-type", "trial")

        # Fill in the date
        page.fill("#session-date", "2026-01-10")

        # Paste the transcript
        page.fill("#transcript-text", TRIAL_TRANSCRIPT)

        # Submit
        page.click("text=Process Transcript")

        # Wait for processing result
        page.wait_for_selector("#processing-result", state="visible", timeout=10000)

        # Verify the result shows goals
        result_text = page.text_content("#result-content")
        assert "Goals Identified" in result_text
        assert "Topics Mapped" in result_text

        # Verify specific goals were extracted
        assert "algebra" in result_text.lower() or "equation" in result_text.lower()

        # Click "View Dashboard" to return
        page.click("text=View Dashboard")
        page.wait_for_load_state("networkidle")

        # Verify goals appear in the dashboard
        goals_section = page.text_content("#goals-list")
        assert goals_section is not None
        assert len(goals_section.strip()) > 0

        # Verify topics appear in the heatmap
        heatmap = page.text_content("#heatmap-grid")
        assert heatmap is not None

        browser.close()


def test_trial_transcript_api_creates_goals(reset_db, base_url):
    """Verify trial processing via API directly."""
    import requests

    resp = requests.post(f"{base_url}/api/process/trial", json={
        "student_id": 1,
        "transcript": TRIAL_TRANSCRIPT,
        "session_date": "2026-01-10"
    })

    assert resp.status_code == 201
    data = resp.json()

    # Verify goals were extracted
    assert len(data["result"]["goals"]) >= 2
    assert data["result"]["session_id"] is not None

    # Verify topics were mapped
    assert len(data["result"]["topics"]) >= 2

    # Verify curriculum was inferred
    assert "AMC" in data["result"]["curriculum_recommendation"] or \
           "Competition" in data["result"]["curriculum_recommendation"]

    # Verify goals are in the database
    goals_resp = requests.get(f"{base_url}/api/students/1/goals")
    goals = goals_resp.json()
    assert len(goals) >= 4  # Seeded goals + new ones
