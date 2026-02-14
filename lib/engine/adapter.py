"""Abstract transcript processor interface — swap implementations here."""
from abc import ABC, abstractmethod
from typing import Dict, Any


class TranscriptProcessor(ABC):
    """Interface for transcript processing adapters."""

    @abstractmethod
    def process_trial(self, transcript: str, student_id: int) -> Dict[str, Any]:
        """
        Process a trial/intake transcript.
        Returns:
            {
                "goals": [{"description": str, "measurable_outcome": str, "deadline": str|None}],
                "topics": [{"name": str, "parent": str|None}],
                "summary": str,
                "curriculum_recommendation": str
            }
        """
        pass

    @abstractmethod
    def process_session(self, transcript: str, student_id: int) -> Dict[str, Any]:
        """
        Process a session transcript.
        Returns:
            {
                "topics_discussed": [str],
                "misconceptions": [str],
                "strengths": [str],
                "engagement_score": float,
                "mastery_updates": [{"topic": str, "improvement": float, "errors": int, "independent_solves": int}],
                "mental_block_signals": [{"description": str, "severity": float}],
                "parent_summary": str,
                "tutor_insight": str,
                "recommended_next": str
            }
        """
        pass
