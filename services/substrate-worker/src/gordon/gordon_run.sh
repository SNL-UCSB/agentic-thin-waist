#!/usr/bin/env bash
# Gordon prober runner — Exp8 / Fig 13 (per-CCA CWND vote).
#
# Vendored from github.com/NUS-SNL/Gordon ("The Great Internet TCP CC Census",
# SIGMETRICS 2019), adapted to run inside the ATW substrate worker's shaped
# namespace (ns1) instead of a standalone mahimahi mm-delay shell:
#   * RTT / bandwidth / queue are applied by ATW's tc/netem on the ns1 veth
#     (so we do NOT launch `mm-delay`; the original launch.sh did).
#   * The NFQUEUE rule matches packets destined to the ns1 client IP (veth1 =
#     172.16.1.1) rather than the mm-delay ingress IP 100.64.0.2.
#   * Requires CAP_NET_ADMIN (NFQUEUE + iptables) — satisfied because the
#     substrate worker runs privileged with NET_ADMIN/SYS_ADMIN.
#
# Usage (run from inside ns1, e.g. `ip netns exec ns1 gordon_run.sh ...`):
#   gordon_run.sh <target_url> [trials] [client_ip]
#
# Produces $GORDON_WORKDIR/Data/windows.csv (CWND-vs-RTT) and prints the
# classified CCA on stdout.
set -u

TARGET="${1:?usage: gordon_run.sh <target_url> [trials] [client_ip]}"
TRIALS="${2:-40}"
CLIENT_IP="${3:-172.16.1.1}"          # ns1 veth1
QUEUE_NUM="${GORDON_QUEUE_NUM:-0}"

GORDON_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKDIR="${GORDON_WORKDIR:-$GORDON_DIR}"
PROBER="${GORDON_PROBER:-/usr/local/bin/gordon-prober}"
export GORDON_WINDOWS_CSV="${WORKDIR}/Data/windows.csv"
BUFF_CSV="${WORKDIR}/Data/buff.csv"

mkdir -p "${WORKDIR}/Data"
echo "0 0 0" > "$GORDON_WINDOWS_CSV"
echo "0 0"   > "$BUFF_CSV"

command -v "$PROBER" >/dev/null 2>&1 || PROBER="${GORDON_DIR}/gordon-prober"
[ -x "$PROBER" ] || { echo "gordon-prober not found/executable ($PROBER)" >&2; exit 3; }

echo "== Gordon: target=$TARGET trials=$TRIALS client=$CLIENT_IP queue=$QUEUE_NUM =="
for i in $(seq 1 "$TRIALS"); do
    # intercept the established flow's inbound packets into NFQUEUE
    iptables -I INPUT -p tcp -d "$CLIENT_IP" -m state --state ESTABLISHED \
        -j NFQUEUE --queue-num "$QUEUE_NUM" 2>/dev/null
    # prober args: <url> <first_delay_us> <second_delay_us> <switch_point>
    "$PROBER" "$TARGET" 8000 5000 1000 >> "$BUFF_CSV" 2>/dev/null
    iptables -D INPUT -p tcp -d "$CLIENT_IP" -m state --state ESTABLISHED \
        -j NFQUEUE --queue-num "$QUEUE_NUM" 2>/dev/null
    rm -f index* 2>/dev/null
done

echo "== windows.csv (${GORDON_WINDOWS_CSV}) =="
wc -l "$GORDON_WINDOWS_CSV"

# classify the collected CWND-vs-RTT trace -> the Fig-13 per-CCA vote
python3 "${GORDON_DIR}/gordon_classify.py" "$GORDON_WINDOWS_CSV"
