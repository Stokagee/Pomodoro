# Security Implementation Plan

**Tým:** Security Team
**Trvání:** 2 týdny
**Priority:** KRITICKÁ

## Shrnutí

Zavést komplexní bezpečnostní opatření včetně rate limiting, CORS whitelist, API authentication, input validation a security scanning.

## Současný Stav

### Co Máme
- Prometheus metrics
- Structured logging

### Co Chybí (KRITICKÉ PRO PRODUCTION)
- ❌ Rate limiting
- ❌ CORS whitelist (používá `cors_allowed_origins="*"`)
- ❌ API authentication
- ❌ Input validation middleware
- ❌ Output sanitization
- ❌ Security headers
- ❌ Secret management
- ❌ SAST/DAST scanning

## Security Issues

### Kritické
1. **CORS**: `cors_allowed_origins="*"` - úplně otevřené
2. **Rate limiting**: Žádná ochrana proti DoS/brute force
3. **Authentication**: Veřejný API bez auth
4. **Input validation**: Žádná validace vstupů

### Důležité
5. **Secrets**: Environment variables v docker-compose
6. **Security headers**: Chybí Helmet.js equivalent
7. **CSRF**: Chybí CSRF protection
8. **XSS**: Chybí output escaping

## Implementační Plán

### Phase 1: Rate Limiting (3 dny)

#### 1.1 Flask-Limiter Setup
```bash
pip install Flask-Limiter redis
```

#### 1.2 Configuration
```python
# extensions.py
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="redis://redis:6379"
)
```

#### 1.3 Endpoint-Specific Limits
```python
# api/routes/sessions.py
from flask import request
from app.extensions import limiter

# Strict rate limiting for session creation
@bp.route('/log', methods=['POST'])
@limiter.limit("10 per minute")
def log_session():
    pass

# Lenient for public endpoints
@bp.route('/stats/today', methods=['GET'])
@limiter.limit("100 per minute")
def get_today_stats():
    pass
```

#### 1.4 Redis Configuration
```yaml
# docker-compose.yml
redis:
  image: redis:7-alpine
  ports:
    - "6379:6379"
  volumes:
    - redis_data:/data
```

### Phase 2: CORS Configuration (2 dny)

#### 2.1 CORS Whitelist
```python
# app/__init__.py
from flask_cors import CORS

ALLOWED_ORIGINS = [
    'http://localhost:5000',
    'https://pomodoro.local',
    'https://*.pomodoro.app'  # Wildcard subdomains
]

def create_app(config_name='development'):
    app = Flask(__name__)

    # CORS configuration
    cors_config = {
        'origins': ALLOWED_ORIGINS if config_name == 'production' else '*',
        'methods': ['GET', 'POST', 'PUT', 'DELETE'],
        'allow_headers': ['Content-Type', 'Authorization'],
        'supports_credentials': True
    }

    CORS(app, **cors_config)
    return app
```

#### 2.2 Pre-flight Handling
```python
# middleware/cors.py
from flask import request

@app.before_request
def handle_options():
    """Handle CORS pre-flight requests."""
    if request.method == 'OPTIONS':
        response = jsonify({'status': 'ok'})
        response.headers.add('Access-Control-Allow-Origin', request.headers.get('Origin'))
        response.headers.add('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type, Authorization')
        response.headers.add('Access-Control-Max-Age', '86400')
        return response
```

### Phase 3: Authentication & Authorization (4 dny)

#### 3.1 JWT Authentication
```bash
pip install Flask-JWT-Extended
```

#### 3.2 JWT Configuration
```python
# extensions.py
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity

jwt = JWTManager()

def init_jwt(app):
    jwt.init_app(app)
    app.config['JWT_SECRET_KEY'] = os.getenv('JWT_SECRET_KEY')
    app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(hours=1)
    app.config['JWT_REFRESH_TOKEN_EXPIRES'] = timedelta(days=30)
```

