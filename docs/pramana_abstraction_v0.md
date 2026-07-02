# The Pramana Programming Abstraction — v0

> **⚠️ HISTORICAL DOCUMENT — SUPERSEDED.** The current, authoritative
> specification is **`PRAMANA_DESIGN_SPEC.md`**. Decisions recorded here were
> revised during later reviews — in particular, all "rendezvous channel",
> broker, S3-importer, and mesh/tunnel transport designs were **rejected**:
> the shipped model is the current implementation (workers made reachable via
> operator-scoped security groups; the Core only dials out; results pulled by
> the Core). Read this file as design history and evidence, not as the spec.



**UCSB SNL · 2026-07-02 · The §4.1 of Pramana.** Companion to
`pramana_spec_v0.md` (architecture), `pramana_interfaces_v0.md` (contracts),
`pramana_vs_netunicorn.md` (lineage). Grounded in: netUnicorn CCS '23 §4.1,
NetForge arXiv:2507.13476 (v1–v3), the SIGCSE Pramana design section, and the
implemented code of NetGent (fork + workflow registry), netforge (`controler.py`,
`setup.sh`), and the CTP Service in this repo.

---

## 0.0 The philosophy and the grammar (added same day, on convergence)

**Design philosophy, one sentence:** spend intelligence **above the waist, never
below it** — every concern of an experiment (behavior, conditions, placement) is
progressively disaggregated into a compiled, parameterized, replayable artifact, so
that everything below the waist is composition and replay, not authorship. Model use
above the waist splits into *offline authoring* (workflow generation, capability
drafting — always human-gated) and exactly one *per-request* site, `compile()`.

**The abstraction, as a grammar** (revised after adversarial review, see
`pramana_adversarial_review_2026-07-02.md`):

```
Evidence      = collect(ExperimentSet)                      ── SIGCSE: "a single function from
ExperimentSet = fix(λA. compile(Intent, A))                     experiment description to a
              | user-written Spec (same validation gate)        labeled measurement set"
                where A grows by Clarification (backflow)   ── compile is an iterative
                                                                fixpoint, not a pure call
ExperimentSet = ⟨ nodes, mapping, secrets, leaves ⟩         ── the waist artifact; leaves
                                                                are flat/fully expanded
sweep         : Experiment × dim → ExperimentSet            ── expansion happens above the
                                                                waist (CTP.select(n) is a
                                                                sweep generator)
Experiment    = ⟨ Workflow(params) ⊗ Regime ⟩ @ Roles       ── leaf; plus telemetry, verify,
                × iterations                                    iterations as annotations
identity(e)   = H(workflow@sha, params, static, dynamic)    ── nodes/mapping/iterations/
                                                                attempts are OUTSIDE identity
                                                                (⇒ cross-tier dedupe works)
Roles         = ⟨ client: Node, server: Node? ⟩             ── the two-endpoint requirement,
                                                                first-class
Workflow      = CLI(app, role) ▸ NFA⟨states, {{params}}⟩    ── NetGent
Regime        = Static⟨capacity↓↑, latency, queue⟩ ⊗ Dynamic⟨pressure⟩   ── NetReplica
pressure      = replay(ctp)                                 ── open-loop (trace-mined)
              | load(Workflow* ↦ Node*)                     ── closed-loop (real apps as
              | replay(ctp) ⊕ load(…)                           cross-traffic; both allowed)
select        : criteria → ℘(corpus)                        ── a query, not an algebra op
ctp           ∈ closure(corpus; transform, merge)           ── closed: transform/merge yield
                                                                corpus CTPs (verified in
                                                                ctp-service merge.py — our
                                                                claim, not NetForge's)
Nodes         = Pool.{active|latent}.filter(attrs).take(n)  ── netUnicorn++, with pool
Node          ∈ Nodes;  persistence ∈ {set, experiment,         provenance and persistence
                fresh-per-experiment}
mapping       : nodes → connectors                          ── the only thing that changes
                                                                across T1/T2/T3
collect       = deploy ; prepare ; verify ; run ; publish   ── sequenced; deterministic;
                                                                AI-free
⊗             = independent late binding: factors bind at different times and never
                constrain each other's identity
```

