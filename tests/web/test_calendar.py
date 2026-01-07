"""
Calendar and Daily Focus Tests.
Tests for calendar API endpoints and multiple themes per day functionality.
"""
import pytest
from datetime import datetime, date, timedelta
import sys
import os

# Add web directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'web'))


class TestDailyFocusMultipleThemes:
    """Test multiple themes per day functionality."""

    def test_set_daily_focus_with_single_theme(self, mock_db, monkeypatch):
        """set_daily_focus() should work with a single theme."""
        import models.database as db_module
        monkeypatch.setattr(db_module, 'db', mock_db)

        target_date = date.today()
        themes = [{'theme': 'Learning', 'planned_sessions': 3, 'notes': ''}]

        result = db_module.set_daily_focus(target_date, themes, 'Test notes')

        assert result is not None

        # Verify document exists
        doc = mock_db.daily_focus.find_one({'date': target_date.isoformat()})
        assert doc is not None
        assert 'themes' in doc
        assert len(doc['themes']) == 1
        assert doc['themes'][0]['theme'] == 'Learning'
        assert doc['themes'][0]['planned_sessions'] == 3

    def test_set_daily_focus_with_multiple_themes(self, mock_db, monkeypatch):
        """set_daily_focus() should store multiple themes."""
        import models.database as db_module
        monkeypatch.setattr(db_module, 'db', mock_db)

        target_date = date.today()
        themes = [
            {'theme': 'Database', 'planned_sessions': 2, 'notes': 'Morning'},
            {'theme': 'Learning', 'planned_sessions': 3, 'notes': 'Afternoon'},
            {'theme': 'Frontend', 'planned_sessions': 1, 'notes': ''}
        ]

        result = db_module.set_daily_focus(target_date, themes, 'Multi-theme day')

        doc = mock_db.daily_focus.find_one({'date': target_date.isoformat()})
        assert doc is not None
        assert len(doc['themes']) == 3
        assert doc['planned_sessions'] == 6  # 2 + 3 + 1

    def test_set_daily_focus_empty_themes(self, mock_db, monkeypatch):
        """set_daily_focus() should handle empty themes list."""
        import models.database as db_module
        monkeypatch.setattr(db_module, 'db', mock_db)

        target_date = date.today()
        themes = []

        result = db_module.set_daily_focus(target_date, themes, 'No themes')

        doc = mock_db.daily_focus.find_one({'date': target_date.isoformat()})
        assert doc is not None
        assert doc['themes'] == []
        assert doc['planned_sessions'] == 0

    def test_get_daily_focus_returns_themes_array(self, mock_db, monkeypatch):
        """get_daily_focus() should return themes array."""
        import models.database as db_module
        monkeypatch.setattr(db_module, 'db', mock_db)

        target_date = date.today()
        # Insert with themes array
        mock_db.daily_focus.insert_one({
            'date': target_date.isoformat(),
            'themes': [
                {'theme': 'Database', 'planned_sessions': 2, 'notes': ''},
                {'theme': 'Learning', 'planned_sessions': 4, 'notes': ''}
            ],
            'notes': 'Test',
            'planned_sessions': 6,
            'created_at': datetime.now(),
            'updated_at': datetime.now()
        })

        focus = db_module.get_daily_focus(target_date)

        assert focus is not None
        assert 'themes' in focus
        assert len(focus['themes']) == 2
        assert focus['planned_sessions'] == 6

    def test_get_daily_focus_backward_compatibility(self, mock_db, monkeypatch):
        """get_daily_focus() should convert old single theme to themes array."""
        import models.database as db_module
        monkeypatch.setattr(db_module, 'db', mock_db)

        target_date = date.today()
        # Insert with old format (single theme)
        mock_db.daily_focus.insert_one({
            'date': target_date.isoformat(),
            'theme': 'Learning',
            'planned_sessions': 5,
            'notes': 'Old format',
            'created_at': datetime.now()
        })

        focus = db_module.get_daily_focus(target_date)

        assert focus is not None
        assert 'themes' in focus
        assert len(focus['themes']) == 1
        assert focus['themes'][0]['theme'] == 'Learning'
        assert focus['themes'][0]['planned_sessions'] == 5

    def test_default_sessions_is_one(self, mock_db, monkeypatch):
        """Default planned_sessions should be 1 (not 3)."""
        import models.database as db_module
        monkeypatch.setattr(db_module, 'db', mock_db)

        target_date = date.today()
        # Theme without explicit planned_sessions
        themes = [{'theme': 'Learning'}]

        result = db_module.set_daily_focus(target_date, themes, '')

        doc = mock_db.daily_focus.find_one({'date': target_date.isoformat()})
        assert doc['themes'][0]['planned_sessions'] == 1


