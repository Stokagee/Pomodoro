# Performance Optimization & FastAPI Migration Plan

**Tým:** Performance Team
**Trvání:** 2-3 týdny
**Priority:** DŮLEŽITÁ

## Shrnutí

Migrovat ML service na FastAPI pro vyšší performance a implementovat caching layer s Redis pro optimalizaci response times.

## Proč FastAPI?

### Performance Comparison (2025)

| Metrika | Flask | FastAPI | Zlepšení |
|---------|-------|---------|----------|
| Requests/Second | 3,000-4,000 | 15,000-20,000+ | **5-10x** |
| Latency p95 | ~200ms | ~70ms | **-65%** |
| Async Support | Přidáno (eventlet) | Native | **Out-of-box** |
| Type Safety | Volitelné | Požadováno | **Built-in** |

### Klíčové Výhody
- ✅ Native async/await - velké plus pro AI calls
- ✅ Automatic Pydantic validation (již používám)
- ✅ Native OpenAPI documentation
- ✅ 50+ endpoints - vysoká throughput je důležitá
- ✅ Lepší type safety

## Rozhodnutí

### ML Service → MIGROVAT NA FASTAPI
**Důvody:**
- Vysoká throughput potřeba pro ML predictions
- Hodně async operations (AI calls, DB queries)
- 50+ endpoints
- Pydantic už používám

### Web Service → ZŮSTAT NA FLASK
**Důvody:**
- SocketIO WebSocket komplexita
- Funguje dobře prozatím
- Nižší throughput požadavky
- Menší prioritní migrace

## Cílová Struktura (ML Service)

```
ml-service/
├── app/
│   ├── __init__.py              # FastAPI app factory
│   ├── main.py                  # FastAPI instance
│   ├── config.py                # Configuration
│   │
│   ├── api/                     # API Routers
│   │   ├── __init__.py
│   │   ├── predictions.py       # /api/prediction/*
│   │   ├── recommendations.py   # /api/recommendation
│   │   ├── analysis.py          # /api/analysis
│   │   ├── ai.py                # /api/ai/*
│   │   ├── cache.py             # /api/cache/*
│   │   └── health.py            # /health, /api/health
│   │
│   ├── models/                  # ML Models (existing)
│   │   ├── productivity_analyzer.py
│   │   ├── preset_recommender.py
│   │   ├── session_predictor.py
│   │   ├── burnout_predictor.py
│   │   ├── focus_optimizer.py
│   │   ├── quality_predictor.py
│   │   ├── anomaly_detector.py
│   │   ├── ai_analyzer.py
│   │   └── ai_challenge_generator.py
│   │
│   ├── services/                # Business Logic
│   │   ├── __init__.py
│   │   ├── prediction_service.py
│   │   ├── ai_service.py        # Async AI client
│   │   ├── embedding_service.py
│   │   └── cache_service.py
│   │
│   ├── repositories/            # Data Access
│   │   ├── __init__.py
│   │   └── session_repository.py
│   │
│   ├── schemas/                 # Pydantic Models
│   │   ├── __init__.py
│   │   ├── predictions.py
│   │   ├── recommendations.py
│   │   ├── ai.py
│   │   └── common.py
│   │
│   ├── middleware/              # Custom Middleware
│   │   ├── __init__.py
│   │   ├── correlation.py       # Distributed tracing
│   │   ├── rate_limit.py
│   │   └── auth.py
│   │
│   ├── utils/                   # Utilities
│   │   ├── __init__.py
│   │   ├── logger.py
│   │   └── metrics.py
│   │
│   └── db.py                    # Async PostgreSQL
│
├── tests/
│   ├── unit/
│   ├── integration/
│   └── e2e/
│
└── main.py                      # Uvicorn entry point
```

## Implementační Plán

### Phase 1: Foundation (1 týden)

#### 1.1 Setup FastAPI Project
```bash
# Install dependencies
pip install fastapi uvicorn httpx asyncpg
pip install pydantic-settings
```

