# The Pramana Programming Abstraction — v0

**UCSB SNL · 2026-07-02 · The §4.1 of Pramana.** Companion to
`pramana_spec_v0.md` (architecture), `pramana_interfaces_v0.md` (contracts),
`pramana_vs_netunicorn.md` (lineage). Grounded in: netUnicorn CCS '23 §4.1,
NetForge arXiv:2507.13476 (v1–v3), the SIGCSE Pramana design section, and the
implemented code of NetGent (fork + workflow registry), netforge (`controler.py`,
`setup.sh`), and the CTP Service in this repo.

---

## 0.0 The philosophy and the grammar (added same day, on convergence)

**Design philosophy, one sentence:** spend intelligence at authoring time, never at
run time — every concern of an experiment (behavior, conditions, placement) is
progressively disaggregated into a compiled, parameterized, replayable artifact, so
that running science is composition and replay, not authorship.

**The abstraction, as a grammar:**

```
Evidence      = collect(ExperimentSet)                      ── SIGCSE: "a single function from
ExperimentSet = compile(Intent)  |  user-written Spec           experiment description to a
                                                                labeled measurement set"
ExperimentSet = ⟨ nodes, mapping, leaves ⟩                  ── the waist artifact
Experiment    = Workflow(params) ⊗ Regime ⊗ Node  × iterations   (leaf; content-hashed)

Workflow      = CLI(app, role) ▸ NFA⟨states, {{params}}⟩    ── NetGent
Regime        = Static⟨capacity↓↑, latency, queue⟩ ⊗ Dynamic⟨ctp⟩   ── NetReplica
ctp           ∈ closure(corpus; select, transform, merge)   ── the CTP algebra (closed)
Node          = Pool.{active|latent}.filter(attrs).take(n) + persistence   ── netUnicorn++
mapping       : pipelines → nodes → connectors              ── netUnicorn's map(), explicit
collect       = deploy ∘ verify ∘ replay ∘ publish          ── deterministic; AI-free
```

Cleanliness properties: (1) every factor **late-bound** (params at dispatch, CTP at
runtime, placement at mapping) — one spec, three tiers; (2) every factor **closed
under its own operations** (CTP ops yield CTPs; sweeps yield sets; pools yield
pools); (3) the **AI boundary is a production rule**, not a convention — `compile()`
is the only place a model may appear.

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
- **Hybrid replay** is the fidelity rule: pressure is open-loop (fixed by the
  CTP), the application under test stays fully closed-loop against the resulting
  queue. CCA is *not* a regime knob — it belongs to the endpoint's stack.

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

es = ExperimentSet.sweep(exp, latency=["10ms", "100ms"])     # tree: 2 × 100 leaves
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

## 4. Fidelity notes carried over from the sources

- Latency is applied off the shaped queue (netforge: netem on the egress leg) so
  queueing delay and propagation delay never conflate.
- CTP replay enters at the *endpoints* and traverses the same bottleneck as the
  reactive workload — pressure and application share the queue, which is the
  entire point.
- Parallel in-container regimes scale to ~8 per host before netem timer
  granularity degrades (NetReplica v2 appendix) — a planner packing constraint,
  i.e., a node attribute.
