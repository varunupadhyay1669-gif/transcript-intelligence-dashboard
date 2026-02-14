"""Mastery score update formula — transparent and adjustable."""

# ──────────────────────────────────────────────
# CONFIGURABLE WEIGHTS (adjust as needed)
# ──────────────────────────────────────────────
IMPROVEMENT_WEIGHT = 5.0       # Points per improvement signal
ERROR_PENALTY_WEIGHT = 3.0     # Points deducted per error signal
INDEPENDENT_SOLVE_BONUS = 4.0  # Points per independent solve signal
MAX_SCORE = 100.0
MIN_SCORE = 0.0


def update_mastery(prev_score: float, improvement_factor: float,
                   error_count: int, independent_solves: int) -> float:
    """
    Compute updated mastery score.

    Formula:
        new = prev + (improvement × 5) - (errors × 3) + (independent_solves × 4)

    All values are clamped to [0, 100].

    Args:
        prev_score: Current mastery score (0-100)
        improvement_factor: Normalized improvement signal (0.0-1.0)
        error_count: Number of errors detected in session
        independent_solves: Number of problems solved independently

    Returns:
        Updated mastery score clamped to [0, 100]
    """
    delta = (
        (improvement_factor * IMPROVEMENT_WEIGHT)
        - (error_count * ERROR_PENALTY_WEIGHT)
        + (independent_solves * INDEPENDENT_SOLVE_BONUS)
    )
    new_score = prev_score + delta
    return max(MIN_SCORE, min(MAX_SCORE, round(new_score, 1)))


def update_confidence(prev_confidence: float, hesitation_count: int,
                      positive_signals: int) -> float:
    """
    Update confidence score based on session signals.

    Args:
        prev_confidence: Current confidence score (0-100)
        hesitation_count: Number of hesitation/avoidance signals
        positive_signals: Number of confident language signals

    Returns:
        Updated confidence score clamped to [0, 100]
    """
    delta = (positive_signals * 3.0) - (hesitation_count * 4.0)
    new_score = prev_confidence + delta
    return max(MIN_SCORE, min(MAX_SCORE, round(new_score, 1)))