#### 1.2 Configuration
```python
# app/config.py
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    """Application settings."""

    # Database
    database_url: str = "postgresql+asyncpg://user:pass@host/db"

    # AI Provider
    ai_provider: str = "cloud"
    ai_api_key: str
    ai_api_url: str = "https://api.openai.com/v1"

    # Cache
    redis_url: str = "redis://localhost:6379"

    # Application
    app_name: str = "Pomodoro ML Service"
    debug: bool = False

    class Config:
        env_file = ".env"

settings = Settings()
```

#### 1.3 FastAPI App Factory
```python
# app/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.middleware.correlation import CorrelationMiddleware
from app.api import predictions, recommendations, analysis, ai, cache, health

def create_app() -> FastAPI:
    """Create FastAPI application."""
    app = FastAPI(
        title=settings.app_name,
        description="ML service for Pomodoro Timer",
        version="2.0.0"
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5000"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Middleware
    app.add_middleware(CorrelationMiddleware)

    # Routers
    app.include_router(predictions.router, prefix="/api/prediction", tags=["predictions"])
    app.include_router(recommendations.router, prefix="/api", tags=["recommendations"])
    app.include_router(analysis.router, prefix="/api/analysis", tags=["analysis"])
    app.include_router(ai.router, prefix="/api/ai", tags=["ai"])
    app.include_router(cache.router, prefix="/api/cache", tags=["cache"])
    app.include_router(health.router, tags=["health"])

    return app

app = create_app()
```

#### 1.4 Async Database
```python
# app/db.py
from asyncpg import create_pool, Pool
from app.config import settings

class Database:
    """Async database connection pool."""

    def __init__(self):
        self.pool: Pool = None

    async def connect(self):
        """Create connection pool."""
        self.pool = await create_pool(
            settings.database_url,
            min_size=5,
            max_size=20
        )

    async def disconnect(self):
        """Close connection pool."""
        if self.pool:
            await self.pool.close()

    async def get_connection(self):
        """Get connection from pool."""
        return self.pool.acquire()

db = Database()

@app.on_event("startup")
async def startup():
    """Startup event."""
    await db.connect()

@app.on_event("shutdown")
async def shutdown():
    """Shutdown event."""
    await db.disconnect()
```

### Phase 2: Async AI Service (3 dny)

#### 2.1 Async AI Client
```python
# app/services/ai_service.py
import httpx
from typing import Dict, Any
from app.config import settings

class AIService:
    """Async AI service client."""

    def __init__(self):
        self.client = httpx.AsyncClient(timeout=180.0)
        self.api_key = settings.ai_api_key
        self.api_url = settings.ai_api_url

    async def completion(
        self,
        prompt: str,
        model: str = "gpt-4o-mini",
        max_tokens: int = 1000
    ) -> Dict[str, Any]:
        """Get AI completion."""
        response = await self.client.post(
            f"{self.api_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": max_tokens
            }
        )
        response.raise_for_status()
        return response.json()

    async def close(self):
        """Close HTTP client."""
        await self.client.aclose()

ai_service = AIService()
```

#### 2.2 Async Endpoint Example
```python
# app/api/ai.py
from fastapi import APIRouter, Depends, BackgroundTasks
from app.services.ai_service import ai_service
from app.schemas.ai import MorningBriefingRequest, MorningBriefingResponse

router = APIRouter()

@router.post("/morning-briefing", response_model=MorningBriefingResponse)
async def morning_briefing(request: MorningBriefingRequest):
    """Generate morning briefing."""
    # Prepare prompt
    prompt = f"Generate morning briefing for {request.date}..."

    # Async AI call
    response = await ai_service.completion(prompt)

    # Process response
    return MorningBriefingResponse(
        insights=response["choices"][0]["message"]["content"]
    )
```

### Phase 3: Migrate Core Endpoints (1 týden)

