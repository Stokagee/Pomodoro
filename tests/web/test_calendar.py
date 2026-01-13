"""
Calendar and Daily Focus Tests.
Tests for calendar API endpoints and multiple themes per day functionality.
"""
import pytest
from datetime import datetime, date, timedelta
from unittest.mock import MagicMock, patch
import sys
import os

# Add web directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'web'))


class TestDailyFocusMultipleThemes:
    """Test multiple themes per day functionality."""

    def test_set_daily_focus_with_single_theme(self, app):
        """set_daily_focus() should work with a single theme."""
        import models.database as db_module

        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = {'count': 0, 'avg_rating': None, 'id': 1}

        with patch.object(db_module, 'get_cursor') as mock_get_cursor:
            mock_get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
            mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)

            target_date = date.today()
            themes = [{'theme': 'Learning', 'planned_sessions': 3, 'notes': ''}]

            result = db_module.set_daily_focus(target_date, themes, 'Test notes')

            assert result is True
            # Verify INSERT was called
            call_args = mock_cursor.execute.call_args_list[-1]
            assert 'INSERT INTO daily_focus' in call_args[0][0]

    def test_set_daily_focus_with_multiple_themes(self, app):
        """set_daily_focus() should store multiple themes."""
        import models.database as db_module

        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = {'count': 0, 'avg_rating': None, 'id': 1}

        with patch.object(db_module, 'get_cursor') as mock_get_cursor:
            mock_get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
            mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)

            target_date = date.today()
            themes = [
                {'theme': 'Database', 'planned_sessions': 2, 'notes': 'Morning'},
                {'theme': 'Learning', 'planned_sessions': 3, 'notes': 'Afternoon'},
                {'theme': 'Frontend', 'planned_sessions': 1, 'notes': ''}
            ]

            result = db_module.set_daily_focus(target_date, themes, 'Multi-theme day')

            assert result is True
            # Check total planned_sessions = 6 (2+3+1) was passed
            call_args = mock_cursor.execute.call_args_list[-1]
            params = call_args[0][1]
            # planned_sessions should be 6
            assert 6 in params

    def test_set_daily_focus_empty_themes(self, app):
        """set_daily_focus() should handle empty themes list."""
        import models.database as db_module

        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = {'count': 0, 'avg_rating': None, 'id': 1}

        with patch.object(db_module, 'get_cursor') as mock_get_cursor:
            mock_get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
            mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)

            target_date = date.today()
            themes = []

            result = db_module.set_daily_focus(target_date, themes, 'No themes')

            assert result is True

    def test_get_daily_focus_returns_themes_array(self, app):
        """get_daily_focus() should return themes array."""
        import models.database as db_module

        target_date = date.today()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = {
            'id': 1,
            'date': target_date,
            'themes': [
                {'theme': 'Database', 'planned_sessions': 2, 'notes': ''},
                {'theme': 'Learning', 'planned_sessions': 4, 'notes': ''}
            ],
            'notes': 'Test',
            'planned_sessions': 6,
            'actual_sessions': 0,
            'productivity_score': 0,
            'created_at': datetime.now(),
            'updated_at': datetime.now()
        }

        with patch.object(db_module, 'get_cursor') as mock_get_cursor:
            mock_get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
            mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)

            focus = db_module.get_daily_focus(target_date)

            assert focus is not None
            assert 'themes' in focus
            assert len(focus['themes']) == 2
            assert focus['total_planned'] == 6

    def test_get_daily_focus_backward_compatibility(self, app):
        """get_daily_focus() should handle themes=None gracefully."""
        import models.database as db_module

        target_date = date.today()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = {
            'id': 1,
            'date': target_date,
            'themes': None,  # Old format - no themes
            'notes': 'Old format',
            'planned_sessions': 5,
            'actual_sessions': 0,
            'productivity_score': 0,
            'created_at': datetime.now(),
            'updated_at': datetime.now()
        }

        with patch.object(db_module, 'get_cursor') as mock_get_cursor:
            mock_get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
            mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)

            focus = db_module.get_daily_focus(target_date)

            assert focus is not None
            assert 'themes' in focus
            assert focus['themes'] == []

    def test_default_sessions_is_one(self, app):
        """Default planned_sessions should be 1."""
        import models.database as db_module

        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = {'count': 0, 'avg_rating': None, 'id': 1}

        with patch.object(db_module, 'get_cursor') as mock_get_cursor:
            mock_get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
            mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)

            target_date = date.today()
            themes = [{'theme': 'Learning'}]  # No planned_sessions specified

            result = db_module.set_daily_focus(target_date, themes, '')

            assert result is True
            # planned_sessions defaults to 1
            call_args = mock_cursor.execute.call_args_list[-1]
            params = call_args[0][1]
            assert 1 in params


