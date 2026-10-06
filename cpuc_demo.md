# CPUC Demo — Prudentia YouTube VoD @ 6 Mbps / 100 ms

The Prudentia (SIGCOMM '24, Table 1) YouTube video-on-demand reference workload —
Big Buck Bunny — over a shaped 6 Mbps bottleneck with 100 ms added latency,
collecting **pcap**, **queue trace**, and **YouTube player stats** together.

| Attribute | Value | Note |
|---|---|---|
| Capacity | 6 Mbps | HTB cap on `veth2` / `veth4` |
| Added latency | 100 ms | netem |
| AQM | `pfifo` | drop-tail |
| Buffer | 32 packets | BDP ≈ 50 pkt, so this is ~0.64×BDP — a deliberately shallow buffer |
| CCA | cubic | |
| Duration | 25 s playback + 5 s page load | one trial, sized to fit browserless' 30 s session cap |
| Video | `aqz-KE-bpKQ` | Big Buck Bunny, Blender's official upload |
| Player stats | 25 samples @ 1 s | `getStatsForNerds()` every 2nd sample |

## Run the intent in the terminal, plot in the notebook

Same flow as the wget quick start: curl the intent, poll it, grab the
`experiment_id`, paste it into the notebook.

The request body lives in `cpuc_intent.json` — the regime overrides plus the
workflow itself. Passing the workflow through `context.workflow` makes the
orchestrator use it verbatim instead of picking one from the library
(`app/agent/orchestrator/agent.py:255` — "user-provided"), which is what gets you
the `youtube_stats` action. There is no `context` key for workflow *parameters*,
so the workflow in that file carries literal values rather than `{{placeholders}}`
and declares `"parameters": []`.

### 1. Submit

```bash
ORCH_ID=$(curl -s -X POST http://localhost:8005/intent \
  -H "Content-Type: application/json" \
  -d @cpuc_intent.json \
  | python3 -c "import json,sys;print(json.load(sys.stdin)['orchestration_id'])")
echo "orchestration_id = $ORCH_ID"
```

### 2. Watch it run

```bash
while STATUS=$(curl -s http://localhost:8005/orchestration/$ORCH_ID | python3 -c "import json,sys;print(json.load(sys.stdin)['status'])"); \
      [ "$STATUS" != "complete" ] && [ "$STATUS" != "failed" ]; do
  echo "$(date +%T) $STATUS"
  sleep 5
done
echo "final: $STATUS"
```

Expect ~2 minutes: worker provisioning, the synchronized capture + browser
window, then artifact upload to telemetry.

### 3. Pull the experiment + result IDs

```bash
EXP=$(curl -s http://localhost:8005/orchestration/$ORCH_ID/results \
        | python3 -c "import json,sys;print(json.load(sys.stdin)['results'][0]['experiment_id'])")
RID=$(curl -s "http://localhost:8004/results?experiment_id=$EXP&limit=1" \
        | python3 -c "import json,sys;print(json.load(sys.stdin)['results'][0]['result_id'])")
echo "exp=$EXP  rid=$RID"
```

Sanity-check that the player stats made it into telemetry before opening the
notebook:

```bash
curl -s "http://localhost:8004/results/$RID" | grep -o '"resolution":"[^"]*"' | head -1
```

### 4. Plot

```bash
EXPERIMENT_ID=$EXP jupyter lab cpuc_demo.ipynb
```

**Run All.** The notebook pulls the pcap and queue trace from telemetry by
`EXPERIMENT_ID`, finds the `youtube_stats` output inside the result's
`qoe_metrics`, and plots:

1. Download throughput vs the 6 Mbps line
2. Queue occupancy vs the 32-packet `pfifo` limit
3. Drop rate
4. Stats for nerds — resolution, itag/codecs, buffer health, dropped frames, the
   player's own bandwidth estimate, and the quality ladder it was offered
5. DASH segment cadence derived from the pcap
6. Combined view — player state stacked over the queue on one time axis

### Tuning the run

Edit `cpuc_intent.json`:

| To change | Edit |
|---|---|
| Playback length | `samples` × `interval_seconds` in the `youtube_stats` action |
| Sample density | `interval_seconds` (0.5 gives twice the points) |
| Capacity / latency / queue | `capacities`, `latencies`, `buffer_packets` in `context`, and the matching numbers in the `intent` prose |
| Video | the `url` in the `go_to_url` action |

Keep the total (5 s load + playback) under ~30 s — see the browserless note
below. `duration_seconds` in `context` should be a few seconds longer than that
so the capture covers the whole run.

---

## Alternative: the runner script

`cpuc_demo_run.py` does the same thing without the orchestrator — it drives the
substrate worker directly and writes a local run directory instead of going
through telemetry. Useful when the orchestrator is down or you want a run that
does not touch the database.

```bash
python3 cpuc_demo_run.py --watch-seconds 20 --interval-seconds 0.5
RUN_DIR=cpuc_runs/<name-it-printed> jupyter lab cpuc_demo.ipynb
```

The notebook reads either source: `EXPERIMENT_ID` for telemetry, `RUN_DIR` for a
local run, and with neither set it picks the most recent local run.

---

## The workflow

The workflow lives inline in `cpuc_intent.json` under `context.workflow`, so the
whole demo is one file plus one curl. It is three actions:

```json
{
  "specification": "Prudentia YouTube VoD workload with player telemetry. ...",
  "states": [
    {
      "checks": [{ "type": "always_true", "params": {} }],
      "actions": [
        { "type": "go_to_url",
          "params": { "url": "https://www.youtube.com/watch?v=aqz-KE-bpKQ&autoplay=1",
                      "new_tab": false } },
        { "type": "wait", "params": { "seconds": "5" } },
        { "type": "youtube_stats",
          "params": { "samples": "25", "interval_seconds": "1", "nerd_stats_every": "2" } }
      ],
      "end_state": "Workflow Completed",
      "executed": []
    }
  ],
  "parameters": []
}
```

**`go_to_url`** loads the watch page with `autoplay=1`. **`wait 5`** lets the
player mount and start buffering — polling before this returns an empty series.
**`youtube_stats`** does the rest.

### Why the values are literal

`context.workflow` short-circuits the workflow-selection agent
(`app/agent/orchestrator/agent.py:255`, logged as "user-provided"), which is what
lets the demo run a workflow that is not in the remote library. But the intent
API only forwards a fixed set of `context` keys (`app/api/intent.py:172`:
capacities, latencies, cc_algorithms, aqm_policy, buffer_packets, qdisc_params,
duration_seconds, num_trials) — **workflow parameters are not among them**.

So the workflow declares `"parameters": []` and spells its values out. Templating
it with `{{video_id}}` would fail validation: `WorkflowRunner._check_parameters`
rejects a run whose declared parameters were never supplied.

The parameterised version — `video_id`, `samples`, `interval_seconds` —
lives at
`shared/clients/netgent/scripts/workflow/prudentia_youtube_vod_stats_workflow.json`
and is what `cpuc_demo_run.py` uses, since the direct `/run` API *does* take a
`parameters` dict.

### The `youtube_stats` action

`shared/clients/netgent/src/registry/actions/playwright.py`.

Every sample it reads the HTML5 `<video>` element — resolution, buffer health
(buffered-ahead minus playhead), dropped and total frames, `currentTime`,
readyState. Every `nerd_stats_every`-th sample it also calls the player's own
`getStatsForNerds()` for codecs/itag, optimal res, and the player's bandwidth
estimate; that call rebuilds the entire debug panel, so it is throttled rather
than run every tick.

Polling doubles as the watch timer — `samples` × `interval_seconds` is the
playback duration, so there is no separate `wait` to keep in sync. If the page
disappears mid-run the action stops after three consecutive failures and reports
`stopped_early` instead of sleeping out the remaining window.

| Param | Default | Meaning |
|---|---|---|
| `samples` | `1` | number of polls |
| `interval_seconds` | `1` | seconds between polls |
| `nerd_stats_every` | `5` | call `getStatsForNerds()` every Nth sample |

Output: a `samples` series (one dict per poll, each with `rel_t`), plus the
latest non-null value of each field flattened to the top level. The notebook
re-derives that flattening from the series itself, so a run collected by any
version of the action plots correctly.

---

## Two open issues

### 1. Browserless caps every browser run at 30 s

`curl -s http://localhost:3000/config` reports `"timeout": 30000`. Browserless
tears down the page, context, and browser when that expires, which surfaces as
`Target page, context or browser has been closed` — so the 60 s run above
collected only 5 player samples spanning 4 s before the page vanished.

This is not specific to player stats. It silently truncates **every** browser
experiment in this stack past ~30 s, including the existing `wait`-based
Prudentia workflows — those just never notice, because `wait` does not touch the
page, so a dead video looks like a successful run with a quiet pcap. Worth
re-checking any long browser result collected before this was found.

`shared/clients/netgent/src/main.py` now appends `?timeout=900000` to the
browserless WS endpoint (override with `NETGENT_BROWSER_TIMEOUT_MS`). The same
commit also fixes the action's summary flattening, which previously read only the
final sample and so dropped the throttled `getStatsForNerds()` fields. **Neither
is loaded yet** — the substrate worker imported those modules at startup:

```bash
docker compose restart substrate-worker
python3 cpuc_demo_run.py --watch-seconds 60   # expect 60/60 samples
```

The notebook does its own flattening across the samples series, so it already
recovers `codecs` / `itag` / `bandwidth_kbps` from whichever sample carried them
regardless of which version of the action produced the run.

### 2. The run is application-limited, so the queue barely fills

In the verified 60 s run the player picked **480p** and pulled 2.27 Mbps — 38% of
the 6 Mbps cap. Queue occupancy peaked at 5 packets against a 32-packet limit,
with **zero** drops. Nothing about the bottleneck was actually exercised.

The cause is the viewport: ABR players size their quality ladder off it, and the
default is 1280×720. The player offered `hd2160` down to `tiny` but delivered
itag 397 (480p AV1). `_playwright_page` in `shared/clients/netgent/src/main.py`
already documents this, and Prudentia drove real 4K monitors for exactly this
reason.

To put the link under real pressure, raise the viewport:

```bash
NETGENT_VIEWPORT_WIDTH=3840 NETGENT_VIEWPORT_HEIGHT=2160 \
  docker compose up -d substrate-worker
```

or lower the capacity below what 480p needs (`--mbps 1.5`) so the player is
forced to step down the ladder — which is the more interesting demo anyway, since
the resolution panel then has something to show.

---

## Preflight

```bash
for p in 8000 8001 8002 8003 8004 8005; do
  printf "port %s: " $p
  curl -s -m 2 -o /dev/null -w "%{http_code}\n" http://localhost:$p/health
done
curl -s http://localhost:8002/state  | python3 -m json.tool   # current shaping
curl -s http://localhost:3000/config | python3 -m json.tool   # browserless timeout
```
