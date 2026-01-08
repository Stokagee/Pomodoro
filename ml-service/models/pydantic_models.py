"""
Pydantic Models for FocusAI Structured Output

These models ensure reliable JSON output from Ollama by using
the format=Model.model_json_schema() parameter.
"""

from pydantic import BaseModel, Field
from typing import List, Optional
from enum import Enum
from datetime import datetime


class Priority(str, Enum):
    """Priority level for recommendations"""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class CategoryStatus(str, Enum):
    """Category balance status"""
    TOO_MUCH = "too_much"
    BALANCED = "balanced"
    TOO_LITTLE = "too_little"


class SkillGap(BaseModel):
    """Identified skill gap in user's profile"""
    category: str = Field(description="Category name (e.g., Coding, Learning)")
    current_level: int = Field(ge=1, le=5, description="Current skill level 1-5")
    recommended_level: int = Field(ge=1, le=5, description="Recommended target level")
    gap_description: str = Field(description="Description of the gap in Czech")
    importance: Priority = Field(description="How important is this gap to address")


class TopicSuggestion(BaseModel):
    """Suggested topic for learning"""
    topic: str = Field(description="Specific topic to learn (e.g., 'React hooks', 'Python async')")
    category: str = Field(description="Which category this belongs to")
    reason: str = Field(description="Why this topic is recommended, in Czech")
    priority: Priority = Field(description="Priority of this suggestion")
    estimated_sessions: int = Field(ge=1, le=20, description="Estimated sessions to complete")
    related_to: Optional[str] = Field(default=None, description="Related topic user already knows")


class CategoryBalance(BaseModel):
    """Analysis of category time distribution"""
    category: str = Field(description="Category name")
    current_percentage: float = Field(ge=0, le=100, description="Current percentage of time")
    recommended_percentage: float = Field(ge=0, le=100, description="Recommended percentage")
    status: CategoryStatus = Field(description="Whether this category needs more or less attention")


class SessionSuggestion(BaseModel):
    """Quick suggestion for next session"""
    category: str = Field(description="Suggested category")
    topic: str = Field(description="Suggested topic/task")
    preset: str = Field(description="Recommended preset (deep_work, standard, short_focus)")
    reason: str = Field(description="Why this is suggested, in Czech")
    confidence: float = Field(ge=0, le=1, description="AI confidence in this suggestion")


class UserKnowledge(BaseModel):
    """Extracted knowledge from user's task history"""
    technologies: List[str] = Field(default_factory=list, description="Technologies user works with")
    concepts: List[str] = Field(default_factory=list, description="Concepts user is learning")
    expertise_areas: List[str] = Field(default_factory=list, description="Areas of expertise")


class LearningRecommendation(BaseModel):
    """Complete learning recommendation from FocusAI"""
    skill_gaps: List[SkillGap] = Field(default_factory=list, description="Identified skill gaps")
    recommended_topics: List[TopicSuggestion] = Field(default_factory=list, description="Topics to learn")
    category_balance: List[CategoryBalance] = Field(default_factory=list, description="Category analysis")
    personalized_tips: List[str] = Field(default_factory=list, description="Personalized tips in Czech")
    next_session_suggestion: SessionSuggestion = Field(description="Immediate next session suggestion")
    user_knowledge: UserKnowledge = Field(description="Extracted user knowledge")
    motivational_message: str = Field(description="Motivational message in Czech")
    analysis_summary: str = Field(description="Summary of analysis in Czech")
    generated_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    confidence_score: float = Field(ge=0, le=1, description="Overall confidence in recommendations")


class ProductivityPattern(BaseModel):
    """Productivity pattern analysis"""
    best_hours: List[int] = Field(description="Most productive hours (0-23)")
    worst_hours: List[int] = Field(description="Least productive hours")
    best_day: str = Field(description="Most productive day of week")
    avg_sessions_per_day: float = Field(description="Average sessions per day")
    consistency_score: float = Field(ge=0, le=1, description="How consistent is the user")


class PatternAnalysis(BaseModel):
    """Complete pattern analysis"""
    productivity: ProductivityPattern
    recommendations: List[str] = Field(description="Recommendations based on patterns")
    warnings: List[str] = Field(default_factory=list, description="Potential issues detected")


# Fallback models for when AI is unavailable
class FallbackSuggestion:
    """Static fallback suggestions when Ollama is unavailable"""

    @staticmethod
    def get_session_suggestion(category: str = None, hour: int = 12) -> dict:
        """Get a fallback session suggestion"""
        suggestions = [
            {"category": "Coding", "topic": "Code review a refaktoring", "preset": "deep_work",
             "reason": "Pravidelny code review zlepsuje kvalitu kodu", "confidence": 0.5},
            {"category": "Learning", "topic": "Dokumentace a tutorialy", "preset": "standard",
             "reason": "Uceni novych technologii rozsiruje moznosti", "confidence": 0.5},
            {"category": "Planning", "topic": "Sprint planning a organizace", "preset": "short_focus",
             "reason": "Dobre planovani setri cas", "confidence": 0.5},
            {"category": "Writing", "topic": "Technicka dokumentace", "preset": "deep_work",
             "reason": "Dokumentace je dulezita pro tym", "confidence": 0.5},
        ]

        # Time-based selection
        if 6 <= hour < 12:
            # Morning - creative work
            return suggestions[0]
        elif 12 <= hour < 17:
            # Afternoon - learning
            return suggestions[1]
        else:
            # Evening - planning
            return suggestions[2]

    @staticmethod
    def get_learning_recommendation() -> dict:
        """Get a fallback learning recommendation"""
        return {
            "skill_gaps": [],
            "recommended_topics": [
                {
                    "topic": "Prozkoumat nove technologie",
                    "category": "Learning",
                    "reason": "Pravidelne uceni udrzuje znalosti aktualni",
                    "priority": "medium",
                    "estimated_sessions": 5,
                    "related_to": None
                }
            ],
            "category_balance": [],
            "personalized_tips": [
                "Zkuste stridavat ruzne typy prace pro lepsi produktivitu",
                "Pravidelne prestavky pomahaji udrzet soustredeni"
            ],
            "next_session_suggestion": {
                "category": "Learning",
                "topic": "Osobni rozvoj",
                "preset": "standard",
                "reason": "Vzdy je dobry cas pro uceni",
                "confidence": 0.3
            },
            "user_knowledge": {
                "technologies": [],
                "concepts": [],
                "expertise_areas": []
            },
            "motivational_message": "Kazda session te priblizuje k tvym cilum!",
            "analysis_summary": "Pro detailnejsi analyzu potrebuji vice dat o tvych sessions.",
            "generated_at": datetime.now().isoformat(),
            "confidence_score": 0.3
        }
