# netReplica — Distributed Testbed Setup

This directory contains the service scripts for deploying the **netReplica distributed testbed**, which consists of three physical servers and a managed switch.  Each server runs a dedicated role; traffic between them is shaped by LibreQoS before reaching the internet.

For the full system architecture, see **Figure 4** of the paper:
📄 https://arxiv.org/pdf/2507.13476

---

## Architecture Overview

```
                        [Internet]
                            |
                   ┌────────────────┐
                   │ Upstream Server│  Edge router, NAT gateway
                   │  upstream.sh   │  (e.g. Server 2)
                   └───────┬────────┘
                           │  VLAN 22 — access port
                   ┌───────┴────────┐
                   │    Switch      │  Managed L2 switch
                   │  switch.sh     │  VLANs isolate upstream ↔ downstream
                   └──┬──────────┬──┘
        VLAN 11        │          │  VLAN 11 + 22 — trunk port
     access port       │          │
             ┌─────────┴──┐  ┌────┴───────────┐
             │ Downstream  │  │  LibreQoS       │
             │  Server     │  │  Server         │
             │downstream.sh│  │  libreqos.sh    │
             └─────────────┘  └─────────────────┘
                   |
         GRE tunnels to Pinot / client nodes
```

### Roles

| Server | Role | Script |
|---|---|---|
| Upstream | Edge router / NAT gateway. Receives shaped traffic from LibreQoS via the switch and NATs it to the internet. | `upstream.sh` |
| Downstream | Core router / aggregator. Terminates GRE tunnels from Pinot/client nodes and routes traffic toward LibreQoS through the switch. | `downstream.sh` |
| LibreQoS | Traffic shaper. Runs on-a-stick between two VLANs on the switch trunk port, applying per-subscriber bandwidth policies via XDP. | `libreqos.sh` |
| Switch | Managed L2 switch. Two VLANs ensure all traffic flows through LibreQoS; the LibreQoS port is a trunk, the others are access ports. | `switch.sh` |

---

## File Structure

```
distributed/
├── README.md          ← you are here
├── config.env         ← EDIT THIS: all configurable parameters
├── common.sh          ← shared utility library (sourced by service scripts)
├── setup.sh           ← orchestrator and interactive setup guide
├── upstream.sh        ← upstream server service
├── downstream.sh      ← downstream server service
├── libreqos.sh        ← LibreQoS server service
└── switch.sh          ← switch configuration guide (interactive)
```

---

## Requirements

### Hardware
- Three physical servers, each with at least **two NICs**:
  - One NIC connected to the managed switch (the "switch-facing" interface)
  - One NIC connected to the internet or management network
- One managed L2 switch that supports **802.1Q VLANs** (access + trunk ports)
- USB-to-serial cable from the downstream server to the switch console port (for initial switch configuration)

### Software — all servers
- Ubuntu 20.04+ or Debian 11+ (other systemd-based distros should work)
- `iproute2` (almost always pre-installed)
- `bash` ≥ 4.0

### Software — upstream server
- `iptables` and `iptables-persistent`
- On kernels that default to **nftables** (Ubuntu 20.04+): the `deps` command automatically switches `iptables` to the legacy backend so that rules created inside network namespaces are not silently ignored

### Software — downstream server
- `iproute2` (GRE tunnel support via `ip tunnel`)
- `iptables`
- **Docker** (must be installed separately before running `start`)
- Kernel module `ip_gre` (loaded automatically by `deps`)

### Software — LibreQoS server
- **LibreQoS** installed and its default config files present — follow the official guide at https://libreqos.readthedocs.io before running these scripts
- Kernel module `8021q` (loaded automatically by `deps`)
- `ethtool`
- `vlan` package

### Software — switch configuration
- `minicom` (on the server connected to the switch console)

---

## Quick Start

### 1. Edit `config.env`

Copy the file to each server and fill in the values that match **your hardware**.  The most important ones:

```bash
# On the upstream server — set to the actual interface names shown by 'ip -br link'
UPSTREAM_SWITCH_IFACE="eno2"        # interface cabled to the switch
UPSTREAM_INTERNET_IFACE="eno1"      # interface cabled to the internet

# On the downstream server
DOWNSTREAM_SWITCH_IFACE="ens2f1"
DOWNSTREAM_INTERNET_IFACE="eno1"
SERVER_INTERNET_IP="128.111.5.236"  # public IP of this server (GRE local endpoint)
PINOT_IPS="169.231.171.58"          # space-separated list of Pinot/client public IPs

# On the LibreQoS server
LIBREQOS_SWITCH_IFACE="enp216s0f0"  # interface cabled to the switch (trunk port)
```

Validate the file (no network changes):

```bash
./setup.sh check-config
```

### 2. Configure the switch

Run on the server connected to the switch console (usually the downstream server):

