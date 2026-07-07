# Pramana Conditions Model and Grammar v2

The conditions abstraction, stated completely. Every construct here expresses a
real, published experiment: the model was validated against 111 experiment sets
from 13 measurement papers (`SNL-UCSB/agentic-replication`,
`arpit/intent-corpus/`). Companion to `PRAMANA_DESIGN_SPEC.md` §2 (grammar) and
`PRAMANA_INTERFACE_DEFINITIONS.md` (field-level models).

---

## 1. Network conditions are two behaviors, encoded differently

An experiment studies traffic crossing a network under controlled conditions.
Those conditions are two distinct behaviors, and the grammar encodes them
differently because they *are* different.

### The bottleneck link — specified precisely, shared

Every experiment has one link whose capacity constrains it: the bottleneck. It
is the object of study. Pramana specifies it exactly and completely:

- **capacity** (downlink, uplink),
- **queue**: discipline, size, AQM parameters, ECN,
- **dynamic cross-traffic pressure** competing for it: trace replay or
  real-application load.

Every workflow contending through the bottleneck experiences the same
bottleneck, so this specification is **common** to all of them, not per-workflow.
Congestion delay and loss at the bottleneck are not parameters: they are
*emergent* from queue and pressure. We set the link and the load; the queueing
that results is the physics we are measuring.

### The rest of the path — approximated, per-workflow

Between each endpoint and the bottleneck lie other links Pramana does not study.
Their aggregate effect is approximated with three parameters:

- **latency, jitter, packet loss** (with reorder and duplication as
  loss-adjacent).

**Capacity is absent here, by design.** Off-bottleneck links do not constrain
the experiment — only the bottleneck's capacity does. Every other location on
the path contributes only to latency, jitter, and loss, never to the effective
capacity, so those are the only parameters worth carrying.

**The path is specified per workflow.** Different flows sharing one bottleneck
take different routes to different destinations. A YouTube session and a Zoom
session driven from the same node traverse different paths, with different
latency, jitter, and loss. The path is therefore a property of the *workflow* —
the application session and its destination — not of the node it runs on and not
of the shared bottleneck. The workflow is the exact unit at which a route is
well-defined: a node hosts many workflows; each workflow has one path.

### General form

A path is a sequence of links, each with its own characteristics; the realized
behavior is their composition. Pramana specifies the two-link specialization —
the bottleneck link exactly, the remainder as one aggregate approximation —
because for the experiments we run, only the bottleneck's behavior needs to be
precise and the rest needs only to be plausible. The model extends to the full
multi-link path with no structural change: each additional link is another
characterized segment on the workflow's path.

---

## 2. Congestion control and AQM are structured objects, not menu items

For a large class of measurement papers the congestion-control algorithm or the
queue discipline *is* the object of study, so the grammar specifies each
structurally rather than as a flat selector.

**Congestion control is per workflow and structured:**
```
cca = ⟨ algo, stack, version, params, flags, build ⟩
```
The same algorithm behaves differently across implementations — a kernel module
versus a QUIC userspace stack (`mvfst`, `xquic`, `quiche`, `chromium`), or one
kernel build versus another (BBR@4.15 versus BBR@5.15). It carries tunable
parameters (`cwnd_gain`, `pacing_gain`), toggled features (HyStart, RFC 8312),
and sometimes a patched build. Because congestion control is per connection, it
attaches to the workflow, alongside its path: two competitors on one bottleneck
can run different algorithms.

**The queue is structured, with typed parameters and ECN:**
```
queue = ⟨ discipline, size, params, ecn, mode ⟩
```
The discipline names the AQM (CoDel, PIE, CAKE, RED, ...); `params` carries its
typed knobs (`target`, `interval`, thresholds); `ecn` and `mode` are first-class
because papers that study AQMs vary them directly. Parameters are typed and
capability-matched, not hidden in an opaque argument string.

---

## 3. Experiments repeat until a condition is met

An experiment runs until a stated condition holds, not for a fixed count:
```
iterations = int | until( event(metric, target), min, max )
```
Stopping when a metric converges — run 10 to 30 trials until the 95% confidence
interval of the median is within a target — is the first instance of a general
**event-triggered action** facility. Events trigger actions *within* a run.
(Choosing the *next* experiment from the last result is the intent-producer's
search, which lives above the waist, not in the grammar.)

---

## 4. The foreground is workflows mapped to nodes

```
Foreground = { Workflow_i @ node_i }
```
The foreground is a set of workflows placed on nodes, each carrying its own path
and congestion control, each with its result attributed to it. More than one
workflow per node is the norm — two competitors sharing a bottleneck are two
workflows on their respective nodes. The abstraction always mapped arbitrary
workflows to arbitrary nodes; the grammar states it directly.

---

## 5. What is deliberately outside the model

- **Cross-traffic is dynamic pressure, not a scheduled envelope.** Time-varying
  conditions that create load are expressed by `Dynamic.pressure` (trace replay
  and real-application load), Pramana's native mechanism for exactly this.
  Reconfiguring the static envelope on a timer to fake pressure is a workaround
  from tools that could not synthesize dynamic pressure; Pramana can, so the
  model does not carry the workaround.
- **Deriving a value by measuring the testbed first is intent extraction, not a
  production.** Measuring a service's native RTT and padding it to a target
  yields a `path.latency` value; the grammar expresses the value, and how it was
  obtained is an extraction concern.
- **Iterative search over experiments and reaching deployed edge infrastructure
  live above the waist and in the connector layer**, respectively.

---

## 6. Implementation map

The field-level target, so the implementation is complete.

| Model element | `PRAMANA_DESIGN_SPEC.md` §2 | `PRAMANA_INTERFACE_DEFINITIONS.md` (`shared/models/spec.py` + §8.2) |
|---|---|---|
| Bottleneck vs path split | Regime, Workflow, `path` | `Static` = ⟨capacity, queue⟩ only (drop latency/jitter/impair); `Workflow` gains a `Path` model {latency, jitter, loss, reorder, dup}; §8.2 publishes path knobs per-workflow |
| Structured CCA (per workflow) | `cca` | `cca` → `Cca` model on the workflow; §8.2 publishes stacks/params/flags |
| Structured AQM | `queue` | `Queue` gains `size, params, ecn, mode` |
| Event-triggered stop | `iterations` | `iterations: int \| StopCriterion` |
| Foreground of workflows | Experiment/Foreground | per-workflow result attribution |

Design capability is the grammar; implementation capability is what the
capability files publish today. The remaining deltas the corpus found are
implementation items the capability files already name (unwritten NetGent
workflows; closed-loop `load` co-scheduling; QUIC userspace stacks), so the
design-reach-versus-implementation-reach coverage is precisely computable.

## Related documents

- **Grammar productions:** `PRAMANA_DESIGN_SPEC.md` §2 (updated inline).
- **Field-level models and capability surface:** `PRAMANA_INTERFACE_DEFINITIONS.md`
  (`Static`, `Workflow`/`Path`, `Queue`, `iterations`, §8.2).
- **Empirical validation:** `SNL-UCSB/agentic-replication`,
  `arpit/intent-corpus/` — `SPEC_FEEDBACK.md` (the per-finding trail) and the
  111-set corpus under `papers/`.
