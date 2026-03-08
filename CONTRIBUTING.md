# Contributing to Agentic Thin Waist

## Local Development Environment

### Prerequisites

- Python 3.10+
- Docker & Docker Compose
- Git

### Option A: Docker Compose (full stack)

Start all services locally:

```bash
make build        # Build Docker images
make up           # Start services in the background
make status       # Verify everything is running
make logs         # Tail logs (Ctrl-C to stop)
make down         # Tear everything down
```

Service endpoints once running:

| Service | URL |
|---|---|
| Experiment API | http://localhost:8000 |
| CTP Service | http://localhost:8001 |
| Substrate Worker | http://localhost:8002 |
| NetGent Service | http://localhost:8003 |
| Telemetry Service | http://localhost:8004 |
| Orchestration | http://localhost:8005 |

### Option B: Python virtualenv (single service)

When you only need to work on one service:

```bash
python -m venv .venv

# Linux / macOS
source .venv/bin/activate

# Windows (PowerShell)
.venv\Scripts\Activate.ps1

# Install root-level deps + the service you're working on
pip install -r requirements.txt
pip install -r services/<service-name>/requirements.txt
```

Replace `<service-name>` with one of: `experiment-api`, `ctp-service`, `substrate-worker`, `netgent-service`, `telemetry-service`, `orchestration`.

---

## Branch → PR → Review → Merge Workflow

We use **feature branches** off `main`. The naming convention is `<username>/<area>/<short-description>`.
You can either use the VS Code / Cursor Git UI or the command line to manage branches and commits.

### 1. Create a branch

```bash
git switch main
git pull origin main
git switch -c yourname/experiment-api/add-validation
```

### 2. Make changes and commit

```bash
git add -A
git commit -m "experiment-api: add input validation for POST /experiments"
```

Write concise commit messages prefixed with the service or area you touched.

### 3. Push and open a PR

```bash
git push -u origin yourname/experiment-api/add-validation
```

Then open a Pull Request on GitHub against `main`. If your work is still in progress, mark the PR as **Draft** — this signals reviewers that the code isn't ready for final review yet. Convert it to "Ready for review" when you're done.

### 4. Address review feedback

```bash
# Make changes locally, then:
git add -A
git commit -m "address review: tighten capacity_mbps bounds check"
git push
```

### 5. Merge

Once approved, merge it via the GitHub UI.

---

## Testing

### Where tests live

Every service has a `tests/` directory:

```
services/
  experiment-api/tests/
  ctp-service/tests/
  substrate-worker/tests/
  netgent-service/tests/
  telemetry-service/tests/
  orchestration/tests/
shared/tests/
tests/              ← repo-wide / integration tests
```

Test files follow the `test_*.py` naming convention so pytest discovers them automatically.

### Running tests

Run tests from the **service directory** you're working on:

```bash
cd services/experiment-api
pytest tests/ -v
```

With coverage:

```bash
pytest tests/ -v --cov=app --cov-report=term-missing
```

To run the shared library tests:

```bash
cd shared
pytest tests/ -v
```

To run all tests across the repo quickly:

```bash
make test-local
```

---

## Linting & Formatting

We use **Black** for code formatting. Run it from the subdirectory you're working in:

```bash
# Format a single service
cd services/experiment-api
black app/ tests/

# Check without modifying files
black --check app/ tests/
```

Or format everything from the repo root:

```bash
black services/ shared/ tests/
```

All Python code should be formatted with Black before opening a PR.

---

## PR Description Template

When opening a pull request, use the following structure for the description:

```markdown
## What changed

<!-- Summarize the changes in a few bullet points. -->

- ...

## Why

<!-- What problem does this solve, or what feature does it enable? -->

- ...

## How to test

<!-- Steps a reviewer can follow to verify the change works. -->

1. `cd services/<service-name>`
2. `pytest tests/ -v`
3. (any additional manual steps)

## Notes

<!-- Optional: anything reviewers should know — open questions, follow-ups, etc. -->
```

If your PR is a work in progress, open it as a **Draft PR** so the team knows it isn't ready for final review.
