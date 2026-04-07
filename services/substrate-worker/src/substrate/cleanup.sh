#!/bin/bash
set -e

NS1="ns1"
NS2="ns2"
BR="netrepBr"

ip link set $BR down 2>/dev/null || true
ip link delete $BR type bridge 2>/dev/null || true

for i in veth2 veth4 veth6; do
    ip link delete $i 2>/dev/null || true
done

ip netns delete $NS1 2>/dev/null || true
ip netns delete $NS2 2>/dev/null || true

iptables -t nat -F