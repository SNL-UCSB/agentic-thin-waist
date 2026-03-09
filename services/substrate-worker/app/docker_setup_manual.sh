#### Docker solo 

# Run a docker container with the name "solo" in detached mode, with the network "docBr", and with the capabilities NET_ADMIN and SYS_ADMIN, and with privileged access, using the ubuntu:22.04 image, and running the command "sleep infinity".
# create docbr network with address at given subnet but subnet should not be 172.16.0.0/16 because it is used for the namespaces

docker run -itd \
  --name solo \
  --network docBr \
  --cap-add=NET_ADMIN \
  --cap-add=SYS_ADMIN \
  --privileged \
  ubuntu:22.04 \
  sleep infinity

# install the packages
apt update && apt install -y tshark iputils-ping net-tools iperf3 curl wget iproute2 iptables


# defining namespaces and number of queues for veth pairs, you can change the number of queues to 4 or 8 depending on your system capabilities.
NS1="ns1"
NS2="ns2"
NUM_QUEUE=4

# Setting up downstream namespace (ns1)
ip netns add $NS1
ip link add veth1 type veth peer name veth2
ip addr add 172.16.1.2/30 dev veth2
ip link set veth2 up
ip link set veth1 netns $NS1
ip netns exec $NS1 ip addr add 172.16.1.1/30 dev veth1
ip netns exec $NS1 ip link set veth1 up
ip netns exec $NS1 ip route add default via 172.16.1.2

# Perform NATing to make sure the traffic comes back to ns2 
sysctl -w net.ipv4.ip_forward=1
iptables -t nat -A POSTROUTING -o eth0 -j MASQUERADE
ip netns exec $NS1 sh -c 'echo "nameserver 8.8.8.8" > /etc/resolv.conf'


# setting up upstream namespace (ns2)
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

# Perfrom NATing to make sure the traffic goes through the bridge to the ns1 and not directly. 
iptables -t nat -A POSTROUTING -o eth0 -j MASQUERADE 
ip netns exec $NS2 iptables -t nat -A POSTROUTING -o veth5 -j MASQUERADE 
ip netns exec $NS2 sh -c 'echo "nameserver 8.8.8.8" > /etc/resolv.conf'



# Routhing downstream traffic through the bridge 
ip netns exec $NS1 ip route change default dev veth1
ip netns exec $NS1 ip route change default dev veth1 via 172.16.3.1 

# Routing upstream traffic through the bridge
ip netns exec $NS2 ip route add 172.16.1.0/30 dev veth3 
ip netns exec $NS2 ip route change default via 172.16.3.2 dev veth5

# Setting up the bridge
BR='netrepBr'
ip link add $BR type bridge
ip link set dev veth2 master $BR
ip link set dev veth4 master $BR
ip link set dev $BR up