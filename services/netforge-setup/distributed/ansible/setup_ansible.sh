#!/usr/bin/env bash
# =============================================================================
# setup_ansible.sh — Bootstrap Ansible on the control node
#
# This script prepares whichever machine you choose as your Ansible control
# node (one of the three servers, or a separate management machine).
#
# What it does:
#   1. Installs Python 3, pip, and virtualenv if missing
#   2. Creates a Python virtual environment and installs requirements.txt
#   3. Generates an SSH keypair if none exists at ~/.ssh/id_ed25519
#   4. Copies the public key to every server in your inventory
#   5. Tests Ansible connectivity (ansible all -m ping)
#
# Usage:
#   chmod +x setup_ansible.sh
#   ./setup_ansible.sh
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${SCRIPT_DIR}/.venv"
INVENTORY="${SCRIPT_DIR}/inventory/hosts.yml"

# Colour helpers
info()  { printf '\033[0;34m[INFO]\033[0m  %s\n' "$*"; }
ok()    { printf '\033[0;32m[ OK ]\033[0m  %s\n' "$*"; }
warn()  { printf '\033[0;33m[WARN]\033[0m  %s\n' "$*"; }
error() { printf '\033[0;31m[ERR ]\033[0m  %s\n' "$*" >&2; }
die()   { error "$*"; exit 1; }

# ── 1. Detect OS and install system-level dependencies ──────────────────────

info "Detecting operating system..."

if command -v apt-get &>/dev/null; then
    OS_FAMILY="debian"
elif command -v dnf &>/dev/null; then
    OS_FAMILY="rhel"
elif command -v brew &>/dev/null; then
    OS_FAMILY="macos"
else
    die "Unsupported OS. Install Python 3.10+, pip3, and openssh-client manually, then re-run."
fi

info "OS family: ${OS_FAMILY}"

install_system_packages() {
    case "${OS_FAMILY}" in
        debian)
            sudo apt-get update -q
            sudo apt-get install -y python3 python3-pip python3-venv openssh-client sshpass
            ;;
        rhel)
            sudo dnf install -y python3 python3-pip openssh-clients sshpass
            ;;
        macos)
            # Homebrew does not need sudo
            brew install python3 openssh
            ;;
    esac
}

if ! command -v python3 &>/dev/null; then
    info "Python 3 not found — installing..."
    install_system_packages
else
    ok "Python 3 found: $(python3 --version)"
fi

# ── 2. Create virtual environment and install Python requirements ────────────

info "Setting up Python virtual environment at ${VENV_DIR} ..."
python3 -m venv "${VENV_DIR}"
# shellcheck source=/dev/null
source "${VENV_DIR}/bin/activate"

pip install --quiet --upgrade pip
pip install --quiet -r "${SCRIPT_DIR}/requirements.txt"
ok "Python dependencies installed (ansible, pytest, black, etc.)"

# ── 3. Generate SSH key if none exists ───────────────────────────────────────

SSH_KEY="${HOME}/.ssh/id_ed25519"
if [[ ! -f "${SSH_KEY}" ]]; then
    info "No SSH key found at ${SSH_KEY} — generating one..."
    mkdir -p "${HOME}/.ssh"
    chmod 700 "${HOME}/.ssh"
    ssh-keygen -t ed25519 -N "" -f "${SSH_KEY}" -C "netreplica-ansible"
    ok "SSH key generated: ${SSH_KEY}"
else
    ok "SSH key already exists: ${SSH_KEY}"
fi

info "Your public key (copy this if you need to add it manually):"
cat "${SSH_KEY}.pub"
echo ""

# ── 4. Verify inventory/hosts.yml is filled in ──────────────────────────────

info "Checking inventory/hosts.yml for placeholder values..."
if grep -q "UPSTREAM_MGMT_IP\|DOWNSTREAM_MGMT_IP\|LIBREQOS_MGMT_IP" "${INVENTORY}"; then
    error "inventory/hosts.yml still contains placeholder IPs."
    error "Edit ${INVENTORY} and replace:"
    error "  UPSTREAM_MGMT_IP   → management IP of your upstream server"
    error "  DOWNSTREAM_MGMT_IP → management IP of your downstream server"
    error "  LIBREQOS_MGMT_IP   → management IP of your LibreQoS server"
    die "Update inventory/hosts.yml then re-run this script."
