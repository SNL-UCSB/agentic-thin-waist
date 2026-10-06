set -u
timeout 15 wget -O /dev/null --header="Cache-Control: no-cache"   "http://$MAHIMAHI_BASE:5501/bigfile.bin" 2>/dev/null
true