#### 3.3 Auth Routes
```python
# api/routes/auth.py
from flask import request, jsonify
from flask_jwt_extended import create_access_token, create_refresh_token

@bp.route('/auth/register', methods=['POST'])
def register():
    """Register new user."""
    data = request.get_json()
    # Validate input
    # Create user
    # Return tokens
    return jsonify({
        'access_token': create_access_token(identity=user_id),
        'refresh_token': create_refresh_token(identity=user_id)
    })

@bp.route('/auth/login', methods=['POST'])
def login():
    """Login user."""
    data = request.get_json()
    # Validate credentials
    # Return tokens
    pass

@bp.route('/auth/refresh', methods=['POST'])
@jwt_required(refresh=True)
def refresh():
    """Refresh access token."""
    identity = get_jwt_identity()
    return jsonify({
        'access_token': create_access_token(identity=identity)
    })
```

#### 3.4 Protected Routes
```python
# api/routes/sessions.py
from flask_jwt_extended import jwt_required, get_jwt_identity

@bp.route('/log', methods=['POST'])
@jwt_required()
def log_session():
    """Create session (protected)."""
    user_id = get_jwt_identity()
    # Process request
    pass
```

#### 3.5 OAuth2 Integration
```bash
pip install authlib
```

```python
# api/routes/oauth.py
from authlib.integrations.flask_client import OAuth

oauth = OAuth(app)

google = oauth.register(
    'google',
    client_id=os.getenv('GOOGLE_CLIENT_ID'),
    client_secret=os.getenv('GOOGLE_CLIENT_SECRET'),
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'}
)

@bp.route('/auth/google')
def login_google():
    """Login with Google."""
    redirect_uri = url_for('auth.google_callback', _external=True)
    return google.authorize_redirect(redirect_uri)

@bp.route('/auth/google/callback')
def google_callback():
    """Google OAuth callback."""
    token = google.authorize_access_token()
    user_info = google.parse_id_token(token)
    # Create/update user
    # Return JWT tokens
    pass
```

### Phase 4: Input Validation (3 dny)

#### 4.1 Pydantic Schemas
```python
# schemas/session.py
from pydantic import BaseModel, Field, validator
from typing import Optional

class SessionCreate(BaseModel):
    preset: str = Field(..., regex='^(deep_work|learning|quick_tasks|flow_mode)$')
    category: str = Field(..., min_length=1, max_length=50)
    task: str = Field(..., min_length=1, max_length=200)
    duration_minutes: int = Field(..., ge=1, le=180)
    productivity_rating: Optional[int] = Field(None, ge=1, le=5)
    notes: Optional[str] = Field(None, max_length=500)

    @validator('task')
    def sanitize_task(cls, v):
        """Sanitize task input."""
        # Remove any HTML tags
        import re
        return re.sub(r'<[^>]+>', '', v)

    @validator('notes')
    def sanitize_notes(cls, v):
        """Sanitize notes input."""
        if v:
            import html
            return html.escape(v)
        return v

class SessionResponse(BaseModel):
    id: int
    preset: str
    category: str
    task: str
    duration_minutes: int
    completed: bool
    created_at: datetime
```

#### 4.2 Validation Middleware
```python
# middleware/validation.py
from functools import wraps
from pydantic import ValidationError

def validate_request(schema_class):
    """Validate request using Pydantic schema."""
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            try:
                data = request.get_json()
                validated_data = schema_class(**data)
                request.validated_data = validated_data.dict()
                return f(*args, **kwargs)
            except ValidationError as e:
                return jsonify({
                    'error': 'Validation Error',
                    'details': e.errors()
                }), 400
        return wrapper
    return decorator

# Usage
@bp.route('/log', methods=['POST'])
@validate_request(SessionCreate)
def log_session():
    data = request.validated_data
    # Process validated data
    pass
```

#### 4.3 SQL Injection Prevention
```python
# repositories/session_repository.py
# Use parameterized queries (already implemented)
# This is a reminder to NEVER use string concatenation

def find_by_id(self, session_id: int):
    """Find session by ID (safe from SQL injection)."""
    with self.get_cursor() as cur:
        cur.execute(
            "SELECT * FROM sessions WHERE id = %s",
            (session_id,)  # Parameterized query
        )
        return cur.fetchone()
```

### Phase 5: Security Headers (2 dny)

#### 5.1 Flask-Talisman
```bash
pip install Flask-Talisman
```

