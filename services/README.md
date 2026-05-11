# Services

Six microservices organized into three logical planes. See each service's own `README.md` for the full HTTP surface.

## Registry

| Service | Port | Plane | Path |
|---|---|---|---|
| Experiment API | 8000 | Intent | [`experiment-api/`](experiment-api/) |
| CTP Service | 8001 | Representation | [`ctp-service/`](ctp-service/) |
| Substrate Worker | 8002 | Execution | [`substrate-worker/`](substrate-worker/) |
| NetGent Service | 8003 | Execution (application) | [`netgent-service/`](netgent-service/) |
| Telemetry Service | 8004 | Representation (storage) | [`telemetry-service/`](telemetry-service/) |
| Orchestration | 8005 | Intent (agentic) | [`orchestration/`](orchestration/) |

Auxiliary containers:
- `browserless-substrate-worker/` — headless browser pool; shares the substrate-worker network/PID namespaces.
- `netgent-worker` (built from `netgent-service/`) — Procrastinate job worker for NetGent.

## Three planes

| Plane | Services | Responsibility |
|---|---|---|
| **Intent** | Experiment API, Orchestration | Accept research intent; generate experiment specs; coordinate execution. |
| **Representation** | CTP Service, Telemetry Service | Define Cross-Traffic Profiles; persist results with contextual metadata. |
| **Execution** | Substrate Worker, NetGent | Apply traffic shaping, replay cross-traffic, capture PCAPs, run application workflows. |

## Design principles

- **Dumb services, smart controller.** Each downstream service is narrow and stateless: it receives one configuration, executes it, returns a result. Sequencing, retry, and progress tracking live in the controller (Experiment API / Orchestration).
- **No direct coupling between NetGent and Telemetry.** NetGent produces artifacts; Telemetry stores them. The controller wires them together.
- **Static + dynamic bottleneck regime.** Substrate Worker owns *all* kernel-level network operations (tc, netem, tshark, tcpreplay). CTP Service owns profile data and operations but never touches the kernel.

## Typical interaction flow (one iteration)

```
Orchestration (NL intent)
    │
    ▼
Experiment API
    │
    ├─ pre-flight: CTP ready? worker available? workflow generated?
    │
    ├─ CTP Service        ── select/transform → replay-ready PCAP
    ├─ Substrate Worker   ── shape (tc/netem) + start capture (tshark) + replay (tcpreplay)
    ├─ NetGent Service    ── execute browser/shell workflow
    ├─ Substrate Worker   ── stop capture, drain metrics
    └─ Telemetry Service  ── persist result + artifacts (PCAP, JSON)
```

## Core requirements

The architecture targets four properties:

1. **Controllability** — CTP algebra defines conditions; Substrate Worker enforces them via tc and tcpreplay.
2. **Composability** — services are independently deployable; the controller composes them.
3. **Fidelity** — verification ensures applied conditions match specifications within tolerance.
4. **Replicability** — contextual trees capture full provenance; PCAPs enable offline replay.

## Deployment

Local Docker Compose is the default. All services share a host clock and filesystem (with bind mounts for capture/CTP dirs). The control plane (Experiment API, Orchestration) can stay local while substrate workers run on remote hosts (see `docker-compose.aws.yml`).
