---
title: "The AI Scientist-v2: Workshop-Level Automated Scientific Discovery via Agentic Tree Search"
authors: Yutaro Yamada, Robert Tjarko Lange, Cong Lu, Shengran Hu, Chris Lu, Jakob Foerster, Jeff Clune, David Ha
venue: arXiv:2504.08066 (Apr 2025)
year: 2025
category: systems-building
pass: 1
relevance: high
---

# [Pass 1]

**CATEGORY:** Systems-building (end-to-end autonomous scientific discovery framework)

**PROBLEM:** Can AI autonomously conduct the full scientific research loop — from idea generation through experimentation to manuscript writing — and produce work that passes peer review? v1 was limited by human-authored code templates and linear experimentation.

**CONTRIBUTION:** AI Scientist v2 eliminates template dependency, introduces agentic tree search for experimentation, and produces the first fully AI-generated peer-review-accepted workshop paper (ICLR 2025 ICBINB workshop, scores 6/7/6).

**ARCHITECTURE — Four Phases:**

1. **Idea Generation**: LLM generates ~20 research ideas from broad topic prompts. Novelty checked via Semantic Scholar. Human selects 3 most promising ideas (this is the only human intervention — and it's PI-level selection, not implementation).

2. **Tree-Based Experimentation** (managed by Experiment Progress Manager):
   - **Stage 1 — Preliminary Investigation**: establish feasibility, get basic prototype working
   - **Stage 2 — Hyperparameter Tuning**: optimize baseline configuration
   - **Stage 3 — Research Agenda Execution**: run core experiments
   - **Stage 4 — Ablation Studies**: systematic component-importance assessment
   - Each stage uses **agentic tree search**: nodes = (experiment code, plan, results, plots). Buggy nodes → debug children. Non-buggy nodes → refinement children. Best-first selection via LLM evaluator.
   - Parallel execution of nodes within each stage.

3. **Paper Writing**: Single-pass generation + reflection via reasoning model (o1). VLM feedback loop for figure quality.

4. **LLM Paper Reviewing**: Automated review for quality filtering.

**KEY DESIGN CHOICES:**
- **Tree search over linear iteration**: v1 was strictly sequential (each experiment built on the previous one). v2 explores multiple branches in parallel, selects best via LLM-as-judge. This is fundamentally about **exploring the hypothesis space** more efficiently.
- **Experiment Progress Manager**: Coarse-grained stage management. Each stage has explicit stopping criteria (e.g., Stage 1 stops when a working prototype exists, Stage 2 when hyperparameters converge). This mirrors how human researchers structure their work.
- **No code templates**: v2 generates all experiment code from scratch using the LLM. Datasets loaded via Hugging Face Hub. This makes it domain-general.
- **VLM feedback on figures**: Vision-Language Model checks figure quality (labels, legends, clarity) during experimentation and writing. Catches visual issues before they reach reviewers.

**EVALUATION:**
- 3 AI-generated manuscripts submitted to ICLR 2025 ICBINB workshop (43 total submissions)
- 1 accepted (scores 6, 7, 6 — top 45% of submissions, would have passed meta-review)
- Withdrawn before entering scientific record (ethical decision)
- Internal assessment: workshop-quality, not main-conference-quality
- Known issues: citation hallucination, 57% train-test overlap in accepted paper's dataset, insufficient methodological depth

**CRITICAL OBSERVATION FOR THIN-WAIST RELEVANCE:**

AI Scientist v2 reveals the **experiment execution bottleneck** with crystal clarity:

1. **Experiments = Python scripts on local machine**: Every experiment is a self-contained Python script that trains an ML model on a Hugging Face dataset. The "evaluation playground" is just a Python interpreter + GPU. There is no external infrastructure, no real-world data collection, no controlled experimental conditions.

2. **This works for ML but fundamentally cannot work for systems/networking research**:
   - ML experiments are self-contained: data in → model → metrics out
   - Systems experiments require: infrastructure configuration (tc, tshark), traffic generation (tcpreplay), application execution (browser automation), multi-vantage-point telemetry
   - You cannot "generate a Python script" that runs a controlled network experiment — you need an **orchestrated infrastructure pipeline**

3. **The tree search methodology IS applicable to systems research** — but only if the evaluation playground exists. The Experiment Progress Manager's 4-stage structure (feasibility → tuning → research agenda → ablation) maps perfectly to how systems researchers work. But each "node" execution needs to be a multi-service experiment, not a single Python script.

**This is exactly the gap the thin-waist fills.** AI Scientist's Experiment Progress Manager could orchestrate experiments through the thin-waist API instead of executing local Python scripts. The tree search explores the hypothesis space; the thin-waist executes each hypothesis on real infrastructure.

**LIMITATIONS:**
- Only ML domains (all experiments are model training runs)
- Human idea selection still required (PI-level curation)
- Workshop quality, not conference quality — "significant challenges remain in consistently achieving top-tier quality"
- Citation hallucination
- No handling of experiments that require physical infrastructure
- Cost not reported but likely significant (uses o1/o3 for reasoning steps)

**PAPERS WORTH CHASING FROM REFERENCES:**
- Gottweis et al. 2025 — "Towards an AI co-scientist" (Google's AI Research Copilot) — arXiv:2502.18864
- Si et al. 2025 — "Can LLMs generate novel research ideas?" (100+ NLP researcher evaluation)
- Eger et al. 2025 — "Transforming science with LLMs" survey — arXiv:2502.05151
- AIDE (Jiang et al. 2025) — AI-driven exploration in code space — arXiv:2502.13138
- MLEBench (Chan et al. 2025) — benchmark for ML engineering agents
- CycleResearcher (Weng et al. 2025) — automated research via automated review
- Bengio et al. 2025 — "Superintelligent agents pose catastrophic risks: Can scientist AI offer a safer path?"
- Agent Laboratory (Schmidgall et al. 2025) — already in corpus
- RE-Bench (Wijk et al. 2024) — evaluating frontier AI R&D capabilities
