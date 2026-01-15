# Backend Refactoring Plan - Application Factory & Blueprints

**Tým:** Backend Team
**Trvání:** 2-3 týdny
**Priority:** KRITICKÁ

## Shrnutí

Přeorganizovat monolitické `app.py` soubory (2,945 lines web, 1,829 lines ML) do modulární struktury s Application Factory pattern a Blueprint pattern.

## Současný Stav

### Web Service (`web/app.py`)
```
- 2,945 řádků v jednom souboru
- Všechny routy, business logic, DB operace míchané
- Není oddělení concerns
- Není configuration management
- Není service/repository layer
```

### ML Service (`ml-service/app.py`)
```
- 1,829 řádků v jednom souboru
- 50+ API endpoints
- 10 ML models
- AI/LLM integration
- Plánovaná migrace na FastAPI (viz Performance Team plan)
```

## Cílová Struktura

### Web Service
```
web/
├── app/
│   ├── __init__.py              # Application Factory
│   ├── config.py                # Configuration classes
│   ├── extensions.py            # Flask extensions init
│   │
│   ├── api/                     # API Blueprint
│   │   ├── __init__.py
│   │   ├── routes/
│   │   │   ├── __init__.py
│   │   │   ├── sessions.py
│   │   │   ├── stats.py
│   │   │   ├── config.py
│   │   │   ├── calendar.py
│   │   │   ├── achievements.py
│   │   │   └── wellness.py
│   │   └── schemas/
│   │       ├── session.py
│   │       ├── stats.py
│   │       └── common.py
│   │
│   ├── web/                     # Web Routes Blueprint
│   │   ├── __init__.py
│   │   └── routes.py
│   │
│   ├── ws/                      # WebSocket Blueprint
│   │   ├── __init__.py
│   │   └── events.py
│   │
│   ├── errors/                  # Error Handler Blueprint
│   │   ├── __init__.py
│   │   ├── handlers.py
│   │   └── exceptions.py
│   │
│   ├── services/                # Business Logic Layer
│   │   ├── __init__.py
│   │   ├── session_service.py
│   │   ├── stats_service.py
│   │   ├── ml_service.py
│   │   ├── achievement_service.py
│   │   └── wellness_service.py
│   │
│   ├── repositories/            # Data Access Layer
│   │   ├── __init__.py
│   │   ├── session_repository.py
│   │   ├── user_repository.py
│   │   ├── achievement_repository.py
│   │   └── cache_repository.py
│   │
│   ├── middleware/
│   │   ├── __init__.py
│   │   ├── correlation.py
│   │   └── validation.py
│   │
│   ├── utils/
│   │   ├── __init__.py
│   │   ├── logger.py
│   │   ├── scheduler.py
│   │   └── validators.py
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   └── database.py
│   │
│   ├── static/
│   └── templates/
│
├── tests/
│   ├── unit/
│   │   ├── routes/
│   │   ├── services/
│   │   └── repositories/
│   └── integration/
│
├── run.py                       # Entry point
└── wsgi.py                      # WSGI entry
```

### ML Service (před FastAPI migrací)
```
ml-service/
├── app/
│   ├── __init__.py              # Application Factory
│   ├── config.py
│   │
│   ├── api/                     # API Blueprint
│   │   ├── __init__.py
│   │   ├── predictions.py
│   │   ├── recommendations.py
│   │   ├── analysis.py
│   │   ├── ai.py
│   │   ├── cache.py
│   │   └── health.py
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   ├── prediction_service.py
│   │   ├── ai_service.py
│   │   └── cache_service.py
│   │
│   ├── repositories/
│   │   ├── __init__.py
│   │   └── session_repository.py
│   │
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── predictions.py
│   │   └── common.py
│   │
│   ├── models/
│   │   └── (existing ML models)
│   │
│   ├── utils/
│   │   ├── __init__.py
│   │   ├── logger.py
│   │   └── metrics.py
│   │
│   └── db.py
│
└── main.py                      # Entry point
```

## Implementační Plán

### Týden 1: Základy

#### Den 1-2: Configuration Management
```python
# app/config.py
import os
from dotenv import load_dotenv

class Config:
    """Base configuration."""
    load_dotenv()
    SECRET_KEY = os.getenv('SECRET_KEY')
    DATABASE_URL = os.getenv('DATABASE_URL')
    ML_SERVICE_URL = os.getenv('ML_SERVICE_URL')
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')

class DevelopmentConfig(Config):
    DEBUG = True
    TESTING = False

class ProductionConfig(Config):
    DEBUG = False
    TESTING = False

class TestingConfig(Config):
    TESTING = True
    DATABASE_URL = 'sqlite:///:memory:'

config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig
}
```

#### Den 3-4: Application Factory
```python
# app/__init__.py
from flask import Flask
from flask_socketio import SocketIO
from app.config import config
from app.extensions import init_extensions

def create_app(config_name='development'):
    """Application factory pattern."""
    app = Flask(__name__)
    app.config.from_object(config[config_name])

    # Initialize extensions
    init_extensions(app)

    # Register blueprints
    from app.api import bp as api_bp
    from app.web import bp as web_bp
    from app.ws import bp as ws_bp
    from app.errors import bp as errors_bp

    app.register_blueprint(api_bp, url_prefix='/api')
    app.register_blueprint(web_bp)
    app.register_blueprint(ws_bp)
    app.register_blueprint(errors_bp)

    return app

# run.py
from app import create_app

app = create_app(os.getenv('FLASK_ENV', 'development'))

if __name__ == '__main__':
    from app.extensions import socketio
    socketio.run(app, host='0.0.0.0', port=5000)
```