class TestCalendarMonthData:
    """Test calendar month data retrieval."""

    def test_get_calendar_month_returns_themes_array(self, mock_db, monkeypatch):
        """get_calendar_month() should return themes array for each day."""
        import models.database as db_module
        monkeypatch.setattr(db_module, 'db', mock_db)

        year = 2026
        month = 1

        # Insert focus with themes
        mock_db.daily_focus.insert_one({
            'date': '2026-01-15',
            'themes': [
                {'theme': 'Database', 'planned_sessions': 3, 'notes': ''},
                {'theme': 'Frontend', 'planned_sessions': 2, 'notes': ''}
            ],
            'notes': 'Test day',
            'planned_sessions': 5,
            'created_at': datetime.now()
        })

        result = db_module.get_calendar_month(year, month)

        assert '2026-01-15' in result
        day_data = result['2026-01-15']
        assert 'themes' in day_data
        assert len(day_data['themes']) == 2
        assert day_data['planned_sessions'] == 5

    def test_get_calendar_month_backward_compat(self, mock_db, monkeypatch):
        """get_calendar_month() should handle old single theme format."""
        import models.database as db_module
        monkeypatch.setattr(db_module, 'db', mock_db)

        year = 2026
        month = 1

        # Insert focus with old format
        mock_db.daily_focus.insert_one({
            'date': '2026-01-20',
            'theme': 'Learning',
            'planned_sessions': 4,
            'notes': 'Old format',
            'created_at': datetime.now()
        })

        result = db_module.get_calendar_month(year, month)

        assert '2026-01-20' in result
        day_data = result['2026-01-20']
        assert 'themes' in day_data
        assert len(day_data['themes']) == 1
        assert day_data['themes'][0]['theme'] == 'Learning'

    def test_get_calendar_month_empty_day(self, mock_db, monkeypatch):
        """get_calendar_month() should return empty themes for days without focus."""
        import models.database as db_module
        monkeypatch.setattr(db_module, 'db', mock_db)

        year = 2026
        month = 1

        result = db_module.get_calendar_month(year, month)

        # Day without any focus set
        day_data = result['2026-01-01']
        assert day_data['themes'] == []
        assert day_data['planned_sessions'] == 0


class TestCalendarWeekData:
    """Test calendar week data retrieval."""

    def test_get_calendar_week_returns_themes(self, mock_db, monkeypatch):
        """get_calendar_week() should return themes array for each day."""
        import models.database as db_module
        monkeypatch.setattr(db_module, 'db', mock_db)

        week_start = date(2026, 1, 5)  # Monday

        # Insert focus for a day in that week
        mock_db.daily_focus.insert_one({
            'date': '2026-01-06',
            'themes': [{'theme': 'Learning', 'planned_sessions': 5, 'notes': ''}],
            'notes': '',
            'planned_sessions': 5,
            'created_at': datetime.now()
        })

        result = db_module.get_calendar_week(week_start)

        assert 'days' in result
        assert '2026-01-06' in result['days']
        day_data = result['days']['2026-01-06']
        assert 'themes' in day_data
        assert len(day_data['themes']) == 1


