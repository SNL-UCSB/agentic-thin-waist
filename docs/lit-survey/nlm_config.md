# NotebookLM Configuration

## Survey Notebook

- **notebook_id:** `6f2b2b44-34c0-4918-8a22-aff2b035da53`
- **title:** survey-agentic-systems-research
- **sources ingested:** 22 (verification tools batch added 2026-07-02: Maler STL, RTAMT, Necula TV, SMT Handbook ch.26, Outlines, Segura MT survey, TLA+ at AWS; plus Glia, AI Scientist v2, AI Scientist v1, Agent Laboratory, POPPER, netUnicorn [abstract-only + full-text PDF added 2026-07-02], NetConfEval*, Confucius, NetArena, Learned Cloud Emulators, Mininet, Mininet-HiFi, NetForge v3, NetGent)
- **NLM binary:** `nlm` on PATH (`/Users/profg-agent/.local/bin/nlm`)
- **Access method:** CLI via Bash (MCP does not work)

*Note: NetConfEval arXiv URL resolved to wrong paper (2310.10183 is a math paper). Need to re-add with correct source.

## Chat Configuration

- **goal:** custom
- **custom_prompt:** "You are a research corpus query engine for a PI surveying agentic systems for accelerating systems and networking research. The surveyor is an Examiner building a comprehensive narrative survey. They are the builder of netUnicorn and the agentic-thin-waist platform. Goals: (1) map how the community uses agentic AI for systems research, (2) identify first-principles architecture for the agentic research loop, (3) validate that a composable empirical backend (thin-waist) is the right investment. Always cite specific papers and quote relevant passages."
- **response_length:** longer
- **tags:** survey, agentic-systems, networking, systems-research
