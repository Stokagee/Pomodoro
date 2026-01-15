# QA Testing Plan - Coverage, Integration & E2E

**Tým:** QA Team
**Trvání:** 1-2 týdny
**Priority:** DŮLEŽITÁ

## Shrnutí

Zavést komplexní testovací infrastrukturu s coverage reporting, integration tests a end-to-end tests. Dosáhnout minimálně 80% code coverage.

## Současný Stav

### Co Máme
- 17 test souborů (11 ML, 6 web)
- Mock fixtures (MockCursor, MockConnection, MockPool)
- Sample data fixture
- Pytest konfigurace

### Co Chybí
- ❌ pytest-cov (coverage reporting)
- ❌ Coverage threshold
- ❌ Integration tests s Docker
- ❌ E2E tests
- ❌ Load tests
- ❌ API testing framework

## Cílová Struktura

```
tests/
├── conftest.py                  # Shared fixtures
├── unit/
│   ├── web/
│   │   ├── routes/
│   │   │   ├── test_sessions.py
│   │   │   ├── test_stats.py
│   │   │   ├── test_config.py
│   │   │   └── test_calendar.py
│   │   ├── services/
│   │   │   ├── test_session_service.py
│   │   │   ├── test_stats_service.py
│   │   │   └── test_ml_service.py
│   │   ├── repositories/
│   │   │   ├── test_session_repository.py
│   │   │   └── test_user_repository.py
│   │   └── utils/
│   │       └── test_validators.py
│   │
│   └── ml_service/
│       ├── models/
│       │   ├── test_productivity_analyzer.py
│       │   ├── test_preset_recommender.py
│       │   └── test_quality_predictor.py
│       ├── services/
│       │   └── test_ai_service.py
│       └── repositories/
│           └── test_session_repository.py
│
├── integration/
│   ├── test_api_integration.py
│   ├── test_database_integration.py
│   ├── test_ml_integration.py
│   ├── test_websocket_integration.py
│   └── docker-compose.test.yml
│
├── e2e/
│   ├── test_user_journeys.py
│   ├── test_timer_flow.py
│   ├── test_achievement_flow.py
│   └── playwright/
│       ├── test_timer_ui.py
│       ├── test_calendar_ui.py
│       └── test_settings_ui.py
│
├── performance/
│   ├── load_tests.py            # Locust
│   ├── benchmarks.py
│   └── profiling.py
│
└── fixtures/
    ├── data_generators.py
    ├── api_client.py
    └── db_seeder.py
```

## Implementační Plán

### Phase 1: pytest-cov Integration (2 dny)

#### 1.1 Nainstalovat pytest-cov
```bash
pip install pytest-cov
```

#### 1.2 Aktualizovat pytest.ini
```ini
[pytest]
testpaths = tests
python_files = test_*.py
python_functions = test_*
python_classes = Test*
addopts =
    -v
    --tb=short
    --cov=web
    --cov=ml-service
    --cov-report=term-missing
    --cov-report=html:htmlcov
    --cov-report=xml:coverage.xml
    --cov-report=json:coverage.json
    --cov-fail-under=80
filterwarnings =
    ignore::DeprecationWarning
    ignore::PendingDeprecationWarning
markers =
    slow: marks tests as slow
    integration: marks tests as integration
    e2e: marks tests as end-to-end
    freeze_time: marks tests that need frozen time
```

#### 1.3 Coverage Targets
- **Unit tests**: >90%
- **Integration tests**: >70%
- **Overall**: >80%

### Phase 2: Integration Tests (3 dny)

#### 2.1 Docker Compose pro Testování
```yaml
# tests/integration/docker-compose.test.yml
version: '3.8'

services:
  test-postgres:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_DB: pomodoro_test
      POSTGRES_USER: test
      POSTGRES_PASSWORD: test
    ports:
      - "5433:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U test -d pomodoro_test"]

  test-ml-service:
    build: ../../ml-service
    environment:
      DATABASE_URL: postgresql://test:test@test-postgres:5432/pomodoro_test
      FLASK_ENV: testing
    depends_on:
      test-postgres:
        condition: service_healthy

  test-web-service:
    build: ../../web
    environment:
      DATABASE_URL: postgresql://test:test@test-postgres:5432/pomodoro_test
      ML_SERVICE_URL: http://test-ml-service:5002
      FLASK_ENV: testing
    depends_on:
      test-postgres:
        condition: service_healthy
      test-ml-service:
        condition: service_started
```

#### 2.2 Integration Test Příklady
```python
# tests/integration/test_api_integration.py
import pytest
import requests
from docker import from_env

@pytest.fixture(scope="session")
def docker_compose():
    """Start Docker Compose for integration tests."""
    client = from_env()
    # Start services
    yield
    # Cleanup

@pytest.mark.integration
def test_session_lifecycle(docker_compose):
    """Test complete session lifecycle."""
    # Create session
    response = requests.post('http://localhost:5000/api/log', json={
        'preset': 'deep_work',
        'category': 'Testing',
        'task': 'Integration test',
        'duration_minutes': 52,
        'productivity_rating': 5
    })
    assert response.status_code == 201

    # Verify in database
    # Verify in stats
    # Verify in ML service
```

### Phase 3: E2E Tests (3 dny)

