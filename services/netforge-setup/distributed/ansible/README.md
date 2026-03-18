# netReplica Distributed Testbed — Ansible Automation

This directory contains a fully automated Ansible deployment for the netReplica distributed testbed.  It configures all three servers and guides you through the one manual step (switch VLAN setup) in a single command.

---

## Architecture

```
[Internet]
    |
[Upstream Server]  ──── VLAN 22 (access) ────┐
[LibreQoS Server]  ──── trunk (VLAN 11+22) ──┤ Managed L2 Switch
[Downstream Server] ─── VLAN 11 (access) ────┘
        |
GRE tunnels → Pinot / client nodes
```

| Server     | Role                                      | Ansible group  |
|------------|-------------------------------------------|----------------|
| Upstream   | Edge Router / NAT gateway                 | `upstream`     |
| Downstream | Core Router / GRE aggregator              | `downstream`   |
| LibreQoS   | Traffic Shaper (XDP, on-a-stick VLAN)     | `libreqos`     |

---

## Prerequisites

### Hardware
- Three physical servers, each with at least two NICs
- One managed L2 switch (802.1Q VLAN support required)
- USB-to-serial cable from the downstream server to the switch console port

### Software — before running Ansible
- **LibreQoS** must be pre-installed on the LibreQoS server
  ([official guide](https://libreqos.readthedocs.io))
- All three servers must be reachable via SSH from your control node
- Ubuntu 20.04+ or Debian 11+ on all servers

### Control node
Choose **one** of:
- Any of the three servers
- A separate management machine (laptop, jump host, etc.)

---

## Quick Start

### Step 1 — Bootstrap the control node

Run this once on the machine you chose as your Ansible control node:

```bash
cd services/netforge-setup/distributed/ansible
chmod +x setup_ansible.sh
./setup_ansible.sh
```

The script will:
1. Install Python 3 and create a virtual environment
2. Install Ansible and all dependencies from `requirements.txt`
3. Generate an SSH key (or reuse an existing one)
4. Copy the SSH key to all three servers
5. Run `ansible all -m ping` to confirm connectivity

> **If your control node IS one of the servers**, uncomment `ansible_connection: local`
> for that host in `inventory/hosts.yml` before running the script.

### Step 2 — Edit the inventory

Open **`inventory/hosts.yml`** and replace the three placeholder IPs:

```yaml
upstream_server:
  ansible_host: "192.168.1.10"   # ← replace with your upstream server IP
  ansible_user: "ubuntu"          # ← replace with your SSH username

downstream_server:
  ansible_host: "192.168.1.20"
  ansible_user: "ubuntu"

libreqos_server:
  ansible_host: "192.168.1.30"
  ansible_user: "ubuntu"
```

### Step 3 — Edit the variables

Open **`inventory/group_vars/all.yml`** and fill in every variable.  Every variable has a comment explaining exactly what it is and where to find the value on your hardware.

Key variables to change:

```yaml
# On the upstream server — find with: ip -br link
upstream_switch_iface: "eno2"         # interface cabled to the switch
upstream_internet_iface: "eno1"       # interface cabled to the internet
upstream_switch_ip: "192.168.0.203"   # IP on the switch-facing interface

# On the downstream server
downstream_switch_iface: "ens2f1"
server_internet_ip: "128.111.5.236"   # public IP (find with: curl ifconfig.me)
pinot_ips: "169.231.171.58"           # space-separated list of Pinot node IPs

# On the LibreQoS server
libreqos_switch_iface: "enp216s0f0"   # trunk port interface

# Switch ports
switch_upstream_port: "te1/0/3"
switch_downstream_port: "te1/0/4"
switch_libreqos_port: "te1/0/1"
vlan_upstream_id: "22"
vlan_downstream_id: "11"
```

### Step 4 — Run the deployment

```bash
source .venv/bin/activate
ansible-playbook -i inventory/hosts.yml playbooks/site.yml
```

This runs all steps in order:

1. **Switch commands** — prints pre-filled CLI commands and pauses.
   Apply them via minicom before pressing Enter to continue.
2. **LibreQoS server** — installs packages, creates VLAN sub-interfaces,
   writes LibreQoS config, installs systemd service.
3. **Upstream server** — installs iptables, creates namespace/veths/NAT,
   configures policy routing, installs systemd service.
4. **Downstream server** — installs Docker, creates GRE tunnels and Docker
   network, installs systemd service.
5. **Verify** — runs connectivity and service-state checks across all servers.

### Step 5 — Run tests

```bash
pytest tests/ -v
```

---

## Individual Playbooks

Run any component independently:

```bash
# Configure only one server
ansible-playbook -i inventory/hosts.yml playbooks/libreqos.yml
ansible-playbook -i inventory/hosts.yml playbooks/upstream.yml
ansible-playbook -i inventory/hosts.yml playbooks/downstream.yml

# Print switch commands without deploying
ansible-playbook -i inventory/hosts.yml playbooks/switch_commands.yml

# Re-run verification only
ansible-playbook -i inventory/hosts.yml playbooks/verify.yml

# Run tests
pytest tests/ -v
pytest tests/test_setup.py::TestConnectivity -v
```

If your servers require a sudo password:

```bash
ansible-playbook -i inventory/hosts.yml playbooks/site.yml --ask-become-pass
```

---

## Directory Structure

```
ansible/
├── README.md                        ← you are here
├── requirements.txt                 ← Python deps (ansible, pytest, black, …)
├── setup_ansible.sh                 ← bootstrap script for the control node
│
├── inventory/
│   ├── hosts.yml                    ← server IPs and SSH users (EDIT THIS)
│   └── group_vars/
│       └── all.yml                  ← all network variables (EDIT THIS)
│
├── playbooks/
│   ├── site.yml                     ← main playbook (runs everything)
│   ├── upstream.yml
│   ├── downstream.yml
│   ├── libreqos.yml
│   ├── switch_commands.yml          ← prints switch CLI commands (manual step)
│   └── verify.yml                   ← end-to-end checks
│
├── roles/
│   ├── common/                      ← copies scripts, renders config.env
│   │   ├── tasks/main.yml
│   │   └── templates/config.env.j2
│   ├── upstream/tasks/main.yml
│   ├── downstream/tasks/main.yml    ← also installs Docker
│   ├── libreqos/tasks/main.yml
│   └── verify/tasks/main.yml        ← assertions run on every server
│
└── tests/
    ├── conftest.py                  ← pytest fixtures
    └── test_setup.py                ← end-to-end Python tests (black-compliant)
```

---

## What Ansible Installs

| Server     | Packages installed by Ansible                          |
|------------|--------------------------------------------------------|
| All        | `iproute2`, `bash`, `curl`, `git`                      |
| Upstream   | `iptables`, `iptables-persistent`, `netfilter-persistent` |
| Downstream | Docker Engine, `iproute2`, `iptables`, `minicom`       |
| LibreQoS   | `ethtool`, `vlan` (includes `8021q` kernel module)     |

LibreQoS itself must be pre-installed manually.

---

## Testing

Tests are in `tests/test_setup.py` and use `pytest`.  They SSH into each server
via Ansible ad-hoc commands and assert the expected state.

Test classes:

| Class                  | What it checks                                    |
|------------------------|---------------------------------------------------|
| `TestUpstreamServer`   | Service, forwarding, namespace, NAT, policy routing |
| `TestDownstreamServer` | Service, forwarding, ip_gre, GRE interfaces, Docker |
| `TestLibreQoSServer`   | Service, 8021q, VLAN interfaces, lqosd, configs   |
| `TestConnectivity`     | Routing tables, all-servers Ansible ping          |
| `TestSystemdServices`  | All services enabled + unit files present         |

The Ansible `verify.yml` playbook performs additional checks including:
- iptables MASQUERADE rule verification
- `ethtool` RX VLAN offload check
- Live ping tests between servers across switch VLANs

---

## Troubleshooting

**`ansible all -m ping` fails**
- Check that `ansible_host` IPs in `inventory/hosts.yml` are correct.
- Verify SSH is running: `systemctl status ssh` on each server.
- Ensure the control node's public key is in `~/.ssh/authorized_keys` on each server.
- Run `./setup_ansible.sh` again — it will retry key distribution.

**Playbook fails on a specific server**
- Run that server's playbook alone for cleaner output:
  `ansible-playbook -i inventory/hosts.yml playbooks/upstream.yml -vv`
- Check the existing scripts manually first:
  `sudo ./upstream.sh status` on the upstream server.

**`verify.yml` ping tests fail**
- Check switch VLAN assignment (`show vlan brief` on switch console).
- Ensure the VLAN IDs in `group_vars/all.yml` match what you configured on the switch.
- Re-run `playbooks/switch_commands.yml` to see the exact expected switch commands.

**LibreQoS `configure` step fails**
- Ensure LibreQoS is installed and its default config files exist:
  `/opt/libreqos/src/ispConfig.py` and `/etc/lqos.conf`.
- If installed to a non-default path, update `libreqos_isp_config` and
  `libreqos_lqos_conf` in `group_vars/all.yml`.

**`lqosd` fails to start**
- This is expected if LibreQoS is not fully configured. The playbook uses
  `ignore_errors: true` for this step.
- Complete the full LibreQoS configuration per the official docs, then run:
  `sudo systemctl start lqosd`

**Tests fail with import errors**
- Activate the virtual environment: `source .venv/bin/activate`
- Reinstall requirements: `pip install -r requirements.txt`
