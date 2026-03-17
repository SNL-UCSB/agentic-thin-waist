#!/usr/bin/env bash
# =============================================================================
# common.sh — Shared utilities for netReplica distributed setup services
#
# SOURCE this file at the top of each service script; do not execute directly.
#   source "$(dirname "${BASH_SOURCE[0]}")/common.sh"
# =============================================================================

# Abort on unset variable or pipeline failure.
set -euo pipefail

# -----------------------------------------------------------------------------
# Logging helpers
# All messages are prefixed with a log level and timestamp so output is
# machine-parseable and easy to grep in systemd journal.
# -----------------------------------------------------------------------------

log_info()  { echo "[INFO]  $(date '+%Y-%m-%d %H:%M:%S')  $*"; }
log_ok()    { echo "[OK]    $(date '+%Y-%m-%d %H:%M:%S')  $*"; }
log_warn()  { echo "[WARN]  $(date '+%Y-%m-%d %H:%M:%S')  $*" >&2; }
log_error() { echo "[ERROR] $(date '+%Y-%m-%d %H:%M:%S')  $*" >&2; }

# -----------------------------------------------------------------------------
# Permission check
# Many ip/iptables/modprobe commands require CAP_NET_ADMIN / root.
# Call require_root at the top of any service function that needs it.
# -----------------------------------------------------------------------------

##
# require_root
#   Exits with an error if the effective UID is not 0.
#   Prints a hint so the user knows exactly how to re-run.
##
require_root() {
    if [[ $EUID -ne 0 ]]; then
        log_error "This operation requires root privileges."
        log_error "Re-run with: sudo $0 ${*:-}"
        exit 1
    fi
}

# -----------------------------------------------------------------------------
# Configuration loader
# -----------------------------------------------------------------------------

##
# load_config [path]
#   Sources the config.env file.  Searches in the following order:
#     1. Value of $CONFIG_FILE environment variable (if set)
#     2. Explicit [path] argument
#     3. config.env in the same directory as the calling script
#   Exits if the file is not found.
##
load_config() {
    local config_path="${CONFIG_FILE:-${1:-$(dirname "${BASH_SOURCE[1]}")/config.env}}"

    if [[ ! -f "$config_path" ]]; then
        log_error "Configuration file not found: $config_path"
        log_error "Create it from the template: cp config.env.example config.env"
        exit 1
    fi

    # shellcheck source=/dev/null
    source "$config_path"
    log_info "Loaded configuration from: $config_path"
}

# -----------------------------------------------------------------------------
# Prerequisite checks
# -----------------------------------------------------------------------------

##
# require_cmd <command> [package-hint]
#   Exits if <command> is not found in PATH.
#   Optionally prints the package name to install.
##
require_cmd() {
    local cmd="$1"
    local hint="${2:-$1}"
    if ! command -v "$cmd" &>/dev/null; then
        log_error "Required command not found: $cmd"
        log_error "Install it with: sudo apt-get install $hint"
        exit 1
    fi
}

##
# require_iface <interface>
#   Exits if the network interface does not exist on the system.
#   Use this to catch mismatches between config.env and actual hardware early.
##
require_iface() {
    local iface="$1"
    if ! ip link show "$iface" &>/dev/null; then
        log_error "Network interface not found: $iface"
        log_error "Check your config.env.  Available interfaces:"
        ip -br link show | awk '{print "  " $1}' >&2
        exit 1
    fi
}

# -----------------------------------------------------------------------------
# Idempotent network helpers
# These wrappers check the current state before applying a change so that the
# service scripts can be safely re-run without leaving duplicate rules/addresses.
# -----------------------------------------------------------------------------

##
# iface_has_ip <ip-with-prefix> <interface>
#   Returns 0 (true) if the address is already assigned, 1 otherwise.
##
iface_has_ip() {
    ip addr show dev "$2" 2>/dev/null | grep -qF "$1"
}

##
# add_ip_addr <ip/prefix> <interface>
#   Assigns an IP address to an interface; skips silently if already present.
##
add_ip_addr() {
    local ip="$1" iface="$2"
    if iface_has_ip "$ip" "$iface"; then
        log_info "Address $ip already set on $iface – skipping."
    else
        ip addr add "$ip" dev "$iface"
        log_ok "Assigned $ip to $iface."
    fi
}

##
# bring_up <interface>
#   Sets an interface to UP state; safe to call when already up.
##
bring_up() {
    ip link set "$1" up
    log_ok "Interface $1 is up."
}

##
# add_route_if_missing <route-spec…>
#   Calls 'ip route add <route-spec>' only if the route is not already present.
#   Example: add_route_if_missing 0.0.0.0/0 dev veth4 table mytable
##
add_route_if_missing() {
    if ip route show "$@" 2>/dev/null | grep -q .; then
        log_info "Route already exists: $* – skipping."
    else
        ip route add "$@"
        log_ok "Added route: $*"
    fi
}