Cleanliness properties: (1) every factor **late-bound** (params at dispatch, CTP at
runtime, placement at mapping) — one spec, three tiers; (2) the conditions factor is
**closed under its operations** (transform/merge yield CTPs; sweeps yield sets);
(3) the **per-request AI boundary is a production rule**, not a convention —
`compile()` is the only production that may invoke a model at request time; all
other model use is offline authoring behind human-signed gates.

Lineage in one line: *Pramana = netUnicorn's composition rule, with the pipeline
production automated (NetGent) and a conditions production added (NetReplica/CTP
algebra), so the sole remaining human production is the intent.*

## 0. The unifying theme

Every predecessor system contributes one **separation**, and each separation is
realized the same way — as a *compiled, parameterized, replayable artifact*:

| System | Separates … from … | The artifact | Expensive generation (once) | Cheap replay (always) |
|---|---|---|---|---|
| netUnicorn | **where** workloads run ↔ **what** is executed | Pipeline ↦ Deployment | human writes Python tasks | node executor |
| NetGent | what an application **does** ↔ how it's **scripted** | `workflow.json` (NL spec + NFA states + parameters) | LLM/browser-use trace → distilled states, self-repair | `WorkflowRunner`, zero LLM |
| NetForge / NetReplica | the **bottleneck regime** ↔ the **contexts** that instantiate it | regime spec + CTP (pcap pair + descriptors) | trace mining (prefix tree, windowing) | tc/HTB + tcpreplay |
| CTP Service | demand **structure** ↔ its **origin** | `CrossTrafficProfile` rows | `extract()` | `select/transform/merge → replay` |

**Pramana's abstraction is the composition of these separations behind one
declarative object.** The one-sentence version:

> An **experiment** is a *workflow* (what the application does) bound to a
> *regime* (what the network does) placed on *nodes* (where it happens), and an
> **experiment set** is a tree of such leaves compiled from one *intent*.
>
> **Experiment = Workflow ⊗ Regime ⊗ Node** — with every factor late-bound:
> workflow parameters at dispatch, dynamic pressure at runtime, placement at
> mapping.

The generate-expensive/replay-cheap pattern is what makes minimum-viable
intelligence (spec R5) possible: all the intelligence is spent **once, offline**,
producing artifacts; run time is registry dispatch and replay. The LLM's runtime
job collapses to filling a typed form whose fields are published by the artifacts
themselves.

## 1. The nouns

### 1.1 Workflow — the behavior axis (from NetGent)

A workflow is a secret-free JSON artifact: `{specification, states, parameters}` —
the retained natural-language rules, the compiled NFA (each state =
`checks → actions → end_state` over registered primitives: `go_to_url`,
`click_element`, `input_text`, … / `ping`, `iperf`, `wget`, …), and declared free
variables injected late as `{{param}}` with type coercion.

- **Roles.** An application offers a client workflow always, a server workflow
  only where meaningful (Zoom/Puffer/NDT yes; YouTube no). Peer-to-peer reduces
  to "the listener is the server."
- **The CLI contract (spec R6).** Each (application, role) is *used* through a
  concrete CLI — `youtube-client -v <url> -d 30s`, `zoom-server -m <code>` —
  owned and evolved independently per application. The **capability-document
  synthesizer** reads across all CLIs and emits the capability files the
  knowledge base ingests. The rest of Pramana never learns that a workflow is an
  NFA; it sees flags, types, defaults, prerequisites.
- **Generation is an authoring tool, not a runtime dependency**: browser-use
  trace → selector synthesis → re-parameterization → repair loop, cached in the
  workflow registry (`index.json` is a package registry with raw-URL links).

*What this replaces in netUnicorn:* hand-written Task classes and hand-composed
pipelines — the unsustainable part.

### 1.2 Regime — the conditions axis (from NetForge; absent in netUnicorn)

A regime is "a declarative description of the congestion behavior the bottleneck
should impose on the target application, independent of any particular testbed,
cloud platform, deployment, or trace" (NetForge §3.2). It has exactly two parts:

