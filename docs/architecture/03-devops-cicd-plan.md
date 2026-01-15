# DevOps CI/CD Pipeline Plan

**Tým:** DevOps Team
**Trvání:** 2 týdny
**Priority:** KRITICKÁ

## Shrnutí

Zavést komplexní CI/CD pipeline s GitHub Actions, automated testing, security scanning a automated deployment.

## Současný Stav

### Co Máme
- Docker Compose pro local development
- Monitoring stack (Prometheus, Grafana, Loki)
- Manual deployment

### Co Chybí
- ❌ GitHub Actions workflow
- ❌ Automated testing v pipeline
- ❌ Security scanning
- ❌ Automated deployment
- ❌ Environment separation
- ❌ Pre-commit hooks

## Cílová Struktura

```
.github/
└── workflows/
    ├── pull-request.yml        # PR checks
    ├── main.yml                 # Main branch pipeline
    ├── release.yml              # Release pipeline
    ├── security-scan.yml        # Security scanning
    └── performance.yml          # Performance benchmarks

.hooks/
├── pre-commit                  # Pre-commit hooks
├── commit-msg                  # Commit message hooks
└── pre-push                    # Pre-push hooks

scripts/
├── build.sh                    # Build scripts
├── deploy.sh                   # Deploy scripts
├── test.sh                     # Test scripts
└── security-scan.sh            # Security scan scripts

environments/
├── development/
│   ├── docker-compose.yml
│   └── .env.example
├── staging/
│   ├── docker-compose.yml
│   └── kubernetes/             # Future
└── production/
    ├── docker-compose.yml
    └── kubernetes/             # Future
```

## Implementační Plán

### Phase 1: Pre-commit Hooks (2 dny)

#### 1.1 Nainstalovat pre-commit
```bash
pip install pre-commit
```

#### 1.2 Vytvořit .pre-commit-config.yaml
```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/psf/black
    rev: 24.1.1
    hooks:
      - id: black
        language_version: python3.11

  - repo: https://github.com/pycqa/isort
    rev: 5.13.2
    hooks:
      - id: isort
        args: ["--profile", "black"]

  - repo: https://github.com/pycqa/flake8
    rev: 7.0.0
    hooks:
      - id: flake8
        args: ["--max-line-length=88", "--extend-ignore=E203"]

  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.8.0
    hooks:
      - id: mypy
        additional_dependencies:
          - types-requests
          - types-flask

  - repo: local
    hooks:
      - id: pytest
        name: Run pytest
        entry: pytest tests/ -v
        language: system
        pass_filenames: false
        always_run: true
```

#### 1.3 Aktivovat
```bash
pre-commit install
pre-commit install --hook-type commit-msg
```

### Phase 2: GitHub Actions - PR Workflow (3 dny)

```yaml
# .github/workflows/pull-request.yml
name: Pull Request Checks

on:
  pull_request:
    branches: [main, develop]

jobs:
  code-quality:
    name: Code Quality
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          pip install black isort flake8 mypy

      - name: Check formatting (black)
        run: black --check web/ ml-service/

      - name: Check imports (isort)
        run: isort --check-only web/ ml-service/

      - name: Lint (flake8)
        run: flake8 web/ ml-service/

      - name: Type check (mypy)
        run: mypy web/ ml-service/

  unit-tests:
    name: Unit Tests
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          pip install -r web/requirements.txt
          pip install -r ml-service/requirements.txt
          pip install -r requirements-test.txt

      - name: Run tests with coverage
        run: |
          pytest tests/ \
            --cov=web \
            --cov=ml-service \
            --cov-report=xml \
            --cov-report=term-missing \
            --cov-fail-under=80

      - name: Upload coverage to Codecov
        uses: codecov/codecov-action@v4
        with:
          file: ./coverage.xml
          fail_ci_if_error: true

  security-scan:
    name: Security Scan
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Run Bandit
        run: |
          pip install bandit[toml]
          bandit -r web/ ml-service/

      - name: Run Semgrep
        uses: returntocorp/semgrep-action@v1
        with:
          config: auto

  build:
    name: Build Images
    runs-on: ubuntu-latest
    needs: [code-quality, unit-tests, security-scan]
    steps:
      - uses: actions/checkout@v4

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Build web image
        uses: docker/build-push-action@v5
        with:
          context: ./web
          cache-from: type=gha
          cache-to: type=gha,mode=max

      - name: Build ML service image
        uses: docker/build-push-action@v5
        with:
          context: ./ml-service
          cache-from: type=gha
          cache-to: type=gha,mode=max
```

### Phase 3: GitHub Actions - Main Branch (3 dny)

```yaml
# .github/workflows/main.yml
name: Main Branch Pipeline

on:
  push:
    branches: [main]

jobs:
  test:
    name: Test
    uses: ./.github/workflows/pull-request.yml

  security-scan:
    name: Security Scan
    uses: ./.github/workflows/security-scan.yml

  build-and-push:
    name: Build and Push
    needs: [test, security-scan]
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Login to Docker Hub
        uses: docker/login-action@v3
        with:
          username: ${{ secrets.DOCKER_USERNAME }}
          password: ${{ secrets.DOCKER_PASSWORD }}

      - name: Build and push web
        uses: docker/build-push-action@v5
        with:
          context: ./web
          push: true
          tags: |
            pomodoro/web:${{ github.sha }}
            pomodoro/web:latest
          cache-from: type=gha
          cache-to: type=gha,mode=max

      - name: Build and push ML service
        uses: docker/build-push-action@v5
        with:
          context: ./ml-service
          push: true
          tags: |
            pomodoro/ml-service:${{ github.sha }}
            pomodoro/ml-service:latest
          cache-from: type=gha
          cache-to: type=gha,mode=max

  deploy-staging:
    name: Deploy to Staging
    needs: [build-and-push]
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Deploy to staging
        run: |
          ssh user@staging-server 'cd /opt/pomodoro && docker-compose pull && docker-compose up -d'

      - name: Smoke tests
        run: |
          curl -f http://staging.pomodoro.local/health || exit 1
          curl -f http://staging.pomodoro.local/api/health || exit 1
```

