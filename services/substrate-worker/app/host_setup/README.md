# NetReplica Local Namespace Setup

This setup creates two namespaces, **upstream** and **downstream**, connected through virtual interfaces. Traffic shaping and aqm is applied on these interfaces, and the script configures all routing and NAT needed for full connectivity.

## Setup
Run the setup script:
```
sudo ./setup.sh
```

### What the Script Does

* Creates upstream and downstream namespaces
* Creates veth pairs to link the namespaces

* Assigns IP addresses to all interfaces

* Applies shaping rules on both veth interfaces

* Configures routing in each namespace

* Enables NAT and forwarding on the host

* Provides end-to-end connectivity for testing traffic

Cleanup
```
sudo ./cleanup.sh
```

### Requirements

1. Linux system

2. iproute2, tc, iptables

3. Root privileges