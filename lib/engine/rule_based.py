"""
Rule-based transcript processor — no external AI needed.
Uses keyword and pattern matching to extract structured data from transcripts.
Implements the TranscriptProcessor interface for easy swap to an LLM later.
"""

import re
from typing import Dict, Any, List
from lib.engine.adapter import TranscriptProcessor
from lib.engine.mental_blocks import detect_mental_block_signals

# ──────────────────────────────────────────────
# MATH TOPIC DICTIONARY
# ──────────────────────────────────────────────
TOPIC_KEYWORDS = {
    "Algebra": ["algebra", "equation", "variable", "expression", "polynomial", "factor", "solve for x",
                "linear", "quadratic", "inequality", "system of equations", "substitution"],
    "Linear Equations": ["linear equation", "slope", "intercept", "y = mx + b", "graph the line",
                         "solve for x", "one variable"],
    "Expressions & Simplification": ["simplify", "combine like terms", "distribute", "expression",
                                     "expand", "foil"],
    "Inequalities": ["inequality", "greater than", "less than", "number line", "≥", "≤", ">", "<"],
    "Fractions": ["fraction", "numerator", "denominator", "mixed number", "improper fraction",
                  "common denominator", "reduce", "simplify fraction"],
    "Decimals": ["decimal", "decimal point", "tenths", "hundredths", "convert decimal"],
    "Ratios & Proportions": ["ratio", "proportion", "rate", "unit rate", "cross multiply",
                             "scale factor"],
    "Geometry": ["geometry", "shape", "angle", "triangle", "circle", "polygon", "congruent",
                 "similar", "parallel", "perpendicular"],
    "Angles & Triangles": ["angle", "triangle", "degree", "acute", "obtuse", "right angle",
                           "isosceles", "equilateral", "scalene", "pythagorean"],
    "Area & Perimeter": ["area", "perimeter", "surface area", "volume", "square units",
                         "length times width"],
    "Word Problems": ["word problem", "story problem", "how many", "how much", "total",
                      "difference", "altogether"],
    "Rate Problems": ["rate", "speed", "distance", "time", "miles per hour", "km per hour"],
    "Age Problems": ["age", "years old", "how old", "older than", "younger than"],
    "Number Sense": ["number", "place value", "rounding", "estimation", "mental math",
                     "arithmetic", "calculation"],
    "Exponents": ["exponent", "power", "squared", "cubed", "base"],
    "Probability": ["probability", "chance", "likely", "outcome", "event", "random"],
    "Statistics": ["mean", "median", "mode", "range", "average", "data", "graph", "chart"],
}

# Goal extraction keywords
GOAL_KEYWORDS = {
    "improve": ["improve", "get better", "strengthen", "build", "develop"],
    "score": ["score", "grade", "marks", "points", "percentage", "percent"],
    "exam": ["exam", "test", "sat", "act", "amc", "competition", "olympiad", "mathcounts"],
    "speed": ["faster", "speed", "quick", "timed", "mental math"],
    "confidence": ["confident", "confidence", "comfortable", "not afraid"],
    "understand": ["understand", "grasp", "concept", "foundation", "basics"],
}

# Misconception signals
MISCONCEPTION_SIGNALS = [
    r"(?:i thought|i think)\s+(?:it was|it's|you)\s+",
    r"(?:wait|no)\s*,?\s*(?:isn't it|is it|shouldn't)",
    r"(?:but|why)\s+(?:isn't|doesn't|can't|won't)",
    r"(?:i keep getting|i got)\s+(?:a different|the wrong|a wrong)",
    r"(?:that doesn't make sense|i'm confused about)",
    r"(?:oh wait|oh no|oops)",
    r"(?:i forgot|i don't remember)\s+(?:how to|the rule|the formula)",
    r"(?:why do we|why can't we|why does)\s+",
]