- **Static envelope** — per-direction capacity (HTB rate/ceil), base latency
  (netem, deliberately decoupled from the shaped queues), queueing (qdisc string
  carries AQM *and* buffer: `bfifo limit 100kb`, `codel`, `cake`, …).
- **Dynamic pressure** — one CTP: a paired `{incoming, outgoing}` pcap segment
  plus its statistical index (intensity, burstiness, temporal correlation,
  structure), drawn from the corpus by `select()` over descriptor ranges, adapted
  by `transform()` (profile *filtering* preserves semantics; *trimming* expands
  the usable corpus), composed by `merge()`.
- **Dynamic pressure has two production alternatives, and Pramana refuses the
  open-vs-closed-loop battleground by supporting both (Arpit, 07-02):**
  *open-loop* = `replay(ctp)` — trace-mined pressure, non-reactive, the NetReplica
  contribution; *closed-loop* = `load(workflows ↦ nodes)` — real applications run
  as cross-traffic on additional nodes sharing the bottleneck. The elegant part:
  closed-loop pressure requires **no new abstraction** — it is just more workflows
  mapped to more nodes, drawn from the same pools (a Mininet-synthesized topology
  or PINOT RPis both qualify as those nodes). Hybrid replay remains the open-loop
  fidelity rule: pressure fixed, application-under-test fully reactive.
- **Regimes have two realization modes.** **Imposed**: the bottleneck is emulated
  (tc/HTB on veths) and the static envelope is *set* — the T1/laptop default.
  **Inhabited**: the bottleneck is a *real* link reached through a connector — a
  PINOT RPi on the campus wireless network, a Starlink terminal, a cellular
  modem — where the envelope is a property of the environment and pressure can
  still be injected via `load(...)` on co-located nodes. Wireless/cellular/LEO are
  therefore **not out of scope; they are inhabited regimes on the right
  infrastructure** — a connector question, not an abstraction limit. The
  verification probe changes *semantics*, not machinery, across modes: in imposed
  mode it **verifies** (realized vs. requested); in inhabited mode it
  **characterizes** (measure the regime you got and label the data with it —
  ground truth either way).
- CCA is **declared in the static context** (it is part of experiment identity and
  the substrate applies it at the endpoint), but it is *not* a property of the
  bottleneck itself — it configures the endpoint's transport stack. [A2]

### 1.3 Pool and Node — the placement axis (from netUnicorn, made explicit)

- A **Pool** is where nodes come from. Pools are **active** (already running —
  the laptop's bootstrap containers, a lab server's standing workers) or
  **latent** (materializable on demand by a **connector** — `deploy()` on
  local_docker/aws/ssh). Pool initiation is a *mechanism below the abstraction*,
  never Core logic.
- A **Node** is one execution endpoint drawn from a pool (`filter(attrs).take(n)`
  over node attributes: browser, audio, public reachability, host-kernel CCAs,
  disk for prefetch), carrying a **pipeline** (ordered workflows) and a
  **persistence level** (`iteration | experiment | experiment_set`).
- **Two endpoint configurations** for a regime's bottleneck: the **in-container
  pair** (netforge's `ns1 —veth— bridge —veth— ns2` inside one privileged
  container: both endpoints *and* the bottleneck in one Docker — the T1 default
  and the laptop story), or the **split pair** (client-side bottleneck node +
  named external service node, local or remote).

### 1.4 Experiment and ExperimentSet — the composition

- **Experiment (leaf):** one unique `Workflow ⊗ Regime ⊗ Node` binding. Same
  triple ⇒ same experiment (content-hashed). `iterations` re-runs it without
  teardown.
- **Mapping is explicit and first-class** (netUnicorn's `map()` — the thing the
  current Pramana implementation does implicitly and must stop doing implicitly):
  pipelines → nodes, regime → the bottleneck placement, all recorded as
  deployment records with per-node lifecycle.
- **ExperimentSet:** the tree an intent compiles into — internal nodes are
  sweeps, leaves are experiments. It is the **waist artifact**: fully concrete,
  AI-free below this line, portable across tiers by changing only the mapping.
- **Evidence** closes the function the SIGCSE paper names as the whole mental
  model — *"a single function from an experiment description to a labeled
  measurement set"*: every result carries its full regime + workflow context as
  ground-truth labels, plus realized-condition verification.

