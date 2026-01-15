# Documentation & Knowledge Sharing Plan

**Tým:** Documentation Team
**Trvání:** 2 týdny
**Priority:** STŘEDNÍ

## Shrnutí

Vytvořit komplexní dokumentaci včetně API dokumentace (OpenAPI), architektury, deployment guide, runbooks a knowledge base.

## Současný Stav

### Co Máme
- ✅ CLAUDE.md (project documentation)
- ✅ Monitoring stack (Grafana dashboards)
- ✅ Docker Compose s komentáři

### Co Chybí
- ❌ API documentation (OpenAPI/Swagger)
- ❌ Architecture documentation
- ❌ Deployment guide
- ❌ Runbooks
- ❌ Developer documentation
- ❌ Knowledge base
- ❌ Troubleshooting guide

## Cílová Struktura

```
docs/
├── README.md                   # Documentation index
│
├── api/                        # API Documentation
│   ├── openapi.yaml            # OpenAPI 3.1 spec
│   ├── web/
│   │   ├── sessions.md         # Session endpoints
│   │   ├── stats.md            # Statistics endpoints
│   │   ├── config.md           # Configuration endpoints
│   │   ├── calendar.md         # Calendar endpoints
│   │   ├── achievements.md     # Gamification endpoints
│   │   └── wellness.md         # Wellness endpoints
│   │
│   └── ml-service/
│       ├── predictions.md      # Prediction endpoints
│       ├── recommendations.md  # Recommendation endpoints
│       ├── analysis.md         # Analysis endpoints
│       ├── ai.md               # AI/LLM endpoints
│       └── cache.md            # Cache endpoints
│
├── architecture/               # Architecture Documentation
│   ├── overview.md             # System overview
│   ├── components.md           # Component diagrams
│   ├── data-flow.md            # Data flow diagrams
│   ├── database.md             # Database schema
│   └── microservices.md        # Microservices architecture
│
├── deployment/                 # Deployment Documentation
│   ├── local-setup.md          # Local development setup
│   ├── docker.md               # Docker deployment
│   ├── kubernetes.md           # Kubernetes deployment (future)
│   ├── monitoring.md           # Monitoring setup
│   └── backup-restore.md       # Backup & restore procedures
│
├── development/                # Developer Documentation
│   ├── getting-started.md      # Quick start guide
│   ├── code-structure.md       # Code structure guide
│   ├── coding-standards.md     # Coding standards
│   ├── testing.md              # Testing guide
│   ├── debugging.md            # Debugging guide
│   └── contributing.md         # Contributing guidelines
│
├── runbooks/                   # Runbooks
│   ├── incident-response.md    # Incident response procedures
│   ├── deployment.md           # Deployment procedures
│   ├── rollback.md             # Rollback procedures
│   ├── troubleshooting.md      # Troubleshooting guide
│   └── maintenance.md          # Maintenance procedures
│
└── knowledge-base/             # Knowledge Base
    ├── faq.md                  # Frequently asked questions
    ├── known-issues.md         # Known issues & workarounds
    ├── best-practices.md       # Best practices
    ├── lessons-learned.md      # Lessons learned
    └── glossary.md             # Glossary of terms
```

## Implementační Plán

### Phase 1: API Documentation (3 dny)

#### 1.1 OpenAPI Specification
```yaml
# api/openapi.yaml
openapi: 3.1.0
info:
  title: Pomodoro Timer API
  description: Productivity timer with ML recommendations
  version: 2.0.0
  contact:
    name: API Support
    email: support@pomodoro.app

servers:
  - url: http://localhost:5000/api
    description: Local development
  - url: https://api.pomodoro.app
    description: Production

paths:
  /log:
    post:
      summary: Create a new session
      tags:
        - Sessions
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/SessionCreate'
      responses:
        '201':
          description: Session created successfully
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Session'

components:
  schemas:
    SessionCreate:
      type: object
      required:
        - preset
        - category
        - task
        - duration_minutes
      properties:
        preset:
          type: string
          enum: [deep_work, learning, quick_tasks, flow_mode]
        category:
          type: string
          minLength: 1
          maxLength: 50
        task:
          type: string
          minLength: 1
          maxLength: 200
        duration_minutes:
          type: integer
          minimum: 1
          maximum: 180
```

