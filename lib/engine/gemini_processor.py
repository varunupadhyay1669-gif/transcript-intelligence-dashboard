"""
Gemini-powered transcript processor — real AI intelligence.
Implements the TranscriptProcessor interface.
Falls back to RuleBasedProcessor if no API key or on error.
"""
import os
import json
import re
from typing import Dict, Any

from lib.engine.adapter import TranscriptProcessor


class GeminiProcessor(TranscriptProcessor):
    """Google Gemini AI transcript processor."""

    def __init__(self):
        self.api_key = os.environ.get("GEMINI_API_KEY", "")
        self.model = None
        if self.api_key:
            try:
                import google.generativeai as genai
                genai.configure(api_key=self.api_key)
                self.model = genai.GenerativeModel("gemini-2.0-flash")
            except Exception as e:
                print(f"⚠️ Gemini init failed: {e}. Will use rule-based fallback.")
                self.model = None

    @property
    def is_available(self):
        return self.model is not None

    def process_trial(self, transcript: str, student_id: int) -> Dict[str, Any]:
        """Process a trial/intake transcript using Gemini AI."""
        prompt = f"""You are an expert math tutor analyzing a trial/intake session transcript.
Extract structured data from the transcript below. Return ONLY valid JSON (no markdown, no code blocks).

Transcript:
---
{transcript}
---

Return a JSON object with exactly these fields:
{{
    "goals": [
        {{
            "description": "clear goal statement",
            "measurable_outcome": "how to measure success",
            "deadline": null or "YYYY-MM-DD"
        }}
    ],
    "topics": [
        {{
            "name": "specific math topic",
            "parent": "parent topic or null"
        }}
    ],
    "summary": "2-3 sentence summary of the trial session",
    "curriculum_recommendation": "recommended curriculum track (e.g., 'Competition Math (AMC/MathCounts)', 'SAT/ACT Prep', 'Common Core Aligned', 'General Math Proficiency')"
}}

Guidelines:
- Extract 2-6 specific, actionable goals from the conversation
- Map topics to a hierarchy (e.g., "Linear Equations" under "Algebra")
- Infer curriculum from context clues (competition mentions, exam names, grade level)
- Be specific and insightful in the summary"""

        try:
            response = self.model.generate_content(prompt)
            text = response.text.strip()
            # Clean markdown code blocks if present
            text = re.sub(r'^```(?:json)?\s*', '', text)
            text = re.sub(r'\s*```$', '', text)
            result = json.loads(text)

            # Validate required fields
            if "goals" not in result or "topics" not in result:
                raise ValueError("Missing required fields in response")

            # Ensure proper structure
            result.setdefault("summary", "Trial session processed by AI.")
            result.setdefault("curriculum_recommendation", "General Math Proficiency")

            return result

        except Exception as e:
            print(f"⚠️ Gemini trial processing error: {e}")
            raise

    def process_session(self, transcript: str, student_id: int) -> Dict[str, Any]:
        """Process a session transcript using Gemini AI."""
        prompt = f"""You are an expert math tutor analyzing a tutoring session transcript.
Extract detailed performance data. Return ONLY valid JSON (no markdown, no code blocks).

Transcript:
---
{transcript}
---

Return a JSON object with exactly these fields:
{{
    "topics_discussed": ["list of specific math topics covered"],
    "misconceptions": ["specific misconceptions or errors detected"],
    "strengths": ["specific strengths demonstrated by the student"],
    "engagement_score": 0-100 numeric engagement score,
    "mastery_updates": [
        {{
            "topic": "topic name",
            "improvement": 0.0-1.0 improvement factor,
            "errors": number of errors on this topic,
            "independent_solves": number of problems solved independently
        }}
    ],
    "mental_block_signals": [
        {{
            "description": "what the mental block is about",
            "type": "avoidance, emotional, or confusion",
            "severity": 1.0-10.0
        }}
    ],
    "parent_summary": "A warm, encouraging 2-3 sentence summary for parents. Mention what was worked on, positives first, then areas for growth. Use simple language.",
    "tutor_insight": "A technical 2-3 sentence analysis for the tutor. Include specific observations about understanding gaps, pedagogical suggestions, and conceptual connections.",
    "recommended_next": "Specific recommendation for the next session focus and approach."
}}

Guidelines:
- Be very specific about misconceptions — quote student errors if possible
- Engagement score: 80+ = very engaged, 60-79 = normal, 40-59 = disengaged, <40 = very disengaged
- Mental block signals: look for avoidance language, emotional reactions, repeated confusion
- Parent summary should be positive and encouraging — parents worry!
- Tutor insight should be actionable and technically detailed
- Recommended next should be a specific lesson plan suggestion"""

        try:
            response = self.model.generate_content(prompt)
            text = response.text.strip()
            # Clean markdown code blocks if present
            text = re.sub(r'^```(?:json)?\s*', '', text)
            text = re.sub(r'\s*```$', '', text)
            result = json.loads(text)

            # Validate and set defaults
            result.setdefault("topics_discussed", [])
            result.setdefault("misconceptions", [])
            result.setdefault("strengths", [])
            result.setdefault("engagement_score", 50)
            result.setdefault("mastery_updates", [])
            result.setdefault("mental_block_signals", [])
            result.setdefault("parent_summary", "Session completed successfully.")
            result.setdefault("tutor_insight", "Session data processed.")
            result.setdefault("recommended_next", "Continue with current progression.")

            # Ensure engagement_score is a number
            result["engagement_score"] = float(result["engagement_score"])

            return result

        except Exception as e:
            print(f"⚠️ Gemini session processing error: {e}")
            raise
