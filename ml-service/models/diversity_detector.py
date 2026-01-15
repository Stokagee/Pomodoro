"""
Diversity Detector - Detekuje kdy uživatel dělal příliš mnoho stejné kategorie/topicu.

Poskytuje "task burnout detection" pro AI suggestions - pomáhá vyhnout se
návrhům na úkoly kterými se uživatel právě unavil.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional
from collections import defaultdict, Counter
import re
import logging

logger = logging.getLogger(__name__)


class DiversityDetector:
    """Detekuje category/topic concentration pro variety v AI suggestions."""

    # Priority categories podle job hunting kontextu
    PRIORITY_CATEGORIES = [
        "Job Hunting",      # Priority #1
        "Skill Building",   # Priority #2
        "Learning",         # Priority #3
        "Coding",
        "Database",
        "Other"
    ]

    # Default categories pokud uživatel nemá vlastní
    DEFAULT_CATEGORIES = [
        "Job Hunting",
        "Skill Building",
        "Learning",
        "Coding",
        "Database"
    ]

    def __init__(self, categories: List[str] = None):
        """
        Initialize DiversityDetector.

        Args:
            categories: User's configured categories (from config.json)
        """
        self.categories = categories or self.DEFAULT_CATEGORIES
        logger.info(f"DiversityDetector initialized with {len(self.categories)} categories")

    def detect_category_overload(
        self,
        sessions: List[Dict],
        days: int = 2,
        threshold: float = 0.70
    ) -> Dict:
        """
        Analyzuje sessions a detekuje category concentration.

        Args:
            sessions: List of session documents from database
            days: Kolik dní zpátky analyzovat (default: 2)
            threshold: Percentage threshold pro overload (default: 0.70 = 70%)

        Returns:
            {
                "overloaded_categories": ["Coding"],
                "overload_reason": "Včera 5/5 sessions na Coding (REST API)",
                "avoid_categories": ["Coding"],
                "recommended_alternatives": ["Database", "Job Hunting"],
                "confidence": 0.9,
                "reasoning": "Detekován category burnout: Včera 100% sessions na Coding",
                "category_distribution": {"Coding": 5, "Database": 0, ...},
                "analysis_days": 2
            }
        """
        if not sessions:
            return self._no_data_response()

        # 1. Získat sessions z posledních X dní
        cutoff_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
        recent_sessions = [
            s for s in sessions
            if s.get('date', '') >= cutoff_date
        ]

        if not recent_sessions:
            return self._no_data_response(days)

        # 2. Analyzovat category distribution
        category_counts = Counter(s.get('category', 'Unknown') for s in recent_sessions)
        total_sessions = len(recent_sessions)

        # 3. Detekovat overloaded categories
        overloaded = []
        for category, count in category_counts.items():
            concentration = count / total_sessions
            if concentration > threshold:
                overloaded.append({
                    'category': category,
                    'count': count,
                    'concentration': concentration,
                    'sessions': count
                })

        # 4. Analyzovat consecutive repeats
        consecutive = self._detect_consecutive_repeats(recent_sessions, threshold)

        # 5. Analyzovat topic burnout z notes
        topic_burnout = self._detect_topic_burnout(recent_sessions)

        # 6. Sestavit výsledek
        if not overloaded and not consecutive and not topic_burnout:
            return self._no_overload_response(category_counts, total_sessions, days)

        return self._build_overload_response(
            overloaded,
            consecutive,
            topic_burnout,
            category_counts,
            total_sessions,
            days
        )

    def _detect_consecutive_repeats(
        self,
        sessions: List[Dict],
        threshold: float
    ) -> Optional[Dict]:
        """
        Detekuje když stejná kategorie se opakuje v řadě.

        Args:
            sessions: Seřazené sessions podle času (nejnovější první)
            threshold: Concentration threshold

        Returns:
            None nebo dict s consecutive info
        """
        if len(sessions) < 3:
            return None

        # Seskupit sessions podle date a seřadit
        by_date = defaultdict(list)
        for s in sessions:
            by_date[s['date']].append(s)

        # Pro každý den, zkontrolovat consecutive
        for date, day_sessions in by_date.items():
            if len(day_sessions) < 3:
                continue

            # Check first 3 sessions
            first_three = day_sessions[:3]
            categories = [s.get('category', 'Unknown') for s in first_three]

            if len(set(categories)) == 1:  # All same category
                return {
                    'category': categories[0],
                    'consecutive_count': 3,
                    'date': date
                }

        return None

    def _detect_topic_burnout(self, sessions: List[Dict]) -> Optional[Dict]:
        """
        Detekuje když stejný topic se opakuje v notes.

        Args:
            sessions: List of sessions with notes

        Returns:
            None nebo dict s topic burnout info
        """
        # Extrahovat topics z notes (keywords)
        topic_keywords = Counter()

        for session in sessions:
            notes = session.get('notes', '')
            if not notes:
                continue

            # Extrahovat klíčová slova (2+ characters, lowercase)
            words = re.findall(r'\b[a-z]{2,}\b', notes.lower())

            # Filtrovat běžná slova
            stop_words = {
                'the', 'and', 'for', 'are', 'but', 'not', 'you', 'all', 'can',
                'had', 'her', 'was', 'one', 'our', 'out', 'has', 'been', 'there',
                'use', 'any', 'this', 'that', 'with', 'they', 'from', 'have', 'been'
            }

            meaningful_words = [w for w in words if w not in stop_words and len(w) > 2]
            topic_keywords.update(meaningful_words)

        # Check top topics
        if not topic_keywords:
            return None

        top_topic, count = topic_keywords.most_common(1)[0]

        if count >= 3:  # Topic appears 3+ times
            return {
                'topic': top_topic,
                'occurrence_count': count
            }

        return None

    def _get_recommended_alternatives(
        self,
        overloaded_categories: List[str],
        category_counts: Counter,
        days: int = 14
    ) -> List[str]:
        """
        Vybere alternativní kategorie (Smart Mix: priority + least used).

        Args:
            overloaded_categories: Které kategorie se mají vyhnout
            category_counts: Current category counts
            days: Kolik dní zpátky brát v úvahu pro "least used"

        Returns:
            List of recommended alternative categories
        """
        # Get least used categories
        available = [cat for cat in self.categories if cat not in overloaded_categories]

        if not available:
            return []

        # Filter by priority (top 3 priorities)
        priority_alternatives = [cat for cat in self.PRIORITY_CATEGORIES if cat in available]

        # Limit to top 3
        return priority_alternatives[:3]

    def _build_overload_response(
        self,
        overloaded: List[Dict],
        consecutive: Optional[Dict],
        topic_burnout: Optional[Dict],
        category_counts: Counter,
        total_sessions: int,
        days: int
    ) -> Dict:
        """Sestaví response když je detekován overload."""

        # Identify categories to avoid
        avoid_categories = []
        overload_reasons = []

        if overloaded:
            for item in overloaded:
                avoid_categories.append(item['category'])
                pct = int(item['concentration'] * 100)
                overload_reasons.append(
                    f"{item['count']}/{total_sessions} sessions na {item['category']} ({pct}%)"
                )

        if consecutive and consecutive['category'] not in avoid_categories:
            avoid_categories.append(consecutive['category'])
            overload_reasons.append(
                f"3x po sobě na {consecutive['category']} v {consecutive['date']}"
            )

        # Build reason
        if topic_burnout:
            topic = topic_burnout['topic']
            count = topic_burnout['occurrence_count']
            overload_reasons.append(f"Topic '{topic}' se opakuje {count}x v notes")

        overload_reason = " | ".join(overload_reasons)

        # Get alternatives
        recommended_alternatives = self._get_recommended_alternatives(
            avoid_categories,
            category_counts
        )

        # Build reasoning
        reasoning_parts = []
        if overloaded:
            reasoning_parts.append(f"Detekován category burnout: Včera {overload_reasons[0]}")
        if consecutive:
            reasoning_parts.append(f"Consecutive repeats: {consecutive['category']} 3x v řadě")
        if topic_burnout:
            reasoning_parts.append(f"Topic burnout: '{topic_burnout['topic']}' se opakuje")

        reasoning = " | ".join(reasoning_parts)

        return {
            "overloaded_categories": avoid_categories,
            "overload_reason": overload_reason,
            "avoid_categories": avoid_categories,
            "recommended_alternatives": recommended_alternatives,
            "confidence": 0.9,
            "reasoning": reasoning,
            "category_distribution": dict(category_counts),
            "analysis_days": days,
            "total_sessions_analyzed": total_sessions
        }

    def _no_overload_response(
        self,
        category_counts: Counter,
        total_sessions: int,
        days: int
    ) -> Dict:
        """Response když není detekován overload."""
        return {
            "overloaded_categories": [],
            "overload_reason": "",
            "avoid_categories": [],
            "recommended_alternatives": [],
            "confidence": 0.0,
            "reasoning": "No category burnout detected",
            "category_distribution": dict(category_counts),
            "analysis_days": days,
            "total_sessions_analyzed": total_sessions
        }

    def _no_data_response(self, days: int = 2) -> Dict:
        """Response když není dostatek dat."""
        return {
            "overloaded_categories": [],
            "overload_reason": "",
            "avoid_categories": [],
            "recommended_alternatives": self.PRIORITY_CATEGORIES[:3],
            "confidence": 0.0,
            "reasoning": f"Insufficient data for analysis (need sessions from last {days} days)",
            "category_distribution": {},
            "analysis_days": days,
            "total_sessions_analyzed": 0
        }