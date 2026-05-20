#!/bin/bash
set -e

# Profile: AWS baseline (current AWS-compatible behavior).

# SNAT must match the host's real uplink. Docker often uses eth0; EC2 frequently
# uses ens5, enX0, etc. Wrong interface => MASQUERADE never fires => no return
# path for ns1/ns2 traffic => ping -c N exits 1 (no replies).
detect_wan_if() {
  local iface=""
  iface="$(ip -4 route get 1.1.1.1 2>/dev/null | awk '/dev/ {for (i=1;i<=NF;i++) if ($i=="dev") {print $(i+1); exit}}')"
  if [ -z "$iface" ]; then
    iface="$(ip -4 route show default 2>/dev/null | awk '{print $5; exit}')"
  fi
  echo "$iface"
}

WAN_IF="${SUBSTRATE_WAN_IF:-}"
if [ -z "$WAN_IF" ]; then
  # On some boots routing can appear a few seconds after cloud-init starts.
  for _ in 1 2 3 4 5; do
    WAN_IF="$(detect_wan_if)"
    if [ -n "$WAN_IF" ] && [ -d "/sys/class/net/$WAN_IF" ]; then
      break
    fi
    sleep 2
  done
fi
if [ -z "$WAN_IF" ] || [ ! -d "/sys/class/net/$WAN_IF" ]; then
  WAN_IF="eth0"
fi
echo "substrate setup: SNAT/MASQUERADE on ${WAN_IF} (set SUBSTRATE_WAN_IF to override)"

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

# ns1 traffic is SNATed in ns2 onto 172.16.3.0/30 before entering root netns,
# so WAN MASQUERADE must include that transit subnet as well.
iptables -t nat -A POSTROUTING -s 172.16.1.0/30 -o "$WAN_IF" -j MASQUERADE
iptables -t nat -A POSTROUTING -s 172.16.3.0/30 -o "$WAN_IF" -j MASQUERADE
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
# ns2 is the transit router between ns1 and WAN; forwarding must be enabled
# in this namespace (root sysctl does not apply inside ns2).
ip netns exec $NS2 sysctl -w net.ipv4.ip_forward=1
ip netns exec $NS2 ip route add default via 172.16.3.2

iptables -t nat -A POSTROUTING -s 172.16.2.0/30 -o "$WAN_IF" -j MASQUERADE
ip netns exec $NS2 iptables -t nat -A POSTROUTING -o veth5 -j MASQUERADE
ip netns exec $NS2 sh -c 'echo "nameserver 8.8.8.8" > /etc/resolv.conf'

########################
# Routing adjustments  #
########################

# Keep ns1 default gateway on its directly connected peer (veth2 in root).
# Routing ns1 default to 172.16.3.1 is invalid from ns1 and causes total packet loss.
ip netns exec $NS1 ip route replace default via 172.16.1.2 dev veth1

ip netns exec $NS2 ip route add 172.16.1.0/30 dev veth3
ip netns exec $NS2 ip route change default via 172.16.3.2 dev veth5

# Some hardened images default FORWARD policy to DROP. Make namespace <-> WAN
# forwarding explicit so ICMP and workflow traffic can return correctly.
iptables -A FORWARD -i "$WAN_IF" -o veth6 -m state --state RELATED,ESTABLISHED -j ACCEPT
iptables -A FORWARD -i veth6 -o "$WAN_IF" -j ACCEPT

################
# Bridge setup #
################

ip link add $BR type bridge
ip link set dev veth2 master $BR
ip link set dev veth4 master $BR
ip addr del 172.16.1.2/30 dev veth2
ip addr del 172.16.2.2/30 dev veth4
ip addr add 172.16.1.2/30 dev $BR
ip addr add 172.16.2.2/30 dev $BR
ip link set dev $BR up

# Once veth2/veth4 are bridge ports, L3 is on the bridge device itself.
# Allow routed traffic between the bridge domain and WAN.
iptables -A FORWARD -i "$WAN_IF" -o "$BR" -m state --state RELATED,ESTABLISHED -j ACCEPT
iptables -A FORWARD -i "$BR" -o "$WAN_IF" -j ACCEPT

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
# modules. EC2 stock kernels usually
# ship all 15; missing ones are logged
# but non-fatal.
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

  On EC2 / real Linux hosts this usually means linux-modules-extra-\$(uname -r)
  isn't installed. Install it and restart the worker to enable the full
  CCAnalyzer set.
EOF
fi

echo
echo "======================================"
echo " netreplica solo setup completed successfully "
echo "======================================"
echo