## 2. The composition, as code

netUnicorn Listing 1 (bruteforce study) took ~32 lines, three hand-authored
pipelines, and in-band readiness flags. The same *shape* in Pramana:

```python
# Pramana — Zoom under a 10 Mbps bottleneck with realistic cross-traffic
pool   = Pool.active("laptop")                      # or Pool.latent("aws", max=50)
room   = Node.service(Workflow("zoom", role="server"),      # zoom-server -m <code>
                      persist="experiment_set").place(pool) # or .place("ssh:snl-5")

regime = Regime(static  = dict(down="10mbps", up="10mbps",
                               latency="10ms", queue="codel"),
                dynamic = CTP.select(intensity_mbps=(4, 8),
                                     burstiness_pmr=(2, None), n=100))

exp = Experiment(workflow = Workflow("zoom", role="client",  # zoom-client ...
                                     server=room, duration="30s"),
                 regime   = regime,
                 iterations = 1)

es = ExperimentSet.sweep(exp, latency=["10ms", "100ms"])     # sweep dims: latency (2) x
                                                              # ctp (CTP.select = sweep
                                                              # generator, 100) -> 200 leaves
es.map(pool).deploy().collect()                              # compose → verify → evidence
```

Line-for-line against netUnicorn's Listing 1:

| netUnicorn Listing 1 | Pramana | Why it got shorter |
|---|---|---|
| `Pipeline().then(start_http_server).then(start_pcap).then(set_readiness_flag)` | `Node.service(Workflow("zoom", role="server"))` | server workflow is a published artifact behind a CLI; capture is a telemetry default, not a task |
| hand-written `patator_attack`, `benign_traffic` tasks | `Workflow("zoom", role="client")` | NetGent authored it once; replay is deterministic |
| *(no equivalent — conditions impossible)* | `Regime(static…, dynamic=CTP.select(…))` | the axis netUnicorn never had |
| `wait_for_readiness_flag` in every follower pipeline | service-node startup precedence | ordering is a property of node kinds, not in-band tasks |
| `Nodes.filter('location','aws').take(40)` | `Pool.latent("aws", max=50)` + attribute filter at mapping | pools active/latent; materialization is the connector's job |
| `Experiment().map(p1,h1).map(p2,h2)…; deploy(); execute()` | `es.map(pool).deploy().collect()` | same verbs — this part netUnicorn got right and Pramana keeps |
| *(nothing above this API)* | intent → this object, via LLM form-filling | the NL layer emits the same abstraction users can write by hand |

And the intent path produces exactly the object above: *"compare Zoom at 10ms and
100ms under moderately bursty campus cross-traffic"* → parser fills the form →
match resolves `meeting_code` by asking (backflow) → the same `ExperimentSet`.
One abstraction, two front doors (R5: the LLM door must stay simple enough for a
self-hosted model; R8: both doors open from a terminal).

## 3. What the abstraction demands of the implementation

The current codebase realizes the *factors* but not the *composition*:

1. **No `Pool`/`Node` types exist anywhere** — placement is implicit in
   `ConnectivityManager.create_worker()` per spec. The mapping must become an
   explicit, inspectable object (deployment records).
2. **The regime is scattered** — static knobs live in the intent-service prompt files,
   CTP handling in two services and a hack flag. `Regime` should be one typed
   object in `shared/models`, compiled to substrate calls.
3. **The CLI contract (R6) doesn't exist yet** — workflows are invoked by id +
   params dict. Per-(application, role) CLIs + the capability-document
   synthesizer are the bridge from NetGent's registry to the knowledge base.
4. **`ExperimentSet` must be the only thing the intent layer produces** and the
   only thing the scheduler consumes — the enforcement point for "AI-free below
   the waist."

## 4. The intellectual trajectory: Mininet → Pramana (added 07-02)

Mininet is the intellectual origin, and the arc is cleanest stated as: **each system
in the line turns one remaining hand-crafted element of a Mininet experiment into a
declarative, replayable object — while preserving Mininet's founding bet that
fidelity comes from real kernel stacks and real applications, not models.**