class TestCalendarMonthData:
    """Test calendar month data retrieval."""

    def test_get_calendar_month_returns_themes_array(self, app):
        """get_calendar_month() should return themes array for each day."""
        import models.database as db_module

        mock_cursor = MagicMock()
        # First query returns focus data
        mock_cursor.fetchall.side_effect = [
            [{'date': date(2026, 1, 15), 'themes': [
                {'theme': 'Database', 'planned_sessions': 3, 'notes': ''},
                {'theme': 'Frontend', 'planned_sessions': 2, 'notes': ''}
            ], 'notes': 'Test', 'planned_sessions': 5}],
            []  # sessions data
        ]

        with patch.object(db_module, 'get_cursor') as mock_get_cursor:
            mock_get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
            mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)

            result = db_module.get_calendar_month(2026, 1)

            assert '2026-01-15' in result
            day_data = result['2026-01-15']
            assert 'themes' in day_data
            assert len(day_data['themes']) == 2

    def test_get_calendar_month_backward_compat(self, app):
        """get_calendar_month() should handle missing themes gracefully."""
        import models.database as db_module

        mock_cursor = MagicMock()
        mock_cursor.fetchall.side_effect = [
            [{'date': date(2026, 1, 20), 'themes': None, 'notes': 'Old', 'planned_sessions': 4}],
            []
        ]

        with patch.object(db_module, 'get_cursor') as mock_get_cursor:
            mock_get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
            mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)

            result = db_module.get_calendar_month(2026, 1)

            assert '2026-01-20' in result
            day_data = result['2026-01-20']
            assert 'themes' in day_data
            assert day_data['themes'] == []

    def test_get_calendar_month_empty_day(self, app):
        """get_calendar_month() should return empty themes for days without focus."""
        import models.database as db_module

        mock_cursor = MagicMock()
        mock_cursor.fetchall.side_effect = [[], []]  # No focus data, no sessions

        with patch.object(db_module, 'get_cursor') as mock_get_cursor:
            mock_get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
            mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)

            result = db_module.get_calendar_month(2026, 1)

            day_data = result['2026-01-01']
            assert day_data['themes'] == []
            assert day_data['total_planned'] == 0


class TestCalendarWeekData:
    """Test calendar week data retrieval."""

    def test_get_calendar_week_returns_themes(self, app):
        """get_calendar_week() should return themes array for each day."""
        import models.database as db_module

        mock_cursor = MagicMock()
        mock_cursor.fetchall.side_effect = [
            [{'date': date(2026, 1, 6), 'themes': [
                {'theme': 'Learning', 'planned_sessions': 5, 'notes': ''}
            ], 'notes': '', 'planned_sessions': 5}],
            []  # sessions data
        ]

        with patch.object(db_module, 'get_cursor') as mock_get_cursor:
            mock_get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
            mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)

            result = db_module.get_calendar_week(date(2026, 1, 5))

            assert 'days' in result
            assert '2026-01-06' in result['days']
            day_data = result['days']['2026-01-06']
            assert 'themes' in day_data
            assert len(day_data['themes']) == 1