```bash
./switch.sh check-deps       # verify minicom and serial device
./switch.sh show-cmds        # print switch CLI commands to copy-paste
./switch.sh connect          # open a minicom session and apply the commands
```

### 3. LibreQoS server

```bash
sudo ./libreqos.sh deps        # install 8021q, ethtool
sudo ./libreqos.sh start       # create VLAN sub-interfaces
sudo ./libreqos.sh configure   # write ispConfig.py and lqos.conf
sudo ./libreqos.sh install     # register as systemd service (auto-start on boot)
sudo ./libreqos.sh status      # verify
```

Then start the LibreQoS daemon:

```bash
sudo systemctl start lqosd
```

### 4. Upstream server

```bash
sudo ./upstream.sh deps      # install iptables, handle nftables if needed
sudo ./upstream.sh start     # configure namespace, veth pairs, NAT, routing
sudo ./upstream.sh install   # register as systemd service
sudo ./upstream.sh status    # verify
```

### 5. Downstream server

```bash
sudo ./downstream.sh deps    # install iproute2, load ip_gre module
sudo ./downstream.sh start   # configure GRE tunnels, routing, Docker network
sudo ./downstream.sh install # register as systemd service
sudo ./downstream.sh status  # verify
```

### Alternatively — use the interactive guide

```bash
./setup.sh guide
```

This prints every step in order with the exact commands to run on each server.

---

## Service Commands

Every service script (`upstream.sh`, `downstream.sh`, `libreqos.sh`) supports the same set of commands:

| Command | Description |
|---|---|
| `deps` | Install packages and kernel modules required by this service. |
| `start` | Apply network configuration. **Idempotent** — safe to re-run. |
| `stop` | Tear down all configuration created by `start`. |
| `status` | Print current state of interfaces, routes, and rules. |
| `install` | Write a systemd unit file and enable the service (runs `start` on every boot). |
| `uninstall` | Disable and remove the systemd unit file. |

`switch.sh` is different — it is a configuration guide, not a service:

| Command | Description |
|---|---|
| `check-deps` | Verify minicom and serial device. |
| `show-cmds` | Print switch CLI commands pre-filled from `config.env`. |
| `connect` | Open a minicom console session to the switch. |

`libreqos.sh` has one extra command:

| Command | Description |
|---|---|
| `configure` | Write `ispConfig.py` and `lqos.conf` from `config.env` (backs up originals). |

---

## Permission Notes

All `start`, `stop`, `install`, `uninstall`, `deps`, and `configure` commands require **root privileges** and must be run with `sudo`.  The scripts check this at startup and print a clear error with the correct re-run command if not.

`status`, `show-cmds`, `check-config`, and `guide` can be run as a normal user.

To avoid typing `sudo` for every command, you can open a root shell once:

```bash
sudo -i
cd /path/to/distributed
./upstream.sh start
```

---

## Adding More GRE Tunnels (Pinot Nodes)

Add the public IP of each new Pinot node to `PINOT_IPS` in `config.env` as a space-separated list:

```bash
PINOT_IPS="169.231.171.58 169.231.171.99 1.2.3.4"
```

Then run `sudo ./downstream.sh start` again — it will create the missing tunnels and skip the ones that already exist.  Tunnel addressing uses sequential `/30` blocks from `GRE_TUNNEL_BASE`:

| Tunnel | Interface | Server IP | Client IP |
|---|---|---|---|
| 1 | gre1 | `<base>.2/30` | `<base>.3` |
| 2 | gre2 | `<base>.6/30` | `<base>.7` |
| 3 | gre3 | `<base>.10/30` | `<base>.11` |
| … | … | … | … |

---

## Troubleshooting

**Traffic not flowing end-to-end**
- Check `sudo ./upstream.sh status` and `sudo ./downstream.sh status` on each server.
- Verify the switch VLAN assignments with `show vlan brief` on the switch console.
- Check `ip route` and `ip rule` on both servers.
- Ensure IPv4 forwarding is enabled: `cat /proc/sys/net/ipv4/ip_forward` should print `1`.

**NAT not working on the upstream server**
- Check `sudo iptables -t nat -L -n` for `MASQUERADE` rules on both the main namespace and inside `ns1`.
- On Ubuntu 20.04+, run `sudo ./upstream.sh deps` to ensure `iptables-legacy` is active and nftables rules are flushed.

**GRE tunnel is up but no traffic**
- Verify `ip_gre` module is loaded: `lsmod | grep ip_gre`
- Check that `SERVER_INTERNET_IP` in `config.env` matches the actual IP the Pinot node is trying to reach.
- Confirm the firewall on both ends allows GRE (IP protocol 47).

**LibreQoS not shaping traffic**
- Confirm the XDP bridge is running: `sudo systemctl status lqosd`
- Run `sudo ./libreqos.sh status` to verify both VLAN sub-interfaces are up.
- Check that `ethtool -K <iface> rxvlan off` was applied; re-run `sudo ./libreqos.sh start` if not.
