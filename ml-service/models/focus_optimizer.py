"""
Focus Optimizer - Analyzes historical data to recommend optimal work schedules
based on time-of-day and day-of-week productivity patterns.
"""

from datetime import datetime
from collections import defaultdict
from typing import List, Dict, Optional, Tuple


class FocusOptimizer:
    """
    Analyzes productivity patterns to generate optimal work schedules.

    Features:
    - Identifies peak productive hours
    - Identifies hours to avoid
    - Recommends best preset for each hour
    - Generates optimal daily schedule for N sessions
    """

    # Preset definitions (same as other models)
    PRESETS = {
        'deep_work': {'work': 52, 'break': 17, 'name': 'Deep Work'},
        'learning': {'work': 45, 'break': 15, 'name': 'Learning'},
        'quick_tasks': {'work': 25, 'break': 5, 'name': 'Quick Tasks'},
        'flow_mode': {'work': 90, 'break': 20, 'name': 'Flow Mode'}
    }

    # Czech day names
    DAY_NAMES = ['Pondělí', 'Úterý', 'Středa', 'Čtvrtek', 'Pátek', 'Sobota', 'Neděle']
    DAY_NAMES_EN = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

    # Working hours range
    WORK_HOUR_START = 6
    WORK_HOUR_END = 22

    def __init__(self, sessions: List[dict]):
        """
        Initialize with session data.

        Args:
            sessions: List of session documents from MongoDB
        """
        # Filter only completed sessions
        self.sessions = [s for s in sessions if s.get('completed', False)]
        self.time_matrix = {}
        self._build_time_matrix()

    def _normalize_rating(self, rating) -> Optional[float]:
        """
        Normalize productivity rating to 0-100 scale.
        Handles backward compatibility with old 1-5 scale.
        """
        if rating is None:
            return None

        try:
            rating = float(rating)
            # Old format: 1-5 scale -> convert to 0-100
            if 1 <= rating <= 5:
                return rating * 20
            # New format: 0-100 scale
            return rating
        except (ValueError, TypeError):
            return None

    def _build_time_matrix(self):
        """
        Build 7x24 matrix of productivity data.
        Each cell contains ratings, preset performance, and completion data.
        """
        # Initialize matrix: 7 days x 24 hours
        for day in range(7):
            self.time_matrix[day] = {}
            for hour in range(24):
                self.time_matrix[day][hour] = {
                    'ratings': [],
                    'presets': defaultdict(list),  # preset -> list of ratings
                    'completed': 0,
                    'total': 0
                }

        # Populate matrix with session data
        for session in self.sessions:
            day = session.get('day_of_week', 0)
            hour = session.get('hour', 12)
            rating = self._normalize_rating(session.get('productivity_rating'))
            preset = session.get('preset', 'deep_work')

            # Ensure day and hour are valid
            day = max(0, min(6, day))
            hour = max(0, min(23, hour))

            cell = self.time_matrix[day][hour]
            cell['total'] += 1

            if session.get('completed', False):
                cell['completed'] += 1

            if rating is not None:
                cell['ratings'].append(rating)
                cell['presets'][preset].append(rating)

    def _get_default_score(self, hour: int) -> float:
        """
        Return default productivity score based on typical circadian patterns.
        Used when no historical data is available.
        """
        # Morning peak: 8-12
        if 8 <= hour <= 12:
            return 75.0
        # Early afternoon: 13-15 (post-lunch dip)
        elif 13 <= hour <= 15:
            return 55.0
        # Late afternoon: 16-18
        elif 16 <= hour <= 18:
            return 70.0
        # Evening: 19-21
        elif 19 <= hour <= 21:
            return 60.0
        # Early morning: 6-7
        elif 6 <= hour <= 7:
            return 65.0
        # Night/early morning: 22-5
        else:
            return 45.0

    def _calculate_hour_score(self, day: int, hour: int) -> dict:
        """
        Calculate productivity score for a specific day+hour combination.

        Returns:
            dict with score, avg_productivity, completion_rate, session_count, confidence
        """
        cell = self.time_matrix[day][hour]

        # Default values when no data
        if not cell['ratings']:
            default_score = self._get_default_score(hour)
            return {
                'score': default_score,
                'avg_productivity': None,
                'completion_rate': None,
                'session_count': 0,
                'confidence': 0.1,
                'data_source': 'default'
            }

        avg_productivity = sum(cell['ratings']) / len(cell['ratings'])
        completion_rate = (cell['completed'] / cell['total'] * 100) if cell['total'] > 0 else 100

        # Confidence based on sample size
        # 1-2 sessions: low, 3-5: medium, 6+: high
        sample_size = len(cell['ratings'])
        if sample_size >= 6:
            data_confidence = 1.0
        elif sample_size >= 3:
            data_confidence = 0.7
        else:
            data_confidence = 0.4

        # Weighted score calculation:
        # 60% productivity rating (0-100)
        # 30% completion rate (0-100)
        # 10% bonus for high data confidence
        score = (
            0.6 * avg_productivity +
            0.3 * completion_rate +
            0.1 * (data_confidence * 100)
        )

        return {
            'score': round(score, 1),
            'avg_productivity': round(avg_productivity, 1),
            'completion_rate': round(completion_rate, 1),
            'session_count': sample_size,
            'confidence': round(data_confidence, 2),
            'data_source': 'historical'
        }

    def _get_best_preset_for_hour(self, day: int, hour: int) -> Tuple[str, Optional[float]]:
        """
        Find which preset works best at this specific time.

        Returns:
            Tuple of (preset_name, average_rating or None)
        """
        cell = self.time_matrix[day][hour]

        if not cell['presets']:
            # Default preset recommendations by time of day
            if 6 <= hour < 12:
                return ('deep_work', None)  # Morning = deep work
            elif 12 <= hour < 14:
                return ('quick_tasks', None)  # Lunch time = quick tasks
            elif 14 <= hour < 17:
                return ('learning', None)  # Afternoon = learning
            elif 17 <= hour < 20:
                return ('quick_tasks', None)  # Evening = quick tasks
            else:
                return ('learning', None)  # Night = light learning

        # Find preset with highest average rating
        best_preset = None
        best_avg = 0

        for preset, ratings in cell['presets'].items():
            if ratings:
                avg = sum(ratings) / len(ratings)
                if avg > best_avg or best_preset is None:
                    best_avg = avg
                    best_preset = preset

        return (best_preset or 'deep_work', round(best_avg, 1) if best_avg else None)

    def _get_low_productivity_reason(self, hour: int, score_data: dict) -> str:
        """Generate reason why this hour has low productivity."""
        if 12 <= hour <= 14:
            return "Polední útlum"
        elif 15 <= hour <= 16:
            return "Odpolední únava"
        elif hour >= 21:
            return "Večerní únava"
        elif hour < 8:
            return "Ranní rozjezd"
        elif score_data.get('completion_rate') and score_data['completion_rate'] < 70:
            return "Nízká míra dokončení"
        else:
            return "Nižší produktivita dle historie"

    def get_peak_hours(self, day: int, top_n: int = 5) -> List[dict]:
        """
        Get top N most productive hours for a specific day.

        Args:
            day: Day of week (0=Monday, 6=Sunday)
            top_n: Number of top hours to return

        Returns:
            List of hour data dicts sorted by productivity score
        """
        hour_scores = []

        for hour in range(self.WORK_HOUR_START, self.WORK_HOUR_END + 1):
            score_data = self._calculate_hour_score(day, hour)
            preset, preset_rating = self._get_best_preset_for_hour(day, hour)

            hour_scores.append({
                'hour': hour,
                'time': f'{hour:02d}:00',
                'expected_productivity': score_data['avg_productivity'] or score_data['score'],
                'score': score_data['score'],
                'recommended_preset': preset,
                'preset_name': self.PRESETS.get(preset, {}).get('name', preset),
                'preset_rating': preset_rating,
                'session_count': score_data['session_count'],
                'confidence': score_data['confidence']
            })

        # Sort by score descending
        hour_scores.sort(key=lambda x: x['score'], reverse=True)

        return hour_scores[:top_n]

    def get_avoid_hours(self, day: int, bottom_n: int = 5) -> List[dict]:
        """
        Get bottom N least productive hours for a specific day.
        Only considers working hours (6-22).

        Args:
            day: Day of week (0=Monday, 6=Sunday)
            bottom_n: Number of worst hours to return

        Returns:
            List of hour data dicts sorted by productivity score (ascending)
        """
        hour_scores = []

        for hour in range(self.WORK_HOUR_START, self.WORK_HOUR_END + 1):
            score_data = self._calculate_hour_score(day, hour)
            reason = self._get_low_productivity_reason(hour, score_data)

            hour_scores.append({
                'hour': hour,
                'time': f'{hour:02d}:00',
                'expected_productivity': score_data['avg_productivity'] or score_data['score'],
                'score': score_data['score'],
                'reason': reason,
                'session_count': score_data['session_count'],
                'confidence': score_data['confidence']
            })

        # Sort by score ascending (worst first)
        hour_scores.sort(key=lambda x: x['score'])

        return hour_scores[:bottom_n]

    def get_hourly_breakdown(self, day: int) -> Dict[str, dict]:
        """
        Get productivity data for all 24 hours of a specific day.

        Args:
            day: Day of week (0=Monday, 6=Sunday)

        Returns:
            Dict mapping hour (as string) to productivity data
        """
        breakdown = {}

        for hour in range(24):
            score_data = self._calculate_hour_score(day, hour)
            preset, preset_rating = self._get_best_preset_for_hour(day, hour)

            breakdown[str(hour)] = {
                'hour': hour,
                'time': f'{hour:02d}:00',
                'productivity': score_data['avg_productivity'],
                'score': score_data['score'],
                'recommended_preset': preset,
                'preset_name': self.PRESETS.get(preset, {}).get('name', preset),
                'preset_rating': preset_rating,
                'session_count': score_data['session_count'],
                'completion_rate': score_data['completion_rate'],
                'confidence': score_data['confidence'],
                'data_source': score_data['data_source']
            }

        return breakdown

    def get_optimal_schedule(self, day: int, num_sessions: int = 6) -> dict:
        """
        Generate optimal schedule for N sessions on a given day.
        Selects best hours with appropriate time gaps between sessions.

        Args:
            day: Day of week (0=Monday, 6=Sunday)
            num_sessions: Number of sessions to schedule (1-12)

        Returns:
            Dict with sessions list and summary stats
        """
        num_sessions = max(1, min(12, num_sessions))

        # Get all working hours ranked by productivity
        all_hours = []
        for hour in range(self.WORK_HOUR_START, self.WORK_HOUR_END):
            score_data = self._calculate_hour_score(day, hour)
            preset, _ = self._get_best_preset_for_hour(day, hour)

            all_hours.append({
                'hour': hour,
                'score': score_data['score'],
                'preset': preset,
                'productivity': score_data['avg_productivity'] or score_data['score'],
                'confidence': score_data['confidence']
            })

        # Sort by score descending
        all_hours.sort(key=lambda x: x['score'], reverse=True)

        # Select top hours ensuring minimum gaps
        selected = []
        used_hours = set()

        for hour_data in all_hours:
            if len(selected) >= num_sessions:
                break

            hour = hour_data['hour']
            preset = hour_data['preset']

            # Determine minimum gap based on preset duration
            preset_info = self.PRESETS.get(preset, {'work': 25})
            work_duration = preset_info['work']

            # For longer sessions (>30 min), require 2-hour gaps
            # For shorter sessions, 1-hour gap is fine
            min_gap = 2 if work_duration > 30 else 1

            # Check if hour is not too close to already selected hours
            too_close = any(abs(hour - h) < min_gap for h in used_hours)

            if not too_close:
                selected.append(hour_data)
                used_hours.add(hour)

        # Sort selected by time (chronological order)
        selected.sort(key=lambda x: x['hour'])

        # Format output
        schedule = []
        total_work_minutes = 0
        total_break_minutes = 0
        total_productivity = 0

        for i, slot in enumerate(selected):
            preset = slot['preset']
            preset_info = self.PRESETS.get(preset, {'work': 25, 'break': 5, 'name': preset})

            schedule.append({
                'slot': i + 1,
                'hour': slot['hour'],
                'time': f"{slot['hour']:02d}:00",
                'preset': preset,
                'preset_name': preset_info.get('name', preset),
                'work_minutes': preset_info['work'],
                'break_minutes': preset_info['break'],
                'expected_productivity': round(slot['productivity'], 1),
                'confidence': slot['confidence']
            })

            total_work_minutes += preset_info['work']
            total_break_minutes += preset_info['break']
            total_productivity += slot['productivity']

        avg_productivity = round(total_productivity / len(selected), 1) if selected else 0

        return {
            'sessions': schedule,
            'total_work_minutes': total_work_minutes,
            'total_break_minutes': total_break_minutes,
            'total_time_minutes': total_work_minutes + total_break_minutes,
            'avg_expected_productivity': avg_productivity,
            'sessions_count': len(schedule)
        }

    def _calculate_confidence(self, day: int) -> float:
        """
        Calculate overall confidence based on data volume for this day.

        Args:
            day: Day of week (0=Monday, 6=Sunday)

        Returns:
            Confidence score between 0.0 and 1.0
        """
        total_sessions = 0
        hours_with_data = 0

        for hour in range(self.WORK_HOUR_START, self.WORK_HOUR_END + 1):
            cell = self.time_matrix[day][hour]
            if cell['ratings']:
                hours_with_data += 1
                total_sessions += len(cell['ratings'])

        # Confidence factors:
        # 1. Total sessions (more = better), max at 50 sessions
        # 2. Coverage of hours (more hours with data = better)
        working_hours = self.WORK_HOUR_END - self.WORK_HOUR_START + 1

        session_confidence = min(1.0, total_sessions / 50)
        coverage_confidence = hours_with_data / working_hours

        # Weighted average: sessions matter more than coverage
        confidence = 0.7 * session_confidence + 0.3 * coverage_confidence

        return round(confidence, 2)

    def _get_total_sessions_analyzed(self) -> int:
        """Get total number of sessions across all days and hours."""
        total = 0
        for day in range(7):
            for hour in range(24):
                total += len(self.time_matrix[day][hour]['ratings'])
        return total

    def analyze(self, day: int = None, num_sessions: int = 6) -> dict:
        """
        Main method - returns complete focus optimization analysis.

        Args:
            day: Day of week (0=Monday, 6=Sunday), defaults to today
            num_sessions: Number of sessions to schedule

        Returns:
            Complete analysis dict with peak hours, avoid hours,
            hourly breakdown, optimal schedule, and summary
        """
        if day is None:
            day = datetime.now().weekday()

        # Ensure day is valid
        day = max(0, min(6, day))

        # Get all components
        peak_hours = self.get_peak_hours(day, top_n=5)
        avoid_hours = self.get_avoid_hours(day, bottom_n=5)
        hourly_breakdown = self.get_hourly_breakdown(day)
        schedule = self.get_optimal_schedule(day, num_sessions)
        confidence = self._calculate_confidence(day)
        total_sessions = self._get_total_sessions_analyzed()

        # Generate summary
        if peak_hours:
            # Find best contiguous time range
            peak_hour_values = sorted([h['hour'] for h in peak_hours[:3]])
            best_start = peak_hour_values[0]
            best_end = peak_hour_values[-1] + 1
            best_range = f"{best_start:02d}:00 - {best_end:02d}:00"
        else:
            best_range = "09:00 - 12:00"

        # Identify recommended break times (based on avoid hours)
        break_times = [h['hour'] for h in avoid_hours[:2]] if avoid_hours else [12, 15]

        return {
            'date': datetime.now().strftime('%Y-%m-%d'),
            'day_of_week': self.DAY_NAMES[day],
            'day_of_week_en': self.DAY_NAMES_EN[day],
            'day_of_week_num': day,

            'peak_hours': peak_hours,
            'avoid_hours': avoid_hours,
            'hourly_breakdown': hourly_breakdown,

            'optimal_schedule': schedule,

            'summary': {
                'best_time_range': best_range,
                'recommended_break_times': break_times,
                'recommended_sessions': num_sessions,
                'total_work_minutes': schedule['total_work_minutes'],
                'total_break_minutes': schedule['total_break_minutes'],
                'total_time_minutes': schedule['total_time_minutes'],
                'expected_avg_productivity': schedule['avg_expected_productivity']
            },

            'confidence': confidence,
            'total_sessions_analyzed': total_sessions,
            'recommendation_basis': f"Založeno na {total_sessions} sessions" if total_sessions > 0 else "Výchozí doporučení (zatím žádná data)"
        }
