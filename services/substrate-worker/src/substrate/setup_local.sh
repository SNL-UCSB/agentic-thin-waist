#!/bin/bash
set -e

NS1="ns1"
NS2="ns2"
NUM_QUEUE=4
BR="netrepBr"
RUNTIME_DIR="/var/run/substrate"

# Enable forwarding
sysctl -w net.ipv4.ip_forward=1

########################
# Downstream namespace #
########################

ip netns add $NS1

ip link add veth1 type veth peer name veth2
ip addr add 172.16.1.2/30 dev veth2
ip link set veth2 up

ip link set veth1 netns $NS1
ip netns exec $NS1 ip addr add 172.16.1.1/30 dev veth1
ip netns exec $NS1 ip link set lo up
ip netns exec $NS1 ip link set veth1 up
ip netns exec $NS1 ip route add default via 172.16.1.2

iptables -t nat -A POSTROUTING -o eth0 -j MASQUERADE
ip netns exec $NS1 sh -c 'echo "nameserver 8.8.8.8" > /etc/resolv.conf'

######################
# Upstream namespace #
######################

ip netns add $NS2

ip link add veth3 type veth peer name veth4
ip link add veth5 type veth peer name veth6

ip addr add 172.16.2.2/30 dev veth4
ip addr add 172.16.3.2/30 dev veth6
ip link set veth4 up
ip link set veth6 up

ip link set veth3 netns $NS2
ip link set veth5 netns $NS2

ip netns exec $NS2 ip addr add 172.16.2.1/30 dev veth3
ip netns exec $NS2 ip addr add 172.16.3.1/30 dev veth5
ip netns exec $NS2 ip link set lo up
ip netns exec $NS2 ip link set veth3 up
ip netns exec $NS2 ip link set veth5 up
ip netns exec $NS2 ip route add default via 172.16.3.2

iptables -t nat -A POSTROUTING -o eth0 -j MASQUERADE
ip netns exec $NS2 iptables -t nat -A POSTROUTING -o veth5 -j MASQUERADE
ip netns exec $NS2 sh -c 'echo "nameserver 8.8.8.8" > /etc/resolv.conf'

########################
# Routing adjustments  #
########################

ip netns exec $NS1 ip route change default dev veth1
ip netns exec $NS1 ip route change default via 172.16.3.1 dev veth1

ip netns exec $NS2 ip route add 172.16.1.0/30 dev veth3
ip netns exec $NS2 ip route change default via 172.16.3.2 dev veth5

################
# Bridge setup #
################

ip link add $BR type bridge
ip link set dev veth2 master $BR
ip link set dev veth4 master $BR
ip link set dev $BR up

########################
# Namespace anchors    #
########################

mkdir -p "$RUNTIME_DIR"

ip netns exec $NS1 sleep infinity &
echo $! > "$RUNTIME_DIR/${NS1}.pid"

ip netns exec $NS2 sleep infinity &
echo $! > "$RUNTIME_DIR/${NS2}.pid"

########################################
# Preload CCAnalyzer congestion-control
# modules so experiments can ask for
# any of the 15 algorithms without
# round-tripping a modprobe per /run.
# Missing modules (e.g. on Docker
# Desktop's LinuxKit kernel) are
# logged but non-fatal — the worker
# still exposes whatever the kernel
# already has built in (cubic, reno).
########################################
echo
echo "=== Loading CCAnalyzer congestion-control modules ==="
LOADED_CCAS=()
SKIPPED_CCAS=()
for mod in tcp_bbr tcp_bic tcp_cdg tcp_cubic tcp_highspeed \
           tcp_htcp tcp_hybla tcp_illinois tcp_nv \
           tcp_scalable tcp_vegas tcp_veno tcp_westwood tcp_yeah; do
  if modprobe "$mod" 2>/dev/null; then
    echo "  + loaded $mod"
    LOADED_CCAS+=("${mod#tcp_}")
  else
    echo "  - skipped $mod (module not available in this kernel)"
    SKIPPED_CCAS+=("${mod#tcp_}")
  fi
done
# reno is always available as the kernel built-in fallback.
LOADED_CCAS+=("reno")

CCA_AVAILABLE="$(sysctl -n net.ipv4.tcp_available_congestion_control 2>/dev/null)"
echo
echo "  -> tcp_available_congestion_control = ${CCA_AVAILABLE}"
echo "  -> loaded ${#LOADED_CCAS[@]} of 15 CCAnalyzer CCAs"
if [ ${#SKIPPED_CCAS[@]} -gt 0 ]; then
  cat <<EOF

  WARNING: ${#SKIPPED_CCAS[@]} CCAs are not loadable on this host kernel
  ($(uname -r)): ${SKIPPED_CCAS[*]}.

  This is expected on Docker Desktop's LinuxKit kernel — it ships only
  cubic + reno. To use the full CCAnalyzer set, run the substrate worker
  on a real Linux host with linux-modules-extra-\$(uname -r) installed
  and /lib/modules bind-mounted (already wired up in docker-compose.yml).
  See services/substrate-worker/README.md for details.
EOF
fi

echo
echo "======================================"
echo " netreplica solo setup completed successfully "
echo "======================================"
echo
