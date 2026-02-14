"""Mental block detection and severity scoring."""

ESCALATION_THRESHOLD = 3  # Sessions before severity escalates
SEVERITY_INCREMENT = 1.5
MAX_SEVERITY = 10.0

# Language signals indicating mental blocks
AVOIDANCE_PHRASES = [
    "i don't want to",
    "can we skip",
    "i hate",
    "not this again",
    "this is too hard",
    "i can't do this",
    "i'll never get",
    "let's do something else",
    "i give up",
    "this is boring",
    "do we have to",
]

HESITATION_PHRASES = [
    "i'm not sure",
    "i don't know",
    "wait",
    "umm",
    "uh",
    "i think maybe",
    "i forgot",
    "is it",
    "i'm confused",
    "what do you mean",
    "i don't understand",
    "can you explain again",
]

EMOTIONAL_PHRASES = [
    "i'm stressed",
    "i'm nervous",
    "i feel dumb",
    "everyone else gets it",
    "i'm so lost",
    "my brain hurts",
    "i'm going to fail",
    "i feel stupid",
]


def detect_mental_block_signals(transcript_lower: str) -> list:
    """
    Scan transcript for mental block signals.

    Returns list of:
        {"description": str, "type": "avoidance"|"hesitation"|"emotional", "severity": float}
    """
    signals = []

    for phrase in AVOIDANCE_PHRASES:
        if phrase in transcript_lower:
            signals.append({
                "description": f"Avoidance language detected: '{phrase}'",
                "type": "avoidance",
                "severity": 3.0
            })

    for phrase in EMOTIONAL_PHRASES:
        if phrase in transcript_lower:
            signals.append({
                "description": f"Emotional distress signal: '{phrase}'",
                "type": "emotional",
                "severity": 4.0
            })

    # Count hesitation density
    hesitation_count = sum(1 for p in HESITATION_PHRASES if p in transcript_lower)
    if hesitation_count >= 3:
        signals.append({
            "description": f"High hesitation density ({hesitation_count} signals)",
            "type": "hesitation",
            "severity": 2.0 + (hesitation_count * 0.5)
        })

    return signals


def compute_severity(frequency_count: int, has_avoidance: bool,
                     has_emotional: bool) -> float:
    """
    Compute mental block severity score.

    Severity increases when:
    - Same confusion appears 3+ sessions (frequency_count >= 3)
    - Student expresses avoidance language
    - Emotional hesitation detected

    Returns severity score clamped to [0, 10]
    """
    base = min(frequency_count * 1.0, 5.0)

    if frequency_count >= ESCALATION_THRESHOLD:
        base += SEVERITY_INCREMENT

    if has_avoidance:
        base += 2.0

    if has_emotional:
        base += 1.5

    return min(base, MAX_SEVERITY)
