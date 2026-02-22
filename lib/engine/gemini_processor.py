"""
Gemini-powered transcript processor — real AI intelligence.
Implements the TranscriptProcessor interface.
Falls back to RuleBasedProcessor if no API key or on error.
"""
import json
import logging
import os
import re
import time
from typing import Dict, Any, Optional

from lib.engine.adapter import TranscriptProcessor

logger = logging.getLogger(__name__)

# ────────────────────────────────────────────
# CONFIG
# ────────────────────────────────────────────
MAX_RETRIES = 3
RETRY_BASE_DELAY = 1.0          # seconds, doubles each retry
MAX_TRANSCRIPT_CHARS = 120_000  # ~30K tokens safety limit
DEFAULT_MODEL = "gemini-2.0-flash"


class GeminiProcessor(TranscriptProcessor):
    """Google Gemini AI transcript processor."""

    def __init__(self):
        self.api_key = os.environ.get("GEMINI_API_KEY", "")
        self.model_name = os.environ.get("GEMINI_MODEL", DEFAULT_MODEL)
        self.model = None
        if self.api_key:
            try:
                import google.generativeai as genai
                genai.configure(api_key=self.api_key)
                self.model = genai.GenerativeModel(
                    self.model_name,
                    generation_config=genai.GenerationConfig(
                        temperature=0.2,
                        response_mime_type="application/json",
                    ),
                )
                logger.info("Gemini initialized: model=%s", self.model_name)
            except Exception as e:
                logger.warning("Gemini init failed: %s. Will use rule-based fallback.", e)
                self.model = None

    @property
    def is_available(self):
        return self.model is not None

    # ────────────────────────────────────────────
    # SHARED HELPERS
    # ────────────────────────────────────────────

    @staticmethod
    def _truncate_transcript(transcript: str) -> str:
        """Cap transcript length to stay within model context limits."""
        if len(transcript) <= MAX_TRANSCRIPT_CHARS:
            return transcript
        logger.warning(
            "Transcript truncated: %d chars → %d chars",
            len(transcript), MAX_TRANSCRIPT_CHARS,
        )
        return transcript[:MAX_TRANSCRIPT_CHARS] + "\n\n[TRANSCRIPT TRUNCATED — original was too long]"

    @staticmethod
    def _extract_json(text: str) -> dict:
        """Extract the first complete JSON object from text, handling markdown fences."""
        # Strip markdown code fences
        cleaned = re.sub(r'^```(?:json)?\s*', '', text.strip())
        cleaned = re.sub(r'\s*```$', '', cleaned)

        # Try direct parse first (fast path)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass

        # Fallback: find outermost { … } pair
        start = text.find('{')
        if start == -1:
            raise ValueError("No JSON object found in Gemini response")

        depth = 0
        for i in range(start, len(text)):
            if text[i] == '{':
                depth += 1
            elif text[i] == '}':
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start:i + 1])
                    except json.JSONDecodeError as e:
                        raise ValueError(f"Invalid JSON in Gemini response: {e}") from e

        raise ValueError("Unclosed JSON object in Gemini response")

    def _call_gemini(self, prompt: str) -> dict:
        """Call Gemini with retry + backoff, return parsed JSON dict."""
        last_error: Optional[Exception] = None
        prompt_chars = len(prompt)

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                t0 = time.monotonic()
                response = self.model.generate_content(prompt)
                elapsed = time.monotonic() - t0
                logger.info(
                    "Gemini call OK: attempt=%d, prompt_chars=%d, time=%.2fs",
                    attempt, prompt_chars, elapsed,
                )
                return self._extract_json(response.text.strip())
            except Exception as e:
                last_error = e
                if attempt < MAX_RETRIES:
                    delay = RETRY_BASE_DELAY * (2 ** (attempt - 1))
                    logger.warning(
                        "Gemini call failed (attempt %d/%d): %s — retrying in %.1fs",
                        attempt, MAX_RETRIES, e, delay,
                    )
                    time.sleep(delay)
                else:
                    logger.error(
                        "Gemini call failed after %d attempts: %s", MAX_RETRIES, e,
                    )

        raise last_error  # type: ignore[misc]

    # ────────────────────────────────────────────
    # OUTPUT VALIDATORS
    # ────────────────────────────────────────────

    @staticmethod
    def _validate_trial_result(result: dict) -> dict:
        """Validate and sanitize trial processing output."""
        # Required top-level fields
        if "goals" not in result or "topics" not in result:
            raise ValueError("Missing required fields: 'goals' and 'topics'")

        # Filter goals — each must have at least a description
        valid_goals = []
        for g in result["goals"]:
            if isinstance(g, dict) and g.get("description"):
                g.setdefault("measurable_outcome", "")
                g.setdefault("evidence_quote", "")
                g.setdefault("suggested_intervention", "")
                g.setdefault("deadline", None)
                valid_goals.append(g)
        result["goals"] = valid_goals

        if not result["goals"]:
            raise ValueError("No valid goals extracted from transcript")

        # Filter topics — each must have a name
        result["topics"] = [
            t for t in result["topics"]
            if isinstance(t, dict) and t.get("name")
        ]

        # Sanitize mental blocks
        valid_blocks = []
        for mb in result.get("mental_blocks", []):
            if isinstance(mb, dict) and mb.get("evidence_from_transcript"):
                mb.setdefault("block_type", "confusion")
                mb["severity"] = max(1, min(10, int(mb.get("severity", 5))))
                mb.setdefault("cognitive_explanation", "")
                mb.setdefault("impact_on_learning", "")
                valid_blocks.append(mb)
        result["mental_blocks"] = valid_blocks

        # Defaults
        result.setdefault("summary", "Trial session processed by AI.")
        result.setdefault("curriculum_recommendation", "General Math Proficiency")
        result.setdefault("lesson_recommendations", [])

        return result

    @staticmethod
    def _validate_session_result(result: dict) -> dict:
        """Validate and sanitize session processing output."""
        result.setdefault("topics_discussed", [])
        result.setdefault("misconceptions", [])
        result.setdefault("strengths", [])
        result.setdefault("mastery_updates", [])
        result.setdefault("lesson_recommendations", [])
        result.setdefault("parent_summary", "Session completed successfully.")
        result.setdefault("tutor_insight", "Session data processed.")
        result.setdefault("recommended_next", "Continue with current progression.")

        # Clamp engagement score to [0, 100]
        try:
            score = float(result.get("engagement_score", 50))
        except (ValueError, TypeError):
            score = 50.0
        result["engagement_score"] = max(0.0, min(100.0, score))

        # Sanitize mental block signals
        valid_signals = []
        for sig in result.get("mental_block_signals", []):
            if isinstance(sig, dict) and sig.get("description"):
                sig.setdefault("type", "confusion")
                try:
                    sev = float(sig.get("severity", 1))
                except (ValueError, TypeError):
                    sev = 1.0
                sig["severity"] = max(0.0, min(10.0, sev))
                sig.setdefault("evidence_from_transcript", "")
                sig.setdefault("cognitive_explanation", "")
                sig.setdefault("impact_on_learning", "")
                valid_signals.append(sig)
        result["mental_block_signals"] = valid_signals

        # Sanitize mastery updates
        valid_mastery = []
        for mu in result["mastery_updates"]:
            if isinstance(mu, dict) and mu.get("topic"):
                mu.setdefault("improvement", 0.0)
                mu.setdefault("errors", 0)
                mu.setdefault("independent_solves", 0)
                valid_mastery.append(mu)
        result["mastery_updates"] = valid_mastery

        return result

    # ────────────────────────────────────────────
    # TRIAL / INTAKE SESSION
    # ────────────────────────────────────────────
    def process_trial(self, transcript: str, student_id: int) -> Dict[str, Any]:
        """Process a trial/intake transcript using Gemini AI."""
        transcript = self._truncate_transcript(transcript)

        prompt = f"""You are a senior educational performance analyst evaluating a 1-to-1 math tutoring trial/intake session transcript.

Your job is to extract highly specific, measurable insights that will form the student's learning roadmap.

CRITICAL RULES:
- No vague language. No generic advice.
- BANNED phrases (do NOT use these anywhere in the output): "improve focus", "understand better", "work on skills", "build confidence", "try harder", "practice more", "develop understanding", "get comfortable with".
- Every goal must describe a SPECIFIC, OBSERVABLE STUDENT BEHAVIOR — something a camera could record.
- Every single insight you produce MUST be traceable to EXACT transcript wording. If you cannot point to a specific phrase, sentence, or exchange in the transcript, do NOT include the insight.
- Output strictly valid JSON. No markdown. No explanations outside JSON.

Transcript:
---
{transcript}
---

From this trial session extract:
1. Student's cognitive profile — how they think, process, and respond (cite transcript evidence)
2. 2–6 specific learning goals with measurable outcomes, transcript evidence, and suggested interventions
3. Math topics identified (with parent-child hierarchy)
4. Curriculum recommendation
5. Mental blocks or anxiety patterns with type classification, severity scoring, and direct transcript evidence

GOAL EXTRACTION RULES:
- Extract exactly 2–6 goals. No fewer than 2, no more than 6.
- Each goal MUST describe a measurable, observable behavior (e.g., "Solve 3-step word problems involving fractions by setting up equations independently" — NOT "get better at word problems").
- Each goal MUST include an evidence_quote: copy-paste the exact student words or tutor-student exchange from the transcript that reveals this goal is needed.
- Each goal MUST include a suggested_intervention: a concrete, prescriptive teaching action (e.g., "Use bar-model diagrams for 5 guided problems, then fade to numeric-only").
- If you cannot find transcript evidence for a goal, do NOT include that goal.

MENTAL BLOCK RULES:
- For every mental block, you MUST assign a severity score from 1–10:
  1–3 = mild (brief hesitation, single avoidance phrase)
  4–6 = moderate (visible frustration, repeated avoidance, off-topic deflection)
  7–10 = severe (emotional shutdown, refusal to continue, anxiety-driven errors)
- You MUST include the block_type: one of "avoidance", "emotional", "confusion", or "confidence".
- You MUST include evidence_from_transcript: the EXACT words or exchange from the transcript — direct quotes, not paraphrases.
- Detection signals:
  AVOIDANCE: "can we skip this", changes topic, gives up quickly, "I'll never get this"
  EMOTIONAL: sighing, frustration sounds, "I hate this", anxiety about tests/grades
  CONFUSION: circular questioning, same mistake 3+ times, "I don't even know where to start"
  CONFIDENCE: "I'm dumb", "I can't do math", downplays correct answers

LESSON RECOMMENDATION RULES:
- Every recommendation must be PRESCRIPTIVE and CONCRETE — not generic advice.
- BAD example: "Practice more fraction problems" or "Build conceptual understanding of algebra"
- GOOD example: "Use Cuisenaire rods to model fraction addition for 3 sessions, starting with unit fractions (1/2 + 1/3), then progress to unlike denominators with rod comparison before introducing the LCD algorithm"
- Each recommendation must reference the specific student behavior or gap it addresses.
- Include exact problem types, tools/manipulatives, session counts, or progression steps where applicable.

TRACEABILITY MANDATE:
Every insight in the output — every goal, every mental block, every lesson recommendation, every strength or weakness mentioned in the summary — must be traceable to exact transcript wording. Treat the transcript as your ONLY source of evidence. Do not infer, assume, or generalize beyond what the transcript explicitly shows.

Return a JSON object with EXACTLY these fields:
{{
    "summary": "Concise 2-3 sentence cognitive profile of the student. Reference specific transcript moments (e.g., 'When asked to simplify 3x + 2x, student counted on fingers, suggesting reliance on arithmetic over algebraic reasoning'). No vague statements.",

    "goals": [
        {{
            "description": "Specific, behavior-based goal (e.g., 'Solve systems of 2 linear equations using elimination method without tutor prompting')",
            "measurable_outcome": "Exact success criteria (e.g., 'Score 8/10 on timed drill of 10 elimination problems in under 15 minutes')",
            "evidence_quote": "Exact words or exchange from transcript that shows this goal is needed (e.g., 'Student said: I just guess which one to subtract')",
            "suggested_intervention": "Concrete teaching action to achieve this goal (e.g., 'Color-code variable terms across 5 guided elimination problems, then have student verbalize each step before writing')",
            "deadline": null
        }}
    ],

    "topics": [
        {{
            "name": "specific math topic (e.g., 'Linear Equations')",
            "parent": "parent topic or null (e.g., 'Algebra')"
        }}
    ],

    "curriculum_recommendation": "Recommended curriculum track (e.g., 'Competition Math (AMC/MathCounts)', 'SAT/ACT Prep', 'Common Core Aligned', 'General Math Proficiency')",

    "mental_blocks": [
        {{
            "block_type": "avoidance | emotional | confusion | confidence",
            "severity": 5,
            "evidence_from_transcript": "EXACT quote or exchange from transcript — direct words, not paraphrase (e.g., 'Student: Can we do something else? I really don\\'t get fractions')",
            "cognitive_explanation": "Why this happens — root cause grounded in observed behavior",
            "impact_on_learning": "How this specifically blocks progress, referencing the observed pattern"
        }}
    ],

    "lesson_recommendations": [
        {{
            "intervention_type": "scaffolding | drill | conceptual_rebuild | confidence_building | metacognitive",
            "specific_strategy": "Exact, prescriptive strategy with tools, problem types, and progression steps (e.g., 'Start with visual fraction bars for unit fractions, progress to numerical operations over 3 sessions, use error-analysis worksheets where student identifies and corrects pre-made mistakes')",
            "why_this_will_work": "Evidence-based reasoning tied to THIS student's specific transcript behavior (e.g., 'Student responded well to visual cues when tutor drew a number line at 14:32, suggesting visual scaffolding will accelerate fraction understanding')"
        }}
    ]
}}

Guidelines:
- Extract 2–6 specific, actionable goals — each must describe an OBSERVABLE BEHAVIOR, not a feeling
- Map topics to a hierarchy (e.g., "Quadratic Factoring" under "Algebra")
- Infer curriculum from context clues (competition mentions, exam names, grade level)
- Every insight must be traceable to EXACT transcript wording — no exceptions"""

        try:
            result = self._call_gemini(prompt)
            return self._validate_trial_result(result)
        except Exception as e:
            logger.error("Gemini trial processing error: %s", e)
            raise

    # ────────────────────────────────────────────
    # REGULAR SESSION
    # ────────────────────────────────────────────
    def process_session(self, transcript: str, student_id: int) -> Dict[str, Any]:
        """Process a session transcript using Gemini AI."""
        transcript = self._truncate_transcript(transcript)

        prompt = f"""You are a senior educational performance analyst evaluating a 1-to-1 math tutoring session transcript.

Your job is to extract highly specific, measurable insights about student performance.

CRITICAL RULES:
- No vague language. No generic advice.
- No soft phrases like "improve focus" or "understand better".
- Every observation must be behavior-specific and evidence-based.
- Output strictly valid JSON. No markdown. No explanations outside JSON.

From the transcript, analyze:
1. Attention patterns — when does the student focus vs. drift?
2. Cognitive processing behavior — how do they approach problems?
3. Conceptual gaps — what specifically don't they understand?
4. Execution weaknesses — where do they make errors and why?
5. Parent expectations (if parent is present in transcript)

Transcript:
---
{transcript}
---

Return a JSON object with EXACTLY these fields:
{{
    "topics_discussed": ["list of SPECIFIC math topics covered (e.g., 'Completing the square for quadratics', not just 'Algebra')"],

    "misconceptions": [
        "Be VERY specific — quote student errors where possible. Example: 'Student believes (-3)^2 = -9, showing sign rule confusion in exponentiation'"
    ],

    "strengths": [
        "Specific observed strengths. Example: 'Correctly applied distributive property across 4 problems without prompting'"
    ],

    "engagement_score": 70,

    "mastery_updates": [
        {{
            "topic": "specific topic name",
            "improvement": 0.0,
            "errors": 0,
            "independent_solves": 0
        }}
    ],

    "mental_block_signals": [
        {{
            "description": "What the block is — be specific",
            "type": "avoidance | emotional | confusion",
            "severity": 1.0,
            "evidence_from_transcript": "Direct quote or behavior observed",
            "cognitive_explanation": "Root cause analysis — why does this happen?",
            "impact_on_learning": "How this blocks progress"
        }}
    ],

    "lesson_recommendations": [
        {{
            "intervention_type": "scaffolding | drill | conceptual_rebuild | confidence_building | metacognitive",
            "specific_strategy": "Exact, actionable strategy",
            "why_this_will_work": "Evidence-based reasoning for this student"
        }}
    ],

    "parent_summary": "A warm, encouraging 2-3 sentence summary for parents. Mention what was worked on, positives first, then areas for growth. Use simple language a non-math parent would understand. Never use jargon.",

    "tutor_insight": "A technical 2-3 sentence analysis for the tutor. Include: (1) specific understanding gaps with evidence, (2) pedagogical suggestions grounded in what you observed, (3) conceptual connections to leverage next session.",

    "recommended_next": "Specific, prescriptive recommendation for the next session. Include: exact topic to start with, specific problem types to use, and one warm-up exercise suggestion."
}}

Guidelines for scoring:
- engagement_score: 85-100 = highly engaged (asks questions, attempts independently), 70-84 = good (follows along, some initiative), 50-69 = passive (responds when asked but doesn't initiate), 30-49 = disengaged (one-word answers, off-topic), <30 = very disengaged
- improvement: 0.0 = no progress, 0.3 = slight, 0.5 = moderate, 0.7 = strong, 1.0 = mastered
- severity: 1-3 = mild (minor hesitation), 4-6 = moderate (visible frustration, avoidance), 7-10 = severe (emotional shutdown, refusal)

Rules for mental block detection:
- AVOIDANCE: student says "can we skip this", changes topic, gives up quickly, says "I'll never get this"
- EMOTIONAL: sighing, frustration sounds, "I hate this", anxiety about tests/grades
- CONFUSION: circular questioning, same mistake 3+ times, "I don't even know where to start"

Rules for parent_summary:
- ALWAYS lead with something positive
- Use phrases like "worked on" not "struggled with"
- If there are concerns, frame as "areas we'll keep building on"
- Parents should feel good reading this, not worried"""

        try:
            result = self._call_gemini(prompt)
            return self._validate_session_result(result)
        except Exception as e:
            logger.error("Gemini session processing error: %s", e)
            raise
