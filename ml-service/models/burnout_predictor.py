"""
Burnout Predictor - Detekuje riziko vyhoření na základě vzorců chování
"""

from datetime import datetime, timedelta
from collections import defaultdict
import statistics


class BurnoutPredictor:
    """Predikuje riziko vyhoření na základě pracovních vzorců"""

    ANALYSIS_PERIOD_DAYS = 14
    NIGHT_HOUR_THRESHOLD = 21  # Sessions po 21:00

    # Risk level thresholds
    RISK_THRESHOLDS = {
        'low': (0, 25),
        'medium': (26, 50),
        'high': (51, 75),
        'critical': (76, 100)
    }

    # Czech recommendations for each factor
    RECOMMENDATIONS = {
        'declining_productivity': [
            "Zkuste kratší work sessions (25 min standard místo 52 min deep work)",
            "Naplánujte si 2-3 dny s menším počtem sessions",
            "Změňte kategorii práce pro oživení motivace"
        ],
        'overwork': [
            "Snižte denní počet sessions",
            "Dodržujte plánované přestávky",
            "Stanovte si pevný konec pracovního dne"
        ],
        'night_sessions': [
            "Vyhněte se práci po 21:00 - narušuje spánkový cyklus",
            "Přesuňte večerní úkoly na ranní hodiny",
            "Nastavte si 'digital sunset' v 21:00"
        ],
        'weekend_work': [
            "Rezervujte si alespoň jeden víkendový den bez práce",
            "Víkendová práce zvyšuje riziko vyhoření o 40%",
            "Plánujte víkendy předem jako čas odpočinku"
        ],
        'variability': [
            "Zkuste standardizovat denní rutinu",
            "Zaměřte se na konzistentní pracovní bloky",
            "Sledujte, co způsobuje výkyvy produktivity"
        ],
        'continuous_days': [
            "Naplánujte si den odpočinku",
            "Každých 5-6 dní si dejte volno",
            "Odpočinek zvyšuje dlouhodobou produktivitu"
        ]
    }

    def __init__(self, sessions):
        """
        Initialize with session data

        Args:
            sessions: List of session documents from MongoDB
        """
        self.sessions = sessions
        self.recent_sessions = []
        self.daily_sessions = defaultdict(list)
        self.daily_productivity = defaultdict(list)
        self.all_dates = set()
        self._prepare_data()

    def _prepare_data(self):
        """Filter and organize sessions for analysis (last 14 days)"""
        cutoff = (datetime.now() - timedelta(days=self.ANALYSIS_PERIOD_DAYS)).strftime('%Y-%m-%d')
        today = datetime.now().strftime('%Y-%m-%d')

        for session in self.sessions:
            session_date = session.get('date', '')
            if session_date and cutoff <= session_date <= today:
                self.recent_sessions.append(session)
                self.daily_sessions[session_date].append(session)
                self.all_dates.add(session_date)

                rating = session.get('productivity_rating')
                if rating:
                    self.daily_productivity[session_date].append(rating)

    def predict_burnout(self):
        """
        Main prediction method - returns complete risk assessment

        Returns:
            dict: Risk assessment with score, level, factors, and recommendations
        """
        if len(self.recent_sessions) < 5:
            return self._insufficient_data()

        factors = self._calculate_all_factors()
        risk_score = self._calculate_total_score(factors)
        risk_level = self._get_risk_level(risk_score)
        formatted_factors = self._format_risk_factors(factors)
        recommendations = self._generate_recommendations(factors)

        return {
            'risk_score': risk_score,
            'risk_level': risk_level,
            'risk_factors': formatted_factors,
            'recommendations': recommendations,
            'confidence': self._calculate_confidence(),
            'analyzed_period': f'{self.ANALYSIS_PERIOD_DAYS} days',
            'total_sessions_analyzed': len(self.recent_sessions)
        }

    def _insufficient_data(self):
        """Return default response when insufficient data"""
        return {
            'risk_score': 0,
            'risk_level': 'unknown',
            'risk_factors': [],
            'recommendations': ['Sbírejte více dat pro analýzu rizika vyhoření (minimum 5 sessions)'],
            'confidence': 0.0,
            'analyzed_period': f'{self.ANALYSIS_PERIOD_DAYS} days',
            'total_sessions_analyzed': len(self.recent_sessions),
            'message': 'Nedostatek dat pro predikci'
        }

    def _calculate_all_factors(self):
        """Calculate all 6 risk factors"""
        return {
            'declining_productivity': self._calc_productivity_trend(),
            'overwork': self._calc_overwork(),
            'night_sessions': self._calc_night_sessions(),
            'weekend_work': self._calc_weekend_work(),
            'variability': self._calc_variability(),
            'continuous_days': self._calc_continuous_days()
        }

    def _calc_productivity_trend(self):
        """
        Factor 1: Productivity trend (25 points max)
        Compare last 7 days avg vs previous 7 days avg
        """
        if not self.daily_productivity:
            return {'score': 0, 'severity': 'none', 'value': 0, 'details': 'Žádná data o produktivitě'}

        today = datetime.now()
        week_ago = (today - timedelta(days=7)).strftime('%Y-%m-%d')
        two_weeks_ago = (today - timedelta(days=14)).strftime('%Y-%m-%d')

        recent_ratings = []
        older_ratings = []

        for date_str, ratings in self.daily_productivity.items():
            if date_str >= week_ago:
                recent_ratings.extend(ratings)
            elif date_str >= two_weeks_ago:
                older_ratings.extend(ratings)

        if not recent_ratings or not older_ratings:
            return {'score': 0, 'severity': 'none', 'value': 0, 'details': 'Nedostatek dat pro trend'}

        recent_avg = sum(recent_ratings) / len(recent_ratings)
        older_avg = sum(older_ratings) / len(older_ratings)

        if older_avg == 0:
            return {'score': 0, 'severity': 'none', 'value': 0, 'details': 'Nedostatek historických dat'}

        # Calculate decline percentage
        decline = (older_avg - recent_avg) / older_avg

        # Score based on decline
        if decline > 0.20:  # >20% decline
            score = 25
            severity = 'high'
        elif decline > 0.10:  # 10-20% decline
            score = 15
            severity = 'medium'
        elif decline > 0.05:  # 5-10% decline
            score = 8
            severity = 'low'
        else:
            score = 0
            severity = 'none'

        return {
            'score': score,
            'severity': severity,
            'value': round(decline * 100, 1),
            'details': f'Produktivita klesla o {round(decline * 100)}% za poslední týden' if decline > 0.05 else 'Produktivita je stabilní'
        }

    def _calc_overwork(self):
        """
        Factor 2: Overwork detection (20 points max)
        Compare recent session count vs historical average
        """
        if not self.daily_sessions:
            return {'score': 0, 'severity': 'none', 'value': 0, 'details': 'Žádná data'}

        # Calculate average sessions per day historically
        all_completed = [s for s in self.sessions if s.get('completed', True)]
        if len(all_completed) < 10:
            return {'score': 0, 'severity': 'none', 'value': 1.0, 'details': 'Nedostatek historických dat'}

        # Get unique dates from all sessions
        all_dates = set()
        for s in all_completed:
            if s.get('date'):
                all_dates.add(s['date'])

        if not all_dates:
            return {'score': 0, 'severity': 'none', 'value': 1.0, 'details': 'Žádná data'}

        historical_daily_avg = len(all_completed) / len(all_dates)

        # Recent 7 days
        today = datetime.now()
        week_ago = (today - timedelta(days=7)).strftime('%Y-%m-%d')
        recent_count = sum(1 for s in self.recent_sessions if s.get('date', '') >= week_ago)

        # Days with sessions in last 7 days
        recent_dates = set(s.get('date') for s in self.recent_sessions if s.get('date', '') >= week_ago)
        if not recent_dates:
            return {'score': 0, 'severity': 'none', 'value': 1.0, 'details': 'Žádné nedávné sessions'}

        recent_daily_avg = recent_count / len(recent_dates)

        # Calculate ratio
        if historical_daily_avg == 0:
            return {'score': 0, 'severity': 'none', 'value': 1.0, 'details': 'Žádná historická data'}

        ratio = recent_daily_avg / historical_daily_avg

        # Score based on ratio
        if ratio > 2.0:  # >200% of normal
            score = 20
            severity = 'high'
        elif ratio > 1.5:  # 150-200%
            score = 12
            severity = 'medium'
        elif ratio > 1.2:  # 120-150%
            score = 6
            severity = 'low'
        else:
            score = 0
            severity = 'none'

        return {
            'score': score,
            'severity': severity,
            'value': round(ratio, 2),
            'details': f'Pracujete {round(ratio * 100)}% oproti vašemu průměru' if ratio > 1.2 else 'Pracovní zátěž je normální'
        }

    def _calc_night_sessions(self):
        """
        Factor 3: Night sessions after 21:00 (15 points max)
        """
        if not self.recent_sessions:
            return {'score': 0, 'severity': 'none', 'value': 0, 'details': 'Žádná data'}

        night_count = 0
        for session in self.recent_sessions:
            hour = session.get('hour', 0)
            if hour >= self.NIGHT_HOUR_THRESHOLD:
                night_count += 1

        total = len(self.recent_sessions)
        ratio = night_count / total if total > 0 else 0

        # Score based on percentage
        if ratio > 0.30:  # >30% at night
            score = 15
            severity = 'high'
        elif ratio > 0.20:  # 20-30%
            score = 10
            severity = 'medium'
        elif ratio > 0.10:  # 10-20%
            score = 5
            severity = 'low'
        else:
            score = 0
            severity = 'none'

        return {
            'score': score,
            'severity': severity,
            'value': round(ratio * 100, 1),
            'details': f'{round(ratio * 100)}% sessions po 21:00' if ratio > 0.10 else 'Málo nočních sessions'
        }

    def _calc_weekend_work(self):
        """
        Factor 4: Weekend work ratio (15 points max)
        Saturday = 5, Sunday = 6
        """
        if not self.recent_sessions:
            return {'score': 0, 'severity': 'none', 'value': 0, 'details': 'Žádná data'}

        weekend_count = 0
        for session in self.recent_sessions:
            day_of_week = session.get('day_of_week')
            if day_of_week is None:
                # Try to calculate from date
                try:
                    date_obj = datetime.strptime(session.get('date', ''), '%Y-%m-%d')
                    day_of_week = date_obj.weekday()
                except (ValueError, TypeError):
                    continue

            if day_of_week in [5, 6]:  # Saturday, Sunday
                weekend_count += 1

        total = len(self.recent_sessions)
        ratio = weekend_count / total if total > 0 else 0

        # Score based on percentage
        if ratio > 0.40:  # >40% on weekends
            score = 15
            severity = 'high'
        elif ratio > 0.25:  # 25-40%
            score = 10
            severity = 'medium'
        elif ratio > 0.10:  # 10-25%
            score = 5
            severity = 'low'
        else:
            score = 0
            severity = 'none'

        return {
            'score': score,
            'severity': severity,
            'value': round(ratio * 100, 1),
            'details': f'{round(ratio * 100)}% sessions o víkendu' if ratio > 0.10 else 'Minimální víkendová práce'
        }

    def _calc_variability(self):
        """
        Factor 5: Productivity variability - std dev (15 points max)
        """
        all_ratings = []
        for ratings in self.daily_productivity.values():
            all_ratings.extend(ratings)

        if len(all_ratings) < 3:
            return {'score': 0, 'severity': 'none', 'value': 0, 'details': 'Nedostatek dat'}

        try:
            std_dev = statistics.stdev(all_ratings)
        except statistics.StatisticsError:
            return {'score': 0, 'severity': 'none', 'value': 0, 'details': 'Nelze vypočítat variabilitu'}

        # Score based on std deviation (0-100 scale ratings)
        if std_dev > 25:
            score = 15
            severity = 'high'
        elif std_dev > 15:
            score = 10
            severity = 'medium'
        elif std_dev > 8:
            score = 5
            severity = 'low'
        else:
            score = 0
            severity = 'none'

        return {
            'score': score,
            'severity': severity,
            'value': round(std_dev, 1),
            'details': f'Variabilita produktivity: {round(std_dev, 1)}' if std_dev > 8 else 'Stabilní produktivita'
        }

    def _calc_continuous_days(self):
        """
        Factor 6: Continuous work days without break (10 points max)
        """
        if not self.all_dates:
            return {'score': 0, 'severity': 'none', 'value': 0, 'details': 'Žádná data'}

        # Sort dates
        sorted_dates = sorted(self.all_dates)

        # Find longest streak
        max_streak = 1
        current_streak = 1

        for i in range(1, len(sorted_dates)):
            try:
                prev_date = datetime.strptime(sorted_dates[i - 1], '%Y-%m-%d')
                curr_date = datetime.strptime(sorted_dates[i], '%Y-%m-%d')
                diff = (curr_date - prev_date).days

                if diff == 1:  # Consecutive day
                    current_streak += 1
                    max_streak = max(max_streak, current_streak)
                else:
                    current_streak = 1
            except ValueError:
                continue

        # Score based on streak length
        if max_streak > 14:
            score = 10
            severity = 'high'
        elif max_streak > 10:
            score = 7
            severity = 'medium'
        elif max_streak > 7:
            score = 4
            severity = 'low'
        else:
            score = 0
            severity = 'none'

        return {
            'score': score,
            'severity': severity,
            'value': max_streak,
            'details': f'{max_streak} dní bez pauzy' if max_streak > 7 else 'Odpočíváte pravidelně'
        }

    def _calculate_total_score(self, factors):
        """Sum all factor scores (max 100)"""
        total = sum(f['score'] for f in factors.values())
        return min(total, 100)

    def _get_risk_level(self, score):
        """Convert score to risk level string"""
        for level, (min_score, max_score) in self.RISK_THRESHOLDS.items():
            if min_score <= score <= max_score:
                return level
        return 'unknown'

    def _format_risk_factors(self, factors):
        """Format factors for API response - only include non-zero factors"""
        formatted = []
        factor_names = {
            'declining_productivity': 'Klesající produktivita',
            'overwork': 'Přepracování',
            'night_sessions': 'Noční práce',
            'weekend_work': 'Víkendová práce',
            'variability': 'Nestabilní produktivita',
            'continuous_days': 'Nepřetržitá práce'
        }

        for key, data in factors.items():
            if data['score'] > 0:
                formatted.append({
                    'factor': key,
                    'name': factor_names.get(key, key),
                    'severity': data['severity'],
                    'score': data['score'],
                    'value': data['value'],
                    'message': data['details']
                })

        # Sort by score descending
        formatted.sort(key=lambda x: x['score'], reverse=True)
        return formatted

    def _generate_recommendations(self, factors):
        """Generate top recommendations based on highest severity factors"""
        recommendations = []

        # Sort factors by score
        sorted_factors = sorted(
            [(k, v) for k, v in factors.items() if v['score'] > 0],
            key=lambda x: x[1]['score'],
            reverse=True
        )

        # Get top 3-5 recommendations
        seen_factors = set()
        for factor_key, factor_data in sorted_factors[:5]:
            if factor_key in self.RECOMMENDATIONS and factor_key not in seen_factors:
                # Get first recommendation for this factor
                recs = self.RECOMMENDATIONS[factor_key]
                if recs:
                    recommendations.append(recs[0])
                    seen_factors.add(factor_key)

            if len(recommendations) >= 3:
                break

        # Add generic recommendation if no specific ones
        if not recommendations:
            recommendations.append('Pokračujte v dobrém pracovním rytmu!')

        return recommendations

    def _calculate_confidence(self):
        """Calculate confidence based on data volume"""
        count = len(self.recent_sessions)
        if count < 5:
            return 0.0
        elif count < 15:
            return 0.3
        elif count < 30:
            return 0.5
        elif count < 50:
            return 0.7
        else:
            return 0.85
