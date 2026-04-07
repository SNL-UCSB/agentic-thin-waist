import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

SUBSTRATE_API_URL = os.environ.get("SUBSTRATE_API_URL", "http://localhost:8002")


def apply_shaping(download_mbps, upload_mbps, latency_ms, qdisc):
    print(
        f"[*] Applying shaping: {download_mbps}Mbps down, {upload_mbps}Mbps up, {latency_ms}ms latency, {qdisc} qdisc..."
    )
    payload = {
        "upstream_iface": "veth4",
        "downstream_iface": "veth2",
        "download_mbps": download_mbps,
        "upload_mbps": upload_mbps,
        "latency_ms": latency_ms,
        "qdisc": qdisc,
        "buffer_packets": 1000,
    }

    req = urllib.request.Request(
        f"{SUBSTRATE_API_URL}/shape",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req) as response:
            result = json.loads(response.read().decode())
            print(f"[+] Shaping applied successfully. Status: {result['status']}")
    except urllib.error.URLError as e:
        print(f"[-] Failed to apply shaping: {e}")
        if hasattr(e, "read"):
            print(e.read().decode())
        sys.exit(1)


def apply_congestion(algorithm):
    print(f"[*] Applying congestion control algorithm: {algorithm}...")
    payload = {"algorithm": algorithm, "namespace": "ns1"}

    req = urllib.request.Request(
        f"{SUBSTRATE_API_URL}/congestion",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req) as response:
            result = json.loads(response.read().decode())
            print(
                f"[+] Congestion control applied successfully: {result['current_algorithm']}"
            )
    except urllib.error.URLError as e:
        print(f"[-] Failed to apply congestion control: {e}")
        if hasattr(e, "read"):
            print(e.read().decode())
        sys.exit(1)


def run_workflow(workflow_path, runtime):
    print(f"[*] Running {runtime} workflow: {workflow_path}...")
    env = os.environ.copy()

    # Resolve the workflow path relative to where the script is executed
    resolved_path = os.path.abspath(workflow_path)
    if not os.path.exists(resolved_path):
        print(f"[-] Error: Workflow file not found at {resolved_path}")
        sys.exit(1)

    env["NETGENT_WORKFLOW_PATH"] = resolved_path
    env["NETGENT_WORKFLOW_TYPE"] = runtime

    # Ensure uv runs the module correctly regardless of where the script is executed
    cmd = ["uv", "run", "--no-sync", "python", "-m", "netgent.src.main"]

    process = subprocess.Popen(
        cmd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd="/usr/src/app" if os.path.exists("/usr/src/app") else "/app",
    )

    stdout, stderr = process.communicate()

    if process.returncode != 0:
        print(f"[-] Workflow execution failed with exit code {process.returncode}")
        print("STDERR:")
        print(stderr)
        sys.exit(process.returncode)

    print("\n[+] Workflow Output:")
    print(stdout)


def main():
    parser = argparse.ArgumentParser(
        description="Run a NetGent workflow with specific network conditions"
    )
    parser.add_argument(
        "--workflow", required=True, help="Path to the workflow JSON file"
    )
    parser.add_argument(
        "--runtime",
        choices=["shell", "browser"],
        default="shell",
        help="Workflow runtime (shell or browser)",
    )
    parser.add_argument(
        "--download", type=float, default=100.0, help="Download bandwidth in Mbps"
    )
    parser.add_argument(
        "--upload", type=float, default=100.0, help="Upload bandwidth in Mbps"
    )
    parser.add_argument(
        "--latency", type=float, default=0.0, help="One-way latency in ms"
    )
    parser.add_argument(
        "--qdisc",
        type=str,
        default="pfifo",
        help="Queue discipline (e.g. pfifo, fq_codel)",
    )
    parser.add_argument(
        "--cca",
        type=str,
        default="cubic",
        help="TCP Congestion Control Algorithm (e.g., cubic, bbr, reno)",
    )

    args = parser.parse_args()

    apply_shaping(args.download, args.upload, args.latency, args.qdisc)
    apply_congestion(args.cca)
    run_workflow(args.workflow, args.runtime)


if __name__ == "__main__":
    main()
