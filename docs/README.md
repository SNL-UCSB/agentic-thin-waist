# Agentic Thin Waist: Documentation Index

Welcome to the Agentic Thin Waist project documentation. This directory provides comprehensive guides for understanding, implementing, and deploying the system.

## Available Documentation

### QUICKSTART.md
**Start here if you're new to the project.**

A 5-minute guide to get your first experiment running locally:
- Docker Compose setup
- Launching your first experiment
- Querying results
- Common troubleshooting steps

### ARCHITECTURE.md
**Read this to understand the system design.**

Deep dive into the hourglass architecture and three-plane model:
- Three planes: Intent (research questions), Representation (CTP Service), Execution (Substrate)
- Service interactions and data flow
- The four requirements: controllability, composability, fidelity, replicability
- Design decisions and architectural tradeoffs

### API_REFERENCE.md
**Use this as a reference when building clients or debugging.**

Complete API reference for all services:
- All endpoints with request/response examples
- Error codes and recovery procedures
- Rate limits and quotas
- Dataclass contracts for service communication

### DEPLOYMENT.md
**Read this when preparing for production deployment.**

Deployment guides for different environments:
- Local Docker Compose (development)
- SNL servers (production)
- AWS (cloud)
- Azure (cloud)
- Kubernetes (distributed)

---

## Documentation Structure

```
docs/
├── README.md                    # This file
├── QUICKSTART.md               # 5-minute getting started guide
├── ARCHITECTURE.md             # System design, planes, and requirements
├── API_REFERENCE.md            # Complete API documentation
├── DEPLOYMENT.md               # Deployment guides
├── TROUBLESHOOTING.md          # Common issues and solutions
├── CONTRIBUTING.md             # Contributing guidelines
├── images/                      # Diagrams and screenshots
│   ├── architecture-hourglass.png
│   ├── three-planes-model.png
│   ├── service-interaction-flow.png
│   └── deployment-modes.png
└── examples/                    # Example requests/responses
    ├── example-experiment-ctp.json
    ├── example-bottleneck-state.json
    └── example-intent-request.json
```

## Quick Navigation by Role

### For Jaber (D1: Foundation - CRITICAL)
- **QUICKSTART.md** — Get the system running locally
- **ARCHITECTURE.md** — Understand the Intent → Representation → Execution planes
- Service READMEs: Experiment API, CTP Service, Substrate Worker
- **tests/README.md** → D1 bottleneck verification tests

### For Eugene + Jaber (D2: Application Layer - HIGH)
- **ARCHITECTURE.md** → Application plane and NetGent Service
- **API_REFERENCE.md** → Endpoint specifications for browser automation
- Service README: NetGent Service (NFA workflows)
- **tests/README.md** → D2 workflow execution tests

### For Manni (D3: Data Layer - HIGH)
- **ARCHITECTURE.md** → Data layer design
- **API_REFERENCE.md** → Result schema and storage contracts
- Service README: Telemetry Service
- **tests/README.md** → D3 result storage tests

### For Haarika (D5: Intelligence - VERY CRITICAL)
- **ARCHITECTURE.md** → Intelligence plane and orchestration
- **API_REFERENCE.md** → Orchestration Service endpoints
- Service README: Orchestration Service (Claude + OpenClaw integration)
- **tests/README.md** → D5 orchestration tests

### For Sylee (Testing, Architecture Review, CI/CD)
- **tests/README.md** → Complete testing guide
- **ARCHITECTURE.md** → System architecture and four requirements
- CI/CD configuration in `.github/workflows/`
- Testing pyramid: schema validation → unit → service integration → end-to-end

---

## Key Concepts

### The Hourglass Architecture

The Agentic Thin Waist uses an hourglass model to decouple research intent from infrastructure:

```
┌─────────────────────────────────────────┐
│  Diverse Research Intents               │  (Wide)
├─────────────────────────────────────────┤
│ Intent Plane | Representation | Exec    │  (Thin)
├─────────────────────────────────────────┤
│  Diverse Infrastructure                 │  (Wide)
└─────────────────────────────────────────┘
```

### Three Planes

1. **Intent Plane**: Experiment specifications and research questions
2. **Representation Plane**: Cross-Traffic Profile (CTP) Service—core bottleneck regime definition (static attributes + dynamic congestion pressure)
3. **Execution Plane**: Substrate Worker—realizes the bottleneck on diverse infrastructure

### Four Requirements

All services must satisfy these four requirements:

1. **Controllability**: Monotonic attribute changes produce predictable behavior
2. **Composability**: Static and dynamic attributes compose correctly and predictably
3. **Fidelity**: Closed-loop realism is preserved throughout execution
4. **Replicability**: Same specification produces comparable results across runs

### Service Tiers

**D1: Foundation (Network Virtualization)** — CRITICAL (Jaber)
- Experiment API: Orchestration and experiment lifecycle management
- CTP Service: Cross-Traffic Profile representation and bottleneck regime management
- Substrate Worker: Execution and network realization

**D2: Application Layer** — HIGH (Eugene + Jaber)
- NetGent Service: Browser automation and NFA workflow execution

**D3: Data Layer** — HIGH (Manni)
- Telemetry Service: Results, artifacts, and experiment query management

**D5: Intelligence** — VERY CRITICAL (Haarika)
- Orchestration Service: Claude + OpenClaw integration for intelligent orchestration

### Development Timeline

The project follows a **4-week parallel timeline** (NOT sequential):
- Week 1-2: D1 foundation services
- Week 1-3: D2 application layer (parallel to D1)
- Week 2-4: D3 data layer (parallel to D1/D2)
- Week 1-4: D5 intelligence layer (parallel to all)

### Dataclass Contracts

All service-to-service communication uses strongly-typed dataclasses:
- `Experiment`: Complete experiment specification
- `BottleneckState`: Network bottleneck regime (static + dynamic attributes)
- `ExperimentResult`: Results with metadata and contextual tree
- `ContextualTreeNode`: Rich tagging and hierarchical annotation

See `shared/models/README.md` for complete type definitions.

---

## Development Workflow

1. **Review QUICKSTART.md** — Get the system running locally
2. **Study ARCHITECTURE.md** — Understand the three planes and four requirements
3. **Identify your service** — Reference the role-based navigation above
4. **Read ARCHITECTURE.md** for your tier details
5. **Review API_REFERENCE.md** — Understand dataclass contracts and endpoints
6. **Read the service README** — Implementation-specific guidance
7. **Write tests** — Follow the testing pyramid in **tests/README.md**
8. **Run tests locally** — `pytest tests/` or `make test`
9. **Submit PR** — Include tests, documentation updates, and verify four requirements

---

## Team and Contacts

**PI**: Prof. Arpit Gupta
**Team**:
- Jaber (D1 Foundation — CRITICAL)
- Eugene + Jaber (D2 Application — HIGH)
- Manni (D3 Data — HIGH)
- Haarika (D5 Intelligence — VERY CRITICAL)
- Sylee (Architecture Review, CI/CD, Testing Infrastructure)

---

**Last Updated**: 2026-03-04
**Status**: Documentation framework established
**Next Milestone**: Complete QUICKSTART, ARCHITECTURE, and API_REFERENCE guides
