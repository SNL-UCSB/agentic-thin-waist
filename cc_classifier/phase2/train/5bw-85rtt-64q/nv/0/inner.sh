set -u
iperf3 -c "$MAHIMAHI_BASE" -p 5627 -R -t 20 -C nv -J > "/home/jaber/agentic-thin-waist/cc_classifier/phase2/train/5bw-85rtt-64q/nv/0/iperf_client.json" 2>/dev/null
true
