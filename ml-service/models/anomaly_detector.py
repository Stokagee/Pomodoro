"""
Pattern Anomaly Detector.
Detects unusual patterns in user behavior for proactive notifications.

Anomaly Types:
- productivity_drop: Sudden decline in productivity
- unusual_hours: Working outside normal schedule
- category_shift: Change in preferred categories
- streak_break: Missing days after long streak
- overwork_spike: Sudden increase in work intensity
- quality_decline: Drop in session ratings
"""
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from collections import Counter, defaultdict
from statistics import mean, stdev, median
from utils.logger import logger


class PatternAnomalyDetector:
    """Detects unusual patterns in user behavior."""

    # Analysis periods
    BASELINE_DAYS = 14
    RECENT_DAYS = 3
    MIN_DATA_DAYS = 7

    # Z-score thresholds for severity
    SEVERITY_THRESHOLDS = {
        'low': 1.5,
        'medium': 2.0,
        'high': 2.5,
        'critical': 3.0
    }

    # Anomaly type metadata
    ANOMALY_TYPES = {
        'productivity_drop': {
            'name': 'Pokles produktivity',
            'icon': '📉',
            'description_template': 'Produktivita klesla o {change}% za posledni {days} dny'
        },
        'unusual_hours': {
            'name': 'Neobvykle hodiny',
            'icon': '🌙',
            'description_template': 'Pracujes mimo svuj obvykly rozvrh ({range})'
        },
        'category_shift': {
            'name': 'Zmena kategorii',
            'icon': '🔄',
            'description_template': 'Zmena v preferenci kategorii: {category} ({change}%)'
        },
        'streak_break': {
            'name': 'Preruseny streak',
            'icon': '💔',
            'description_template': 'Vynechano {gap} dnu po {streak}-dennim streaku'
        },
        'overwork_spike': {
            'name': 'Narust intenzity',
            'icon': '🔥',
            'description_template': 'Pracujes {ratio}% vice nez obvykle'
        },
        'quality_decline': {
            'name': 'Pokles kvality',
            'icon': '⚠️',
            'description_template': '{count} sessions za sebou pod prumerem'
        }
    }

    # Recommendations for each anomaly type
    RECOMMENDATIONS = {
        'productivity_drop': [
            'Zvaz delsi prestavky mezi sessions',
            'Zkus zmenit prostredi',
            'Mozna potrebujes odpocinek'
        ],
        'unusual_hours': [
            'Udrzuj pravidelny rozvrh',
            'Nocni prace snizuje produktivitu',
            'Zkus se vratit ke svym obvyklym hodinam'
        ],
        'category_shift': [
            'Sleduj, zda ti nova kategorie vyhovuje',
            'Mozna je cas diverzifikovat ukoly'
        ],
        'streak_break': [
            'Nevadi, kazdy potrebuje pauzu',
            'Zkus zacit s kratkou session',
            'Nastav si maly cil pro dnesek'
        ],
        'overwork_spike': [
            'Dej si pozor na vycerpani',
            'Kvalita je dulezitejsi nez kvantita',
            'Nezapomen na prestavky'
        ],
        'quality_decline': [
            'Mozna je cas na zmenu',
            'Zkus kratsi sessions',
            'Zvaz jiny typ ukolu'
        ]
    }

    def __init__(self, sessions: List[dict]):
        """Initialize detector with session history."""
        self.sessions = sessions
        self.today = datetime.now().date()
        self._prepare_data()
        self._build_baseline()

    def _prepare_data(self):
        """Prepare and normalize session data."""
        for session in self.sessions:
            # Ensure timestamp is datetime
            if isinstance(session.get('timestamp'), str):
                try:
                    session['timestamp'] = datetime.fromisoformat(
                        session['timestamp'].replace('Z', '+00:00')
                    )
                except (ValueError, AttributeError):
                    pass

            # Extract date if not present
            if 'date' not in session and 'timestamp' in session:
                ts = session['timestamp']
                if isinstance(ts, datetime):
                    session['date'] = ts.strftime('%Y-%m-%d')

            # Normalize productivity rating to 0-100 scale
            if 'productivity_rating' in session and session['productivity_rating'] is not None:
                rating = session['productivity_rating']
                if rating <= 5:  # Old 1-5 scale
                    session['normalized_rating'] = rating * 20
                else:
                    session['normalized_rating'] = rating
            else:
                session['normalized_rating'] = None

    def _build_baseline(self):
        """Build baseline statistics from historical data."""
        baseline_sessions = self._get_sessions_last_n_days(self.BASELINE_DAYS)

        if len(baseline_sessions) < 5:
            self.baseline = None
            return

        # Calculate baseline metrics
        ratings = [s['normalized_rating'] for s in baseline_sessions
                   if s.get('normalized_rating') is not None]
        hours = [s.get('hour', 12) for s in baseline_sessions]
        categories = [s.get('category', 'Unknown') for s in baseline_sessions]

        # Sessions per day
        session_dates = defaultdict(int)
        for s in baseline_sessions:
            if 'date' in s:
                session_dates[s['date']] += 1

        self.baseline = {
            'avg_productivity': mean(ratings) if ratings else 70.0,
            'std_productivity': stdev(ratings) if len(ratings) > 1 else 10.0,
            'avg_sessions_per_day': mean(session_dates.values()) if session_dates else 3.0,
            'std_sessions_per_day': stdev(session_dates.values()) if len(session_dates) > 1 else 1.0,
            'typical_hours': self._calculate_iqr(hours),
            'category_distribution': self._calculate_distribution(categories),
            'top_category': Counter(categories).most_common(1)[0][0] if categories else None,
            'total_sessions': len(baseline_sessions),
            'unique_days': len(session_dates)
        }

    def _calculate_iqr(self, values: List[float]) -> dict:
        """Calculate IQR-based range for values."""
        if not values:
            return {'q1': 8, 'q3': 18, 'min': 6, 'max': 22}

        sorted_vals = sorted(values)
        n = len(sorted_vals)
        q1_idx = n // 4
        q3_idx = (3 * n) // 4

        q1 = sorted_vals[q1_idx]
        q3 = sorted_vals[q3_idx]
        iqr = q3 - q1

        return {
            'q1': q1,
            'q3': q3,
            'min': max(0, q1 - 1.5 * iqr),
            'max': min(23, q3 + 1.5 * iqr),
            'median': median(sorted_vals)
        }

    def _calculate_distribution(self, values: List[str]) -> dict:
        """Calculate percentage distribution."""
        if not values:
            return {}

        counter = Counter(values)
        total = sum(counter.values())
        return {k: v / total for k, v in counter.items()}

    def _get_sessions_last_n_days(self, n: int) -> List[dict]:
        """Get sessions from last N days."""
        cutoff = self.today - timedelta(days=n)
        result = []

        for session in self.sessions:
            try:
                if 'date' in session:
                    session_date = datetime.strptime(session['date'], '%Y-%m-%d').date()
                elif 'timestamp' in session:
                    ts = session['timestamp']
                    if isinstance(ts, datetime):
                        session_date = ts.date()
                    else:
                        continue
                else:
                    continue

                if session_date >= cutoff:
                    result.append(session)
            except (ValueError, TypeError):
                continue

        return result

    def _calculate_z_score(self, value: float, mean_val: float, std_val: float) -> float:
        """Calculate Z-score for a value."""
        if std_val == 0 or std_val is None:
            return 0.0
        return (value - mean_val) / std_val

    def _get_severity(self, z_score: float) -> str:
        """Get severity level from absolute Z-score."""
        abs_z = abs(z_score)
        if abs_z >= self.SEVERITY_THRESHOLDS['critical']:
            return 'critical'
        elif abs_z >= self.SEVERITY_THRESHOLDS['high']:
            return 'high'
        elif abs_z >= self.SEVERITY_THRESHOLDS['medium']:
            return 'medium'
        elif abs_z >= self.SEVERITY_THRESHOLDS['low']:
            return 'low'
        return None

    def _detect_productivity_drop(self) -> Optional[dict]:
        """Detect sudden productivity decline."""
        if not self.baseline:
            return None

        recent = self._get_sessions_last_n_days(self.RECENT_DAYS)
        recent_ratings = [s['normalized_rating'] for s in recent
                         if s.get('normalized_rating') is not None]

        if len(recent_ratings) < 2:
            return None

        recent_avg = mean(recent_ratings)
        baseline_avg = self.baseline['avg_productivity']
        baseline_std = self.baseline['std_productivity']

        z_score = self._calculate_z_score(recent_avg, baseline_avg, baseline_std)

        # Only detect drops (negative z-score)
        if z_score < -self.SEVERITY_THRESHOLDS['low']:
            change_percent = ((recent_avg - baseline_avg) / baseline_avg) * 100

            return {
                'type': 'productivity_drop',
                'name': self.ANOMALY_TYPES['productivity_drop']['name'],
                'severity': self._get_severity(z_score),
                'z_score': round(z_score, 2),
                'current_value': round(recent_avg, 1),
                'baseline_value': round(baseline_avg, 1),
                'change_percent': round(change_percent, 1),
                'description': f'Produktivita klesla o {abs(round(change_percent))}% za posledni {self.RECENT_DAYS} dny',
                'recommendation': self.RECOMMENDATIONS['productivity_drop'][0],
                'icon': self.ANOMALY_TYPES['productivity_drop']['icon'],
                'evidence': {
                    'period': f'last_{self.RECENT_DAYS}_days',
                    'data_points': [round(r, 1) for r in recent_ratings[-5:]]
                }
            }

        return None

    def _detect_unusual_hours(self) -> Optional[dict]:
        """Detect working outside normal schedule."""
        if not self.baseline:
            return None

        recent = self._get_sessions_last_n_days(self.RECENT_DAYS)
        if not recent:
            return None

        typical = self.baseline['typical_hours']
        unusual_sessions = []

        for s in recent:
            hour = s.get('hour')
            if hour is not None:
                if hour < typical['min'] or hour > typical['max']:
                    unusual_sessions.append({
                        'hour': hour,
                        'time': f"{hour:02d}:00"
                    })

        if len(unusual_sessions) >= 2:
            return {
                'type': 'unusual_hours',
                'name': self.ANOMALY_TYPES['unusual_hours']['name'],
                'severity': 'low' if len(unusual_sessions) == 2 else 'medium',
                'description': f'Pracujes mimo svuj obvykly rozvrh ({int(typical["q1"])}:00 - {int(typical["q3"])}:00)',
                'recommendation': self.RECOMMENDATIONS['unusual_hours'][0],
                'icon': self.ANOMALY_TYPES['unusual_hours']['icon'],
                'evidence': {
                    'normal_range': f'{int(typical["q1"])}:00 - {int(typical["q3"])}:00',
                    'unusual_sessions': [s['time'] for s in unusual_sessions[:5]]
                }
            }

        return None

    def _detect_category_shift(self) -> Optional[dict]:
        """Detect change in category preferences."""
        if not self.baseline or not self.baseline.get('category_distribution'):
            return None

        recent = self._get_sessions_last_n_days(7)
        recent_categories = [s.get('category', 'Unknown') for s in recent if s.get('category')]

        if len(recent_categories) < 3:
            return None

        recent_dist = self._calculate_distribution(recent_categories)
        baseline_dist = self.baseline['category_distribution']

        # Find biggest shift
        max_shift = 0
        shifted_category = None

        for cat in set(recent_dist.keys()) | set(baseline_dist.keys()):
            recent_pct = recent_dist.get(cat, 0)
            baseline_pct = baseline_dist.get(cat, 0)
            shift = abs(recent_pct - baseline_pct)

            if shift > max_shift:
                max_shift = shift
                shifted_category = cat

        if max_shift > 0.30:  # 30% shift threshold
            return {
                'type': 'category_shift',
                'name': self.ANOMALY_TYPES['category_shift']['name'],
                'severity': 'low',
                'category': shifted_category,
                'change_percent': round(max_shift * 100, 1),
                'description': f'Zmena v preferenci kategorii: {shifted_category} ({round(max_shift * 100)}%)',
                'recommendation': self.RECOMMENDATIONS['category_shift'][0],
                'icon': self.ANOMALY_TYPES['category_shift']['icon'],
                'evidence': {
                    'baseline_top': self.baseline.get('top_category'),
                    'recent_distribution': {k: round(v * 100, 1) for k, v in recent_dist.items()}
                }
            }

        return None

    def _detect_streak_break(self) -> Optional[dict]:
        """Detect missing days after long streak."""
        if len(self.sessions) < 7:
            return None

        # Build date set
        dates = set()
        for s in self.sessions:
            if 'date' in s:
                try:
                    dates.add(datetime.strptime(s['date'], '%Y-%m-%d').date())
                except ValueError:
                    pass

        if not dates:
            return None

        # Find longest streak before gap
        sorted_dates = sorted(dates)
        current_streak = 0
        max_streak_before_gap = 0
        gap_start = None

        for i in range(len(sorted_dates) - 1):
            if (sorted_dates[i + 1] - sorted_dates[i]).days == 1:
                current_streak += 1
            else:
                gap_days = (sorted_dates[i + 1] - sorted_dates[i]).days - 1
                if current_streak >= 6 and gap_days >= 2:  # 7+ day streak, 2+ day gap
                    max_streak_before_gap = current_streak + 1
                    gap_start = sorted_dates[i] + timedelta(days=1)
                current_streak = 0

        # Check if there's a recent gap
        if max_streak_before_gap >= 7:
            days_since_gap = (self.today - gap_start).days if gap_start else 0

            if days_since_gap <= 7:  # Gap happened within last week
                return {
                    'type': 'streak_break',
                    'name': self.ANOMALY_TYPES['streak_break']['name'],
                    'severity': 'medium' if max_streak_before_gap >= 10 else 'low',
                    'streak_days': max_streak_before_gap,
                    'gap_days': 2,  # Minimum gap
                    'description': f'Vynechano 2+ dnu po {max_streak_before_gap}-dennim streaku',
                    'recommendation': self.RECOMMENDATIONS['streak_break'][0],
                    'icon': self.ANOMALY_TYPES['streak_break']['icon'],
                    'evidence': {
                        'streak_length': max_streak_before_gap,
                        'gap_start': gap_start.strftime('%Y-%m-%d') if gap_start else None
                    }
                }

        return None

    def _detect_overwork_spike(self) -> Optional[dict]:
        """Detect sudden increase in work intensity."""
        if not self.baseline:
            return None

        recent = self._get_sessions_last_n_days(self.RECENT_DAYS)
        if not recent:
            return None

        # Count sessions per day for recent period
        recent_dates = defaultdict(int)
        for s in recent:
            if 'date' in s:
                recent_dates[s['date']] += 1

        if not recent_dates:
            return None

        recent_avg = mean(recent_dates.values())
        baseline_avg = self.baseline['avg_sessions_per_day']
        baseline_std = self.baseline['std_sessions_per_day']

        ratio = (recent_avg / baseline_avg) if baseline_avg > 0 else 1

        if ratio > 1.5:  # 150% threshold
            z_score = self._calculate_z_score(recent_avg, baseline_avg, baseline_std)

            return {
                'type': 'overwork_spike',
                'name': self.ANOMALY_TYPES['overwork_spike']['name'],
                'severity': 'medium' if ratio > 2.0 else 'low',
                'ratio': round(ratio * 100),
                'current_avg': round(recent_avg, 1),
                'baseline_avg': round(baseline_avg, 1),
                'description': f'Pracujes {round(ratio * 100)}% vice nez obvykle',
                'recommendation': self.RECOMMENDATIONS['overwork_spike'][0],
                'icon': self.ANOMALY_TYPES['overwork_spike']['icon'],
                'evidence': {
                    'recent_sessions_per_day': round(recent_avg, 1),
                    'baseline_sessions_per_day': round(baseline_avg, 1)
                }
            }

        return None

    def _detect_quality_decline(self) -> Optional[dict]:
        """Detect consecutive sessions below average."""
        if not self.baseline:
            return None

        recent = self._get_sessions_last_n_days(7)
        rated_sessions = [s for s in recent if s.get('normalized_rating') is not None]

        if len(rated_sessions) < 3:
            return None

        baseline_avg = self.baseline['avg_productivity']

        # Count consecutive below-average sessions from the end
        consecutive_below = 0
        for s in reversed(rated_sessions):
            if s['normalized_rating'] < baseline_avg:
                consecutive_below += 1
            else:
                break

        if consecutive_below >= 3:
            recent_ratings = [s['normalized_rating'] for s in rated_sessions[-consecutive_below:]]

            return {
                'type': 'quality_decline',
                'name': self.ANOMALY_TYPES['quality_decline']['name'],
                'severity': 'medium' if consecutive_below >= 5 else 'low',
                'consecutive_count': consecutive_below,
                'avg_recent': round(mean(recent_ratings), 1),
                'baseline_avg': round(baseline_avg, 1),
                'description': f'{consecutive_below} sessions za sebou pod prumerem',
                'recommendation': self.RECOMMENDATIONS['quality_decline'][0],
                'icon': self.ANOMALY_TYPES['quality_decline']['icon'],
                'evidence': {
                    'consecutive_ratings': [round(r, 1) for r in recent_ratings],
                    'baseline_threshold': round(baseline_avg, 1)
                }
            }

        return None

    def _get_overall_status(self, anomalies: List[dict]) -> str:
        """Determine overall status from anomalies."""
        if not anomalies:
            return 'healthy'

        severities = [a.get('severity', 'low') for a in anomalies]

        if 'critical' in severities:
            return 'critical'
        elif 'high' in severities:
            return 'alert'
        elif 'medium' in severities:
            return 'warning'
        else:
            return 'info'

    def _generate_proactive_tips(self, anomalies: List[dict]) -> List[dict]:
        """Generate proactive tips based on detected anomalies."""
        tips = []

        for anomaly in anomalies:
            anomaly_type = anomaly.get('type')
            recommendations = self.RECOMMENDATIONS.get(anomaly_type, [])

            for rec in recommendations[1:]:  # Skip first (already in anomaly)
                tips.append({
                    'type': 'suggestion',
                    'icon': '💡',
                    'message': rec,
                    'related_anomaly': anomaly_type
                })

        # Add general tips if no anomalies
        if not anomalies:
            tips.append({
                'type': 'positive',
                'icon': '✨',
                'message': 'Zadne anomalie detekovany. Skvela prace!'
            })

        return tips[:3]  # Max 3 tips

    def _get_patterns_summary(self) -> dict:
        """Get summary of detected patterns."""
        if not self.baseline:
            return {
                'productivity_trend': 'unknown',
                'work_intensity': 'unknown',
                'schedule_regularity': 'unknown'
            }

        # Productivity trend
        recent = self._get_sessions_last_n_days(7)
        recent_ratings = [s['normalized_rating'] for s in recent
                         if s.get('normalized_rating') is not None]

        if len(recent_ratings) >= 3:
            recent_avg = mean(recent_ratings)
            baseline_avg = self.baseline['avg_productivity']
            diff = recent_avg - baseline_avg

            if diff > 5:
                productivity_trend = 'improving'
            elif diff < -5:
                productivity_trend = 'declining'
            else:
                productivity_trend = 'stable'
        else:
            productivity_trend = 'unknown'

        # Work intensity
        recent_dates = defaultdict(int)
        for s in recent:
            if 'date' in s:
                recent_dates[s['date']] += 1

        if recent_dates:
            recent_intensity = mean(recent_dates.values())
            baseline_intensity = self.baseline['avg_sessions_per_day']
            ratio = recent_intensity / baseline_intensity if baseline_intensity > 0 else 1

            if ratio > 1.3:
                work_intensity = 'high'
            elif ratio < 0.7:
                work_intensity = 'low'
            else:
                work_intensity = 'normal'
        else:
            work_intensity = 'unknown'

        # Schedule regularity
        hours = [s.get('hour', 12) for s in recent]
        if len(hours) >= 3:
            hour_std = stdev(hours) if len(hours) > 1 else 0
            if hour_std <= 2:
                schedule_regularity = 'regular'
            elif hour_std <= 4:
                schedule_regularity = 'moderate'
            else:
                schedule_regularity = 'irregular'
        else:
            schedule_regularity = 'unknown'

        return {
            'productivity_trend': productivity_trend,
            'work_intensity': work_intensity,
            'schedule_regularity': schedule_regularity
        }

    def _calculate_current_streak(self) -> int:
        """Calculate current streak length."""
        dates = set()
        for s in self.sessions:
            if 'date' in s:
                try:
                    dates.add(datetime.strptime(s['date'], '%Y-%m-%d').date())
                except ValueError:
                    pass

        if not dates or self.today not in dates:
            # Check if yesterday has a session (streak may continue today)
            yesterday = self.today - timedelta(days=1)
            if yesterday not in dates:
                return 0

        streak = 0
        check_date = self.today

        while check_date in dates:
            streak += 1
            check_date -= timedelta(days=1)

        # Also check from yesterday if today not in dates
        if self.today not in dates:
            check_date = self.today - timedelta(days=1)
            streak = 0
            while check_date in dates:
                streak += 1
                check_date -= timedelta(days=1)

        return streak

    def detect_all(self) -> dict:
        """Main method - detect all anomalies and return comprehensive report."""
        # Check for sufficient data
        unique_days = len(set(
            s.get('date') for s in self.sessions if s.get('date')
        ))

        if unique_days < self.MIN_DATA_DAYS:
            return {
                'anomalies_detected': 0,
                'overall_status': 'insufficient_data',
                'anomalies': [],
                'proactive_tips': [],
                'message': f'Potrebuji alespon {self.MIN_DATA_DAYS} dni dat pro analyzu',
                'baseline_summary': None,
                'patterns': None,
                'confidence': 0.0,
                'metadata': {
                    'model_version': '1.0',
                    'total_sessions_analyzed': len(self.sessions),
                    'unique_days': unique_days,
                    'required_days': self.MIN_DATA_DAYS,
                    'timestamp': datetime.now().isoformat()
                }
            }

        # Run all detections
        anomalies = []

        detectors = [
            self._detect_productivity_drop,
            self._detect_unusual_hours,
            self._detect_category_shift,
            self._detect_streak_break,
            self._detect_overwork_spike,
            self._detect_quality_decline
        ]

        for detector in detectors:
            try:
                result = detector()
                if result:
                    anomalies.append(result)
            except Exception as e:
                # Log but don't fail
                logger.warning("ANOMALY_DETECTOR_ERROR", message=f"Detection error in {detector.__name__}", error={"type": type(e).__name__, "message": str(e)}, context={"detector": detector.__name__})

        # Calculate confidence based on data quality
        confidence = min(0.9, 0.3 + (unique_days / 30) * 0.4 + (len(self.sessions) / 100) * 0.2)

        # Build baseline summary for response
        baseline_summary = None
        if self.baseline:
            typical_hours = self.baseline.get('typical_hours', {})
            baseline_summary = {
                'avg_productivity': round(self.baseline['avg_productivity'], 1),
                'typical_hours': {
                    'start': int(typical_hours.get('q1', 9)),
                    'end': int(typical_hours.get('q3', 18))
                },
                'top_category': self.baseline.get('top_category'),
                'avg_sessions_per_day': round(self.baseline['avg_sessions_per_day'], 1),
                'current_streak': self._calculate_current_streak(),
                'analysis_period_days': self.BASELINE_DAYS
            }

        return {
            'anomalies_detected': len(anomalies),
            'overall_status': self._get_overall_status(anomalies),
            'anomalies': anomalies,
            'proactive_tips': self._generate_proactive_tips(anomalies),
            'baseline_summary': baseline_summary,
            'patterns': self._get_patterns_summary(),
            'confidence': round(confidence, 2),
            'metadata': {
                'model_version': '1.0',
                'total_sessions_analyzed': len(self.sessions),
                'analysis_period': f'{self.BASELINE_DAYS} days',
                'timestamp': datetime.now().isoformat()
            }
        }
