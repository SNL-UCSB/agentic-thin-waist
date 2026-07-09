set -u
iface=$(ip -o link show | awk -F': ' '$2!="lo"{print $2; exit}')
dumpcap -i "$iface" -f "tcp port 8091" -w "/home/jaber/agentic-thin-waist/ai_cc/results/5bw-85rtt-64q/cubic/0/capture.pcap" -q &
DP=$!
sleep 0.4
timeout 60 wget -O /dev/null --header="Cache-Control: no-cache"     "http://$MAHIMAHI_BASE:8091/bigfile.bin" 2> "/home/jaber/agentic-thin-waist/ai_cc/results/5bw-85rtt-64q/cubic/0/wget.log"
sleep 0.3
kill $DP 2>/dev/null
wait $DP 2>/dev/null
true