#### 3.1 Prediction Endpoints
```python
# app/api/predictions.py
from fastapi import APIRouter, Query
from app.schemas.predictions import TodayPredictionResponse, WeekPredictionResponse
from app.services.prediction_service import PredictionService

router = APIRouter()

@router.get("/today", response_model=TodayPredictionResponse)
async def get_today_prediction(
    date: str = Query(default_factory=lambda: datetime.now().strftime("%Y-%m-%d"))
):
    """Get today's session predictions."""
    service = PredictionService()
    predictions = await service.predict_today(date)
    return predictions

@router.get("/week", response_model=WeekPredictionResponse)
async def get_week_prediction(
    start_date: str = Query(default_factory=lambda: get_monday())
):
    """Get weekly session predictions."""
    service = PredictionService()
    predictions = await service.predict_week(start_date)
    return predictions
```

#### 3.2 Recommendation Endpoint
```python
# app/api/recommendations.py
from fastapi import APIRouter
from app.schemas.recommendations import RecommendationResponse
from app.services.prediction_service import PredictionService

router = APIRouter()

@router.get("/recommendation", response_model=RecommendationResponse)
async def get_recommendation(
    current_hour: int = Query(default_factory=lambda: datetime.now().hour),
    current_day: int = Query(default_factory=lambda: datetime.now().weekday())
):
    """Get preset recommendation based on context."""
    service = PredictionService()
    recommendation = await service.recommend_preset(current_hour, current_day)
    return recommendation
```

### Phase 4: Redis Caching (3 dny)

#### 4.1 Redis Configuration
```yaml
# docker-compose.yml
redis:
  image: redis:7-alpine
  ports:
    - "6379:6379"
  volumes:
    - redis_data:/data
```

#### 4.2 Cache Service
```python
# app/services/cache_service.py
import json
from typing import Optional, Any
import aioredis
from app.config import settings

class CacheService:
    """Redis cache service."""

    def __init__(self):
        self.redis: aioredis.Redis = None

    async def connect(self):
        """Connect to Redis."""
        self.redis = await aioredis.from_url(settings.redis_url)

    async def disconnect(self):
        """Disconnect from Redis."""
        if self.redis:
            await self.redis.close()

    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache."""
        value = await self.redis.get(key)
        if value:
            return json.loads(value)
        return None

    async def set(self, key: str, value: Any, ttl: int = 3600):
        """Set value in cache."""
        await self.redis.setex(key, ttl, json.dumps(value))

    async def delete(self, key: str):
        """Delete value from cache."""
        await self.redis.delete(key)

    async def invalidate_pattern(self, pattern: str):
        """Invalidate keys by pattern."""
        keys = await self.redis.keys(pattern)
        if keys:
            await self.redis.delete(*keys)

cache_service = CacheService()
```

#### 4.3 Cached Endpoints
```python
from fastapi_cache import FastAPICache
from fastapi_cache.backends.redis import RedisBackend
from app.services.cache_service import cache_service

@app.on_event("startup")
async def startup_cache():
    """Initialize cache."""
    FastAPICache.init(RedisBackend(cache_service.redis), prefix="pomodoro-api")

from fastapi_cache.decorator import cache

@router.get("/recommendation")
@cache(expire=300)  # 5 minutes
async def get_recommendation():
    """Get cached recommendation."""
    pass
```

### Phase 5: Integration & Testing (3 dny)

#### 5.1 Integration Tests
```python
# tests/integration/test_fastapi_api.py
import pytest
from httpx import AsyncClient
from app.main import app

@pytest.mark.asyncio
async def test_get_recommendation():
    """Test recommendation endpoint."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/api/recommendation")
        assert response.status_code == 200
        data = response.json()
        assert "preset" in data
        assert "confidence" in data

@pytest.mark.asyncio
async def test_ai_service():
    """Test AI service."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post("/api/ai/morning-briefing", json={
            "date": "2025-01-15"
        })
        assert response.status_code == 200
```