class TestFocusAPIEndpoints:
    """Test focus API endpoints."""

    def test_api_focus_today_success_format(self, client):
        """GET /api/focus/today should return success and focus object."""
        response = client.get('/api/focus/today')
        data = response.get_json()

        assert 'success' in data
        assert 'focus' in data

    def test_api_focus_date_returns_themes(self, client, app):
        """GET /api/focus/<date> should return themes array."""
        # Patch where the function is used (in app), not where it's defined (in db_module)
        with patch('app.get_daily_focus') as mock_get:
            mock_get.return_value = {
                '_id': '1',
                'date': '2026-01-15',
                'themes': [{'theme': 'Learning', 'planned_sessions': 2, 'notes': ''}],
                'notes': '',
                'planned_sessions': 2,
                'total_planned': 2
            }

            response = client.get('/api/focus/2026-01-15')
            data = response.get_json()

            assert data['success'] == True
            assert 'themes' in data['focus']

    def test_api_set_focus_with_themes_array(self, client, app):
        """POST /api/focus should accept themes array."""
        import models.database as db_module

        with patch.object(db_module, 'set_daily_focus') as mock_set:
            mock_set.return_value = True

            with patch.object(db_module, 'get_daily_focus') as mock_get:
                mock_get.return_value = {
                    'date': '2026-01-20',
                    'themes': [
                        {'theme': 'Database', 'planned_sessions': 3, 'notes': ''},
                        {'theme': 'Learning', 'planned_sessions': 2, 'notes': ''}
                    ],
                    'total_planned': 5
                }

                response = client.post('/api/focus', json={
                    'date': '2026-01-20',
                    'themes': [
                        {'theme': 'Database', 'planned_sessions': 3},
                        {'theme': 'Learning', 'planned_sessions': 2}
                    ],
                    'notes': 'Test multi-theme'
                })

                data = response.get_json()
                assert data['success'] == True

    def test_api_set_focus_backward_compat(self, client, app):
        """POST /api/focus should accept old single theme format."""
        import models.database as db_module

        with patch.object(db_module, 'set_daily_focus') as mock_set:
            mock_set.return_value = True

            with patch.object(db_module, 'get_daily_focus') as mock_get:
                mock_get.return_value = {
                    'date': '2026-01-21',
                    'themes': [{'theme': 'Learning', 'planned_sessions': 5, 'notes': ''}],
                    'total_planned': 5
                }

                response = client.post('/api/focus', json={
                    'date': '2026-01-21',
                    'theme': 'Learning',
                    'planned_sessions': 5,
                    'notes': 'Old format test'
                })

                data = response.get_json()
                assert data['success'] == True


class TestCalendarAPIEndpoints:
    """Test calendar API endpoints."""

    def test_api_calendar_month_format(self, client, app):
        """GET /api/calendar/month/<year>/<month> should return correct format."""
        with patch('app.get_calendar_month') as mock_get:
            # Return dict with all 31 days
            mock_days = {f'2026-01-{i:02d}': {
                'date': f'2026-01-{i:02d}',
                'themes': [],
                'total_planned': 0,
                'actual_sessions': 0
            } for i in range(1, 32)}
            mock_get.return_value = mock_days

            response = client.get('/api/calendar/month/2026/1')
            data = response.get_json()

            assert data['success'] == True
            assert 'days' in data

    def test_api_calendar_month_days_have_themes(self, client, app):
        """Calendar month days should have themes array."""
        with patch('app.get_calendar_month') as mock_get:
            mock_days = {f'2026-01-{i:02d}': {
                'date': f'2026-01-{i:02d}',
                'themes': [] if i != 10 else [{'theme': 'Learning', 'planned_sessions': 3}],
                'total_planned': 0 if i != 10 else 3,
                'actual_sessions': 0
            } for i in range(1, 32)}
            mock_get.return_value = mock_days

            response = client.get('/api/calendar/month/2026/1')
            data = response.get_json()

            # Find day 10
            day_10 = next((d for d in data['days'] if d['date'] == '2026-01-10'), None)
            assert day_10 is not None
            assert 'themes' in day_10
            assert len(day_10['themes']) == 1

    def test_api_calendar_month_invalid_date(self, client):
        """Calendar month should reject invalid dates."""
        response = client.get('/api/calendar/month/2026/13')
        assert response.status_code == 400

        response = client.get('/api/calendar/month/2026/0')
        assert response.status_code == 400


class TestPutFocusEndpoint:
    """Test PUT /api/focus/<date> endpoint."""

    def test_api_update_focus_with_themes(self, client, app):
        """PUT /api/focus/<date> should update with themes array."""
        with patch('app.get_daily_focus') as mock_get:
            # First call returns existing focus
            mock_get.return_value = {
                'date': '2026-01-25',
                'themes': [{'theme': 'Database', 'planned_sessions': 2}],
                'total_planned': 2
            }

            with patch('app.set_daily_focus') as mock_set:
                mock_set.return_value = True

                response = client.put('/api/focus/2026-01-25', json={
                    'themes': [
                        {'theme': 'Learning', 'planned_sessions': 4},
                        {'theme': 'Frontend', 'planned_sessions': 1}
                    ],
                    'notes': 'Updated'
                })

                data = response.get_json()
                assert data['status'] == 'ok'

    def test_api_update_focus_not_found(self, client, app):
        """PUT /api/focus/<date> should return 404 for non-existent date."""
        with patch('app.get_daily_focus') as mock_get:
            mock_get.return_value = None  # Not found

            response = client.put('/api/focus/2026-12-31', json={
                'themes': [{'theme': 'Learning', 'planned_sessions': 1}]
            })

            assert response.status_code == 404
