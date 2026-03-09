import os 
import subprocess
import threading

def run_sudo(cmd, password):
    subprocess.run(
        f"sudo -S sh -c '{cmd}'",
        shell=True,
        input=password + "\n",
        text=True,
        check=True,
    )

def shaping(download_mbps, upload_mbps, qdisc, password):
    """
    HTB-based shaping with AQM.
    Rates are in Mbps.

    Supported queuing disciplines:
      pfifo, bfifo, red, gred, pie, codel, fq_codel, fq, cake
    """
    run_sudo(
        f"tc qdisc del dev veth2 root 2>/dev/null || true && "
        f"tc qdisc add dev veth2 root handle 1: htb default 10 && "
        f"tc class add dev veth2 parent 1: classid 1:10 htb "
        f"rate {download_mbps}Mbit ceil {download_mbps}Mbit && "
        f"tc qdisc add dev veth2 parent 1:10 {qdisc}",
        password,
    )

    run_sudo(
        f"tc qdisc del dev veth4 root 2>/dev/null || true && "
        f"tc qdisc add dev veth4 root handle 1: htb default 10 && "
        f"tc class add dev veth4 parent 1: classid 1:10 htb "
        f"rate {upload_mbps}Mbit ceil {upload_mbps}Mbit && "
        f"tc qdisc add dev veth4 parent 1:10 {qdisc}",
        password,
    )

def latency(latency_ms, password):
    """
    Add base latency to veth6 using netem.
    latency_ms is in milliseconds.
    If latency_ms == 0, netem is removed.
    """
    if latency_ms == 0:
        run_sudo(
            "tc qdisc del dev veth6 root 2>/dev/null || true",
            password,
        )
    else:
        run_sudo(
            f"tc qdisc del dev veth6 root 2>/dev/null || true && "
            f"tc qdisc add dev veth6 root netem delay {latency_ms}ms",
            password,
        )

def run_client(cmd, password):
    subprocess.run(
        f"sudo -S ip netns exec ns1 {cmd}",
        shell=True,
        input=password + "\n",
        text=True,
        check=True,
    )

def capture(outputFileName, duration, flags, ip, vantagePoints, overwrite=False):
    upstreamIface = 'veth4'
    downstreamIface = 'veth2'
    outDir = '/home/jaber/captures/'
    upFileName = outDir + 'up_' + outputFileName
    downFileName = outDir + 'down_' + outputFileName

    UpCommand = f"tshark -i {upstreamIface} -a duration:{duration} -w {upFileName} {flags}"
    if ip not in ("all", None, ""):
        UpCommand += f' -f "host {ip}"'

    DownCommand = f"tshark -i {downstreamIface} -a duration:{duration} -w {downFileName} {flags}"
    if ip not in ("all", None, ""):
        DownCommand += f' -f "host {ip}"'

    if 'upstream' in vantagePoints:
        if not overwrite and os.path.exists(upFileName):
            print("\033[91m***** ERROR: Capture file already exists! Use overwrite option to proceed. *****\033[0m")
            return
        subprocess.Popen(UpCommand, shell=True)

    if 'downstream' in vantagePoints:
        if not overwrite and os.path.exists(downFileName):
            print("\033[91m***** ERROR: Capture file already exists! Use overwrite option to proceed. *****\033[0m")
            return
        subprocess.Popen(DownCommand, shell=True)




def ctp(bg_locatoin, ctpName, passwrod ):
    outgoing = (
        f"ip netns exec ns1 tcpreplay-edit -i veth1 "
        "--pnat=169.231.0.0/16:172.16.1.1,128.111.0.0/16:172.16.1.1 "
        f"{bg_locatoin}outgoing/{ctpName}"
    )

    incoming = (
        f"ip netns exec ns2 tcpreplay-edit -i veth3 "
        "--pnat=169.231.0.0/16:172.16.1.1,128.111.0.0/16:172.16.1.1 "
        f"{bg_locatoin}incoming/{ctpName}"
    )

    t1 = threading.Thread(target=run_sudo, args=(incoming, passwrod))
    t2 = threading.Thread(target=run_sudo, args=(outgoing, passwrod))

    t1.start()
    t2.start()