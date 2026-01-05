"""
Productivity Analyzer - Analyzes historical data to find productivity patterns
"""

from datetime import datetime, timedelta
from collections import defaultdict


class ProductivityAnalyzer:
    """Analyzes productivity patterns from session data"""

    def __init__(self, sessions):
        """
        Initialize with session data

        Args:
            sessions: List of session documents from MongoDB
        """
        self.sessions = [s for s in sessions if s.get('productivity_rating')]
        self.day_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

    def analyze(self):
        """
        Run full productivity analysis

        Returns:
            dict: Analysis results
        """
        if not self.sessions:
            return self._empty_analysis()

        return {
            'best_hours': self._get_best_hours(),
            'worst_hours': self._get_worst_hours(),
            'best_day': self._get_best_day(),
            'productivity_by_hour': self._get_hourly_productivity(),
            'productivity_by_day': self._get_daily_productivity(),
            'productivity_by_category': self._get_category_productivity(),
            'productivity_by_preset': self._get_preset_productivity(),
            'trend': self._get_trend(),
            'total_sessions_analyzed': len(self.sessions)
        }

    def _empty_analysis(self):
        """Return empty analysis when no data available"""
        return {
            'best_hours': [],
            'worst_hours': [],
            'best_day': None,
            'productivity_by_hour': {},
            'productivity_by_day': {},
            'productivity_by_category': {},
            'productivity_by_preset': {},
            'trend': 'stable',
            'total_sessions_analyzed': 0
        }

    def _get_hourly_productivity(self):
        """Calculate average productivity by hour"""
        hourly = defaultdict(list)

        for session in self.sessions:
            hour = session.get('hour', 0)
            rating = session.get('productivity_rating', 0)
            if rating:
                hourly[hour].append(rating)

        return {
            hour: round(sum(ratings) / len(ratings), 2)
            for hour, ratings in hourly.items()
            if ratings
        }

    def _get_best_hours(self, top_n=3):
        """Get the most productive hours"""
        hourly = self._get_hourly_productivity()
        if not hourly:
            return []

        sorted_hours = sorted(hourly.items(), key=lambda x: x[1], reverse=True)
        return [hour for hour, _ in sorted_hours[:top_n]]

    def _get_worst_hours(self, top_n=3):
        """Get the least productive hours"""
        hourly = self._get_hourly_productivity()
        if not hourly:
            return []

        sorted_hours = sorted(hourly.items(), key=lambda x: x[1])
        return [hour for hour, _ in sorted_hours[:top_n]]

    def _get_daily_productivity(self):
        """Calculate average productivity by day of week"""
        daily = defaultdict(list)

        for session in self.sessions:
            day_of_week = session.get('day_of_week', 0)
            rating = session.get('productivity_rating', 0)
            if rating:
                day_name = self.day_names[day_of_week]
                daily[day_name].append(rating)

        return {
            day: round(sum(ratings) / len(ratings), 2)
            for day, ratings in daily.items()
            if ratings
        }

    def _get_best_day(self):
        """Get the most productive day of the week"""
        daily = self._get_daily_productivity()
        if not daily:
            return None

        return max(daily.items(), key=lambda x: x[1])[0]

    def _get_category_productivity(self):
        """Calculate average productivity by category"""
        categories = defaultdict(list)

        for session in self.sessions:
            category = session.get('category', 'Other')
            rating = session.get('productivity_rating', 0)
            if rating:
                categories[category].append(rating)

        return {
            cat: {
                'avg_rating': round(sum(ratings) / len(ratings), 2),
                'session_count': len(ratings)
            }
            for cat, ratings in categories.items()
            if ratings
        }

    def _get_preset_productivity(self):
        """Calculate average productivity by preset"""
        presets = defaultdict(list)

        for session in self.sessions:
            preset = session.get('preset', 'deep_work')
            rating = session.get('productivity_rating', 0)
            if rating:
                presets[preset].append(rating)

        return {
            preset: {
                'avg_rating': round(sum(ratings) / len(ratings), 2),
                'session_count': len(ratings)
            }
            for preset, ratings in presets.items()
            if ratings
        }

    def _get_trend(self, days=7):
        """
        Analyze productivity trend over recent days

        Returns:
            str: 'up', 'down', or 'stable'
        """
        if len(self.sessions) < 5:
            return 'stable'

        # Get sessions from last week
        today = datetime.now().date()
        week_ago = today - timedelta(days=days)

        recent = []
        older = []

        for session in self.sessions:
            try:
                session_date = datetime.strptime(session['date'], '%Y-%m-%d').date()
                rating = session.get('productivity_rating', 0)
                if rating:
                    if session_date >= week_ago:
                        recent.append(rating)
                    else:
                        older.append(rating)
            except (ValueError, KeyError):
                continue

        if not recent or not older:
            return 'stable'

        recent_avg = sum(recent) / len(recent)
        older_avg = sum(older) / len(older)

        diff = recent_avg - older_avg

        if diff > 0.3:
            return 'up'
        elif diff < -0.3:
            return 'down'
        else:
            return 'stable'

    def get_hourly_heatmap(self):
        """
        Generate heatmap data for day x hour productivity

        Returns:
            dict: Heatmap data with day/hour combinations
        """
        heatmap = {}

        for day_idx, day_name in enumerate(self.day_names):
            heatmap[day_name] = {}
            for hour in range(24):
                heatmap[day_name][hour] = {
                    'sessions': 0,
                    'avg_rating': 0,
                    'total_rating': 0
                }

        for session in self.sessions:
            day_of_week = session.get('day_of_week', 0)
            hour = session.get('hour', 0)
            rating = session.get('productivity_rating', 0)

            if rating:
                day_name = self.day_names[day_of_week]
                heatmap[day_name][hour]['sessions'] += 1
                heatmap[day_name][hour]['total_rating'] += rating

        # Calculate averages
        for day_name in self.day_names:
            for hour in range(24):
                cell = heatmap[day_name][hour]
                if cell['sessions'] > 0:
                    cell['avg_rating'] = round(cell['total_rating'] / cell['sessions'], 2)
                del cell['total_rating']

        return heatmap
