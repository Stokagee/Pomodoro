"""
Preset Recommender - Recommends optimal preset based on time and historical data
"""

from datetime import datetime
from collections import defaultdict


class PresetRecommender:
    """Recommends the best preset based on current context"""

    # Default preset definitions (should match config.json)
    PRESETS = {
        'deep_work': {
            'name': 'Deep Work',
            'work_minutes': 52,
            'break_minutes': 17,
            'best_for': ['focused_work', 'coding', 'learning']
        },
        'learning': {
            'name': 'Learning',
            'work_minutes': 45,
            'break_minutes': 15,
            'best_for': ['study', 'documentation', 'research']
        },
        'quick_tasks': {
            'name': 'Quick Tasks',
            'work_minutes': 25,
            'break_minutes': 5,
            'best_for': ['emails', 'admin', 'short_tasks']
        },
        'flow_mode': {
            'name': 'Flow Mode',
            'work_minutes': 90,
            'break_minutes': 20,
            'best_for': ['complex_problems', 'debugging', 'deep_analysis']
        }
    }

    def __init__(self, sessions):
        """
        Initialize with session data

        Args:
            sessions: List of session documents from MongoDB
        """
        self.sessions = sessions
        self._build_models()

    def _build_models(self):
        """Build recommendation models from historical data"""
        # Productivity by preset and hour
        self.preset_hour_ratings = defaultdict(lambda: defaultdict(list))

        # Productivity by preset and category
        self.preset_category_ratings = defaultdict(lambda: defaultdict(list))

        # Overall preset ratings
        self.preset_ratings = defaultdict(list)

        for session in self.sessions:
            preset = session.get('preset', 'deep_work')
            hour = session.get('hour', 0)
            category = session.get('category', 'Other')
            rating = session.get('productivity_rating')

            if rating:
                self.preset_hour_ratings[preset][hour].append(rating)
                self.preset_category_ratings[preset][category].append(rating)
                self.preset_ratings[preset].append(rating)

    def recommend(self, category=None):
        """
        Get preset recommendation for current time and optional category

        Args:
            category: Optional category for context-aware recommendation

        Returns:
            dict: Recommendation with preset, reason, and confidence
        """
        now = datetime.now()
        current_hour = now.hour
        current_minute = now.minute

        # Default recommendation based on time of day
        default_rec = self._get_time_based_default(current_hour)

        if not self.sessions:
            return {
                'current_time': f'{current_hour:02d}:{current_minute:02d}',
                'recommended_preset': default_rec,
                'reason': 'Zatím nemáme dost dat. Doporučeno podle času.',
                'alternative': None,
                'confidence': 0.3
            }

        # Calculate scores for each preset
        scores = {}
        for preset in self.PRESETS.keys():
            score = self._calculate_preset_score(preset, current_hour, category)
            scores[preset] = score

        # Get best preset
        best_preset = max(scores.items(), key=lambda x: x[1])
        preset_name = best_preset[0]
        confidence = min(best_preset[1] / 5.0, 1.0)  # Normalize to 0-1

        # Get alternative
        sorted_presets = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        alternative = sorted_presets[1][0] if len(sorted_presets) > 1 else None

        # Generate reason
        reason = self._generate_reason(preset_name, current_hour, category, confidence)

        return {
            'current_time': f'{current_hour:02d}:{current_minute:02d}',
            'recommended_preset': preset_name,
            'reason': reason,
            'alternative': alternative,
            'confidence': round(confidence, 2),
            'all_scores': {k: round(v, 2) for k, v in scores.items()}
        }

    def _get_time_based_default(self, hour):
        """Get default preset based on time of day"""
        if 6 <= hour < 12:
            return 'deep_work'  # Morning - best for deep work
        elif 12 <= hour < 14:
            return 'quick_tasks'  # After lunch - lighter tasks
        elif 14 <= hour < 17:
            return 'learning'  # Afternoon - good for learning
        elif 17 <= hour < 20:
            return 'quick_tasks'  # Evening - wrap up tasks
        else:
            return 'learning'  # Night - relaxed learning

    def _calculate_preset_score(self, preset, hour, category=None):
        """
        Calculate score for a preset based on historical performance

        Returns:
            float: Score from 0-5
        """
        scores = []
        weights = []

        # Hour-based score (weight: 0.4)
        hour_ratings = self.preset_hour_ratings[preset][hour]
        if hour_ratings:
            scores.append(sum(hour_ratings) / len(hour_ratings))
            weights.append(0.4)

        # Category-based score (weight: 0.4)
        if category:
            cat_ratings = self.preset_category_ratings[preset][category]
            if cat_ratings:
                scores.append(sum(cat_ratings) / len(cat_ratings))
                weights.append(0.4)

        # Overall preset score (weight: 0.2)
        overall_ratings = self.preset_ratings[preset]
        if overall_ratings:
            scores.append(sum(overall_ratings) / len(overall_ratings))
            weights.append(0.2)

        if not scores:
            return 3.0  # Neutral score

        # Weighted average
        total_weight = sum(weights)
        return sum(s * w for s, w in zip(scores, weights)) / total_weight

    def _generate_reason(self, preset, hour, category, confidence):
        """Generate human-readable reason for recommendation"""
        preset_info = self.PRESETS.get(preset, {})
        preset_name = preset_info.get('name', preset.replace('_', ' ').title())

        if confidence < 0.5:
            return f'Zatím málo dat. {preset_name} by měl být vhodný pro tuto dobu.'

        hour_str = f'{hour}:00-{hour+1}:00'

        if category:
            cat_ratings = self.preset_category_ratings[preset].get(category, [])
            if cat_ratings:
                avg = round(sum(cat_ratings) / len(cat_ratings), 1)
                return f'Pro {category} máš s {preset_name} průměrný rating {avg}/5.'

        hour_ratings = self.preset_hour_ratings[preset].get(hour, [])
        if hour_ratings:
            avg = round(sum(hour_ratings) / len(hour_ratings), 1)
            return f'Mezi {hour_str} máš s {preset_name} průměrný rating {avg}/5.'

        overall = self.preset_ratings.get(preset, [])
        if overall:
            avg = round(sum(overall) / len(overall), 1)
            return f'Tvůj celkový průměr s {preset_name} je {avg}/5.'

        return f'{preset_name} je doporučený pro tuto dobu.'

    def get_preset_stats(self):
        """Get statistics for each preset"""
        stats = {}

        for preset, ratings in self.preset_ratings.items():
            if ratings:
                stats[preset] = {
                    'avg_rating': round(sum(ratings) / len(ratings), 2),
                    'session_count': len(ratings),
                    'best_hour': self._get_best_hour_for_preset(preset),
                    'best_category': self._get_best_category_for_preset(preset)
                }

        return stats

    def _get_best_hour_for_preset(self, preset):
        """Get the hour with best performance for a preset"""
        hour_ratings = self.preset_hour_ratings[preset]
        if not hour_ratings:
            return None

        best_hour = None
        best_avg = 0

        for hour, ratings in hour_ratings.items():
            if ratings:
                avg = sum(ratings) / len(ratings)
                if avg > best_avg:
                    best_avg = avg
                    best_hour = hour

        return best_hour

    def _get_best_category_for_preset(self, preset):
        """Get the category with best performance for a preset"""
        cat_ratings = self.preset_category_ratings[preset]
        if not cat_ratings:
            return None

        best_cat = None
        best_avg = 0

        for cat, ratings in cat_ratings.items():
            if ratings:
                avg = sum(ratings) / len(ratings)
                if avg > best_avg:
                    best_avg = avg
                    best_cat = cat

        return best_cat
