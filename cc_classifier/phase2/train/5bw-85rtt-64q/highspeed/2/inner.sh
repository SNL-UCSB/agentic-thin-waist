set -u
iperf3 -c "$MAHIMAHI_BASE" -p 5617 -R -t 20 -C highspeed -J > "/home/jaber/agentic-thin-waist/cc_classifier/phase2/train/5bw-85rtt-64q/highspeed/2/iperf_client.json" 2>/dev/null
true
