set -u
iperf3 -c "$MAHIMAHI_BASE" -p 5631 -R -t 20 -C scalable -J > "/home/jaber/agentic-thin-waist/cc_classifier/phase2/train/5bw-85rtt-64q/scalable/1/iperf_client.json" 2>/dev/null
true
