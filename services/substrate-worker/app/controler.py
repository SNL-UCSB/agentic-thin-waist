import os
import subprocess
import threading


def run_cmd(cmd):
    subprocess.run(cmd, shell=True, check=True)


def shaping(download_mbps, upload_mbps, qdisc, r2q=100):
    """
    HTB-based shaping with AQM.
    Rates are in Mbps.

    Supported queuing disciplines:
      pfifo, bfifo, red, gred, pie, codel, fq_codel, fq, cake
    """
    run_cmd(
        f"tc qdisc del dev veth2 root 2>/dev/null || true && "
        f"tc qdisc add dev veth2 root handle 1: htb default 10 r2q {r2q} && "
        f"tc class add dev veth2 parent 1: classid 1:10 htb "
        f"rate {download_mbps}Mbit ceil {download_mbps}Mbit && "
        f"tc qdisc add dev veth2 parent 1:10 {qdisc}"
    )

    run_cmd(
        f"tc qdisc del dev veth4 root 2>/dev/null || true && "
        f"tc qdisc add dev veth4 root handle 1: htb default 10 r2q {r2q} && "
        f"tc class add dev veth4 parent 1: classid 1:10 htb "
        f"rate {upload_mbps}Mbit ceil {upload_mbps}Mbit && "
        f"tc qdisc add dev veth4 parent 1:10 {qdisc}"
    )

def latency(latency_ms):
    if latency_ms == 0:
        run_cmd("tc qdisc del dev veth6 root 2>/dev/null || true")
    else:
        run_cmd(
            f"tc qdisc del dev veth6 root 2>/dev/null || true && "
            f"tc qdisc add dev veth6 root netem delay {latency_ms}ms"
        )


def run_client(cmd):
    run_cmd(f"ip netns exec ns1 {cmd}")


def capture(
    outputFileName,
    duration,
    flags="",
    ip=None,
    vantagePoints=("upstream", "downstream"),
    overwrite=False,
):
    """
    Capture traffic inside the Docker container.

    Captures are stored in ./captures relative to the current
    working directory inside the container.

    Files created:
        captures/up_<outputFileName>
        captures/down_<outputFileName>

    Parameters
    ----------
    outputFileName : str
        Base filename for the capture.

    duration : int
        Capture duration in seconds.

    flags : str
        Extra tshark flags (e.g., "-s 96").

    ip : str or None
        If set, applies BPF filter: host <ip>.

    vantagePoints : iterable
        Any of {"upstream", "downstream"}.

    overwrite : bool
        If False, aborts if file already exists.
    """

    upstreamIface = "veth4"
    downstreamIface = "veth2"

    outDir = os.path.join(os.getcwd(), "captures")
    os.makedirs(outDir, exist_ok=True)

    upFileName = os.path.join(outDir, "up_" + outputFileName)
    downFileName = os.path.join(outDir, "down_" + outputFileName)

    UpCommand = f"tshark -i {upstreamIface} -a duration:{duration} -w {upFileName} {flags}"
    DownCommand = f"tshark -i {downstreamIface} -a duration:{duration} -w {downFileName} {flags}"

    if ip not in (None, "", "all"):
        UpCommand += f' -f "host {ip}"'
        DownCommand += f' -f "host {ip}"'

    if "upstream" in vantagePoints:
        if not overwrite and os.path.exists(upFileName):
            print("\033[91m***** ERROR: Upstream capture exists! *****\033[0m")
        else:
            subprocess.Popen(UpCommand, shell=True)

    if "downstream" in vantagePoints:
        if not overwrite and os.path.exists(downFileName):
            print("\033[91m***** ERROR: Downstream capture exists! *****\033[0m")
        else:
            subprocess.Popen(DownCommand, shell=True)


def ctp(bg_location, ctpName):
    outgoing = (
        f"ip netns exec ns1 tcpreplay-edit -i veth1 "
        "--pnat=169.231.0.0/16:172.16.1.1,128.111.0.0/16:172.16.1.1 "
        f"{bg_location}outgoing/{ctpName}"
    )

    incoming = (
        f"ip netns exec ns2 tcpreplay-edit -i veth3 "
        "--pnat=169.231.0.0/16:172.16.1.1,128.111.0.0/16:172.16.1.1 "
        f"{bg_location}incoming/{ctpName}"
    )

    t1 = threading.Thread(target=run_cmd, args=(incoming,))
    t2 = threading.Thread(target=run_cmd, args=(outgoing,))

    t1.start()
    t2.start()