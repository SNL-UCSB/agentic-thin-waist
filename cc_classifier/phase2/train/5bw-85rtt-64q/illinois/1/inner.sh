set -u
iperf3 -c "$MAHIMAHI_BASE" -p 5625 -R -t 20 -C illinois -J > "/home/jaber/agentic-thin-waist/cc_classifier/phase2/train/5bw-85rtt-64q/illinois/1/iperf_client.json" 2>/dev/null
true
