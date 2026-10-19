# Local Development Runbook

This guide walks through setting up and running the Agent Regression Flywheel locally for development.

## Prerequisites

### Required Software

- **Node.js**: Version 20.9.0 or higher
  - Check with: `node --version`
  - Install with Homebrew: `brew install node`
  - Or use nvm: `nvm install 20 && nvm use 20`
- **Python**: 3.12 (or system Python if it works)
  - Check with: `python3 --version` or `python --version`
- **Git**: For cloning the repository

### Hardware Requirements

- RAM: 8GB+ recommended (4GB minimum)
- Disk: 2GB+ free space

## Quick Start

### 1. Clone the Repository

```bash
git clone https://github.com/vedantjain09/agent-regression-flywheel.git
cd agent-regression-flywheel
```

### 2. Install Python Dependencies

```bash
cd backend
pip install -r requirements.txt
```

### 3. Install Node.js Dependencies

```bash
cd ../frontend
npm install
```

### 4. Configure Environment Variables

```bash
# In the frontend directory
cp .env.example .env.local
```

Edit `.env.local` to point to your backend servers (default ports work):
```
NEXT_PUBLIC_FASTAPI_BASE=http://127.0.0.1:8002
NEXT_PUBLIC_DJANGO_BASE=http://127.0.0.1:8003
```

**Note**: If you want to run with demo data only (no backend), leave both variables unset or commented out.

### 5. Start Backend Services

Open 2 separate terminal windows:

**Terminal 1 - FastAPI:**
```bash
cd backend
export PYTHONPATH=.
uvicorn app.api.main:app --reload --port 8002
```

**Terminal 2 - Django:**
```bash
cd backend/django_admin
# If using system Python 3.12:
python manage.py runserver 8003
# Or if using virtualenv:
python manage.py runserver 8003
```

### 6. Start Frontend

**Terminal 3 - Next.js:**
```bash
cd frontend
npm run dev
```

### 7. Access the Application

Open your browser to:
- **Dashboard**: http://localhost:3000
- **Mining Funnel**: http://localhost:3000/ (default page)
- **Version Comparison**: http://localhost:3000/compare

## Detailed Setup

### Python Environment Setup

#### Option 1: System Python (macOS)

The project uses Python 3.12+ which comes with macOS. Verify:
```bash
python3 --version  # Should show 3.12.x
```

#### Option 2: Virtual Environment (Recommended)

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Node.js Version Management

#### Using nvm (Recommended)

```bash
# Install nvm if not already installed
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.0/install.sh | bash

# Reload your shell or run:
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"

# Install and use Node 20
nvm install 20
nvm use 20
```

#### Using Homebrew

```bash
brew install node
```

#### Verify Installation

```bash
node --version  # Should show v20.x.x or higher
npm --version
```

## Running Tests

### Backend Tests

```bash
cd backend
PYTHONPATH=. pytest tests/ -v
```

Expected: 53 tests passing, 1 documented skip

### Django Admin Tests

```bash
cd backend/django_admin
python manage.py test tasks -v 2
```

Expected: 5 tests passing

### Frontend Type Check

```bash
cd frontend
npx tsc --noEmit
```

Expected: No errors

### Frontend Lint

```bash
cd frontend
npx eslint .
```

Expected: No errors

### Frontend Build

```bash
cd frontend
npm run build
```

Expected: Production build succeeds

### Full Test Suite

```bash
# Backend
cd backend && pip install -r requirements.txt
PYTHONPATH=backend pytest tests/ -v

# Django
cd backend/django_admin && python manage.py test tasks -v 2

# Frontend
cd frontend && npm install && npx tsc --noEmit && npx eslint . && npm run build
```

## Service Architecture

The application has 3 main services:

| Service | Technology | Port | Purpose |
|---------|------------|------|---------|
| FastAPI | Python | 8002 | Agent-facing API, dashboard data |
| Django | Python | 8003 | Back-office review queue, admin interface |
| Next.js | React/TypeScript | 3000 | Dashboard UI |

## Development Workflow

### Making Changes