### Týden 2: Blueprints & Services

#### Den 1-3: API Blueprint
Vytvořit blueprinty pro každou oblast:
- `sessions.py` - Session CRUD operations
- `stats.py` - Statistics endpoints
- `config.py` - Configuration endpoints
- `calendar.py` - Calendar operations
- `achievements.py` - Gamification endpoints
- `wellness.py` - Wellness checkins

#### Den 4-5: Service Layer
Vytvořit service classes pro business logic:
```python
# services/session_service.py
class SessionService:
    def __init__(self, session_repository, ml_service):
        self.session_repo = session_repository
        self.ml_service = ml_service

    def create_session(self, data):
        # Business logic here
        pass

    def get_session_stats(self, date_range):
        # Statistics logic here
        pass
```

### Týden 3: Repositories & Integration

#### Den 1-3: Repository Pattern
```python
# repositories/session_repository.py
class SessionRepository:
    def __init__(self, db_pool):
        self.pool = db_pool

    def save(self, session_data):
        # Database operations
        pass

    def find_by_date(self, date):
        # Database queries
        pass
```

#### Den 4-5: Integration Testing
Otestovat novou strukturu:
- Unit testy pro services
- Integration testy pro repositories
- End-to-end testy pro API

## Konkrétní Úkoly

### Phase 1: Foundation (3 dny)
- [ ] Vytvořit `app/config.py`
- [ ] Vytvořit `app/extensions.py`
- [ ] Implementovat `create_app()` factory
- [ ] Přesunout setup kód z `app.py`

### Phase 2: API Blueprint (4 dny)
- [ ] Vytvořit `app/api/__init__.py`
- [ ] Přesunout session routes → `routes/sessions.py`
- [ ] Přesunout stats routes → `routes/stats.py`
- [ ] Přesunout config routes → `routes/config.py`
- [ ] Přesunout calendar routes → `routes/calendar.py`
- [ ] Přesunout achievements routes → `routes/achievements.py`
- [ ] Přesunout wellness routes → `routes/wellness.py`
- [ ] Vytvořit Pydantic schemas

### Phase 3: Service Layer (3 dny)
- [ ] Vytvořit `services/session_service.py`
- [ ] Vytvořit `services/stats_service.py`
- [ ] Vytvořit `services/ml_service.py`
- [ ] Vytvořit `services/achievement_service.py`
- [ ] Vytvořit `services/wellness_service.py`
- [ ] Přesunout business logic z routes

### Phase 4: Repository Layer (3 dny)
- [ ] Vytvořit `repositories/session_repository.py`
- [ ] Vytvořit `repositories/user_repository.py`
- [ ] Vytvořit `repositories/achievement_repository.py`
- [ ] Vytvořit `repositories/cache_repository.py`
- [ ] Přesunout DB operace z `models/database.py`

### Phase 5: Error Handling (2 dny)
- [ ] Vytvořit `errors/exceptions.py`
- [ ] Vytvořit `errors/handlers.py`
- [ ] Vytvořit `errors/__init__.py` (blueprint)
- [ ] Implementovat unified error response

### Phase 6: Testing & Documentation (2 dny)
- [ ] Přepsat unit testy pro novou strukturu
- [ ] Přidat integration testy
- [ ] Aktualizovat dokumentaci

## Reference

### Best Practices (2025)
- [How To Structure a Large Flask Application - Best Practices for 2025](https://dev.to/gajanan0707/how-to-structure-a-large-flask-application-best-practices-for-2025-9j2)
- [Building Scalable Flask Applications with Blueprints and Application Factories](https://leapcell.io/blog/building-scalable-flask-applications-with-blueprints-and-application-factories)
- [Flask Project Structure Best Practices + Application Factory](https://muneebdev.com/flask-project-structure-best-practices/)

### Klíčové Principy
- **DRY**: Žádná duplicita kódu
- **SOLID**: Jedna třída = jedna zodpovědnost
- **SoC**: Oddělení concerns (routes, services, repositories)
- **Dependency Injection**: Vkládání závislostí
- **Configuration Management**: Environment-based config

## Success Criteria

- [ ] Application Factory pattern implementován
- [ ] Všechny routy v blueprints
- [ ] Business logic v service layer
- [ ] DB operace v repository layer
- [ ] Unit testy passing
- [ ] Integration testy passing
- [ ] Documentation updated
- [ ] Zero functional regressions

## Risks & Mitigation

| Risk | Pravděpodobnost | Dopad | Mitigace |
|------|----------------|-------|----------|
| Breaking changes | Vysoká | Vysoký | Comprehensive testing, gradual rollout |
| Learning curve | Střední | Střední | Code review, pair programming |
| Timeline slip | Střední | Střední | MVP scope, phased rollout |
| Performance regression | Nízká | Střední | Benchmarking, profiling |

## Notes

- Tento refaktoring je předpoklad pro další fáze (testing, security, CI/CD)
- ML service bude následně migrován na FastAPI (Performance Team)
- Vytvořit feature branch pro každou fázi
- Code review je kritický
