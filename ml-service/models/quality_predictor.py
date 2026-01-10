"""
Session Quality Predictor.
Predicts expected productivity before a session starts based on multiple factors.
"""
from typing import List, Dict, Optional, Tuple
from datetime import datetime


class SessionQualityPredictor:
    """
    Predicts session quality/productivity before starting.
    Uses 6 weighted factors from historical data.
    """

    # Factor weights
    WEIGHTS = {
        'hour': 0.25,
        'day': 0.15,
        'preset': 0.20,
        'category': 0.15,
        'fatigue': 0.15,
        'recovery': 0.10
    }

    # Czech day names
    DAY_NAMES = ['Pondeli', 'Utery', 'Streda', 'Ctvrtek', 'Patek', 'Sobota', 'Nedele']

    # Preset info
    PRESETS = {
        'deep_work': {'name': 'Deep Work', 'work': 52, 'break': 17},
        'learning': {'name': 'Learning', 'work': 45, 'break': 15},
        'quick_tasks': {'name': 'Quick Tasks', 'work': 25, 'break': 5},
        'flow_mode': {'name': 'Flow Mode', 'work': 90, 'break': 20}
    }

    def __init__(self, sessions: List[dict]):
        """Initialize with historical sessions."""
        self.sessions = sessions
        self.completed_sessions = [s for s in sessions if s.get('completed', False)]

    def _normalize_rating(self, rating) -> Optional[float]:
        """Normalize rating to 0-100 scale."""
        if rating is None:
            return None
        if isinstance(rating, (int, float)):
            if 1 <= rating <= 5:
                return rating * 20  # Old 1-5 scale
            return float(rating)
        return None

    # =========================================================================
    # Factor 1: Hour Score (weight: 0.25)
    # =========================================================================
    def _calculate_hour_score(self, hour: int) -> Tuple[float, float]:
        """Calculate productivity score for given hour."""
        hour_sessions = [s for s in self.completed_sessions if s.get('hour') == hour]

        if not hour_sessions:
            return self._get_default_hour_score(hour), 0.1

        ratings = [self._normalize_rating(s.get('productivity_rating'))
                   for s in hour_sessions if s.get('productivity_rating') is not None]

        if not ratings:
            return self._get_default_hour_score(hour), 0.2

        avg_rating = sum(ratings) / len(ratings)
        confidence = min(1.0, len(ratings) / 10)

        return avg_rating, confidence

    def _get_default_hour_score(self, hour: int) -> float:
        """Default circadian rhythm scores."""
        if 8 <= hour <= 11:
            return 80.0  # Morning peak
        elif 12 <= hour <= 13:
            return 65.0  # Lunch dip
        elif 14 <= hour <= 17:
            return 75.0  # Afternoon
        elif 18 <= hour <= 20:
            return 70.0  # Evening
        elif 21 <= hour <= 23:
            return 55.0  # Late night
        elif 6 <= hour <= 7:
            return 65.0  # Early morning
        else:
            return 50.0  # Very early/late

    # =========================================================================
    # Factor 2: Day Score (weight: 0.15)
    # =========================================================================
    def _calculate_day_score(self, day: int) -> Tuple[float, float]:
        """Calculate productivity score for given day of week."""
        day_sessions = [s for s in self.completed_sessions if s.get('day_of_week') == day]

        if not day_sessions:
            return self._get_default_day_score(day), 0.1

        ratings = [self._normalize_rating(s.get('productivity_rating'))
                   for s in day_sessions if s.get('productivity_rating') is not None]

        if not ratings:
            return self._get_default_day_score(day), 0.2

        avg_rating = sum(ratings) / len(ratings)
        confidence = min(1.0, len(ratings) / 15)

        return avg_rating, confidence

    def _get_default_day_score(self, day: int) -> float:
        """Default weekday scores - all days equal (no weekend penalty)."""
        return 70.0

    # =========================================================================
    # Factor 3: Preset Score (weight: 0.20)
    # =========================================================================
    def _calculate_preset_score(self, preset: str, hour: int) -> Tuple[float, float]:
        """Calculate how well this preset performs at this hour."""
        # Preset + hour combination
        preset_hour_sessions = [s for s in self.completed_sessions
                                if s.get('preset') == preset and s.get('hour') == hour]

        if preset_hour_sessions:
            ratings = [self._normalize_rating(s.get('productivity_rating'))
                       for s in preset_hour_sessions if s.get('productivity_rating') is not None]
            if ratings:
                return sum(ratings) / len(ratings), min(1.0, len(ratings) / 5)

        # Fallback: preset overall
        preset_sessions = [s for s in self.completed_sessions if s.get('preset') == preset]

        if preset_sessions:
            ratings = [self._normalize_rating(s.get('productivity_rating'))
                       for s in preset_sessions if s.get('productivity_rating') is not None]
            if ratings:
                return sum(ratings) / len(ratings), min(0.7, len(ratings) / 10)

        # Default preset scores
        defaults = {
            'deep_work': 75.0,
            'learning': 70.0,
            'quick_tasks': 65.0,
            'flow_mode': 72.0
        }
        return defaults.get(preset, 70.0), 0.1

    # =========================================================================
    # Factor 4: Category Score (weight: 0.15)
    # =========================================================================
    def _calculate_category_score(self, category: Optional[str], hour: int) -> Tuple[float, float]:
        """Calculate productivity for this category at this hour."""
        if not category:
            return 70.0, 0.1

        # Category + hour combination
        cat_hour_sessions = [s for s in self.completed_sessions
                            if s.get('category') == category and s.get('hour') == hour]

        if cat_hour_sessions:
            ratings = [self._normalize_rating(s.get('productivity_rating'))
                       for s in cat_hour_sessions if s.get('productivity_rating') is not None]
            if ratings:
                return sum(ratings) / len(ratings), min(1.0, len(ratings) / 5)

        # Fallback: category overall
        cat_sessions = [s for s in self.completed_sessions if s.get('category') == category]

        if cat_sessions:
            ratings = [self._normalize_rating(s.get('productivity_rating'))
                       for s in cat_sessions if s.get('productivity_rating') is not None]
            if ratings:
                return sum(ratings) / len(ratings), min(0.7, len(ratings) / 8)

        return 70.0, 0.1

    # =========================================================================
    # Factor 5: Fatigue Score (weight: 0.15)
    # =========================================================================
    def _calculate_fatigue_score(self, sessions_today: int) -> Tuple[float, float]:
        """Calculate productivity decline based on session count."""
        # Analyze historical pattern
        daily_sessions = {}
        for s in self.completed_sessions:
            date = s.get('date')
            if date:
                if date not in daily_sessions:
                    daily_sessions[date] = []
                daily_sessions[date].append(s)

        # Sort each day's sessions by hour
        for date in daily_sessions:
            daily_sessions[date].sort(key=lambda x: x.get('hour', 0))

        # Calculate avg productivity for nth session
        nth_session_ratings = {}
        for date, sessions in daily_sessions.items():
            for i, s in enumerate(sessions):
                n = i + 1
                rating = self._normalize_rating(s.get('productivity_rating'))
                if rating is not None:
                    if n not in nth_session_ratings:
                        nth_session_ratings[n] = []
                    nth_session_ratings[n].append(rating)

        # Get expected productivity for next session
        next_session_num = sessions_today + 1

        if next_session_num in nth_session_ratings:
            ratings = nth_session_ratings[next_session_num]
            return sum(ratings) / len(ratings), min(1.0, len(ratings) / 5)

        # Default fatigue curve
        fatigue_defaults = {
            1: 75.0, 2: 80.0, 3: 78.0, 4: 72.0,
            5: 68.0, 6: 62.0, 7: 55.0, 8: 50.0
        }
        return fatigue_defaults.get(next_session_num, max(45.0, 80 - next_session_num * 5)), 0.1

    # =========================================================================
    # Factor 6: Recovery Score (weight: 0.10)
    # =========================================================================
    def _calculate_recovery_score(self, minutes_since_last: Optional[int]) -> Tuple[float, float]:
        """Calculate productivity based on break duration."""
        if minutes_since_last is None:
            return 75.0, 0.1  # First session of day

        if minutes_since_last < 5:
            return 55.0, 0.5  # No break
        elif minutes_since_last < 15:
            return 68.0, 0.5  # Short break
        elif minutes_since_last <= 30:
            return 82.0, 0.6  # Optimal
        elif minutes_since_last <= 60:
            return 80.0, 0.5  # Good
        elif minutes_since_last <= 120:
            return 75.0, 0.4  # Longer break
        elif minutes_since_last <= 240:
            return 70.0, 0.3  # Extended break
        else:
            return 65.0, 0.2  # Cold start

    # =========================================================================
    # Factors List Builder
    # =========================================================================
    def _build_factors_list(self, scores: Dict, preset: str, sessions_today: int,
                            minutes_since_last: Optional[int]) -> List[dict]:
        """Build list of factors affecting prediction."""
        factors = []

        # Positive factors
        if scores['hour']['score'] >= 75:
            factors.append({
                'type': 'positive',
                'name': 'Vhodna denni doba',
                'description': f"Obvykle {scores['hour']['score']:.0f}% produktivita v tuto hodinu",
                'impact': 'high' if scores['hour']['score'] >= 80 else 'medium'
            })

        if scores['preset']['score'] >= 75:
            preset_name = self.PRESETS.get(preset, {}).get('name', preset)
            factors.append({
                'type': 'positive',
                'name': f'Dobre vysledky s {preset_name}',
                'description': f"Prumerne {scores['preset']['score']:.0f}% produktivita",
                'impact': 'medium'
            })

        if scores['recovery']['score'] >= 80:
            factors.append({
                'type': 'positive',
                'name': 'Optimalni pauza',
                'description': 'Dobre zotaveni od posledni session',
                'impact': 'medium'
            })

        # Negative factors
        if scores['hour']['score'] < 60:
            factors.append({
                'type': 'negative',
                'name': 'Nevhodna denni doba',
                'description': f"Obvykle nizsi produktivita ({scores['hour']['score']:.0f}%)",
                'impact': 'high'
            })

        if scores['fatigue']['score'] < 65:
            factors.append({
                'type': 'negative',
                'name': 'Unava z predchozich sessions',
                'description': f'Session c. {sessions_today + 1} - ocekavana unava',
                'impact': 'high' if scores['fatigue']['score'] < 55 else 'medium'
            })

        if scores['recovery']['score'] < 65 and minutes_since_last is not None:
            factors.append({
                'type': 'negative',
                'name': 'Nedostatecna pauza',
                'description': f'Pouze {minutes_since_last} minut od posledni session',
                'impact': 'medium'
            })

        if scores['day']['score'] < 60:
            factors.append({
                'type': 'negative',
                'name': 'Mene produktivni den',
                'description': 'Historicky nizsi vykon v tento den',
                'impact': 'low'
            })

        # Sort by impact
        impact_order = {'high': 0, 'medium': 1, 'low': 2}
        factors.sort(key=lambda x: impact_order.get(x['impact'], 3))

        return factors[:5]  # Max 5 factors

    # =========================================================================
    # Recommendation Generator
    # =========================================================================
    def _generate_recommendation(self, predicted: float, scores: Dict,
                                 preset: str, sessions_today: int) -> dict:
        """Generate actionable recommendation."""
        # High prediction
        if predicted >= 75:
            return {
                'type': 'positive',
                'message': 'Idealni cas pro praci!',
                'action': None,
                'icon': '🚀'
            }

        # Medium prediction
        if predicted >= 60:
            if scores['fatigue']['score'] < 65:
                return {
                    'type': 'warning',
                    'message': 'Zvys si motivaci - mas za sebou nekolik sessions',
                    'action': 'Zkus kratsi preset nebo si dej delsi pauzu',
                    'icon': '💪'
                }
            if scores['recovery']['score'] < 70:
                return {
                    'type': 'warning',
                    'message': 'Odpocin si jeste chvili',
                    'action': 'Doporucena pauza: jeste 10-15 minut',
                    'icon': '☕'
                }
            return {
                'type': 'neutral',
                'message': 'Prumerna ocekavana produktivita',
                'action': None,
                'icon': '👍'
            }

        # Low prediction
        if scores['hour']['score'] < 60:
            return {
                'type': 'negative',
                'message': 'Tato hodina neni tvuj peak time',
                'action': 'Zkus naplanovat praci na jiny cas',
                'icon': '⚠️'
            }

        if sessions_today >= 6:
            return {
                'type': 'negative',
                'message': 'Mozna je cas na delsi odpocinek',
                'action': 'Doporucuji prestavku nebo dokoncit den',
                'icon': '🛑'
            }

        # Suggest different preset
        if scores['preset']['score'] < 60:
            better_presets = []
            for p in self.PRESETS:
                if p != preset:
                    p_score, _ = self._calculate_preset_score(p, scores.get('_hour', 12))
                    if p_score > scores['preset']['score']:
                        better_presets.append((p, p_score))
            if better_presets:
                best = max(better_presets, key=lambda x: x[1])
                return {
                    'type': 'suggestion',
                    'message': 'Zkus zmenit preset',
                    'action': f"Doporucuji: {self.PRESETS.get(best[0], {}).get('name', best[0])}",
                    'icon': '💡'
                }

        return {
            'type': 'neutral',
            'message': 'Nizsi ocekavana produktivita',
            'action': 'Prizpusob ocekavani nebo zmen podminky',
            'icon': '📊'
        }

    # =========================================================================
    # Main Prediction Method
    # =========================================================================
    def predict(self, hour: int, day: int, preset: str, category: Optional[str],
                sessions_today: int, minutes_since_last: Optional[int]) -> dict:
        """
        Main prediction method.

        Args:
            hour: Current hour (0-23)
            day: Day of week (0=Monday, 6=Sunday)
            preset: Selected preset
            category: Selected category (can be None)
            sessions_today: Number of completed sessions today
            minutes_since_last: Minutes since last session (None if first)

        Returns:
            Prediction dict with productivity, confidence, factors, recommendation
        """
        # Calculate all factor scores
        hour_score, hour_conf = self._calculate_hour_score(hour)
        day_score, day_conf = self._calculate_day_score(day)
        preset_score, preset_conf = self._calculate_preset_score(preset, hour)
        category_score, category_conf = self._calculate_category_score(category, hour)
        fatigue_score, fatigue_conf = self._calculate_fatigue_score(sessions_today)
        recovery_score, recovery_conf = self._calculate_recovery_score(minutes_since_last)

        # Build scores dict
        scores = {
            'hour': {'score': hour_score, 'confidence': hour_conf, 'weight': self.WEIGHTS['hour']},
            'day': {'score': day_score, 'confidence': day_conf, 'weight': self.WEIGHTS['day']},
            'preset': {'score': preset_score, 'confidence': preset_conf, 'weight': self.WEIGHTS['preset']},
            'category': {'score': category_score, 'confidence': category_conf, 'weight': self.WEIGHTS['category']},
            'fatigue': {'score': fatigue_score, 'confidence': fatigue_conf, 'weight': self.WEIGHTS['fatigue']},
            'recovery': {'score': recovery_score, 'confidence': recovery_conf, 'weight': self.WEIGHTS['recovery']},
            '_hour': hour  # For preset recommendation
        }

        # Weighted average for prediction
        predicted_productivity = (
            hour_score * self.WEIGHTS['hour'] +
            day_score * self.WEIGHTS['day'] +
            preset_score * self.WEIGHTS['preset'] +
            category_score * self.WEIGHTS['category'] +
            fatigue_score * self.WEIGHTS['fatigue'] +
            recovery_score * self.WEIGHTS['recovery']
        )

        # Weighted confidence
        overall_confidence = (
            hour_conf * self.WEIGHTS['hour'] +
            day_conf * self.WEIGHTS['day'] +
            preset_conf * self.WEIGHTS['preset'] +
            category_conf * self.WEIGHTS['category'] +
            fatigue_conf * self.WEIGHTS['fatigue'] +
            recovery_conf * self.WEIGHTS['recovery']
        )

        # Build response
        return {
            'predicted_productivity': round(predicted_productivity, 1),
            'confidence': round(overall_confidence, 2),

            'context': {
                'hour': hour,
                'day_of_week': day,
                'day_name': self.DAY_NAMES[day] if 0 <= day <= 6 else 'Unknown',
                'preset': preset,
                'preset_name': self.PRESETS.get(preset, {}).get('name', preset),
                'category': category,
                'sessions_today': sessions_today,
                'minutes_since_last': minutes_since_last
            },

            'factor_scores': {
                'hour': {'score': round(hour_score, 1), 'confidence': round(hour_conf, 2), 'weight': self.WEIGHTS['hour']},
                'day': {'score': round(day_score, 1), 'confidence': round(day_conf, 2), 'weight': self.WEIGHTS['day']},
                'preset': {'score': round(preset_score, 1), 'confidence': round(preset_conf, 2), 'weight': self.WEIGHTS['preset']},
                'category': {'score': round(category_score, 1), 'confidence': round(category_conf, 2), 'weight': self.WEIGHTS['category']},
                'fatigue': {'score': round(fatigue_score, 1), 'confidence': round(fatigue_conf, 2), 'weight': self.WEIGHTS['fatigue']},
                'recovery': {'score': round(recovery_score, 1), 'confidence': round(recovery_conf, 2), 'weight': self.WEIGHTS['recovery']}
            },

            'factors': self._build_factors_list(scores, preset, sessions_today, minutes_since_last),

            'recommendation': self._generate_recommendation(predicted_productivity, scores, preset, sessions_today),

            'metadata': {
                'model_version': '1.0',
                'total_sessions_analyzed': len(self.completed_sessions),
                'timestamp': datetime.now().isoformat()
            }
        }