class TestFocusAPIEndpoints:
    """Test focus API endpoints."""

    def test_api_focus_today_success_format(self, client, mock_db, monkeypatch):
        """GET /api/focus/today should return success and focus object."""
        import models.database as db_module
        monkeypatch.setattr(db_module, 'db', mock_db)

        response = client.get('/api/focus/today')
        data = response.get_json()

        assert 'success' in data
        assert 'focus' in data

    def test_api_focus_date_returns_themes(self, client, mock_db, monkeypatch):
        """GET /api/focus/<date> should return themes array."""
        import models.database as db_module
        monkeypatch.setattr(db_module, 'db', mock_db)

        # Insert focus
        mock_db.daily_focus.insert_one({
            'date': '2026-01-15',
            'themes': [
                {'theme': 'Learning', 'planned_sessions': 2, 'notes': ''}
            ],
            'notes': '',
            'planned_sessions': 2,
            'created_at': datetime.now()
        })

        response = client.get('/api/focus/2026-01-15')
        data = response.get_json()

        assert data['success'] == True
        assert 'themes' in data['focus']
        assert len(data['focus']['themes']) == 1

    def test_api_set_focus_with_themes_array(self, client, mock_db, monkeypatch):
        """POST /api/focus should accept themes array."""
        import models.database as db_module
        monkeypatch.setattr(db_module, 'db', mock_db)

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
        assert 'themes' in data
        assert len(data['themes']) == 2

    def test_api_set_focus_backward_compat(self, client, mock_db, monkeypatch):
        """POST /api/focus should accept old single theme format."""
        import models.database as db_module
        monkeypatch.setattr(db_module, 'db', mock_db)

        response = client.post('/api/focus', json={
            'date': '2026-01-21',
            'theme': 'Learning',
            'planned_sessions': 5,
            'notes': 'Old format test'
        })

        data = response.get_json()
        assert data['success'] == True
        # Should be converted to themes array
        assert 'themes' in data
        assert len(data['themes']) == 1


class TestCalendarAPIEndpoints:
    """Test calendar API endpoints."""

    def test_api_calendar_month_format(self, client, mock_db, monkeypatch):
        """GET /api/calendar/month/<year>/<month> should return correct format."""
        import models.database as db_module
        monkeypatch.setattr(db_module, 'db', mock_db)

        response = client.get('/api/calendar/month/2026/1')
        data = response.get_json()

        assert data['success'] == True
        assert 'days' in data
        assert isinstance(data['days'], list)
        assert len(data['days']) == 31  # January has 31 days

    def test_api_calendar_month_days_have_themes(self, client, mock_db, monkeypatch):
        """Calendar month days should have themes array."""
        import models.database as db_module
        monkeypatch.setattr(db_module, 'db', mock_db)

        # Insert a focus
        mock_db.daily_focus.insert_one({
            'date': '2026-01-10',
            'themes': [{'theme': 'Learning', 'planned_sessions': 3, 'notes': ''}],
            'notes': '',
            'planned_sessions': 3,
            'created_at': datetime.now()
        })

        response = client.get('/api/calendar/month/2026/1')
        data = response.get_json()

        # Find the day with focus
        day_10 = next((d for d in data['days'] if d['date'] == '2026-01-10'), None)
        assert day_10 is not None
        assert 'themes' in day_10
        assert len(day_10['themes']) == 1

    def test_api_calendar_month_invalid_date(self, client, mock_db, monkeypatch):
        """Calendar month should reject invalid dates."""
        import models.database as db_module
        monkeypatch.setattr(db_module, 'db', mock_db)

        response = client.get('/api/calendar/month/2026/13')
        assert response.status_code == 400

        response = client.get('/api/calendar/month/2026/0')
        assert response.status_code == 400


class TestPutFocusEndpoint:
    """Test PUT /api/focus/<date> endpoint."""

    def test_api_update_focus_with_themes(self, client, mock_db, monkeypatch):
        """PUT /api/focus/<date> should update with themes array."""
        import models.database as db_module
        monkeypatch.setattr(db_module, 'db', mock_db)

        # First create a focus
        mock_db.daily_focus.insert_one({
            'date': '2026-01-25',
            'themes': [{'theme': 'Database', 'planned_sessions': 2, 'notes': ''}],
            'notes': 'Original',
            'planned_sessions': 2,
            'created_at': datetime.now()
        })

        # Update it
        response = client.put('/api/focus/2026-01-25', json={
            'themes': [
                {'theme': 'Learning', 'planned_sessions': 4},
                {'theme': 'Frontend', 'planned_sessions': 1}
            ],
            'notes': 'Updated'
        })

        data = response.get_json()
        assert data['status'] == 'ok'
        assert len(data['themes']) == 2
        assert data['planned_sessions'] == 5

    def test_api_update_focus_not_found(self, client, mock_db, monkeypatch):
        """PUT /api/focus/<date> should return 404 for non-existent date."""
        import models.database as db_module
        monkeypatch.setattr(db_module, 'db', mock_db)

        response = client.put('/api/focus/2026-12-31', json={
            'themes': [{'theme': 'Learning', 'planned_sessions': 1}]
        })

        assert response.status_code == 404