#### 1.2 API Documentation Pages
```markdown
# api/web/sessions.md

## Session Management

### Create Session

Create a new Pomodoro session.

**Endpoint:** `POST /api/log`

**Authentication:** Required (JWT token)

**Request Body:**
```json
{
  "preset": "deep_work",
  "category": "SOAP",
  "task": "Study WSDL",
  "duration_minutes": 52,
  "productivity_rating": 5,
  "notes": "Great focus!"
}
```

**Response:**
```json
{
  "id": 123,
  "preset": "deep_work",
  "category": "SOAP",
  "task": "Study WSDL",
  "duration_minutes": 52,
  "completed": true,
  "created_at": "2025-01-15T10:30:00Z"
}
```

**Status Codes:**
- `201` - Session created
- `400` - Validation error
- `401` - Unauthorized
- `500` - Server error

### Get Sessions

Retrieve session history.

**Endpoint:** `GET /api/history`

**Query Parameters:**
- `start_date` (string) - Start date (YYYY-MM-DD)
- `end_date` (string) - End date (YYYY-MM-DD)
- `limit` (integer) - Max results (default: 100)

**Response:**
```json
{
  "sessions": [...],
  "total": 150,
  "limit": 100
}
```
```

### Phase 2: Architecture Documentation (3 dny)

#### 2.1 System Overview
```markdown
# architecture/overview.md

## System Overview

Pomodoro Timer is a microservices-based productivity application optimized for IT professionals with 52/17 Deep Work mode.

### Architecture Diagram

```
┌─────────────┐     ┌─────────────┐
│   Browser   │────▶│ Web Service │
└─────────────┘     └─────────────┘
     │                    │
     │                    ▼
     │            ┌─────────────┐
     └───────────▶│   ML Service│
                  └─────────────┘
                         │
                         ▼
                  ┌─────────────┐
                  │  PostgreSQL │
                  │   + pgvector│
                  └─────────────┘
```

### Components

| Component | Technology | Port | Description |
|-----------|------------|------|-------------|
| Web Service | Flask + SocketIO | 5000 | Main application |
| ML Service | FastAPI | 5002 | ML predictions |
| PostgreSQL | pgvector/pg16 | 5432 | Database |
| Redis | Redis 7 | 6379 | Caching |
| Ollama | ollama/ollama | 11434 | Local AI |

### Data Flow

1. User starts timer → Web Service
2. Web Service logs session → PostgreSQL
3. Web Service requests prediction → ML Service
4. ML Service queries history → PostgreSQL
5. ML Service runs model → Prediction
6. Web Service displays prediction → User
```

#### 2.2 Component Diagrams
```markdown
# architecture/components.md

## Component Diagrams

### Web Service Components

```
┌─────────────────────────────────────┐
│         Web Service (Flask)          │
├─────────────────────────────────────┤
│  ┌─────────┐  ┌─────────┐          │
│  │ Routes  │─▶│Services │─▶┌──────┐│
│  └─────────┘  └─────────┘  │ Repos││
│                            └──────┘│
└─────────────────────────────────────┘
         │                    │
         ▼                    ▼
    ┌─────────┐         ┌─────────┐
    │  ML API │         │   DB    │
    └─────────┘         └─────────┘
```

### ML Service Components

```
┌─────────────────────────────────────┐
│        ML Service (FastAPI)         │
├─────────────────────────────────────┤
│  ┌─────────┐  ┌─────────────────┐  │
│  │ Routers │─▶│  ML Models      │  │
│  └─────────┘  │ (10 models)     │  │
│              └─────────────────┘  │
│              ┌─────────────────┐  │
│              │ AI Service      │  │
│              │ (async)         │  │
│              └─────────────────┘  │
└─────────────────────────────────────┘
```
```

### Phase 3: Deployment Documentation (2 dny)

#### 3.1 Local Development Setup
```markdown
# deployment/local-setup.md

## Local Development Setup

### Prerequisites

- Docker & Docker Compose
- Python 3.11+
- Git

### Quick Start

1. **Clone repository**
   ```bash
   git clone https://github.com/your-org/pomodoro.git
   cd pomodoro
   ```

2. **Configure environment**
   ```bash
   cp .env.example .env
   # Edit .env with your settings
   ```

3. **Start services**
   ```bash
   docker-compose up -d
   ```

4. **Access application**
   - Web: http://localhost:5000
   - ML API: http://localhost:5002
   - Grafana: http://localhost:3000 (admin/admin)
   - Prometheus: http://localhost:9090

### Development Workflow

1. **Make changes**
   - Edit code in `web/` or `ml-service/`
   - Changes auto-reload in development

2. **Run tests**
   ```bash
   pytest tests/
   ```

3. **Check logs**
   ```bash
   docker-compose logs -f
   ```

### Troubleshooting

**Port already in use?**
```bash
# Check what's using the port
lsof -i :5000