##
# add_policy_table <id> <name>
#   Adds a named routing table to /etc/iproute2/rt_tables idempotently.
##
add_policy_table() {
    local id="$1" name="$2"
    if grep -qE "^${id}\s+${name}" /etc/iproute2/rt_tables 2>/dev/null; then
        log_info "Routing table '$name' (id $id) already registered – skipping."
    elif grep -qE "^${id}\s+" /etc/iproute2/rt_tables 2>/dev/null; then
        log_error "Table ID $id is already used by a different table in /etc/iproute2/rt_tables."
        log_error "Change POLICY_TABLE_ID in config.env to a free value (1–252)."
        exit 1
    else
        printf "%s\t%s\n" "$id" "$name" >> /etc/iproute2/rt_tables
        log_ok "Registered routing table '$name' (id $id)."
    fi
}

##
# del_policy_table <id> <name>
#   Removes the named routing table entry from /etc/iproute2/rt_tables.
##
del_policy_table() {
    local id="$1" name="$2"
    sed -i "/^${id}\s\+${name}/d" /etc/iproute2/rt_tables 2>/dev/null || true
    log_ok "Removed routing table entry '$name' (id $id)."
}

# -----------------------------------------------------------------------------
# IPv4 forwarding
# -----------------------------------------------------------------------------

##
# enable_ip_forward
#   Enables IPv4 forwarding for the running kernel and persists it in
#   /etc/sysctl.conf so it survives reboots.
##
enable_ip_forward() {
    require_root
    if [[ "$(cat /proc/sys/net/ipv4/ip_forward)" == "1" ]]; then
        log_info "IPv4 forwarding already enabled."
    else
        echo 1 > /proc/sys/net/ipv4/ip_forward
        log_ok "IPv4 forwarding enabled (runtime)."
    fi

    if ! grep -qE '^net\.ipv4\.ip_forward\s*=\s*1' /etc/sysctl.conf 2>/dev/null; then
        echo 'net.ipv4.ip_forward=1' >> /etc/sysctl.conf
        sysctl -p &>/dev/null
        log_ok "IPv4 forwarding persisted in /etc/sysctl.conf."
    fi
}

# -----------------------------------------------------------------------------
# iptables / nftables compatibility
# -----------------------------------------------------------------------------

##
# ensure_iptables_legacy
#   On systems that default to nftables (Debian 10+, Ubuntu 20.04+) the
#   kernel-level iptables rules created by 'ip netns exec … iptables' may be
#   silently ignored.  This function switches the system to iptables-legacy
#   (backed by the kernel x_tables framework) and flushes any existing nft
#   ruleset.
#
#   Safe to call multiple times; exits with a warning (not an error) if
#   update-alternatives is not available (e.g. on distros that don't use it).
##
ensure_iptables_legacy() {
    require_root

    if ! command -v update-alternatives &>/dev/null; then
        log_warn "update-alternatives not found; skipping iptables-legacy switch."
        return 0
    fi

    # Install iptables-persistent only if not already present.
    if ! dpkg -l iptables iptables-persistent &>/dev/null 2>&1; then
        log_info "Installing iptables and iptables-persistent …"
        DEBIAN_FRONTEND=noninteractive apt-get install -y iptables iptables-persistent
    fi

    local tables=( iptables ip6tables arptables ebtables )
    for t in "${tables[@]}"; do
        local legacy_path="/usr/sbin/${t}-legacy"
        if [[ -f "$legacy_path" ]]; then
            update-alternatives --set "$t" "$legacy_path" 2>/dev/null && \
                log_ok "Switched $t → legacy." || \
                log_warn "Could not switch $t to legacy (may already be set)."
        fi
    done

    # Flush nftables so it doesn't shadow iptables rules.
    if command -v nft &>/dev/null; then
        nft flush ruleset 2>/dev/null || true
        log_ok "Flushed nft ruleset."
    fi

    netfilter-persistent save   2>/dev/null || true
    netfilter-persistent reload 2>/dev/null || true
}

# -----------------------------------------------------------------------------
# systemd service installation helpers
# -----------------------------------------------------------------------------

##
# install_systemd_service <unit-name> <description> <script-path>
#   Writes a systemd unit file that calls <script-path> start/stop on
#   boot/shutdown, then enables and starts the service.
##
install_systemd_service() {
    local unit_name="$1"
    local description="$2"
    local script_path="$3"
    local unit_file="/etc/systemd/system/${unit_name}.service"

    require_root

    cat > "$unit_file" <<EOF
[Unit]
Description=${description}
After=network.target
Wants=network.target

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=${script_path} start
ExecStop=${script_path} stop
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload
    systemctl enable "$unit_name"
    log_ok "Installed and enabled systemd service: $unit_name"
    log_info "Start now with: sudo systemctl start $unit_name"
}

##
# uninstall_systemd_service <unit-name>
#   Stops, disables, and removes a systemd unit file created by
#   install_systemd_service.
##
uninstall_systemd_service() {
    local unit_name="$1"
    local unit_file="/etc/systemd/system/${unit_name}.service"

    require_root

    systemctl stop    "$unit_name" 2>/dev/null || true
    systemctl disable "$unit_name" 2>/dev/null || true
    rm -f "$unit_file"
    systemctl daemon-reload
    log_ok "Removed systemd service: $unit_name"
}
