from fastapi import FastAPI
from pydantic import BaseModel
import uuid
import threading
import subprocess
import os

app = FastAPI()

EXPERIMENTS = {}

def run_cmd(cmd):
    subprocess.run(cmd, shell=True, check=True)

def shaping(download, upload, qdisc):
    run_cmd(f"tc qdisc del dev veth2 root 2>/dev/null || true")
    run_cmd(f"tc qdisc add dev veth2 root handle 1: htb default 10")
    run_cmd(f"tc class add dev veth2 parent 1: classid 1:10 htb rate {download}Mbit ceil {download}Mbit")
    run_cmd(f"tc qdisc add dev veth2 parent 1:10 {qdisc}")

    run_cmd(f"tc qdisc del dev veth4 root 2>/dev/null || true")
    run_cmd(f"tc qdisc add dev veth4 root handle 1: htb default 10")
    run_cmd(f"tc class add dev veth4 parent 1: classid 1:10 htb rate {upload}Mbit ceil {upload}Mbit")
    run_cmd(f"tc qdisc add dev veth4 parent 1:10 {qdisc}")

def latency(ms):
    if ms == 0:
        run_cmd("tc qdisc del dev veth6 root 2>/dev/null || true")
    else:
        run_cmd(f"tc qdisc add dev veth6 root netem delay {ms}ms")

def capture(exp_id, duration):
    os.makedirs("captures", exist_ok=True)

    subprocess.Popen(
        f"tshark -i veth4 -a duration:{duration} -w captures/up_{exp_id}.pcap",
        shell=True
    )

    subprocess.Popen(
        f"tshark -i veth2 -a duration:{duration} -w captures/down_{exp_id}.pcap",
        shell=True
    )

def replay(ctp):
    incoming = f"ip netns exec ns2 tcpreplay-edit -i veth3 ctp/incoming/{ctp}"
    outgoing = f"ip netns exec ns1 tcpreplay-edit -i veth1 ctp/outgoing/{ctp}"

    t1 = threading.Thread(target=run_cmd, args=(incoming,))
    t2 = threading.Thread(target=run_cmd, args=(outgoing,))
    t1.start()
    t2.start()

class ExperimentRequest(BaseModel):
    download_mbps: int
    upload_mbps: int
    latency_ms: int
    qdisc: str
    ctp_file: str
    duration: int
    capture: bool = True

def run_experiment(exp_id, cfg):

    shaping(cfg.download_mbps, cfg.upload_mbps, cfg.qdisc)
    latency(cfg.latency_ms)

    if cfg.capture:
        capture(exp_id, cfg.duration)

    replay(cfg.ctp_file)

    EXPERIMENTS[exp_id]["status"] = "finished"

@app.post("/experiment/run")
def run(cfg: ExperimentRequest):

    exp_id = str(uuid.uuid4())

    EXPERIMENTS[exp_id] = {
        "status": "running",
        "config": cfg.dict()
    }

    t = threading.Thread(target=run_experiment, args=(exp_id, cfg))
    t.start()

    return {"experiment_id": exp_id}

@app.get("/experiment/{exp_id}")
def status(exp_id: str):

    return EXPERIMENTS.get(exp_id, {"error": "not found"})

@app.get("/health")
def health():
    return {"status": "ok"}