# Change port in docker-compose.yml
ports:
  - "5001:5000"  # Use 5001 instead
```

**Database connection issues?**
```bash
# Check PostgreSQL is healthy
docker-compose ps postgres

# Restart database
docker-compose restart postgres
```
```

#### 3.2 Docker Deployment
```markdown
# deployment/docker.md

## Docker Deployment

### Build Images

```bash
# Build web service
docker build -t pomodoro/web:latest ./web

# Build ML service
docker build -t pomodoro/ml-service:latest ./ml-service
```

### Deploy with Docker Compose

```bash
# Start all services
docker-compose up -d

# Check status
docker-compose ps

# View logs
docker-compose logs -f
```

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| DATABASE_URL | PostgreSQL connection | - |
| ML_SERVICE_URL | ML service URL | http://ml-service:5002 |
| LOG_LEVEL | Logging level | INFO |
| AI_PROVIDER | AI provider (ollama/cloud) | cloud |

### Production Deployment

```bash
# Use production configuration
export FLASK_ENV=production

# Start with production settings
docker-compose -f docker-compose.prod.yml up -d
```
```

### Phase 4: Runbooks (3 dny)

#### 4.1 Incident Response
```markdown
# runbooks/incident-response.md

## Incident Response Procedures

### Severity Levels

| Severity | Description | Response Time |
|----------|-------------|---------------|
| P0 - Critical | System down | 15 minutes |
| P1 - High | Major functionality broken | 1 hour |
| P2 - Medium | Partial degradation | 4 hours |
| P3 - Low | Minor issues | 1 day |

### Incident Response Process

1. **Detection**
   - Monitor alerts (Grafana, PagerDuty)
   - User reports

2. **Assessment**
   - Determine severity
   - Identify affected components

3. **Response**
   - Follow runbooks below
   - Escalate if needed

4. **Resolution**
   - Implement fix
   - Verify resolution

5. **Post-Mortem**
   - Document incident
   - Identify root cause
   - Create action items

### Common Incidents

#### High CPU Usage
```bash
# Check CPU usage
docker stats

# Identify problematic container
docker top <container>

# Restart if needed
docker-compose restart <service>
```

#### Database Connection Issues
```bash
# Check connection pool
docker-compose exec web python -c "from models.database import get_pool; print(get_pool())"

# Restart database
docker-compose restart postgres

# Check logs
docker-compose logs postgres
```

#### ML Service Unavailable
```bash
# Check health
curl http://localhost:5002/api/health

# Check logs
docker-compose logs ml-service

# Restart service
docker-compose restart ml-service
```
```

#### 4.2 Deployment Runbook
```markdown
# runbooks/deployment.md

## Deployment Procedures

### Pre-Deployment Checklist

- [ ] All tests passing
- [ ] Code reviewed
- [ ] Documentation updated
- [ ] Database migrations prepared
- [ ] Rollback plan ready
- [ ] Monitoring configured

### Deployment Steps

1. **Preparation**
   ```bash
   # Checkout target branch
   git checkout main
   git pull origin main

   # Verify version
   git log -1
   ```

2. **Backup**
   ```bash
   # Backup database
   ./scripts/backup-db.sh

   # Backup current deployment
   cp docker-compose.yml docker-compose.yml.backup
   ```

3. **Deploy**
   ```bash
   # Pull latest images
   docker-compose pull

   # Restart services
   docker-compose up -d

   # Wait for health checks
   ./scripts/wait-for-health.sh
   ```

4. **Verification**
   ```bash
   # Smoke tests
   ./scripts/smoke-tests.sh

   # Check logs
   docker-compose logs -f
   ```

5. **Monitor**
   - Check Grafana dashboards
   - Monitor error rates
   - Check user feedback

### Rollback Procedure

If deployment fails:

```bash
# Stop services
docker-compose down

# Restore backup
cp docker-compose.yml.backup docker-compose.yml

# Restart with old version
docker-compose up -d

# Verify rollback
./scripts/smoke-tests.sh
```
```

### Phase 5: Developer Documentation (2 dny)

#### 5.1 Coding Standards
```markdown
# development/coding-standards.md

## Coding Standards

### Python Standards

Follow PEP 8 with these modifications:

```python
# Good: Descriptive names
def calculate_productivity_score(sessions: List[Session]) -> float:
    """Calculate weighted productivity score from sessions."""
    pass

