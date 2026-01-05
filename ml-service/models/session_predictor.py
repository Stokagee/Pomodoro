"""
Session Predictor - Predicts daily session count and productivity
"""

from datetime import datetime, timedelta
from collections import defaultdict


class SessionPredictor:
    """Predicts session performance and provides forecasts"""

    def __init__(self, sessions):
        """
        Initialize with session data

        Args:
            sessions: List of session documents from MongoDB
        """
        self.sessions = sessions
        self._build_models()

    def _build_models(self):
        """Build prediction models from historical data"""
        # Daily session counts
        self.daily_sessions = defaultdict(list)

        # Day of week patterns
        self.dow_sessions = defaultdict(list)
        self.dow_ratings = defaultdict(list)

        # Hourly patterns
        self.hourly_counts = defaultdict(list)

        for session in self.sessions:
            try:
                date_str = session.get('date')
                day_of_week = session.get('day_of_week', 0)
                hour = session.get('hour', 0)
                rating = session.get('productivity_rating')

                if date_str:
                    self.daily_sessions[date_str].append(session)

                # Track by day of week
                self.dow_sessions[day_of_week].append(1)
                if rating:
                    self.dow_ratings[day_of_week].append(rating)

                # Track by hour
                self.hourly_counts[hour].append(1)

            except (ValueError, KeyError):
                continue

    def predict_today(self):
        """
        Predict performance for today

        Returns:
            dict: Prediction with session count and productivity
        """
        now = datetime.now()
        today = now.date()
        current_hour = now.hour
        day_of_week = today.weekday()

        # Get today's actual progress
        today_str = today.isoformat()
        today_sessions = self.daily_sessions.get(today_str, [])
        completed_sessions = len(today_sessions)

        # Predict total sessions
        predicted_sessions = self._predict_session_count(day_of_week, current_hour)

        # Predict productivity
        predicted_productivity = self._predict_productivity(day_of_week)

        # Generate schedule recommendation
        recommended_schedule = self._generate_schedule(day_of_week, current_hour)

        # Calculate confidence based on data amount
        confidence = self._calculate_confidence()

        return {
            'date': today_str,
            'current_hour': current_hour,
            'completed_sessions': completed_sessions,
            'predicted_sessions': predicted_sessions,
            'remaining_sessions': max(0, predicted_sessions - completed_sessions),
            'predicted_productivity': predicted_productivity,
            'recommended_schedule': recommended_schedule,
            'confidence': confidence,
            'energy_forecast': self._get_energy_forecast(current_hour)
        }

    def predict_week(self):
        """
        Predict performance for the coming week

        Returns:
            dict: Weekly prediction
        """
        today = datetime.now().date()
        week_prediction = []

        for i in range(7):
            future_date = today + timedelta(days=i)
            day_of_week = future_date.weekday()

            week_prediction.append({
                'date': future_date.isoformat(),
                'day_name': future_date.strftime('%A'),
                'predicted_sessions': self._predict_session_count(day_of_week),
                'predicted_productivity': self._predict_productivity(day_of_week)
            })

        return {
            'predictions': week_prediction,
            'total_predicted_sessions': sum(p['predicted_sessions'] for p in week_prediction),
            'avg_predicted_productivity': round(
                sum(p['predicted_productivity'] for p in week_prediction) / 7, 2
            )
        }

    def _predict_session_count(self, day_of_week, current_hour=None):
        """Predict number of sessions for a day"""
        if not self.daily_sessions:
            return 6  # Default estimate

        # Get historical average for this day of week
        dow_counts = len(self.dow_sessions.get(day_of_week, []))
        if dow_counts == 0:
            # Use overall average
            total_days = len(self.daily_sessions)
            total_sessions = sum(len(s) for s in self.daily_sessions.values())
            avg = total_sessions / max(total_days, 1)
            return round(avg)

        # Calculate average for this day of week
        day_sessions = defaultdict(int)
        for date_str, sessions in self.daily_sessions.items():
            try:
                date = datetime.strptime(date_str, '%Y-%m-%d').date()
                if date.weekday() == day_of_week:
                    day_sessions[date_str] = len(sessions)
            except ValueError:
                continue

        if not day_sessions:
            return 6

        avg = sum(day_sessions.values()) / len(day_sessions)

        # Adjust based on current progress if applicable
        if current_hour is not None:
            # Scale prediction based on remaining hours
            remaining_hours = max(0, 18 - current_hour)  # Assume work until 18:00
            total_work_hours = 10  # Assume 10 hour work window
            adjustment = remaining_hours / total_work_hours
            # This is already for today, no adjustment needed to prediction
            pass

        return round(avg)

    def _predict_productivity(self, day_of_week):
        """Predict productivity rating for a day"""
        ratings = self.dow_ratings.get(day_of_week, [])

        if not ratings:
            # Use overall average
            all_ratings = []
            for dow_ratings in self.dow_ratings.values():
                all_ratings.extend(dow_ratings)

            if not all_ratings:
                return 3.5  # Default neutral

            return round(sum(all_ratings) / len(all_ratings), 1)

        return round(sum(ratings) / len(ratings), 1)

    def _generate_schedule(self, day_of_week, current_hour):
        """Generate recommended schedule for the day"""
        schedule = []

        # Find best hours historically
        best_hours = self._get_best_hours_for_day(day_of_week)

        for hour in range(current_hour, 19):  # Until 19:00
            if hour in best_hours[:5]:  # Top 5 hours
                schedule.append({
                    'hour': hour,
                    'recommended_preset': self._get_preset_for_hour(hour),
                    'priority': 'high'
                })
            elif hour >= 12 and hour <= 14:
                schedule.append({
                    'hour': hour,
                    'recommended_preset': 'quick_tasks',
                    'priority': 'medium'
                })

        return schedule[:6]  # Max 6 recommended slots

    def _get_best_hours_for_day(self, day_of_week):
        """Get best performing hours for a day of week"""
        hour_ratings = defaultdict(list)

        for session in self.sessions:
            if session.get('day_of_week') == day_of_week:
                hour = session.get('hour', 0)
                rating = session.get('productivity_rating')
                if rating:
                    hour_ratings[hour].append(rating)

        if not hour_ratings:
            return [8, 9, 10, 11, 14, 15]  # Default good hours

        # Sort by average rating
        hour_avgs = [
            (hour, sum(ratings) / len(ratings))
            for hour, ratings in hour_ratings.items()
        ]
        hour_avgs.sort(key=lambda x: x[1], reverse=True)

        return [h for h, _ in hour_avgs]

    def _get_preset_for_hour(self, hour):
        """Get recommended preset for an hour"""
        if 6 <= hour < 12:
            return 'deep_work'
        elif 12 <= hour < 14:
            return 'quick_tasks'
        elif 14 <= hour < 17:
            return 'learning'
        else:
            return 'quick_tasks'

    def _get_energy_forecast(self, current_hour):
        """Forecast energy levels based on historical patterns"""
        if current_hour >= 15:
            return {
                'level': 'declining',
                'message': 'Energie klesá po 15:00 - naplánuj pauzu nebo lehčí úkoly.'
            }
        elif current_hour >= 12 and current_hour < 14:
            return {
                'level': 'low',
                'message': 'Po obědě je energie nižší - ideál pro Quick Tasks.'
            }
        elif current_hour >= 8 and current_hour < 12:
            return {
                'level': 'high',
                'message': 'Ranní hodiny - ideální pro Deep Work!'
            }
        else:
            return {
                'level': 'moderate',
                'message': 'Standardní úroveň energie.'
            }

    def _calculate_confidence(self):
        """Calculate confidence in predictions based on data amount"""
        total_sessions = len(self.sessions)

        if total_sessions < 10:
            return 0.3
        elif total_sessions < 30:
            return 0.5
        elif total_sessions < 100:
            return 0.7
        else:
            return 0.85

    def get_trends(self, days=14):
        """
        Analyze trends over recent period

        Args:
            days: Number of days to analyze

        Returns:
            dict: Trend analysis
        """
        today = datetime.now().date()
        cutoff = today - timedelta(days=days)

        recent_sessions = []
        recent_ratings = []

        for session in self.sessions:
            try:
                session_date = datetime.strptime(session['date'], '%Y-%m-%d').date()
                if session_date >= cutoff:
                    recent_sessions.append(session)
                    rating = session.get('productivity_rating')
                    if rating:
                        recent_ratings.append(rating)
            except (ValueError, KeyError):
                continue

        if len(recent_ratings) < 3:
            return {
                'session_trend': 'insufficient_data',
                'productivity_trend': 'insufficient_data',
                'total_sessions': len(recent_sessions),
                'avg_productivity': 0
            }

        # Calculate simple moving average trend
        mid = len(recent_ratings) // 2
        first_half = recent_ratings[:mid] if mid > 0 else recent_ratings
        second_half = recent_ratings[mid:] if mid > 0 else recent_ratings

        first_avg = sum(first_half) / len(first_half) if first_half else 0
        second_avg = sum(second_half) / len(second_half) if second_half else 0

        diff = second_avg - first_avg

        if diff > 0.3:
            trend = 'improving'
        elif diff < -0.3:
            trend = 'declining'
        else:
            trend = 'stable'

        return {
            'session_trend': 'stable',  # Would need daily grouping for this
            'productivity_trend': trend,
            'total_sessions': len(recent_sessions),
            'avg_productivity': round(sum(recent_ratings) / len(recent_ratings), 2) if recent_ratings else 0
        }