#### 3.1 Playwright Setup
```bash
pip install pytest-playwright
playwright install
```

#### 3.2 E2E Test Příklady
```python
# tests/e2e/playwright/test_timer_ui.py
from playwright.sync_api import Page, expect

@pytest.mark.e2e
def test_complete_pomodoro_session(page: Page):
    """Test complete Pomodoro session flow."""
    # Navigate to app
    page.goto("http://localhost:5000")

    # Select preset
    page.select_option("#preset", "deep_work")

    # Start timer
    page.click("#start-button")

    # Wait for completion
    page.wait_for_selector("#timer-complete", timeout=60000)

    # Rate session
    page.click("#rating-5")

    # Verify stats updated
    page.goto("/stats")
    expect(page.locator("#today-sessions")).to_contain_text("1")
```

### Phase 4: Performance Tests (2 dny)

#### 4.1 Locust Load Testing
```python
# tests/performance/load_tests.py
from locust import HttpUser, task, between

class PomodoroUser(HttpUser):
    wait_time = between(1, 3)

    def on_start(self):
        """Login on start."""
        self.client.get("/")

    @task(3)
    def view_dashboard(self):
        """View dashboard."""
        self.client.get("/")

    @task(2)
    def get_stats(self):
        """Get statistics."""
        self.client.get("/api/stats/today")

    @task(1)
    def create_session(self):
        """Create a session."""
        self.client.post("/api/log", json={
            'preset': 'deep_work',
            'category': 'Load Test',
            'task': 'Performance test',
            'duration_minutes': 52
        })
```

#### 4.2 Performance Targets
- **p50 latency**: <100ms
- **p95 latency**: <200ms
- **p99 latency**: <500ms
- **Throughput**: 1000 RPS

### Phase 5: Test Utilities (2 dny)

#### 5.1 API Client Wrapper
```python
# tests/fixtures/api_client.py
import requests
from typing import Dict, Any

class TestAPIClient:
    """Wrapper for API testing."""

    def __init__(self, base_url: str = "http://localhost:5000"):
        self.base_url = base_url
        self.session = requests.Session()

    def create_session(self, **kwargs) -> Dict[str, Any]:
        """Create a session."""
        response = self.session.post(
            f"{self.base_url}/api/log",
            json=kwargs
        )
        response.raise_for_status()
        return response.json()

    def get_stats(self, period: str = "today") -> Dict[str, Any]:
        """Get statistics."""
        response = self.session.get(f"{self.base_url}/api/stats/{period}")
        response.raise_for_status()
        return response.json()

@pytest.fixture
def api_client():
    """API client fixture."""
    return TestAPIClient()
```

#### 5.2 Test Data Generators
```python
# tests/fixtures/data_generators.py
import random
from datetime import datetime, timedelta

def generate_session_data(overwrite: Dict = None) -> Dict:
    """Generate realistic session data."""
    presets = ['deep_work', 'learning', 'quick_tasks', 'flow_mode']
    categories = ['SOAP', 'Robot Framework', 'REST API', 'Database']

    data = {
        'preset': random.choice(presets),
        'category': random.choice(categories),
        'task': f'Test task {random.randint(1, 1000)}',
        'duration_minutes': random.choice([25, 45, 52, 90]),
        'productivity_rating': random.randint(1, 5),
        'completed': True
    }

    if overwrite:
        data.update(overwrite)

    return data

def generate_sessions_batch(count: int) -> List[Dict]:
    """Generate multiple sessions."""
    return [generate_session_data() for _ in range(count)]
```

## Konkrétní Úkoly

### Week 1: Foundation
- [ ] Nainstalovat pytest-cov
- [ ] Aktualizovat pytest.ini
- [ ] Vytvořit test directory structure
- [ ] Přesunout existující testy
- [ ] Spustit coverage baseline

### Week 2: Integration
- [ ] Vytvořit docker-compose.test.yml
- [ ] Implementovat API integration tests
- [ ] Implementovat database integration tests
- [ ] Implementovat ML service integration tests

### Week 3: E2E & Performance
- [ ] Nainstalovat Playwright
- [ ] Implementovat E2E user journeys
- [ ] Implementovat Locust load tests
- [ ] Definovat performance baselines

## Success Criteria

- [ ] pytest-cov integrován
- [ ] Coverage >80%
- [ ] Integration tests passing
- [ ] E2E tests passing
- [ ] Performance benchmarks defined
- [ ] CI/CD integration ready

## Reference

### Best Practices (2025)
- [pytest-cov Official Documentation](https://pytest-cov.readthedocs.io/en/latest/reporting.html)
- [Maximizing Test Coverage with Pytest](https://www.graphapp.ai/blog/maximizing-test-coverage-with-pytest)
- [Master pytest-cov: Boost Your Python Test Coverage](https://blog.mergify.com/pytest-cov-boost-your-python-test-coverage)

### Tools
- **pytest**: Test framework
- **pytest-cov**: Coverage reporting
- **pytest-playwright**: E2E testing
- **Locust**: Load testing
- **Docker**: Integration testing

## Notes

- Testy by měly běžet v každém PR
- Coverage report by měl být viditelný v PR
- Performance testy v nightly builds
- E2E testy před release
