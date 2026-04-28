# Positioning Pramana vs. MCP / A2A / Code-as-Policies

**Purpose:** Help decide how to frame Pramana relative to MCP, A2A, and the broader tool-use / grounding canon. Drafted 2026-04-27 as input to the HotNets §4 (Architecture / Thin-Waist) and §7 (Related Work) sections.

This document presents four candidate framings, the trade-offs of each, and a recommended composite. It does not commit to one — that decision is yours.

---

## What MCP and A2A actually are (so we can be precise)

**MCP (Model Context Protocol).** Anthropic, Nov 2024. A wire protocol — JSON-RPC over stdio/HTTP — that lets an LLM-agent client discover and invoke tools exposed by an MCP server. The unit of interaction is a **tool call**: a function with typed inputs and outputs. MCP standardizes:
- *discovery* (an agent asks "what tools do you have?"),
- *invocation* (an agent calls a named tool with arguments),
- *streaming* (the server can stream partial results),
- *resources* (read-only data the server makes available).

What MCP is *not*: it is not a workflow language, not a compositional interface, not a domain-aware specification format. An MCP tool call is like an RPC. The agent decides when and why to call it; MCP's job is making the call possible.

**A2A (Agent-to-Agent).** Google, 2025. Same architectural layer as MCP but for agent↔agent communication. An A2A endpoint exposes an *agent's* capabilities as discoverable services. Think of A2A as MCP where the "tool" is itself another agent.

**Code-as-Policies / ProgPrompt.** Robotics 2023. Different layer. The contribution is *generating executable code from natural-language intent* and running it in a deterministic substrate. The agent doesn't make tool calls — it emits a program; the program is executed; the program's effects are observed. This is closer to compilation than to RPC.

---

## What Pramana actually is (so we can compare)

Pramana, as currently designed, has three layers:

1. **Intent plane** — the agent receives a natural-language research intent ("compare ABR algorithms under low-bandwidth bottleneck regimes") and emits an **experiment specification** — a structured, declarative artifact describing what to run, on what infrastructure, with what cross-traffic, and what telemetry to collect.

2. **Representation plane** — cross-traffic profiles (CTP) and telemetry types form an intermediate language. The experiment spec references these representations rather than re-describing them every time.

3. **Execution plane** — substrate workers, NetGent browsers, telemetry pipelines apply the spec to real infrastructure.

The thin-waist claim: the **experiment-specification language** is the narrow protocol that lets heterogeneous agents above (Glia-style design agents, ArachNet-style research agents, Confucius-style ops agents) share the same controllable substrate below.

---

## The four candidate framings

### Framing 1 — "Pramana defines a peer protocol to MCP"

**Claim:** Pramana's experiment-spec is a protocol. MCP standardizes agent↔tool. A2A standardizes agent↔agent. Pramana standardizes agent↔experiment-infrastructure. Three peer protocols, three different boundaries.

**Why this works:**
- Clean architectural symmetry, easy to draw in §4.
- Defends against "why not MCP?" — the answer is that MCP is the wrong boundary; it doesn't help an agent specify *experiments*.
- Aligns Pramana with an active and well-respected architectural movement.

**Why this is risky:**
- Pramana is not currently a protocol. It is a system with a declarative interface. Calling it a protocol is partly aspirational. Reviewers may ask: "Is the experiment-spec actually standardized? Specified? Versioned? Or is it just YAML you accept as input?" If the answer is the latter, the framing weakens.
- The peer-protocol move implicitly promises that *other* agentic systems can target Pramana's spec. That is a generalization claim. Reviewers will ask how you know.
- Risk of looking like protocol astronomy if not backed by usage.

**What it requires from the paper:** A clearly specified experiment-spec format with versioning intent. Evidence (or a credible promise) that more than one agent stack can produce it.

---

### Framing 2 — "Pramana is a domain-aware DSL on top of a controllable substrate"

**Claim:** Pramana provides a *declarative interface* (an experiment-specification language) over a controllable execution substrate. It is to network-experiment infrastructure what SQL is to relational databases — a domain-aware language whose value comes from the structure it enforces.

**Why this works:**
- Honest. Pramana *is* a declarative interface, not a wire protocol.
- Sidesteps the protocol-astronomy attack. SQL is uncontroversially a contribution despite being "just a language."
- The SQL analogy is rhetorically powerful: nobody asks "why not raw RPC instead of SQL?" — the answer is obviously "because SQL captures structure that the runtime can exploit."
- Direct lineage to Code-as-Policies / DSPy: the contribution is the *language design*, not the runtime.

**Why this is risky:**
- A DSL is a smaller-sounding contribution than a protocol. Reviewers may ask "is it a DSL or is it a system?" — and either answer can be turned against the paper.
- The SQL analogy is strong but implies completeness (SQL has a closed algebra). Pramana's spec language probably does not, yet.

**What it requires from the paper:** A clean spec syntax + the algebraic intuition for why this language captures the right things (composability of bottleneck regimes, separability of intent and representation, etc.).

---

### Framing 3 — "Pramana operates at a different abstraction level — orthogonal to MCP/A2A"

