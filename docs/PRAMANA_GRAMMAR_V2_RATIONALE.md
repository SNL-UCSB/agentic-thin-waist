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

---

## 7. Refinements (2026-07-07) — ADDITIVE

> The four refinements below were agreed on 2026-07-07 and are recorded here
> additively. They refine, and where noted supersede, the framing in §1, §2, and
> §5 above. Source of truth: `SNL-UCSB/agentic-replication`,
> `arpit/intent-corpus/REFINEMENTS_2026-07-07.md` (sections B and G). Nothing in
> §1 through §6 is deleted; this section states the more general position and
> flags the specific sentences it generalizes.

### 7.1 Topology-first abstraction (generalizes §1)

The abstraction is a **topology**: a graph of links with flows routing across
endpoint pairs and interacting on shared links. A designated subset of those
links are **bottleneck links**, each specified precisely; the connecting
topology is approximated. Single-bottleneck is the **degenerate common case**,
not the definition.

The common case stays a compact one-liner (progressive disclosure): most
experiments name one bottleneck and the intent reads as it does in §1. The
general form is reached only when an experiment needs it, so the waist stays thin
and does not become an ns-3 or Mininet config.

This topology-first framing **subsumes** multipath, dual-bottleneck, parking-lot,
and shared-link cross-traffic. Those are not gaps in the abstraction; they are
demonstrations that it generalizes. Multipath in particular is no longer a
missing production. It is the topology abstraction with more than one designated
bottleneck link. The single-bottleneck restriction was a NetReplica
implementation remnant, not a design boundary. The precise-versus-approximate
split of §1 generalizes accordingly: from "one bottleneck precise, rest
approximate" to "designated bottleneck links precise, connecting topology
approximate."

### 7.2 Grammar over abstract entities, not implementation (generalizes §2)

The grammar expresses **abstract demand**, never an implementation's menu. An
AQM is a discipline plus params plus ecn plus mode; a CCA is an algo plus params
plus flags plus stack. What is realizable today is stated in **capability
files**, and those files are keyed on two axes:

- **Per realization artifact.** The bottleneck-link realization is a swappable
  artifact: `tc`/netem, LibreQoS (CAKE and fq_codel via XDP/eBPF over HTB,
  ISP-scale), BESS (software dataplane), P4/Tofino (hardware), OVS/BMv2
  (software switches). Each artifact publishes the disciplines, CCAs, and
  parameters it can realize.
- **Per execution infrastructure.** Full-control infrastructure (AWS, GCP)
  exposes the whole interface surface; limited-interface infrastructure (RIPE
  Atlas, CAIDA Ark, PINOT) exposes only what its interfaces permit.

The consequence is a clean gap taxonomy. A discipline outside `tc`, a CCA such as
BBRv3 or a QUIC stack not in the shipped 15-CCA list, or a workflow a limited
interface cannot run, are all **GAP-IMPL, not GAP-DESIGN**. An
infrastructure-interface limit is a **capability**, never a design gap. Two
places in the current grammar still leak `tc` into the design and should validate
abstractly, with concrete lists moved to capability files: the `queue.discipline`
enum (today it mirrors tc's qdisc list) and CCA validation against the shipped
kernel's CCAs.

### 7.3 Environment sampling (refines §5, "inhabited" Regime)

Real-path, inhabited measurement (RIPE Atlas, CAIDA Ark, PINOT, GCP or GENI,
real WiFi or cellular) is **design-SAT**, not a design gap. Pramana samples the
available environment via `Workflow @ node` over an **inhabited** Regime,
grounded in the netUnicorn and NetReplica PINOT environment-sampling argument.
The rule is "impose is not express": the inability to *impose* a real path is
exactly what inhabited mode *expresses*. Real-path measurement is therefore
design-SAT, and the per-infrastructure interface surface is a capability, not a
Pramana design gap.

### 7.4 CTP re-expression of time-varying available bandwidth (refines §5, first bullet)

Time-varying available bandwidth is expressed as **`Dynamic.pressure` via
cross-traffic profiles (CTP)**, a more faithful mechanism than trace replay.
Trace-replay experiments (for example Mahimahi FCC and cellular
bandwidth-schedule replay) replayed a recorded trace because they had no
principled way to synthesize time-varying available bandwidth. Pramana expresses
the same experimental intent directly as competing traffic, so the variation
emerges from real contending flows rather than a synthetic rate-limiter.

This must be stated explicitly, not run under the rug: Pramana **re-realizes the
experimental intent** via CTP dynamic pressure, a better mechanism than the
original replay, not an identical byte-for-byte reproduction. This supersedes the
§5 "scheduled envelope" rejection only in framing: the *intent* is re-expressible
via `Dynamic.pressure`; a literal scheduled-capacity envelope remains outside the
model.

---

## Related documents

- **Grammar productions:** `PRAMANA_DESIGN_SPEC.md` §2 (updated inline).
- **Field-level models and capability surface:** `PRAMANA_INTERFACE_DEFINITIONS.md`
  (`Static`, `Workflow`/`Path`, `Queue`, `iterations`, §8.2).
- **Empirical validation:** `SNL-UCSB/agentic-replication`,
  `arpit/intent-corpus/` — `SPEC_FEEDBACK.md` (the per-finding trail) and the
  111-set corpus under `papers/`.