# Strength signals
STRENGTH_SIGNALS = [
    r"(?:i got it|i understand|oh i see|that makes sense)",
    r"(?:let me try|i'll do|i can do)\s+(?:this one|it|the next)",
    r"(?:is it|the answer is|so it's)\s+\d+",  # Confident answer
    r"(?:i remember|i know)\s+(?:this|how to|the)",
    r"(?:easy|simple|straightforward|i see the pattern)",
    r"(?:without help|by myself|on my own|independently)",
]

# Engagement signals
ENGAGEMENT_POSITIVE = [
    "can we do more", "another one", "what about", "interesting", "cool",
    "i like this", "fun", "let me try", "what if", "i have a question",
]
ENGAGEMENT_NEGATIVE = [
    "boring", "when are we done", "how much longer", "can we stop",
    "i'm tired", "whatever", "i don't care",
]


class RuleBasedProcessor(TranscriptProcessor):
    """Rule-based transcript processing using keyword/pattern matching."""

    def process_trial(self, transcript: str, student_id: int) -> Dict[str, Any]:
        """Process a trial/intake transcript to extract goals, topics, and curriculum."""
        lower = transcript.lower()
        lines = transcript.split("\n")

        # --- Extract goals ---
        goals = self._extract_goals(lower, lines)

        # --- Extract topics ---
        topics = self._detect_topics(lower)

        # --- Infer curriculum ---
        curriculum = self._infer_curriculum(lower)

        # --- Generate summary ---
        summary = self._generate_trial_summary(goals, topics, curriculum)

        return {
            "goals": goals,
            "topics": [{"name": t, "parent": self._get_parent_topic(t)} for t in topics],
            "summary": summary,
            "curriculum_recommendation": curriculum,
        }

    def process_session(self, transcript: str, student_id: int) -> Dict[str, Any]:
        """Process a session transcript to extract performance data."""
        lower = transcript.lower()

        # --- Topic detection ---
        topics_discussed = self._detect_topics(lower)

        # --- Misconception detection ---
        misconceptions = self._detect_misconceptions(lower)

        # --- Strength detection ---
        strengths = self._detect_strengths(lower)

        # --- Engagement scoring ---
        engagement = self._score_engagement(lower)

        # --- Mastery update signals ---
        mastery_updates = self._compute_mastery_signals(lower, topics_discussed, misconceptions, strengths)

        # --- Mental block signals ---
        mental_block_signals = detect_mental_block_signals(lower)

        # --- Generate summaries ---
        parent_summary = self._generate_parent_summary(topics_discussed, strengths, misconceptions, engagement)
        tutor_insight = self._generate_tutor_insight(topics_discussed, misconceptions, strengths, mental_block_signals)
        recommended_next = self._generate_recommendation(topics_discussed, misconceptions, mastery_updates)

        return {
            "topics_discussed": topics_discussed,
            "misconceptions": misconceptions,
            "strengths": strengths,
            "engagement_score": engagement,
            "mastery_updates": mastery_updates,
            "mental_block_signals": mental_block_signals,
            "parent_summary": parent_summary,
            "tutor_insight": tutor_insight,
            "recommended_next": recommended_next,
        }

    # ──────────────────────────────────────────
    # PRIVATE HELPERS
    # ──────────────────────────────────────────

    def _extract_goals(self, lower: str, lines: list) -> List[Dict]:
        """Extract explicit and implicit goals from trial transcript."""
        goals = []
        seen = set()

        # Explicit goal extraction
        goal_patterns = [
            r"(?:goal|objective|target|aim|want to|hope to|need to|would like to)\s*(?:is|are|:)?\s*(.+?)(?:\.|$)",
            r"(?:we want|i want|she wants|he wants)\s+(?:him|her|them|to)\s*(.+?)(?:\.|$)",
            r"(?:improve|get better at|work on|focus on|master)\s+(.+?)(?:\.|$)",
        ]

        for pattern in goal_patterns:
            for match in re.finditer(pattern, lower):
                desc = match.group(1).strip().capitalize()
                if len(desc) > 10 and desc.lower() not in seen:
                    seen.add(desc.lower())
                    goals.append({
                        "description": desc,
                        "measurable_outcome": self._infer_outcome(desc),
                        "deadline": None
                    })

        # Implicit goals from topic mentions
        topics = self._detect_topics(lower)
        for topic in topics[:3]:
            desc = f"Build proficiency in {topic}"
            if desc.lower() not in seen:
                seen.add(desc.lower())
                goals.append({
                    "description": desc,
                    "measurable_outcome": f"Score 80%+ on {topic} assessments",
                    "deadline": None
                })

        # Ensure at least one goal
        if not goals:
            goals.append({
                "description": "Build overall math proficiency",
                "measurable_outcome": "Demonstrate consistent improvement across sessions",
                "deadline": None,
            })

        return goals[:6]  # Cap at 6 goals

    def _detect_topics(self, lower: str) -> List[str]:
        """Detect math topics mentioned in transcript."""
        found = []
        for topic, keywords in TOPIC_KEYWORDS.items():
            for kw in keywords:
                if kw in lower:
                    if topic not in found:
                        found.append(topic)
                    break
        return found

    def _get_parent_topic(self, topic: str) -> str:
        """Map sub-topics to parent topics."""
        parent_map = {
            "Linear Equations": "Algebra",
            "Expressions & Simplification": "Algebra",
            "Inequalities": "Algebra",
            "Fractions": "Number Sense",
            "Decimals": "Number Sense",
            "Ratios & Proportions": "Number Sense",
            "Angles & Triangles": "Geometry",
            "Area & Perimeter": "Geometry",
            "Rate Problems": "Word Problems",
            "Age Problems": "Word Problems",
            "Exponents": "Algebra",
            "Probability": "Statistics",
        }
        return parent_map.get(topic)

    def _infer_curriculum(self, lower: str) -> str:
        """Infer curriculum/target from transcript."""
        if any(w in lower for w in ["amc", "competition", "olympiad", "mathcounts"]):
            return "Competition Math (AMC/MathCounts)"
        elif any(w in lower for w in ["sat", "act", "psat"]):
            return "SAT/ACT Prep"
        elif any(w in lower for w in ["common core", "state test", "school"]):
            return "Common Core Aligned"
        elif any(w in lower for w in ["ap", "calculus", "advanced"]):
            return "Advanced / AP Prep"
        return "General Math Proficiency"

    def _infer_outcome(self, goal_desc: str) -> str:
        """Generate a measurable outcome from a goal description."""
        lower = goal_desc.lower()
        if any(w in lower for w in ["score", "grade", "test"]):
            return "Achieve target score on relevant assessment"
        if any(w in lower for w in ["speed", "fast", "quick"]):
            return "Complete timed practice within target duration"
        if any(w in lower for w in ["understand", "concept", "foundation"]):
            return "Demonstrate conceptual understanding through explanation tasks"
        return "Show measurable improvement over 4 consecutive sessions"

    def _detect_misconceptions(self, lower: str) -> List[str]:
        """Detect misconceptions from transcript patterns."""
        found = []
        for pattern in MISCONCEPTION_SIGNALS:
            matches = re.findall(pattern, lower)
            if matches:
                for m in matches[:2]:
                    # Get surrounding context
                    idx = lower.find(m if isinstance(m, str) else m)
                    start = max(0, idx - 30)
                    end = min(len(lower), idx + len(m) + 50)
                    context = lower[start:end].strip()
                    found.append(context)
        return found[:5]

    def _detect_strengths(self, lower: str) -> List[str]:
        """Detect strength signals from transcript."""
        found = []
        for pattern in STRENGTH_SIGNALS:
            matches = re.findall(pattern, lower)
            for m in matches[:2]:
                found.append(m.strip())
        return found[:5]

    def _score_engagement(self, lower: str) -> float:
        """Score engagement from 0-100 based on language signals."""
        positive = sum(1 for p in ENGAGEMENT_POSITIVE if p in lower)
        negative = sum(1 for p in ENGAGEMENT_NEGATIVE if p in lower)

        # Base engagement from transcript length (longer = more engagement)
        word_count = len(lower.split())
        length_score = min(40, word_count / 10)

        engagement = 50 + length_score + (positive * 8) - (negative * 12)
        return max(0, min(100, round(engagement, 1)))

    def _compute_mastery_signals(self, lower: str, topics: list,
                                 misconceptions: list, strengths: list) -> List[Dict]:
        """Compute mastery update signals per topic."""
        updates = []
        error_count = len(misconceptions)
        independent_count = sum(1 for s in strengths if any(w in s for w in
                                ["by myself", "on my own", "i got it", "let me try"]))

        for topic in topics:
            improvement = 0.3 if len(strengths) > len(misconceptions) else 0.1
            updates.append({
                "topic": topic,
                "improvement": improvement,
                "errors": min(error_count, 3),
                "independent_solves": independent_count,
            })
        return updates

    def _generate_parent_summary(self, topics: list, strengths: list,
                                 misconceptions: list, engagement: float) -> str:
        """Generate a parent-friendly summary."""
        parts = []
        if topics:
            parts.append(f"Today we worked on: {', '.join(topics[:3])}.")
        if strengths:
            parts.append(f"Your child showed strength in understanding key concepts.")
        if misconceptions:
            parts.append(f"We identified {len(misconceptions)} area(s) that need more practice.")
        if engagement >= 70:
            parts.append("Engagement was great today!")
        elif engagement >= 50:
            parts.append("Engagement was steady.")
        else:
            parts.append("We're working on building more engagement and motivation.")
        parts.append("Looking forward to continued progress next session!")
        return " ".join(parts)

    def _generate_tutor_insight(self, topics: list, misconceptions: list,
                                strengths: list, mental_blocks: list) -> str:
        """Generate technical tutor insight."""
        parts = []
        parts.append(f"Topics covered: {', '.join(topics) if topics else 'General review'}.")
        if misconceptions:
            parts.append(f"Misconceptions detected ({len(misconceptions)}): "
                         f"Focus on conceptual reinforcement before procedural practice.")
        if strengths:
            parts.append(f"Positive signals ({len(strengths)}): "
                         f"Student showing readiness to advance on demonstrated topics.")
        if mental_blocks:
            parts.append(f"⚠️ Mental block signals ({len(mental_blocks)}): "
                         f"Consider scaffolding approach and confidence-building exercises.")
        return " ".join(parts)

    def _generate_recommendation(self, topics: list, misconceptions: list,
                                 mastery_updates: list) -> str:
        """Generate next session recommendation."""
        if misconceptions:
            return (f"Recommended: Revisit concepts with errors using scaffolded examples. "
                    f"Start with guided practice before independent work.")
        if mastery_updates:
            low_mastery = [u for u in mastery_updates if u["improvement"] < 0.3]
            if low_mastery:
                return f"Recommended: Focus on strengthening {low_mastery[0]['topic']} with varied problem types."
        if topics:
            return f"Recommended: Build on today's progress — introduce next-level problems in {topics[0]}."
        return "Recommended: Review previous session topics and assess readiness for new material."

    def _generate_trial_summary(self, goals: list, topics: list, curriculum: str) -> str:
        """Generate a summary for trial session processing."""
        parts = [f"Curriculum track: {curriculum}."]
        if goals:
            parts.append(f"Identified {len(goals)} learning goal(s).")
        if topics:
            parts.append(f"Key topic areas: {', '.join(topics[:4])}.")
        parts.append("Initial assessment complete — ready for structured lesson planning.")
        return " ".join(parts)
