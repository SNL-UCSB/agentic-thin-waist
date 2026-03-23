#!/bin/bash
set -e

NS1="ns1"
NS2="ns2"
NUM_QUEUE=4
BR="netrepBr"

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

echo
echo "======================================"
echo " netreplica solo setup completed successfully "
echo "======================================"
echo