| System | What became a first-class object | What stayed hand-crafted | The Mininet inheritance |
|---|---|---|---|
| **Mininet** (HotNets '10) / **Mininet-HiFi** (CoNEXT '12) | the **topology**: `Topo(hosts, switches, links)` on one laptop, real stacks via namespaces + veth + tc; HiFi adds resource isolation and **fidelity monitoring** | everything *running on* the topology (workloads scripted per experiment); conditions purely synthetic (static tc params, no realistic contention); no portability off the laptop; no result management | — (the foundation) |
| **netUnicorn** (CCS '23) | the **experiment**: pipeline ↦ nodes, portable across infrastructures | tasks and pipelines (hand-written Python); conditions (absent entirely); fidelity relaxed to "best-effort" | executors on namespaces/containers |
| **NetReplica/NetForge** ('25–'26) | the **conditions**: regime = static envelope ⊗ trace-mined CTP, hybrid replay | application behavior; orchestration at scale | its single-container realization (`ns1 —veth— bridge —veth— ns2` + tc/HTB) *is* a Mininet-HiFi topology, specialized to the one link that matters |
| **NetGent** ('25) | the **application behavior**: NL → NFA workflow artifact, deterministic replay | intent, conditions, placement | real applications on real stacks |
| **Pramana** | the **intent**: `compile()` → ExperimentSet — the composition of all four | only the question itself | all of the above, composed |

Two threads make this arc *defensible* rather than merely narratable:

- **The fidelity thread.** Mininet-HiFi made emulation fidelity a *monitored
  property* of every run; netUnicorn consciously relaxed it to best-effort in
  exchange for scale; Pramana's Spec→Substrate verification probe **restores
  fidelity as a measured, per-run property** — with realized-vs-requested ground
  truth shipped inside every result. "We return to Mininet-HiFi's standard, at
  netUnicorn's scale" is a sentence a SIGCOMM reviewer can check, not challenge.
- **The specialization thread.** Mininet's generality (arbitrary topologies) is
  deliberately traded for bottleneck-centrism — defensible because it is a *stated
  scoping thesis* (single-bottleneck scoping, `thin_waist_one_pager.md`) with an
  escape hatch (regime chaining for multi-hop), not an unexamined limitation.

**Named blind spots (state them before reviewers do):**

1. **Topology generality** — traded away; multi-bottleneck composition is claimed
   (NetForge v2 "chain bottlenecks") but unevaluated.
2. **Wireless/cellular/LEO — reframed (07-02), not discarded.** These are
   *inhabited regimes* reached through connectors (§1.2): PINOT RPis on campus
   wireless, Starlink terminals, cellular modems — with pressure injectable via
   closed-loop `load(...)` on co-located nodes. What honestly remains open: no
   inhabited-mode deployment has been *evaluated* yet, and the probe there
   characterizes rather than verifies. Claim the design generality, not the
   result.
3. **Two fidelity modes, now explicit rather than conflated** — *imposed* regimes
   (emulated, envelope set, probe verifies) vs. *inhabited* regimes (real links,
   envelope measured, probe characterizes); open-loop `replay(ctp)` vs.
   closed-loop `load(workflows)` pressure. Pramana supports all four quadrants by
   construction; every published claim must name its quadrant.
4. **Verification covers one of four layers** — Spec→Substrate only; Intent→Spec,
   Substrate→Result, Result→Claim remain open problems (`verification_gap.md`)
   and must be flagged as such, never implied solved.
5. **The loop is not yet an object** — evidence → next intent (the agentic
   iteration the vision papers promise) has no production in the grammar. It is
   the *sixth object*, explicitly future work.

## 5. Fidelity notes carried over from the sources

- Latency is applied off the shaped queue (netforge: netem on the egress leg) so
  queueing delay and propagation delay never conflate.
- CTP replay enters at the *endpoints* and traverses the same bottleneck as the
  reactive workload — pressure and application share the queue, which is the
  entire point.
- Parallel regime instances scale to ~8 concurrent tasks before kernel scheduling
  in netem becomes the limiting factor (NetReplica v2 §5.5/A4; JSD across tasks
  < 0.14 up to eight) — a planner packing constraint, i.e., a node attribute.