# Bad: Vague names
def calc(s):
    pass
```

### Type Hints

Use type hints for all functions:

```python
from typing import List, Dict, Optional

def get_sessions(
    start_date: str,
    end_date: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Get sessions within date range."""
    pass
```

### Docstrings

Use Google style docstrings:

```python
def create_session(data: SessionCreate) -> SessionResponse:
    """Create a new Pomodoro session.

    Args:
        data: Session creation data with preset, category, task, etc.

    Returns:
        SessionResponse: Created session with ID and timestamp

    Raises:
        ValidationError: If input validation fails
        DatabaseError: If database operation fails
    """
    pass
```

### Error Handling

Use custom exceptions:

```python
# Define custom exceptions
class SessionValidationError(Exception):
    """Raised when session data is invalid."""
    pass

class SessionNotFoundError(Exception):
    """Raised when session is not found."""
    pass

# Use in code
try:
    session = create_session(data)
except SessionValidationError as e:
    logger.error("validation_failed", error=str(e))
    raise
```

### Logging

Use structured logging:

```python
# Good: Structured logging
logger.info("session_created",
           session_id=session.id,
           preset=session.preset,
           duration=session.duration_minutes)

# Bad: Unstructured logging
logger.info(f"Session {session.id} created with preset {session.preset}")
```
```

#### 5.2 Contributing Guidelines
```markdown
# development/contributing.md

## Contributing Guidelines

### Getting Started

1. Fork repository
2. Create feature branch
3. Make changes
4. Submit pull request

### Pull Request Process

1. **Description**
   - Describe changes
   - Reference issues
   - Add screenshots for UI changes

2. **Tests**
   - Add unit tests
   - Add integration tests
   - Ensure coverage >80%

3. **Code Review**
   - Address feedback
   - Keep PRs focused
   - Squash commits if needed

### Commit Messages

Follow Conventional Commits:

```
feat: add preset recommendation endpoint
fix: resolve database connection leak
docs: update API documentation
test: add integration tests for predictions
refactor: extract service layer from routes
```

### Code Review Checklist

- [ ] Code follows standards
- [ ] Tests added/updated
- [ ] Documentation updated
- [ ] No breaking changes (or documented)
- [ ] Performance considered
- [ ] Security reviewed
```

### Phase 6: Knowledge Base (2 dny)

#### 6.1 FAQ
```markdown
# knowledge-base/faq.md

## Frequently Asked Questions

### General

**Q: What is the 52/17 Deep Work mode?**
A: It's a productivity technique with 52 minutes of focused work followed by 17 minutes of break, optimized for IT professionals.

**Q: How does ML prediction work?**
A: The system uses historical data to predict optimal work times, preset recommendations, and productivity scores.

### Technical

**Q: Why Flask + FastAPI?**
A: Web service uses Flask for WebSocket support (SocketIO), ML service uses FastAPI for async AI calls and better performance.

**Q: How does caching work?**
A: Redis caches ML predictions for 5 minutes to reduce API calls and improve response times.

### Troubleshooting

**Q: Database connection refused?**
A: Check PostgreSQL is running: `docker-compose ps postgres`

**Q: ML service timeouts?**
A: Check Ollama is running: `docker-compose ps ollama`
```

## Konkrétní Úkoly

### Week 1: Foundation
- [ ] Vytvořit OpenAPI spec
- [ ] Napsat API documentation
- [ ] Vytvořit architecture diagrams
- [ ] Napsat deployment guides

### Week 2: Advanced
- [ ] Vytvořit runbooks
- [ ] Napsat developer documentation
- [ ] Vytvořit knowledge base
- [ ] Nastavit doc generation

## Success Criteria

- [ ] OpenAPI spec kompletní
- [ ] Architecture dokumentována
- [ ] Deployment guide funguje
- [ ] Runbooks pokrývají scénáře
- [ ] Developer documentation kompletní

## Reference

### Tools
- **Swagger/OpenAPI**: API documentation
- **Mermaid**: Diagrams
- **Sphinx**: Documentation generation
- **MkDocs**: Static site generator

### Best Practices
- [API Documentation Best Practices](https://treblle.com/blog/api-versioning-in-python-2)
- [Documentation as Code](https://www.writethedocs.org/)
- [Diagrams as Code](https://mermaid.js.org/)

## Notes

- Documentation by měla být vedle kódu
- Verzovaná spolu s kódem
- Automatická generace z OpenAPI
- Regular reviews a aktualizace
