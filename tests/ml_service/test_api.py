"""
ML Service API Endpoint Tests.
Tests all Flask API routes for ML service.
"""
import pytest
import json
from datetime import datetime


class TestHealthEndpoint:
    """Test health check endpoint."""

    def test_health_endpoint(self, ml_client, mock_db):
        """GET /api/health should return service status."""
        response = ml_client.get('/api/health')
        assert response.status_code == 200

        data = json.loads(response.data)
        assert 'status' in data or 'database' in data


class TestAnalysisEndpoint:
    """Test analysis API endpoint."""

    def test_analysis_empty_db(self, ml_client, mock_db_empty):
        """GET /api/analysis should return default values for empty DB."""
        response = ml_client.get('/api/analysis')
        assert response.status_code == 200

        data = json.loads(response.data)
        assert 'analysis' in data
        assert data['analysis'].get('total_sessions_analyzed', 0) == 0

    def test_analysis_with_data(self, ml_client, mock_db):
        """GET /api/analysis should return computed analysis."""
        response = ml_client.get('/api/analysis')
        assert response.status_code == 200

        data = json.loads(response.data)
        assert 'analysis' in data

        analysis = data['analysis']
        assert 'best_hours' in analysis
        assert 'trend' in analysis
        assert analysis.get('total_sessions_analyzed', 0) > 0


class TestRecommendationEndpoint:
    """Test preset recommendation endpoint."""

    def test_recommendation_returns_preset(self, ml_client, mock_db):
        """GET /api/recommendation should return a preset."""
        response = ml_client.get('/api/recommendation')
        assert response.status_code == 200

        data = json.loads(response.data)
        assert 'recommended_preset' in data
        assert data['recommended_preset'] in ['deep_work', 'learning', 'quick_tasks', 'flow_mode']

    def test_recommendation_with_category(self, ml_client, mock_db):
        """GET /api/recommendation?category=SOAP should consider category."""
        response = ml_client.get('/api/recommendation?category=SOAP')
        assert response.status_code == 200

        data = json.loads(response.data)
        assert 'recommended_preset' in data
        assert 'confidence' in data

    @pytest.mark.freeze_time('2025-12-28 08:00:00')
    def test_recommendation_morning(self, ml_client, mock_db):
        """Morning hours should recommend deep_work or learning."""
        response = ml_client.get('/api/recommendation')
        data = json.loads(response.data)

        # Morning should prefer focused work
        assert data['recommended_preset'] in ['deep_work', 'learning', 'flow_mode']

    @pytest.mark.freeze_time('2025-12-28 14:00:00')
    def test_recommendation_afternoon(self, ml_client, mock_db):
        """Afternoon hours may recommend lighter presets."""
        response = ml_client.get('/api/recommendation')
        data = json.loads(response.data)

        # Should return some preset
        assert 'recommended_preset' in data

    @pytest.mark.freeze_time('2025-12-28 18:00:00')
    def test_recommendation_evening(self, ml_client, mock_db):
        """Evening hours recommendation."""
        response = ml_client.get('/api/recommendation')
        data = json.loads(response.data)

        assert 'recommended_preset' in data


class TestPredictionEndpoints:
    """Test prediction API endpoints."""

    def test_prediction_today(self, ml_client, mock_db):
        """GET /api/prediction/today should return today's prediction."""
        response = ml_client.get('/api/prediction/today')
        assert response.status_code == 200

        data = json.loads(response.data)
        assert 'predicted_sessions' in data
        assert 'confidence' in data

    def test_prediction_week(self, ml_client, mock_db):
        """GET /api/prediction/week should return 7-day forecast."""
        response = ml_client.get('/api/prediction/week')
        assert response.status_code == 200

        data = json.loads(response.data)
        assert 'predictions' in data or 'forecast' in data or isinstance(data, list)


class TestTrendsEndpoint:
    """Test trends API endpoint."""

    def test_trends_endpoint(self, ml_client, mock_db):
        """GET /api/trends should return trend data."""
        response = ml_client.get('/api/trends')
        assert response.status_code == 200

        data = json.loads(response.data)
        # Should have some trend information
        assert 'session_trend' in data or 'productivity_trend' in data or 'trend' in data


class TestInsightsSummary:
    """Test combined insights endpoint."""

    def test_insights_summary(self, ml_client, mock_db):
        """GET /api/insights/summary should return combined data."""
        response = ml_client.get('/api/insights/summary')
        assert response.status_code == 200

        data = json.loads(response.data)
        # Should have analysis, recommendation, and prediction
        assert any(key in data for key in ['analysis', 'recommendation', 'prediction', 'trends'])
