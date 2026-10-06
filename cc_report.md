2026-07-08T07:49:37+00:00 | cubic_10bw-85rtt-64q: orchestration ended status=failed (orch=orch-cc9258d1)
2026-07-08T07:49:37+00:00 | cubic_10bw-85rtt-64q: no experiment_id from orchestration results (orch=orch-cc9258d1)
2026-07-08T07:49:42+00:00 | bbr_10bw-275rtt-64q: orchestration ended status=failed (orch=orch-a79d902a)
2026-07-08T07:49:42+00:00 | bbr_10bw-275rtt-64q: no experiment_id from orchestration results (orch=orch-a79d902a)

## 2026-07-16 — ATW collection blocked: orchestrator LLM key invalid
- symptom: every POST /intent -> orchestration status=failed in ~1s with
  "Error code: 401 authentication_error: API key is invalid." parse_intent (the
  first LLM step) fails before any shaping/collection happens.
- config: ORCHESTRATOR_LLM_PROVIDER=anthropic, ANTHROPIC_API_KEY=sk-ant… is
  invalid/expired; GOOGLE_API_KEY is commented out. (Earlier campaigns used Gemini.)
- action needed (USER): set a valid key, then restart orchestration. Either
  (a) put a valid ANTHROPIC_API_KEY in .env, or (b) uncomment a valid GOOGLE_API_KEY
  and set ORCHESTRATOR_LLM_PROVIDER=gemini. Then `make up` (also loads the new
  test_iperf3_workflow / test_h2load_workflow).
- resolved: no (waiting on key)
2026-10-01T18:50:43+00:00 | reno2_10bw-20rtt-128q: no orchestration_id from submit
2026-10-01T18:50:44+00:00 | cubic_10bw-20rtt-128q: no orchestration_id from submit
2026-10-01T18:50:44+00:00 | bbr_10bw-20rtt-128q: no orchestration_id from submit
2026-10-01T18:50:44+00:00 | bic_10bw-20rtt-128q: no orchestration_id from submit
2026-10-01T18:50:44+00:00 | reno2_10bw-130rtt-128q: no orchestration_id from submit
2026-10-01T18:53:21+00:00 | reno2_10bw-20rtt-128q: orchestration status=failed (orch=orch-2d41e238)
2026-10-01T18:53:21+00:00 | reno2_10bw-20rtt-128q: no experiment_id (orch=orch-2d41e238)
2026-10-01T18:53:27+00:00 | cubic_10bw-20rtt-128q: orchestration status=failed (orch=orch-9102064f)
2026-10-01T18:53:27+00:00 | cubic_10bw-20rtt-128q: no experiment_id (orch=orch-9102064f)
2026-10-01T18:53:32+00:00 | bbr_10bw-20rtt-128q: orchestration status=failed (orch=orch-c99af19f)
2026-10-01T18:53:32+00:00 | bbr_10bw-20rtt-128q: no experiment_id (orch=orch-c99af19f)
2026-10-01T18:53:38+00:00 | bic_10bw-20rtt-128q: orchestration status=failed (orch=orch-6b7b775a)
2026-10-01T18:53:38+00:00 | bic_10bw-20rtt-128q: no experiment_id (orch=orch-6b7b775a)
2026-10-01T18:53:43+00:00 | reno2_10bw-130rtt-128q: orchestration status=failed (orch=orch-43b63e84)
2026-10-01T18:53:43+00:00 | reno2_10bw-130rtt-128q: no experiment_id (orch=orch-43b63e84)
2026-10-01T18:58:53+00:00 | reno2_10bw-20rtt-128q: orchestration status=failed (orch=orch-7b0e7c14)
2026-10-01T18:58:53+00:00 | reno2_10bw-20rtt-128q: no experiment_id (orch=orch-7b0e7c14)
2026-10-01T18:58:59+00:00 | cubic_10bw-20rtt-128q: orchestration status=failed (orch=orch-d5b0959d)
2026-10-01T18:58:59+00:00 | cubic_10bw-20rtt-128q: no experiment_id (orch=orch-d5b0959d)
2026-10-01T18:59:04+00:00 | bbr_10bw-20rtt-128q: orchestration status=failed (orch=orch-ea6202b9)
2026-10-01T18:59:04+00:00 | bbr_10bw-20rtt-128q: no experiment_id (orch=orch-ea6202b9)
2026-10-01T18:59:10+00:00 | bic_10bw-20rtt-128q: orchestration status=failed (orch=orch-dede8f6b)
2026-10-01T18:59:10+00:00 | bic_10bw-20rtt-128q: no experiment_id (orch=orch-dede8f6b)
2026-10-01T18:59:15+00:00 | reno2_10bw-130rtt-128q: orchestration status=failed (orch=orch-fa9ff91a)
2026-10-01T18:59:15+00:00 | reno2_10bw-130rtt-128q: no experiment_id (orch=orch-fa9ff91a)
2026-10-06T20:18:30+00:00 | cubic_5bw-275rtt-32q-nooffload: orchestration status=timeout (orch=orch-e7b9cbf6)
2026-10-06T20:18:30+00:00 | cubic_5bw-275rtt-32q-nooffload: no experiment_id (orch=orch-e7b9cbf6)
