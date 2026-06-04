# Zoom A/V CTP Sweeps — Reference

Serial sweeps that run a Zoom audio+video experiment for each local CTP
(cross-traffic profile), one after another. Each sweep is fully isolated so it
can run in **parallel** with the others without clashing.

## Isolation model (why they don't clash)

Each parallel sweep needs its own copy of **all four** of these:

1. **Dedicated CTP list file** — the sweep "pins" the current CTP by overwriting
   this file with a single line, so two sweeps sharing one file would race.
2. **Dedicated orchestration container + host port** — one container reads
   exactly one `ORCH_LOCAL_CTP_LIST` path.
3. **Distinct Zoom meeting ID / passcode** — so the two browser participants do
   not land in the same meeting.
4. **Dedicated progress log** (`*_progress.jsonl`) — for resume/skip tracking.

Ephemeral workers are created per-experiment in their own network namespaces, so
network shaping (veth2/veth4, tc qdisc) never collides across sweeps.

> Note: the CTP list files normally show only **1 line** while a sweep is
> running — that's the currently *pinned* CTP. The full list is restored when the
> sweep exits (SIGINT/SIGTERM handler).

## Common parameters (all sweeps)

- Workflow: `run_zoom_av_workflow` (library), application `zoom`
- Media: WAV audio as microphone, MJPEG video as camera
- QDisc/AQM: `pfifo`, CC: `cubic`, trials: 1
- Capture duration: 60 s, display name: `Henry`
- CTP source: `local_list` (pointer mode `local_path`), pcaps under
  `/mnt/md0/haarika/download/<ctp>.pcap` (download + upload directions)

## The sweeps