#### 5.2 Security Headers Configuration
```python
# extensions.py
from flask_talisman import Talisman

def init_security_headers(app):
    """Initialize security headers."""
    Talisman(
        app,
        force_https=not app.debug,
        strict_transport_security=True,
        session_cookie_secure=True,
        session_cookie_httponly=True,
        session_cookie_samesite='Lax',
        content_security_policy={
            'default-src': "'self'",
            'script-src': "'self' 'unsafe-inline' cdn.jsdelivr.net",
            'style-src': "'self' 'unsafe-inline' cdn.jsdelivr.net",
            'img-src': "'self' data:",
            'font-src': "'self' cdn.jsdelivr.net",
            'connect-src': "'self' https://api.openai.com"
        }
    )
```

### Phase 6: Secret Management (2 dny)

#### 6.1 Environment Variables
```bash
# .env.example
DATABASE_URL=postgresql://user:pass@host:5432/db
JWT_SECRET_KEY=your-secret-key
AI_API_KEY=your-api-key
```

#### 6.2 Docker Secrets
```yaml
# docker-compose.yml
version: '3.8'

services:
  web:
    secrets:
      - db_password
      - jwt_secret
    environment:
      - DATABASE_PASSWORD_FILE=/run/secrets/db_password
      - JWT_SECRET_FILE=/run/secrets/jwt_secret

secrets:
  db_password:
    file: ./secrets/db_password.txt
  jwt_secret:
    file: ./secrets/jwt_secret.txt
```

#### 6.3 HashiCorp Vault (Future)
```python
# utils/vault.py
import hvac

class VaultClient:
    """HashiCorp Vault client for secret management."""

    def __init__(self):
        self.client = hvac.Client(
            url=os.getenv('VAULT_ADDR'),
            token=os.getenv('VAULT_TOKEN')
        )

    def get_secret(self, path: str) -> dict:
        """Get secret from Vault."""
        response = self.client.secrets.kv.v2.read_secret_version(path=path)
        return response['data']['data']
```

## Konkrétní Úkoly

### Week 1: Foundation
- [ ] Implementovat rate limiting
- [ ] Nastavit CORS whitelist
- [ ] Implementovat JWT authentication
- [ ] Přidat OAuth2 (Google/GitHub)

### Week 2: Advanced
- [ ] Implementovat input validation
- [ ] Přidat security headers
- [ ] Nastavit secret management
- [ ] Integrát security scanning do CI/CD

## Success Criteria

- [ ] Rate limiting aktivní
- [ ] CORS whitelist nastaven
- [ ] JWT authentication funguje
- [ ] Input validation na všech endpointech
- [ ] Security headers nastaveny
- [ ] Secrets nejsou v gitu
- [ ] SAST/DAST integrováno

## Reference

### Best Practices (2025)
- [Python API Security 2025: Rate Limiting, CORS, OWASP](https://www.ox.security/blog/static-application-security-sast-tools/)
- [API Security Best Practices: 11 Ways to Secure Your APIs](https://www.stackhawk.com/blog/api-security-best-practices-ultimate-guide/)
- [OWASP Top 10 2025](https://www.ateamsoftsolutions.com/web-application-security-checklist-2025-complete-owasp-top-10-implementation-guide-for-ctos/)

### Tools
- **Flask-Limiter**: Rate limiting
- **Flask-JWT-Extended**: JWT authentication
- **Authlib**: OAuth2
- **Pydantic**: Input validation
- **Flask-Talisman**: Security headers
- **HashiCorp Vault**: Secret management

## OWASP Top 10 Coverage

| OWASP Category | Implementation | Status |
|----------------|----------------|--------|
| A01:2021 – Broken Access Control | JWT + RBAC | ⏳ Planované |
| A02:2021 – Cryptographic Failures | TLS, secrets | ⏳ Planované |
| A03:2021 – Injection | Parameterized queries | ✅ Hotovo |
| A04:2021 – Insecure Design | Security by design | ⏳ Planované |
| A05:2021 – Security Misconfiguration | Security headers | ⏳ Planované |
| A06:2021 – Vulnerable Components | Dependency scanning | ⏳ Planované |
| A07:2021 – Auth Failures | Rate limiting, JWT | ⏳ Planované |
| A08:2021 – Data Integrity Failures | Signed tokens | ⏳ Planované |
| A09:2021 – Logging | Structured logging | ✅ Hotovo |
| A10:2021 – SSRF | Input validation | ⏳ Planované |

## Notes

- Security by design, ne jako dodatek
- Principle of least privilege
- Defense in depth
- Regular security audits
- Keep dependencies updated
