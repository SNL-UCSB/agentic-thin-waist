# Network Shaping API Documentation

---

## Runtime profile selection

The substrate worker now supports two runtime profiles selected by
`CONNECTIVITY_BACKEND` at container startup:

- `local_docker` (default): runs `setup_local.sh` and `substrate.main_local`
  (pre-fix local baseline behavior).
- `aws`: runs `setup_aws.sh` and `substrate.main_aws` (current AWS-compatible behavior).

---

## POST `/shape`

**What it does:**
Applies traffic shaping to the network interfaces — sets bandwidth limits and latency.

**Takes:**
```json
{
  "upstream_iface": "veth4",
  "downstream_iface": "veth2",
  "download_mbps": 10.0,
  "upload_mbps": 5.0,
  "latency_ms": 20,
  "qdisc": "pfifo",
  "buffer_packets": 1000
}
```

**Returns:**
```json
{
  "status": "shaped",
  "bottleneck_state": {
    "download_mbps": 10.0,
    "upload_mbps": 5.0,
    "latency_ms": 20,
    "qdisc": "pfifo",
    "verified": true,
    "buffer_packets": 1000,
    "loss_rate_percent": 0.0,
    "verification_log": ["upload: measured=....", "PASS: upload", "PASS: download"]
  },
  "applied_commands": ["tc qdisc add dev veth2 root handle 1: htb ..."]
}
```

---

## GET `/state`

**What it does:**
Returns the currently active traffic shaping configuration.

**Takes:** Nothing

**Returns:**
```json
{
  "status": "ok",
  "bottleneck_state": {
    "download_mbps": 10.0,
    "upload_mbps": 5.0,
    "latency_ms": 20,
    "qdisc": "pfifo",
    "verified": true,
    "buffer_packets": 1000,
    "loss_rate_percent": 0.0,
    "verification_log": ["upload: measured=....", "PASS: upload", "PASS: download"]
  }
}
```

If no shaping has been applied yet, returns `"status": "no_state"` with `"bottleneck_state": null`.

---

## GET `/health`

**What it does:**
Reports whether the service and all its dependencies are available and working.

**Takes:** Nothing

**Returns:**
```json
{
  "status": "ok",
  "root_privileges": true,
  "tc_available": true,
  "tshark_available": true,
  "tcpreplay_available": true,
  "qdisc_support": true,
  "interfaces": ["veth1", "veth2", "veth4"],
  "timestamp": "2024-01-01T00:00:00"
}
```

`status` is `"ok"` only if all checks pass, otherwise `"degraded"`.

---

## POST `/capture`

**What it does:**
Starts a live packet capture on a given interface and saves it as a `.pcap` file.

**Takes:**
```json
{
  "interface": "veth2",
  "capture_filter": "tcp port 443",
  "filename": "my_capture",
  "duration_seconds": 30
}
```

`capture_filter` is optional (captures all traffic if omitted). `duration_seconds` is optional (runs until manually stopped if omitted).

**Returns:**
```json
{
  "capture_id": "d290f1ee-6c54-4b01-90e6-d701748f0851",
  "status": "started",
  "pcap_path": "/home/netreplica/config/captures/my_capture.pcap",
  "interface": "veth2",
  "capture_filter": "tcp port 443"
}
```

Use the returned `capture_id` to check status or stop the capture.

---

## GET `/capture/{capture_id}`

**What it does:**
Returns the current status of a running or completed capture session.

**Takes:** `capture_id` as a URL parameter

**Returns:**
```json
{
  "capture_id": "d290f1ee-6c54-4b01-90e6-d701748f0851",
  "status": "running",
  "pcap_path": "/home/netreplica/config/captures/my_capture.pcap",
  "interface": "veth2",
  "capture_filter": "tcp port 443",
  "start_time": "2024-01-01T00:00:00",
  "exit_code": null
}
```

`status` is either `"running"` or `"finished"`. Returns 404 if the `capture_id` is not found.

---

## DELETE `/capture/{capture_id}`

**What it does:**
Stops a running capture. The `.pcap` file on disk is kept.

**Takes:** `capture_id` as a URL parameter

**Returns:**
```json
{
  "capture_id": "d290f1ee-6c54-4b01-90e6-d701748f0851",
  "status": "stopped"
}
```

Returns 404 if the `capture_id` is not found.

---

## POST `/replay`

**What it does:**
Replays a pre-recorded `.pcap` file through a network interface.

**Takes:**
```json
{
  "ctp_file": "youtube_10mbps",
  "interface": "veth1",
  "rate": "10",
  "loop": false,
  "duration_seconds": 60,
  "pnat": "169.231.0.0/16:172.16.1.1"
}
```

`rate`, `loop`, `duration_seconds`, and `pnat` are all optional. `pnat` rewrites IP addresses in the replayed packets to match the current network topology.

**Returns:**
```json
{
  "replay_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "status": "started",
  "ctp_file": "youtube_10mbps",
  "interface": "veth1",
  "rate": "10"
}
```

Returns 400 if the `ctp_file` does not exist. Use the returned `replay_id` to check status or stop the replay.

---

## GET `/replay/{replay_id}`

**What it does:**
Returns the current status of a running or completed replay session.

**Takes:** `replay_id` as a URL parameter

**Returns:**
```json
{
  "replay_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "status": "running",
  "ctp_file": "youtube_10mbps",
  "interface": "veth1",
  "rate": "10",
  "pnat": null,
  "start_time": "2024-01-01T00:00:00"
}
```

`status` is either `"running"` or `"finished"`. Returns 404 if the `replay_id` is not found.

---

## DELETE `/replay/{replay_id}`

**What it does:**
Stops a running replay session.

**Takes:** `replay_id` as a URL parameter

**Returns:**
```json
{
  "replay_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "status": "stopped"
}
```

Returns 404 if the `replay_id` is not found.