fi
ok "Inventory looks configured."

# ── 5. Copy SSH public key to all servers ───────────────────────────────────

# Parse the ansible_host values from inventory
UPSTREAM_IP=$(grep -A5 'upstream_server:' "${INVENTORY}" | grep 'ansible_host:' | awk '{print $2}' | tr -d '"' | head -1)
DOWNSTREAM_IP=$(grep -A5 'downstream_server:' "${INVENTORY}" | grep 'ansible_host:' | awk '{print $2}' | tr -d '"' | head -1)
LIBREQOS_IP=$(grep -A5 'libreqos_server:' "${INVENTORY}" | grep 'ansible_host:' | awk '{print $2}' | tr -d '"' | head -1)

UPSTREAM_USER=$(grep -A6 'upstream_server:' "${INVENTORY}" | grep 'ansible_user:' | awk '{print $2}' | tr -d '"' | head -1)
DOWNSTREAM_USER=$(grep -A6 'downstream_server:' "${INVENTORY}" | grep 'ansible_user:' | awk '{print $2}' | tr -d '"' | head -1)
LIBREQOS_USER=$(grep -A6 'libreqos_server:' "${INVENTORY}" | grep 'ansible_user:' | awk '{print $2}' | tr -d '"' | head -1)

copy_key() {
    local user="$1"
    local host="$2"
    local label="$3"

    # Skip if this is the local machine
    if [[ "${host}" == "127.0.0.1" || "${host}" == "localhost" ]]; then
        warn "Skipping SSH key copy to ${label} (localhost — local connection assumed)"
        return 0
    fi

    info "Copying SSH key to ${label} (${user}@${host})..."
    if ssh-copy-id -i "${SSH_KEY}.pub" -o StrictHostKeyChecking=accept-new "${user}@${host}"; then
        ok "Key copied to ${label}"
    else
        warn "ssh-copy-id to ${label} failed. You may need to copy the key manually:"
        warn "  ssh-copy-id -i ${SSH_KEY}.pub ${user}@${host}"
    fi
}

copy_key "${UPSTREAM_USER:-ubuntu}"   "${UPSTREAM_IP}"   "upstream server"
copy_key "${DOWNSTREAM_USER:-ubuntu}" "${DOWNSTREAM_IP}" "downstream server"
copy_key "${LIBREQOS_USER:-ubuntu}"   "${LIBREQOS_IP}"   "LibreQoS server"

# ── 6. Test Ansible connectivity ─────────────────────────────────────────────

info "Testing Ansible connectivity (ansible all -m ping)..."
cd "${SCRIPT_DIR}"

if ansible all -i "${INVENTORY}" -m ping; then
    ok "All servers are reachable via Ansible!"
else
    warn "One or more servers did not respond to Ansible ping."
    warn "Troubleshooting tips:"
    warn "  • Verify the IPs in inventory/hosts.yml are correct."
    warn "  • Ensure SSH service is running on each server: systemctl status ssh"
    warn "  • Check firewall rules allow SSH (port 22) from this machine."
    warn "  • If you need a password for sudo, add --ask-become-pass to playbook runs."
    exit 1
fi

# ── 7. Done ──────────────────────────────────────────────────────────────────

echo ""
ok "Bootstrap complete. Next steps:"
echo ""
echo "  1. Edit inventory/group_vars/all.yml with your hardware details."
echo "     Every variable has a description comment explaining what to enter."
echo ""
echo "  2. Run the full deployment:"
echo "     source .venv/bin/activate"
echo "     ansible-playbook -i inventory/hosts.yml playbooks/site.yml"
echo ""
echo "  3. Or run individual roles:"
echo "     ansible-playbook -i inventory/hosts.yml playbooks/libreqos.yml"
echo "     ansible-playbook -i inventory/hosts.yml playbooks/upstream.yml"
echo "     ansible-playbook -i inventory/hosts.yml playbooks/downstream.yml"
echo ""
echo "  4. Verify the setup:"
echo "     ansible-playbook -i inventory/hosts.yml playbooks/verify.yml"
echo "     pytest tests/ -v"
echo ""