#### 5.2 Performance Tests
```python
# tests/performance/test_fastapi_performance.py
import pytest
import asyncio
from httpx import AsyncClient
from app.main import app

@pytest.mark.asyncio
async def test_concurrent_requests():
    """Test concurrent request handling."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        tasks = [client.get("/api/recommendation") for _ in range(100)]
        responses = await asyncio.gather(*tasks)
        assert all(r.status_code == 200 for r in responses)
```

### Phase 6: Deployment (2 dny)

#### 6.1 Uvicorn Configuration
```python
# main.py
import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=5002,
        reload=True,  # Development
        workers=4     # Production
    )
```

#### 6.2 Docker Configuration
```dockerfile
# ml-service/Dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "5002", "--workers", "4"]
```

#### 6.3 Blue-Green Deployment
```yaml
# docker-compose.yml
services:
  ml-service-v1:  # Old version
    build: ./ml-service
    container_name: pomodoro-ml-v1
    ports:
      - "5002:5002"

  ml-service-v2:  # New version
    build: ./ml-service
    container_name: pomodoro-ml-v2
    ports:
      - "5003:5002"
```

## Performance Targets

| Metrika | Aktuální (Flask) | Cíl (FastAPI) | Zlepšení |
|---------|------------------|---------------|----------|
| Requests/Second | 3,000 | 15,000 | **5x** |
| p50 Latency | ~100ms | ~30ms | **-70%** |
| p95 Latency | ~200ms | ~70ms | **-65%** |
| p99 Latency | ~500ms | ~150ms | **-70%** |
| Concurrent Users | 50 | 500 | **10x** |

## Konkrétní Úkoly

### Week 1: Foundation
- [ ] Setup FastAPI project structure
- [ ] Implementovat async database
- [ ] Implementovat async AI service
- [ ] Vytvořit Pydantic schemas

### Week 2: Migrate Endpoints
- [ ] Migrovat prediction endpoints
- [ ] Migrovat recommendation endpoints
- [ ] Migrovat analysis endpoints
- [ ] Migrovat AI endpoints

### Week 3: Caching & Deployment
- [ ] Implementovat Redis cache
- [ ] Přidat cache dekorátory
- [ ] Performance testy
- [ ] Blue-green deployment

## Success Criteria

- [ ] Všechny endpointy migrovány
- [ ] Async operations fungují
- [ ] Cache hit rate >80%
- [ ] Performance baseline splněn
- [ ] Tests passing
- [ ] Zero functional regressions

## Reference

### Best Practices (2025)
- [FastAPI vs Flask in 2025: The Real Differences](https://medium.com/@kaushalsinh73/fastapi-vs-flask-in-2025-the-real-differences-8fbca38d5ab0)
- [FastAPI for Microservices: High-Performance Python API Design Patterns 2025](https://talent500.com/blog/fastapi-microservices-python-api-design-patterns-2025/)
- [We Migrated from Flask to FastAPI. Here's What Actually Changed.](https://blog.stackademic.com/we-migrated-from-flask-to-fastapi-heres-what-actually-changed-a94b8fe6efb7)

### Tools
- **FastAPI**: Web framework
- **Uvicorn**: ASGI server
- **httpx**: Async HTTP client
- **asyncpg**: Async PostgreSQL
- **aioredis**: Async Redis
- **FastAPI-Cache**: Caching decorator

## Risks & Mitigation

| Risk | Pravděpodobnost | Dopad | Mitigace |
|------|----------------|-------|----------|
| Async/await learning curve | Vysoká | Vysoký | Training, gradual migration |
| Flask extensions unavailable | Střední | Střední | Native FastAPI alternatives |
| Performance regression | Nízká | Střední | Benchmarking, testing |
| Deployment complexity | Střední | Střední | Blue-green deployment |

## Notes

- ML service je prioritou pro FastAPI migraci
- Web service zůstává na Flask prozatím
- Paralelní běh během migrace
- Komplexní monitoring během přechodu