**Claim:** MCP and A2A are wire protocols (low-level); Pramana is an experiment-architecture pattern (high-level). They do not compete. An agent could use MCP internally to invoke individual capabilities while Pramana's experiment-spec is the artifact the agent constructs and executes.

**Why this works:**
- Defuses the "why not MCP?" attack by refusing the framing — you're not at the same layer.
- Lets Pramana's substrate use MCP servers internally if convenient, without weakening Pramana's architectural claim.

**Why this is risky:**
- "Orthogonal" can read as "we just don't engage with the protocol literature." Reviewers want to see explicit positioning, not avoidance.
- Loses the rhetorical strength of being part of the protocol-layer movement.
- The "different abstraction level" claim must be argued rigorously — you can't just assert it.

**What it requires from the paper:** A diagram that visibly stacks the layers and shows MCP/A2A and Pramana's spec at distinct ones, with a clean explanation of why.

---

### Framing 4 — "Pramana subsumes MCP-style needs for the experiment domain"

**Claim:** Pramana's substrate exposes the network-infrastructure capability surface; agents construct experiment specs that the substrate executes. The *outer* interface is Pramana's spec language. *Internally*, the substrate may use MCP to invoke specific tools (a packet-capture tool, a bottleneck-shaping tool). MCP is an implementation detail of one Pramana plane; Pramana is the architectural commitment that defines the boundary.

**Why this works:**
- Cleanest separation of concerns: Pramana's contribution is at the *outer* interface (where the agent meets infrastructure); MCP is at the *inner* interface (where Pramana's planes meet specific tools).
- Lets the paper claim Pramana as the architectural contribution while still using MCP as a substrate choice — best of both.
- Mirrors how other systems-research artifacts work: SQL doesn't compete with file-system RPC; SQL is a language, file-system RPC is a substrate it might run on.

**Why this is risky:**
- Requires you to *actually* be willing to use MCP internally if it makes engineering sense. If the substrate doesn't use MCP, the claim is harder to defend.
- Some reviewers will still ask "could you express the experiment-spec layer entirely in terms of MCP tool calls and skip Pramana?" — the answer is a *no* you have to argue.

**What it requires from the paper:** Explicit acknowledgement that MCP is a candidate substrate for Pramana's lower planes, plus the argument for why *spec → substrate* is the right interface even when the substrate is built from MCP servers.

---

## Recommended composite

Use Framings 4 + 2 jointly. Let me restate them as a single positioning:

> **Pramana provides a domain-aware declarative interface — the experiment specification — that mediates between heterogeneous research agents and controllable network-experiment infrastructure. The contribution is not a new wire protocol (MCP and A2A already serve those roles for agent↔tool and agent↔agent) but an architectural commitment about where the agent↔infrastructure boundary should sit, and what shape its interface should take. Internally, Pramana's substrate may compose individual capabilities through MCP servers; externally, it exposes a single spec language that captures experiment intent in a form the substrate can verify, schedule, and reproduce. The thin-waist sits at this outer interface.**

This framing:
- Acknowledges MCP/A2A directly (defends against "why not MCP?").
- Names Pramana's contribution at the right level (architecture + DSL, not wire protocol).
- Stays honest about what Pramana is and is not.
- Generalizes to other domains: the same architectural move would yield ChemOS-spec for autonomous chemistry, LabSpec for biology self-driving labs, etc. — supports the cross-domain "lessons" framing the user asked for.

The two general lessons (Insights A and B from the proposal) sit naturally on top of this framing:
- **Insight A (grounding):** the experiment-spec is the *domain-aware grounding layer* that turns stochastic NL intent into deterministic infrastructure action — the design discipline for that layer is the contribution.
- **Insight B (amortization):** because the spec is declarative and re-executable, it is also the *amortization artifact* — once an agent emits a spec, redundant exploration is cheap and reproducible.

---

## Where the related-work positioning lands

In §7, position MCP/A2A as the **adjacent protocols** (different boundary, same architectural impulse), Code-as-Policies / DSPy / LMQL as the **grounding canon** (same architectural move at a different layer), and Coscientist / ChemOS / Materials Acceleration Platforms as the **cross-domain peers** (same architectural move in different domains). The HotNets paper claims the agent↔experiment-infrastructure boundary as Pramana's contribution to that landscape.

In §4, draw the layer diagram once, with Pramana's spec at the outer interface and MCP/A2A at the inner one (or absent — both should be drawable). Argue the boundary choice in two paragraphs. Move on.

---

## Decision points for you

1. **Are you willing to claim Pramana's experiment-spec is a *language*, not a protocol?** If yes, Framing 2/4 composite. If you specifically want to be a protocol, then 1 — but only if you are committed to versioning + standardization.
2. **Do you want to engage with MCP explicitly, or treat it as orthogonal?** Engaging is stronger. Treating as orthogonal is safer but reviewer-flavored as evasive.
3. **Are you willing to claim the architectural move generalizes — i.e., that ChemOS / LAB-spec / X-spec are cousins?** This is the cross-domain "lessons" defense; it is the most powerful framing but the most ambitious. The corpus expansion (Round 3 Thread E+) is designed to support it.

Once you decide on (1)–(3), §4 and §7 of the HotNets paper write themselves.