### Phase 4: Release Pipeline (2 dny)

```yaml
# .github/workflows/release.yml
name: Release Pipeline

on:
  push:
    tags:
      - 'v*'

jobs:
  create-release:
    name: Create Release
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Generate changelog
        id: changelog
        run: |
          echo "## Changelog" > CHANGELOG.md
          git log --pretty=format:"- %s" $(git describe --tags --abbrev=0 HEAD^)..HEAD >> CHANGELOG

      - name: Create GitHub Release
        uses: softprops/action-gh-release@v1
        with:
          body_path: CHANGELOG.md
          files: |
            docker-compose.yml
            loki-config.yaml
            promtail-config.yaml
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}

  deploy-production:
    name: Deploy to Production
    needs: [create-release]
    runs-on: ubuntu-latest
    environment: production
    steps:
      - uses: actions/checkout@v4

      - name: Deploy to production
        run: |
          ssh user@prod-server 'cd /opt/pomodoro && ./scripts/deploy.sh ${{ github.ref_name }}'

      - name: Health check
        run: |
          for i in {1..30}; do
            curl -f http://prod.pomodoro.local/health && break
            sleep 10
          done

      - name: Rollback on failure
        if: failure()
        run: |
          ssh user@prod-server 'cd /opt/pomodoro && ./scripts/rollback.sh'
```

### Phase 5: Security Scanning (2 dny)

```yaml
# .github/workflows/security-scan.yml
name: Security Scanning

on:
  schedule:
    - cron: '0 0 * * *'  # Daily
  workflow_dispatch:

jobs:
  sast:
    name: SAST
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Run Bandit
        run: |
          pip install bandit[toml]
          bandit -r web/ ml-service/ -f json -o bandit-report.json

      - name: Upload Bandit results
        uses: github/codeql-action/upload-sarif@v3
        with:
          sarif_file: bandit-report.json

  dependency-scan:
    name: Dependency Scan
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Run Snyk
        uses: snyk/actions/python@master
        env:
          SNYK_TOKEN: ${{ secrets.SNYK_TOKEN }}

  container-scan:
    name: Container Scan
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Build images
        run: |
          docker build -t pomodoro/web:scan ./web
          docker build -t pomodoro/ml-service:scan ./ml-service

      - name: Run Trivy
        uses: aquasecurity/trivy-action@master
        with:
          image-ref: pomodoro/web:scan
          format: 'sarif'
          output: 'trivy-results.sarif'

      - name: Upload Trivy results
        uses: github/codeql-action/upload-sarif@v3
        with:
          sarif_file: trivy-results.sarif
```

### Phase 6: Deployment Scripts (2 dny)

```bash
#!/bin/bash
# scripts/deploy.sh

set -e

VERSION=$1
ENVIRONMENT=${2:-production}

echo "Deploying version $VERSION to $ENVIRONMENT"

# Pull latest images
docker-compose pull

# Stop services
docker-compose stop

# Backup database
./scripts/backup-db.sh

# Start new version
docker-compose up -d

# Wait for health checks
./scripts/wait-for-health.sh

# Run smoke tests
./scripts/smoke-tests.sh

echo "Deployment successful!"
```

## Konkrétní Úkoly

### Week 1: Foundation
- [ ] Nastavit pre-commit hooks
- [ ] Vytvořit PR workflow
- [ ] Vytvořit main branch workflow
- [ ] Nastavit GitHub Secrets

### Week 2: Advanced
- [ ] Vytvořit release workflow
- [ ] Vytvořit security scanning workflow
- [ ] Napsat deployment scripts
- [ ] Nastavit environment separation

## Success Criteria

- [ ] Pre-commit hooks aktivní
- [ ] PR checks passing
- [ ] Automated deployment
- [ ] Security scanning integrováno
- [ ] Rollback capability

## Reference

### Best Practices (2025)
- [From Flask App to CI/CD Pipeline with GitHub Actions](https://dev.to/adeleke123/from-flask-app-to-cicd-pipeline-with-github-actions-docker-hub-aoa)
- [A Complete Guide with Flask, Docker, and GitHub Actions](https://medium.com/@noorfatimaafzalbutt/building-a-production-ready-ci-cd-pipeline-a-complete-guide-with-flask-docker-and-github-actions-c2bcea4bcf5b)

### Tools
- **GitHub Actions**: CI/CD platform
- **pre-commit**: Git hooks framework
- **Docker**: Containerization
- **Codecov**: Coverage reporting
- **Snyk**: Dependency scanning
- **Trivy**: Container scanning

## Notes

- Všechny změny musí projít CI
- Merges do main pouze s green CI
- Deployment pouze z main branch
- Rollback capability je kritický
