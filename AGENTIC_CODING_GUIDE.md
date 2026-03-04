# Claude Code Guide for Agentic Thin Waist Development

**Quick start: 10-minute read to become productive with AI-assisted development on this project.**

## 1. What is Claude Code?

Claude Code is a CLI tool from Anthropic that lets you work with an AI agent (Claude) as a collaborator. Instead of writing every line yourself, you describe what you want and Claude explores your codebase, writes code, runs tests, and iterates with you.

**Install:**
```bash
npm install -g @anthropic-ai/claude-code
```

**Basic workflow:**
```bash
cd /path/to/agentic-thin-waist
claude
# Then describe what you want: "Read services/experiment-api/README.md and implement..."
```

## 2. The Mental Model

You are **directing an agent**, not typing code. The agent can:
- Read files and understand your codebase structure
- Write code following your repo's patterns and style
- Run tests and debug failures
- Iterate based on your feedback

**Your job:** Give clear direction, point to relevant documentation, and iterate.

## 3. Effective Prompting for This Project

### Start with context:
```
I'm working on the Experiment API service for the Agentic Thin Waist project.
The service manages network measurement experiments with a state machine (draft → created → running → done).
I'm part of the D1 (NetForge Service) team with Jaber and Snithik.
```

### Be specific about what you want:
```
Create a Flask endpoint POST /experiments that:
1. Accepts an Experiment dataclass
2. Validates all required fields (name, capacity_mbps, duration_s, etc.)
3. Transitions the experiment to 'created' state
4. Returns the experiment object with a unique experiment_id

Follow the API spec in services/experiment-api/README.md and the state machine rules.
```

### Reference the README first:
```
Read services/experiment-api/README.md and then implement the Experiment dataclass
from the Dataclass Contracts section.
```

### Iterate with specific feedback:
```
That's good, but the validation should also check that capacity_mbps > 0 and duration_s > 0.
```

## 4. Per-Service Starter Prompts

Use these as templates for your own prompts. Replace with specific details for what you need.

### Experiment API (Jaber)
```
Read services/experiment-api/README.md. Implement the Experiment dataclass from the
Dataclass Contracts section using Python dataclasses with all required fields.
```

```
Create the Flask route for POST /experiments that:
1. Validates the experiment spec (all required fields, positive numbers)
2. Assigns a unique experiment_id
3. Transitions state to 'created'
4. Returns the experiment object as JSON
Follow the API spec and state machine in the README.
```

### CTP Service (Jaber)
```
Read services/ctp-service/README.md. Implement the CTP extraction pipeline that takes
a pcap file path and extracts intensity, burstiness, temporal_correlation, and structure
as described in the Core Concepts section.
```

```
Create the GET /ctps/select endpoint that:
1. Takes target intensity range (min, max) as query parameters
2. Searches the CTP corpus for matching CTPs
3. Returns a list of matching CTP objects
Follow the endpoint spec in the README.
```

### Substrate Worker (Jaber)
```
Read services/substrate-worker/README.md. Implement the tc configuration module that
applies bandwidth shaping, latency, and queue management using subprocess calls to
tc qdisc and tc class commands.
```

```
Create the BottleneckState verification function that:
1. Measures actual throughput and RTT after tc rules are applied
2. Compares against targets (within 5% tolerance)
3. Sets verified=True if all metrics are within tolerance
4. Returns the BottleneckState with actual measurements
```

### NetGent Service (Eugene + Jaber)
```
Read services/netgent-service/README.md. Implement the YouTube workflow as an NFA:
- States: [homepage, search_results, video_playing, stats_visible]
- Transitions defined by Selenium WebDriver actions
- Follow the state definitions and action examples in the README.
```

```
Create the POST /workflows/execute endpoint that:
1. Accepts a workflow spec (NFA definition)
2. Runs the state machine, executing Selenium actions at each state
3. Collects screenshots and logs at each transition
4. Returns execution results with final state and captured data
```

### Telemetry Service (Manni)
```
Read services/telemetry-service/README.md. Implement the SQLAlchemy models for Result
and ContextualTreeNode with the four-layer context structure (c_static, c_dyn, c_app, c_trans)
as described.
```

```
Create the GET /results endpoint that:
1. Filters results by application name, capacity range, and congestion control algorithm
2. Includes all four context layers in the response
3. Supports pagination with limit and offset parameters
4. Returns results as JSON following the schema in the README
```

### Orchestration (Haarika)
```
Read services/orchestration/README.md. Implement the intent parser that takes
natural language like "Compare YouTube at 10, 25, 50 Mbps" and produces a list of
ExperimentSpec objects with the right parameters.
```

```
Create the TOOLS.md file that declares all service endpoints as tools that Claude
(the orchestration AI) can call. Format should match the tool schema examples.
```

## 5. Common Patterns

### Read a file first
```
Read shared/models/experiment.py and then implement the ExperimentRequest validator.
```

### Request tests alongside code
```
Implement the bandwidth shaper module and write pytest tests that cover:
- Valid shaping configurations
- Invalid inputs (negative values, mismatched ranges)
- Edge cases (zero bandwidth, minimum latency)
```

### Debug with Claude
```
Run the tests for the experiment API. Show me what failed and fix it.
```

### Iterate on code
```
That looks good, but the state machine should reject transitions from 'draft' to 'done'.
Check the README for the valid state transitions and update the code.
```

## 6. Tips for Success

1. **Always point Claude at the README** — Each service has a README with the spec. Reference it explicitly.

2. **Start with dataclass contracts** — In `shared/models/`, the dataclasses are the shared language between services. Implement these first.

3. **Use the existing code style** — Claude will match your repo's patterns. Keep the codebase consistent.

4. **Ask for tests** — Tests help Claude verify the implementation is correct. Request them alongside code.

5. **Verify against the README** — If Claude's output looks wrong, ask it to double-check against the spec in the README.

6. **Break work into small steps** — "Implement validation" is better than "Build the entire API" in one prompt.

7. **Reference past code** — "Look at how experiment validation is done in services/experiment-api/validators.py and follow the same pattern for CTPs."

## 7. When Things Go Wrong

**Claude generated code that doesn't match the README:**
```
Read services/[service]/README.md again. Your implementation of [feature] doesn't match
the spec. The README says [specific detail]. Please fix it.
```

**Tests are failing:**
```
Run pytest on services/[service]/tests/. Show me the failures and fix them.
```

**You're unsure about a requirement:**
```
Read services/[service]/README.md. I'm confused about [feature]. What does the README say?
```

---

**Start simple, iterate fast.** You have 4 weeks. Use Claude to handle the implementation details while you focus on architecture, integration, and testing.
