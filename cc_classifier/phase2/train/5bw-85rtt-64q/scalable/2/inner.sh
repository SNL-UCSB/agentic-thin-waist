set -u
iperf3 -c "$MAHIMAHI_BASE" -p 5632 -R -t 20 -C scalable -J > "/home/jaber/agentic-thin-waist/cc_classifier/phase2/train/5bw-85rtt-64q/scalable/2/iperf_client.json" 2>/dev/null
true
