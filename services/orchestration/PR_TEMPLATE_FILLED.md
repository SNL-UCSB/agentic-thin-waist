# Orchestration Service: Steps 1–8 Implementation

## What changed

<!-- Summarize the changes in a few bullet points. -->

- FastAPI app with health check, directory layout, and Dockerfile (Step 1).
- Pydantic schemas for intents, experiments, and orchestration status/results (Step 2).
- Claude client wrapper and system prompt + knowledge-file loading (Steps 3–4).
- Intent parser (NL → structured JSON) and few-shot examples (Steps 5–6).
- Experiment generator (Cartesian product over apps/capacity/latency/CC) (Step 7).
- `POST /intent` and status/results/reasoning endpoints with in-memory store (Step 8).
- Unit tests for health, models, Claude client, intent parser, generator, and intent API.

## Why

<!-- What problem does this solve, or what feature does it enable? -->

- Delivers the **intent → experiment specs** pipeline for the Orchestration Service (D5): natural-language research intents are parsed by Claude (with system prompt + knowledge + few-shot examples), turned into structured parameters, then into a list of `GeneratedExperiment` specs.
- Enables **async submission and status tracking**: clients can `POST /intent` and poll `/orchestration/{id}` and `/orchestration/{id}/results` without blocking; downstream CTP and Experiment API are stubbed so Steps 1–8 can be developed and tested without other services.
- Aligns with **INTEGRATION_PLAN.md**: foundation (Steps 1–3), core logic (4–7), and API layer for the first working slice (Step 8), so Steps 9–12 (tools, skills, knowledge refinement, real dispatch) can build on this.

## Checklist

- [x] I implemented unit tests  
  - `tests/test_health.py` (Step 1)  
  - `tests/test_models.py` (Step 2)  
  - `tests/test_claude_client.py` (Step 3)  
  - `tests/test_intent_parser.py` (Step 5)  
  - `tests/test_experiment_generator.py` (Step 7)  
  - `tests/test_intent_api.py` (Step 8)

## Notes

<!-- Optional: anything reviewers should know — open questions, follow-ups, etc. -->

- **Step 4**: System prompt and knowledge loading are implemented; manual checks for sample intents (e.g. “Run YouTube at 10 Mbps”, “Compare CUBIC vs BBR”) are suggested in the plan but not automated in this PR.
- **Step 6**: Few-shot examples are on disk and optional via `use_examples=True`; the API currently uses the default (examples can be wired in when calling the parser if desired).
- **Step 8**: `process_intent` is synchronous; background task runs in a thread. Validate/execute are stubs; Step 12 will add real CTP and Experiment API clients.
- **Schema**: `GeneratedExperiment` includes optional `ctp_cluster`; generator defaults it to `ctp_low_background` when not specified in parsed intent.
