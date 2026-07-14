# Per-App Latency for Concurrent Browser Experiments

This document describes the per-app latency feature: how it works, what files
changed, and how to use it.

## Problem

In the default substrate-worker topology, all browser apps in a concurrent
experiment (e.g. YouTube + Twitch + Tubi) share one network namespace (`ns1`),
one bottleneck link, and one flat `netem delay Xms` on `veth3` inside `ns2`.
Every app gets the same latency.

This feature lets each app receive a **different** netem delay on the return
(download) path, classified by which app generated the connection — not by
destination IP.

## Constraints (unchanged)

- Network namespaces (`ns1`, `ns2`), bridge, and veth topology — **not modified**
- HTB rate cap + pfifo on `veth2` / `veth4` in root netns — **not modified**
- Only changed: classification logic + netem on `veth3` in `ns2`

## How browser traffic actually flows

Browsers do **not** run inside `ns1`. Chrome is launched in the root namespace
and pointed at a forward proxy (`browser_proxy.py`) running **inside ns1**:

```
Chrome (root) → browser_proxy (ns1:8888+) → Internet
                     ↑ upstream sockets originate in ns1
                       and traverse the shaped veth path
```

Return (download) path where netem is applied:

```
WAN → ns2:veth5 → CONNMARK restore → ns2:veth3 [per-app netem here]
    → bridge → veth2 [rate cap] → ns1:veth1 → proxy → Chrome
```

## Classification design (Stage 1)

Because all three apps share one proxy process, classification uses **distinct
source IP aliases** on `ns1:veth1` (one per app):

| App     | Alias IP     | Proxy port | fwmark |
|---------|--------------|------------|--------|
| youtube | 172.16.1.5   | 8889       | 10     |
| twitch  | 172.16.1.9   | 8890       | 20     |
| tubi    | 172.16.1.13  | 8891       | 30     |

Each app gets its own `browser_proxy` instance bound to its alias IP. Upstream
sockets are bound to that IP before `connect()`, so outgoing SYNs carry the
alias as source address.

In `ns2`, iptables classifies by source IP and saves the mark to conntrack:

```
PREROUTING -i veth3 -s 172.16.1.5  -j MARK --set-mark 10
PREROUTING -i veth3                -j CONNMARK --save-mark
PREROUTING -i veth5                -j CONNMARK --restore-mark
```

Return packets arrive at `veth3` egress with `skb->mark` restored from
conntrack — ready for Stage 2 `tc filter fw` rules.

> **Note:** `SO_MARK` alone cannot cross veth namespace boundaries in newer
> kernels (`skb->mark` is cleared). Source IP aliases are used as the mark
> carrier instead; L3 addresses survive namespace crossings.

## Per-app netem lanes (Stage 2)

The flat `netem delay Xms` on `veth3` is replaced with an HTB root qdisc and
per-app leaf netem qdiscs:

```
root 1: htb  default 100
  class 1:10  → netem delay 10ms    (YouTube, mark 10)
  class 1:20  → netem delay 150ms   (Twitch,  mark 20)
  class 1:30  → netem delay 40ms    (Tubi,     mark 30)
  class 1:100 → netem delay 50ms    (default / unclassified)

filter fw handle 10 → flowid 1:10
filter fw handle 20 → flowid 1:20
filter fw handle 30 → flowid 1:30
```

HTB classes are uncapped (`rate 1gbit`) — they exist only for classification.
The actual bottleneck rate cap remains on `veth2`/`veth4`.

## Files changed

### `services/substrate-worker/src/substrate/browser_proxy.py` (new)

- Added `--mark` CLI arg and `_FWMARK` / `_BIND_HOST` globals
- Added `_marked_connection()` — sets `SO_MARK` and binds to alias IP **before**
  `connect()` so the SYN carries both mark and source address
- `_handle_connect()` and `_handle_plain()` use `_marked_connection()`

### `services/substrate-worker/src/substrate/main.py`

**New models / fields:**
- `PerAppMarkRequest` — `app_marks`, `default_latency_ms`, `netem_iface`, `netem_ns`
- `RunExperimentRequest` — `app_fwmark`, `browser_proxy_host`, `browser_proxy_port`