1. **Backend changes**:
   - Edit code in `backend/app/`
   - FastAPI auto-reloads on save (watchfiles)
   - Django auto-reloads on save

2. **Frontend changes**:
   - Edit code in `frontend/`
   - Next.js hot-reloads on save (HMR enabled)

3. **Both backends must be running** for full functionality

### Common Development Tasks

#### Add a new API endpoint

1. Edit `backend/app/api/main.py`
2. Add function with appropriate decorators
3. FastAPI auto-reloads the new endpoint

#### Add a new UI component

1. Create component in `frontend/components/`
2. Import and use in `frontend/app/page.tsx`
3. Next.js hot-reloads the changes

#### Add a new task to review queue

1. Django will need database running (Postgres) for full functionality
2. Without Postgres, the app uses demo data from `frontend/lib/demo-data.ts`

## Troubleshooting

### Port Already in Use

If you see `Address already in use`:

```bash
# Find what's using the port
lsof -i :8002  # FastAPI
lsof -i :8003  # Django
lsof -i :3000  # Next.js

# Kill the process
kill -9 <PID>
```

### Node.js Version Too Old

If you see:
```
For Next.js, Node.js version ">=20.9.0" is required
```

Upgrade Node.js:
```bash
nvm install 20
nvm use 20
```

### Python Module Not Found

If Django or FastAPI can't import modules:
```bash
cd backend
pip install -r requirements.txt
```

### Frontend Not Connecting to Backend

1. Check `.env.local` is configured in `frontend/` directory
2. Verify backends are running (check their terminal windows)
3. Check the ports match (8002 for FastAPI, 8003 for Django)
4. Try with demo data by commenting out both env vars in `.env.local`

### Django Migration Required

If Django shows migration errors:
```bash
cd backend/django_admin
python manage.py migrate
```

### Build Errors

If frontend build fails:
```bash
cd frontend
rm -rf .next
npm run build
```

## Environment Variables

### Backend Environment

The backend can be configured via environment variables (optional):

- `DATABASE_URL`: PostgreSQL connection string (defaults to sqlite for dev)
- `REDIS_URL`: Redis connection string (optional, uses in-memory fallback)
- `SNOWFLAKE_ACCOUNT`: Snowflake account for trace warehouse (optional)

### Frontend Environment

In `frontend/.env.local`:

- `NEXT_PUBLIC_FASTAPI_BASE`: URL of FastAPI backend (e.g., `http://127.0.0.1:8002`)
- `NEXT_PUBLIC_DJANGO_BASE`: URL of Django backend (e.g., `http://127.0.0.1:8003`)

**Important**: Both must be set for live data. If unset, the dashboard uses demo fixtures.

## Stopping the Services

When done developing, stop the services by pressing `Ctrl+C` in each terminal window, or close the terminal windows.

## Docker Setup (Alternative)

The project includes Kubernetes manifests in `k8s/` but not Docker Compose. For containerized development, you would need to:

1. Build Docker images for each service
2. Set up Docker Compose orchestration
3. Configure network and volume mounts

This is not currently documented but could be added in the future.

## Production Deployment

See the project README for production deployment guidance.

## Getting Help

If you encounter issues not covered here:

1. Check the main README: `README.md`
2. Check the architecture doc: `ARCHITMERE.md`
3. Check the status doc: `docs/STATUS.md`
4. Review git commit messages for context on changes

## Quick Reference Card

```bash
# Install deps
cd backend && pip install -r requirements.txt
cd ../frontend && npm install

# Configure
cd frontend && cp .env.example .env.local
# Edit .env.local to set backend URLs

# Start services (3 terminals)
# Terminal 1: cd backend && PYTHONPATH=. && uvicorn app.api.main:app --port 8002
# Terminal 2: cd backend/django_admin && python manage.py runserver 8003
# Terminal 3: cd frontend && npm run dev

# Access
open http://localhost:3000

# Run tests
cd backend && PYTHONPATH=. pytest tests/ -v
cd backend/django_admin && python manage.py test tasks -v 2
cd frontend && npx tsc --noEmit && npx eslint . && npm run build
```