| # | Script | Capacity | Latency | Meeting ID | Passcode | Orch port | CTP list | Progress log |
|---|--------|----------|---------|------------|----------|-----------|----------|--------------|
| A | `sweep_zoom_av_all_ctps.py` | 6 Mbps | 100 ms | **847 3047 0603** | **213841** | 8005 (`orchestration`) | `/mnt/md0/haarika/ctps.txt` (first 100) | `sweep_zoom_av_progress.jsonl` |
| 2 | `sweep_zoom_av_10ms.py` | 6 Mbps | 10 ms | **894 5053 0815** | **812664** | 8006 (`orchestration-10ms`) | `/mnt/md0/haarika/ctps_sweep_10ms.txt` | `sweep_zoom_av_10ms_progress.jsonl` |
| 3 | `sweep_zoom_av_100mbps_10ms.py` | 100 Mbps | 10 ms | **839 0820 5391** | **971104** | 8007 (`orchestration-100mbps-10ms`) | `/mnt/md0/haarika/ctps_sweep_100mbps_10ms.txt` (first 100) | `sweep_zoom_av_100mbps_10ms_progress.jsonl` |
| 4 | `sweep_zoom_av_100mbps_10ms_b.py` | 100 Mbps | 10 ms | **875 4831 5231** | **668868** | 8008 (`orchestration-100mbps-10ms-b`) | `/mnt/md0/haarika/ctps_sweep_100mbps_10ms_b.txt` (#101–995) | `sweep_zoom_av_100mbps_10ms_b_progress.jsonl` |
| 6m-p1 | `sweep_zoom_av_all_ctps.py` (env override) | 6 Mbps | 100 ms | **854 7566 9354** | **106487** | 8009 (`orchestration-6mbps-100ms-p1`) | `/mnt/md0/haarika/ctps_6mbps_100ms_p1.txt` (#101–250) | `sweep_6mbps_100ms_p1_progress.jsonl` |
| 6m-p2 | `sweep_zoom_av_all_ctps.py` (env override) | 6 Mbps | 100 ms | **890 4509 4771** | **968159** | 8015 (`orchestration-6mbps-100ms-p2`) | `/mnt/md0/haarika/ctps_6mbps_100ms_p2.txt` (#251–399) | `sweep_6mbps_100ms_p2_progress.jsonl` |
| 6m-p3 | `sweep_zoom_av_all_ctps.py` (env override) | 6 Mbps | 100 ms | **817 3437 7969** | **169100** | 8011 (`orchestration-6mbps-100ms-p3`) | `/mnt/md0/haarika/ctps_6mbps_100ms_p3.txt` (#400–549) | `sweep_6mbps_100ms_p3_progress.jsonl` |
| 6m-p4 | `sweep_zoom_av_all_ctps.py` (env override) | 6 Mbps | 100 ms | **836 1647 3548** | **416458** | 8012 (`orchestration-6mbps-100ms-p4`) | `/mnt/md0/haarika/ctps_6mbps_100ms_p4.txt` (#550–698) | `sweep_6mbps_100ms_p4_progress.jsonl` |
| 6m-p5 | `sweep_zoom_av_all_ctps.py` (env override) | 6 Mbps | 100 ms | **885 0323 9092** | **883135** | 8013 (`orchestration-6mbps-100ms-p5`) | `/mnt/md0/haarika/ctps_6mbps_100ms_p5.txt` (#699–847) | `sweep_6mbps_100ms_p5_progress.jsonl` |
| 6m-p6 | `sweep_zoom_av_all_ctps.py` (env override) | 6 Mbps | 100 ms | **828 2854 0858** | **091853** | 8014 (`orchestration-6mbps-100ms-p6`) | `/mnt/md0/haarika/ctps_6mbps_100ms_p6.txt` (#848–995) | `sweep_6mbps_100ms_p6_progress.jsonl` |

### Partitioning of the 995 CTPs

- Sweeps 1–3 are typically launched with `SWEEP_LIMIT=100` (first 100 CTPs in
  sorted order, skipping any already in their progress log).
- Sweep 4 ("partition B") covers the **remaining 895 CTPs (#101–995)** with no
  limit, so together 3 + 4 cover the full 100 Mbps/10 ms set with no duplicates.

## Docker containers (compose profiles)

```bash
# default orchestration (sweep A / 6Mbps-100ms) is part of the base stack
docker compose up -d orchestration

# extra parallel instances are gated behind profiles:
docker compose --profile sweep10ms          up -d orchestration-10ms            # port 8006
docker compose --profile sweep100mbps10ms   up -d orchestration-100mbps-10ms    # port 8007
docker compose --profile sweep100mbps10msb  up -d orchestration-100mbps-10ms-b  # port 8008
```

## Running a sweep

Each script targets its own orchestration container by default (`ORCH_URL`).
Override env vars as needed.

```bash
cd /home/haarika/imp_files/thinwaist/agentic-fixed-may28th

# Sweep A (6 Mbps / 100 ms), first 100 CTPs
SWEEP_LIMIT=100 ORCH_URL=http://localhost:8005 \
  nohup python3 services/orchestration/scripts/sweep_zoom_av_all_ctps.py \
  > sweep_6mbps_100ms.log 2>&1 &

# Sweep 2 (6 Mbps / 10 ms), first 100 CTPs
SWEEP_LIMIT=100 ORCH_URL=http://localhost:8006 \
  nohup python3 services/orchestration/scripts/sweep_zoom_av_10ms.py \
  > sweep_10ms.log 2>&1 &

# Sweep 3 (100 Mbps / 10 ms, partition A), first 100 CTPs
SWEEP_LIMIT=100 ORCH_URL=http://localhost:8007 \
  nohup python3 services/orchestration/scripts/sweep_zoom_av_100mbps_10ms.py \
  > sweep_100mbps_10ms.log 2>&1 &

# Sweep 4 (100 Mbps / 10 ms, partition B), all remaining CTPs (no limit)
ORCH_URL=http://localhost:8008 \
  nohup python3 services/orchestration/scripts/sweep_zoom_av_100mbps_10ms_b.py \
  > sweep_100mbps_10ms_b.log 2>&1 &
```

### Key env vars per script

- `ZOOM_MEETING_ID`, `ZOOM_PASSCODE` — Zoom meeting (defaults baked in, see table)
- `ZOOM_CAPACITY_MBPS`, `ZOOM_LATENCY_MS`, `ZOOM_QDISC`
- `CTP_LIST_FILE` — the dedicated list file (default per script)
- `SWEEP_LOG` — the dedicated progress log (default per script)
- `SWEEP_LIMIT` — max CTPs this run (0 / unset = all)
- `ORCH_URL` — orchestration endpoint (default per script)

## Monitoring

```bash
# completed count per sweep
wc -l sweep_zoom_av_progress.jsonl \
      sweep_zoom_av_10ms_progress.jsonl \
      sweep_zoom_av_100mbps_10ms_progress.jsonl \
      sweep_zoom_av_100mbps_10ms_b_progress.jsonl

# per-CTP status + elapsed for one sweep
cat sweep_zoom_av_100mbps_10ms_b_progress.jsonl | python3 -c "
import sys, json
for line in sys.stdin:
    r = json.loads(line)
    print(r['ctp_name'], '-', r['status'], '-', r['elapsed_s'], 's')
"

# which CTP each sweep is currently on (the pinned line)
head -1 /mnt/md0/haarika/ctps.txt
head -1 /mnt/md0/haarika/ctps_sweep_10ms.txt
head -1 /mnt/md0/haarika/ctps_sweep_100mbps_10ms.txt
head -1 /mnt/md0/haarika/ctps_sweep_100mbps_10ms_b.txt
```

## Pcap analysis — separating application vs cross-traffic

Captured pcaps contain **both** the Zoom application traffic and the replayed CTP
cross-traffic. They are split by IP (by design — the substrate pnat's the
replayed traffic to a distinct address):

- `ip.addr == 172.16.1.1`  → **Zoom application** traffic (audio + video)
- `ip.addr == 172.16.1.20` → **CTP background** cross-traffic

```bash
# example: split a downloaded pcap
tshark -r exp.pcap -Y "ip.addr==172.16.1.1"  | wc -l   # app packets
tshark -r exp.pcap -Y "ip.addr==172.16.1.20" | wc -l   # ctp packets

# uplink (participant -> Zoom) vs downlink, app only
tshark -r exp.pcap -Y "ip.src==172.16.1.1 && udp.length>200" | wc -l   # outgoing media
tshark -r exp.pcap -Y "ip.dst==172.16.1.1 && udp.length>200" | wc -l   # incoming media
```

Zoom media rides inside **QUIC/UDP** (encrypted), so there are no plain RTP
packets; large UDP/QUIC frames (esp. 1200+ bytes) are video, smaller frames are
audio. On heavily congested 6 Mbps profiles the participant's *uplink* can be
starved by the CTP traffic (cross-traffic alone may exceed the link rate).

## 6 Mbps / 100ms parallel partitions — start / stop

```bash
cd /home/haarika/imp_files/thinwaist/agentic-fixed-may28th

# Start all 6 containers
for p in 1 2 3 4 5 6; do
  docker compose --profile sweep6m100ms_p${p} up -d orchestration-6mbps-100ms-p${p}
done

# Launch all 6 sweeps (reuses sweep_zoom_av_all_ctps.py via env vars)
declare -A MEETINGS=([1]="85475669354:106487:8009" [2]="89045094771:968159:8015" \
  [3]="81734377969:169100:8011" [4]="83616473548:416458:8012" \
  [5]="88503239092:883135:8013" [6]="82828540858:091853:8014")
for p in 1 2 3 4 5 6; do
  IFS=: read -r mid pc port <<< "${MEETINGS[$p]}"
  ZOOM_MEETING_ID=$mid ZOOM_PASSCODE=$pc ZOOM_CAPACITY_MBPS=6 ZOOM_LATENCY_MS=100 ZOOM_QDISC=pfifo \
    CTP_LIST_FILE=/mnt/md0/haarika/ctps_6mbps_100ms_p${p}.txt \
    SWEEP_LOG=./sweep_6mbps_100ms_p${p}_progress.jsonl \
    ORCH_URL=http://localhost:${port} \
    nohup python3 services/orchestration/scripts/sweep_zoom_av_all_ctps.py \
    > sweep_6mbps_100ms_p${p}.log 2>&1 &
  echo "p${p} PID: $!"
done

# Stop all 6 sweeps
pkill -f "sweep_zoom_av_all_ctps.py"  # stops ALL instances including sweep A

# Monitor progress
for p in 1 2 3 4 5 6; do
  echo "p${p}: $(wc -l < sweep_6mbps_100ms_p${p}_progress.jsonl 2>/dev/null || echo 0) done  pinned=$(head -1 /mnt/md0/haarika/ctps_6mbps_100ms_p${p}.txt)"
done
```

## Stopping a sweep

```bash
pkill -f sweep_zoom_av_100mbps_10ms_b.py                 # stop the sweep loop
docker compose --profile sweep100mbps10msb stop orchestration-100mbps-10ms-b
```