**New helpers:**
- `_add_ns1_alias(bind_ip)` — adds `/32` alias to `ns1:veth1`
- `_start_app_proxy(port, mark, bind_ip)` — starts marked proxy in ns1
- `_setup_connmark_rules(app_marks)` — iptables MARK + CONNMARK in ns2
- `apply_per_app_netem(...)` — HTB + per-app netem + `tc filter fw` on veth3
- `teardown_per_app_netem(...)` — removes HTB, restores flat netem

**New endpoints:**
- `POST /shape/per_app_marks` — Stage 1 + optional Stage 2 setup
- `DELETE /shape/per_app_marks` — teardown and restore flat netem

**Changed:**
- `POST /run` — sets per-request browser proxy contextvars and monkey-patches
  NetGent's Playwright launcher to route through the marked proxy

**New (no netgent fork required):**
- `_BROWSER_PROXY_HOST` / `_BROWSER_PROXY_PORT` contextvars
- `_ensure_netgent_playwright_proxy_patch()` — injects proxy + container
  stability flags into `NetGent._playwright_page` at runtime

### `shared/clients/netgent` — **no submodule change**

Per-app proxy routing is handled inside the substrate worker via a runtime
monkey-patch of `NetGent._playwright_page`. You do **not** need to fork or
modify the netgent submodule.

### `services/orchestration/app/engine/connectivity.py`

- `setup_per_app_marks()` — calls worker `POST /shape/per_app_marks`
- `teardown_per_app_marks()` — calls worker `DELETE /shape/per_app_marks`
- `run_workflow()` — accepts and forwards `browser_proxy_host` / `browser_proxy_port`

### `services/orchestration/app/engine/orchestration_manager.py`

- `_fire_workflows()` reads optional `spec["per_app_latency"]` dict
- Auto-assigns proxy ports (8889+) and alias IPs (172.16.1.5/.9/.13)
- Calls `setup_per_app_marks()` before workflows, `teardown_per_app_marks()` after
- Passes per-app proxy host/port to each `run_workflow()` call

## API usage

### Direct worker API

**Setup (Stage 1 + 2):**

```bash
curl -X POST http://localhost:8002/shape/per_app_marks \
  -H "Content-Type: application/json" \
  -d '{
    "app_marks": {
      "youtube": {"mark": 10, "proxy_port": 8889, "bind_ip": "172.16.1.5",  "latency_ms": 10},
      "twitch":  {"mark": 20, "proxy_port": 8890, "bind_ip": "172.16.1.9",  "latency_ms": 150},
      "tubi":    {"mark": 30, "proxy_port": 8891, "bind_ip": "172.16.1.13", "latency_ms": 40}
    },
    "default_latency_ms": 50,
    "netem_iface": "veth3",
    "netem_ns": "ns2"
  }'
```

**Run each app through its proxy:**

```bash
curl -X POST http://localhost:8002/run \
  -H "Content-Type: application/json" \
  -d '{
    "workflow": {...},
    "runtime": "browser",
    "browser_proxy_host": "172.16.1.5",
    "browser_proxy_port": 8889
  }'
```

**Teardown:**

```bash
curl -X DELETE 'http://localhost:8002/shape/per_app_marks?restore_latency_ms=50'
```

### Via orchestration (concurrent multi-app)

Add `per_app_latency` to the experiment spec:

```python
spec["per_app_latency"] = {
    "youtube": 10,
    "twitch": 150,
    "tubi": 40,
}
```

The orchestration manager handles setup, proxy routing, and teardown automatically
in `_fire_workflows()`.

## Verification commands

```bash
# Classification counters
docker exec substrate-worker ip netns exec ns2 iptables -t mangle -L PREROUTING -v -n

# Conntrack marks
docker exec substrate-worker ip netns exec ns2 cat /proc/net/nf_conntrack | grep 'mark='

# HTB + netem tree on veth3
docker exec substrate-worker ip netns exec ns2 tc qdisc show dev veth3
docker exec substrate-worker ip netns exec ns2 tc class show dev veth3
docker exec substrate-worker ip netns exec ns2 tc filter show dev veth3

# Per-lane packet counts
docker exec substrate-worker ip netns exec ns2 tc -s qdisc show dev veth3
```

## Teardown behavior

`DELETE /shape/per_app_marks`:

1. Removes HTB tree on `veth3`, restores flat `netem delay Xms`
2. Flushes ns2 PREROUTING mangle rules
3. Kills all per-app proxy processes
4. Does **not** remove alias IPs from `ns1:veth1` (harmless to leave)
