# Documentation

This directory contains comprehensive documentation for the Agentic Thin Waist project.

## Documentation Files

### QUICKSTART.md
5-minute guide to get a working experiment running locally:
- Docker Compose setup
- Running first experiment
- Querying results
- Common troubleshooting

**Read this first** if you're new to the project.

### ARCHITECTURE.md
Deep dive into system design:
- Full architecture diagrams
- Service interactions
- Data flow through the system
- Design decisions and tradeoffs

**Read this** to understand how everything fits together.

### API_REFERENCE.md
Complete API reference for all services:
- All endpoints with examples
- Request/response formats
- Error codes and recovery
- Rate limits and quotas

**Use this** as a reference when building clients or debugging.

### DEPLOYMENT.md
Deployment guides for different environments:
- Local Docker Compose (development)
- SNL servers (production)
- AWS (cloud)
- Azure (cloud)
- Kubernetes (distributed)

**Read this** when deploying to production.

---

## File Structure

```
docs/
├── README.md                    # This file
├── QUICKSTART.md               # 5-minute getting started guide
├── ARCHITECTURE.md             # System design and philosophy
├── API_REFERENCE.md            # Complete API documentation
├── DEPLOYMENT.md               # Deployment guides
├── TROUBLESHOOTING.md          # Common issues and solutions
├── CONTRIBUTING.md             # Contributing to the project
├── images/                      # Diagrams and screenshots
│   ├── architecture-hourglass.png
│   ├── service-interaction-flow.png
│   └── deployment-modes.png
└── examples/                    # Example requests/responses
    ├── example-experiment-1.json
    ├── example-results-query.json
    └── example-intent-request.json
```

## Quick Navigation

**I want to...**

- **Get started quickly** → Read QUICKSTART.md
- **Understand the system** → Read ARCHITECTURE.md
- **Call a specific endpoint** → Search API_REFERENCE.md
- **Deploy to production** → Read DEPLOYMENT.md
- **Debug an issue** → Read TROUBLESHOOTING.md
- **Contribute code** → Read CONTRIBUTING.md

## Key Concepts

### The Hourglass Model

The Agentic Thin Waist is built on an hourglass architecture:
- **Top** (wide): Diverse research intents
- **Waist** (thin): Core services (D1-D5)
- **Bottom** (wide): Diverse infrastructure

This enables scaling both research questions and computing environments without changing the core.

### Service Tiers

**D1: Foundation (Network Virtualization)**
- Experiment API (orchestration)
- CTP Service (representation)
- Substrate Worker (execution)

**D2: Application Layer**
- NetGent Service (browser automation, NFA workflows)

**D3: Data Layer**
- Storage Service (results, artifacts, queries)

**D4: Distribution** (future)
- Multi-host coordination
- Remote infrastructure support

**D5: Intelligence**
- Orchestration Service (Claude + OpenClaw)

### Dataclass Contracts

All service-to-service communication uses dataclasses:
- `Experiment` — experiment specification
- `ExperimentResult` — results with metadata
- `BottleneckState` — network verification
- `ContextualTreeNode` — rich tagging

See `shared/models/README.md` for complete definitions.

## Development Workflow

1. **Read QUICKSTART.md** — Get system running locally
2. **Read ARCHITECTURE.md** — Understand how services interact
3. **Pick a service to implement** — Start with D1, then D2, D3, D5
4. **Use API_REFERENCE.md** — See exact endpoint specs
5. **Follow the README in each service** — Implementation guide
6. **Run tests** — `pytest tests/` or `make test`
7. **Submit PR** — Include tests and documentation updates

## Testing Documentation

```bash
# Run all tests
make test

# Run tests for a specific service
pytest tests/test_experiment_api.py -v

# Run with coverage
pytest --cov=app tests/

# Run integration tests (slower)
pytest tests/integration/ -v
```

## Continuous Integration

All documentation files are checked:
- Markdown linting
- Link validation
- Code example verification
- Spelling and grammar

Contribute by following the style guide in CONTRIBUTING.md.

---

**Last Updated**: 2026-03-04
**Status**: Initial documentation phase
**Next Milestone**: Complete QUICKSTART, ARCHITECTURE, API_REFERENCE
