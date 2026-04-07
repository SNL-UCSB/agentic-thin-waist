# Deepening Notes — NLM Pass 2 Queries (2026-04-06)

Key quantitative evidence and architectural details extracted via targeted NLM queries on the main notebook (`6f2b2b44`).

---

## 1. Evaluation Infrastructure Per System

| System | Evaluation Substrate | Engineering Effort | Domain-Locked? |
|--------|---------------------|-------------------|----------------|
| **Glia** | Vidur LLM inference simulator + distributed GPU cluster | Custom multi-agent playground (Reasoner, Experimenter, Analyzer) | Yes — LLM serving |
| **AI Scientist v2** | Python/PyTorch/Jax + GPUs; VLM feedback loop for figures | <$15/paper; but v1 had **42% experiment failure rate** due to coding errors | Yes — ML training |
| **Confucius** | Meta production tools: NAPT, Robotron, ODS, Scuba; dry-run validators | **2 years** operational, **60+ apps**, saves **17 eng-hours/week**; apps range 600-6400 LoC | Yes — Meta networks |
| **AlphaEvolve** | Google data center schedulers + hardware accelerator sims | Discovered Strassen improvement (first in 56 years); 0.7% worldwide compute savings | Yes — Google infra |
| **PolicySmith** | Linux kernel sandbox + open-source traces | Generates instance-optimal heuristics integrating directly into kernel | Yes — per-domain |
| **Engram** | Persistent Archive + Research Digest; domain-specific evaluators | Decouples long-horizon exploration from context window constraints | Yes — per-domain |
| **NIKA** | Largest public benchmark for LLM network troubleshooting; zero-effort replay | **5 network scenarios**, **54 representative issues**, modular APIs | Yes — network troubleshooting |
| **POPPER** | Sequential falsification framework; domain-specific observations | **6 domains** demonstrated; **10x speedup** vs. human scientists with Type-I error control | Flexible but manual setup |

---

## 2. Failure Modes When Substrate Is Inadequate

### High Experimental Failure Rates
- AI Scientist v1: **42% of experiments failed** due to coding errors
- Code modifications averaged only **8% more characters per iteration** — limited adaptability

### Hallucinated Results
- AI Scientist: hallucinated numerical results, placeholder text ("Conclusions Here"), repeated sections
- Confucius: when LLM can't find answers in designated sources, it **fabricates responses** — violates fail-early principle

### Coherence Ceiling (Engram)
- Context degradation over long horizons
- Failure to accumulate knowledge across independent runs
- Confucius: context propagation lost in later session parts (e.g., time constraint "7-8pm" ignored as steps grow)

### Domain Locking / Generalizability Failure
- netUnicorn: ML models fail to maintain efficacy across different network environments due to "unrealistic or poor-quality datasets"
- NetArena: existing benchmarks suffer from **contamination due to static design** and high statistical variance

### Novelty Assessment Failure
- AI Scientist: misclassified established concepts (micro-batching for SGD) as novel discoveries
- Median **5 citations**, most outdated (only 5/34 from 2020+)

### Feedback Signal Constraints
- FunSearch: works only when there is **"rich" scoring feedback**; fails at theorem proving because no nuanced signal
- Engram: scalar benchmark scores → **trapped in local optima**

---

## 3. Reasoning-Execution Gap

### Three Dimensions of the Gap
1. **Reliability Gap** (Barbarians): ADRS "crucially assumes the existence of a reliable verifier"
2. **Heuristic Gap** (PolicySmith): manual reasoning can't find instance-optimal heuristics across diverse traces
3. **Coherence + Scalar Gap** (Engram): evolutionary neighborhood bias + context degradation

### Architectural Patterns to Bridge
1. **ADRS Loop** (Barbarians): iterative generation → evaluation → refinement; humans shift to problem formulation
2. **Direct Kernel/Sandbox Integration** (PolicySmith): reasoning immediately constrained by execution environment
3. **Decoupled Long-Horizon Exploration** (Engram): sequence of independent agents + persistent Archive + Research Digest

### Why the Composable Backend Is the Answer
- Provides the **standardized verifier** ADRS assumes exists
- Supports **multi-step shifts** via disaggregated, reusable tasks (netUnicorn/NetForge)
- Ensures data is **endogenous and realistic** — prevents Research Digest from becoming "distilled hallucinations"
