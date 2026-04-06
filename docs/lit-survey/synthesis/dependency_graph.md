# Dependency Graph: Design Tensions Across the Corpus

**Source:** NLM cross-corpus synthesis (2026-04-04)

## Five Fundamental Tensions

### Tension 1: General Code Execution vs. Specialized Playgrounds
- **AI Scientist assumes:** experiments = writing and running Python scripts
- **Glia challenges:** complex systems require specialized Evaluation Playgrounds to ground reasoning in empirical feedback
- **Resolution:** The thin-waist provides the specialized playground as a composable, agent-callable service

### Tension 2: Scalar Fitness vs. White-Box Reasoning
- **AlphaEvolve/AdaEvolve/PolicySmith assume:** evolutionary search guided by scalar scores
- **Glia/Engram challenge:** "Evolutionary methods often remain trapped in local optima by relying on scalar benchmark scores, failing when coordinated multi-step changes are required" (Engram)
- **Resolution:** Both are needed — evolutionary search for well-defined optimization, white-box reasoning for hypothesis-driven exploration

### Tension 3: Leverage Existing Tools vs. Build New Substrates
- **Confucius principle:** "leverage existing network management tools, rather than developing new ones"
- **netUnicorn/NetForge challenge:** existing tools/datasets are "ill-suited or even counterproductive" for generalizability; must build composable infrastructure
- **Resolution:** Operations (Confucius) can leverage; research (thin-waist) must build. Different problems, different requirements.

### Tension 4: Full Autonomy vs. Human-Guided
- **AI Scientist/AlphaEvolve:** strive for full automation
- **Agent Laboratory/Confucius:** "human involvement significantly improves overall quality"; safety-critical tasks require human approval
- **Resolution:** Human-in-the-loop at the intent level (PI selects problems), autonomy at the execution level

### Tension 5: One Model for All vs. Multi-Agent Decomposition
- **NetLLM:** "one model for all tasks" via LLM adaptation
- **Confucius:** single-step approach is "not effective" for complex multi-step tasks
- **Resolution:** Decomposed multi-agent with standardized interfaces (the thin-waist pattern)

## Constraint-Change Analysis

### Scenario A: 10x Better LLM Reasoning
- Backend need **increases** — "if reasoning is perfect, the only remaining bottleneck is the fidelity of the verification"
- Composable empirical backend becomes **more** important, not less

### Scenario B: 10x Cheaper Execution
- Brute-force evolutionary search becomes computationally trivial
- But white-box reasoning (Glia) remains essential for trust and interpretability
- Bottleneck shifts to distillation — need better Research Digest (Engram)

### Scenario C: 10x Infrastructure Complexity
- Monolithic approaches and single-model approaches break
- Confucius's DSL-mediated approach scales (if DSLs are extensible)
- **netUnicorn's composability becomes absolute infrastructure** — only way to maintain realism across heterogeneous environments
