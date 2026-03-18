#!/usr/bin/env bash
# =============================================================================
# upstream.sh — netReplica Upstream Server (Edge Router / NAT Gateway) Service
#
# DESCRIPTION:
#   Configures the upstream server to act as an edge router and NAT gateway.
#   Traffic arriving from the downstream server (via the switch + LibreQoS) is
#   forwarded through a dedicated network namespace (ns1) and NATted to the
#   public internet.
#
#   Network flow:
#     [Downstream / LibreQoS] → eno2 → veth4↔veth3 (ns1) → veth5↔veth6 → eno1 → [Internet]
#
#   All interface names and IP addresses are read from config.env so the script
#   works without modification on any server.
#
# USAGE:
#   sudo ./upstream.sh <command>
#
#   Commands:
#     start      — Apply all network configuration (idempotent).
#     stop       — Tear down all configuration created by 'start'.
#     status     — Show current state of interfaces, routes, and iptables rules.
#     install    — Install a systemd service unit that runs start/stop on boot.
#     uninstall  — Remove the systemd service unit.
#     deps       — Install/check system-level dependencies.
#
# REQUIREMENTS:
#   - Must be run as root (or via sudo).
#   - Packages: iproute2, iptables, iptables-persistent (auto-installed by deps).
#
# SEE ALSO:
#   config.env   — All configurable parameters.
#   common.sh    — Shared utility functions.
# =============================================================================

set -euo pipefail

# Resolve the directory where this script lives, following symlinks.
SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"

# Load shared utilities and user configuration.
# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"
load_config "${SCRIPT_DIR}/config.env"

# Systemd unit name for this service.
readonly SERVICE_NAME="netreplica-upstream"

# =============================================================================
# Internal helpers
# =============================================================================

##
# _validate_config
#   Checks that all config variables required by this script are set and that
#   the declared network interfaces actually exist on this machine.
##
_validate_config() {
    local required_vars=(
        UPSTREAM_SWITCH_IFACE UPSTREAM_INTERNET_IFACE
        UPSTREAM_SWITCH_IP SWITCH_SUBNET DOWNSTREAM_SWITCH_IP
        NS_NAME
        VETH_INTERNET_HOST VETH_INTERNET_NS
        VETH_SWITCH_HOST   VETH_SWITCH_NS
        VETH_INTERNET_HOST_IP VETH_INTERNET_NS_IP
        VETH_SWITCH_HOST_IP   VETH_SWITCH_NS_IP
        POLICY_TABLE_NAME POLICY_TABLE_ID GRE_CLIENT_SUBNET
    )

    for var in "${required_vars[@]}"; do
        if [[ -z "${!var:-}" ]]; then
            log_error "Required config variable '$var' is not set in config.env."
            exit 1
        fi
    done

    require_iface "$UPSTREAM_SWITCH_IFACE"
    require_iface "$UPSTREAM_INTERNET_IFACE"
}

##
# _ns_exists
#   Returns 0 if the NAT namespace already exists.
##
_ns_exists() {
    ip netns list 2>/dev/null | grep -qw "$NS_NAME"
}

##
# _veth_exists <name>
#   Returns 0 if a veth interface with that name exists (in any namespace).
##
_veth_exists() {
    ip link show "$1" &>/dev/null 2>&1 || \
    ip netns exec "$NS_NAME" ip link show "$1" &>/dev/null 2>&1
}

# =============================================================================
# Service lifecycle functions
# =============================================================================

##
# service_deps
#   Installs packages and kernel modules required by this service.
#   Safe to call multiple times.
##
service_deps() {
    require_root
    log_info "Checking / installing dependencies for upstream service …"

    DEBIAN_FRONTEND=noninteractive apt-get install -y iproute2 iptables iptables-persistent
    log_ok "Dependencies satisfied."

    # Switch to iptables-legacy to avoid conflicts with nftables on modern kernels.
    ensure_iptables_legacy
}

##
# service_start
#   Applies the full upstream network configuration.  Individual steps are
#   idempotent so this can be safely re-run if partially applied.
##
service_start() {
    require_root
    _validate_config

    log_info "Starting upstream service …"

    # ------------------------------------------------------------------
    # 1. Assign IP to the switch-facing interface and add the switch route.
    # ------------------------------------------------------------------
    bring_up "$UPSTREAM_SWITCH_IFACE"
    add_ip_addr "$UPSTREAM_SWITCH_IP/24" "$UPSTREAM_SWITCH_IFACE"
    add_route_if_missing "$SWITCH_SUBNET" dev "$UPSTREAM_SWITCH_IFACE"

    # ------------------------------------------------------------------
    # 2. Enable IPv4 forwarding (required for NAT).
    # ------------------------------------------------------------------
    enable_ip_forward

    # ------------------------------------------------------------------
    # 3. Create the NAT network namespace ns1 (if not already present).
    # ------------------------------------------------------------------
    if _ns_exists; then
        log_info "Namespace '$NS_NAME' already exists – skipping creation."
    else
        ip netns add "$NS_NAME"
        log_ok "Created namespace '$NS_NAME'."
    fi

    # ------------------------------------------------------------------
    # 4. Create veth pairs (skip if they already exist).
    #    veth pair A – internet side:  VETH_INTERNET_HOST ↔ VETH_INTERNET_NS
    #    veth pair B – switch side:    VETH_SWITCH_HOST   ↔ VETH_SWITCH_NS
    # ------------------------------------------------------------------
    if ! _veth_exists "$VETH_INTERNET_HOST"; then
        ip link add "$VETH_INTERNET_HOST" type veth peer name "$VETH_INTERNET_NS"
        log_ok "Created veth pair: $VETH_INTERNET_HOST ↔ $VETH_INTERNET_NS"
    fi

    if ! _veth_exists "$VETH_SWITCH_HOST"; then
        ip link add "$VETH_SWITCH_HOST" type veth peer name "$VETH_SWITCH_NS"
        log_ok "Created veth pair: $VETH_SWITCH_HOST ↔ $VETH_SWITCH_NS"
    fi

    # ------------------------------------------------------------------
    # 5. Assign IP addresses to the main-namespace ends.
    # ------------------------------------------------------------------
    add_ip_addr "$VETH_INTERNET_HOST_IP" "$VETH_INTERNET_HOST"
    add_ip_addr "$VETH_SWITCH_HOST_IP"   "$VETH_SWITCH_HOST"
    bring_up "$VETH_INTERNET_HOST"
    bring_up "$VETH_SWITCH_HOST"

    # ------------------------------------------------------------------
    # 6. Move the namespace-side veth interfaces into ns1
    #    (no-op if already there).
    # ------------------------------------------------------------------
    if ! ip netns exec "$NS_NAME" ip link show "$VETH_INTERNET_NS" &>/dev/null; then
        ip link set "$VETH_INTERNET_NS" netns "$NS_NAME"
        log_ok "Moved $VETH_INTERNET_NS into namespace '$NS_NAME'."
    fi

    if ! ip netns exec "$NS_NAME" ip link show "$VETH_SWITCH_NS" &>/dev/null; then
        ip link set "$VETH_SWITCH_NS" netns "$NS_NAME"
        log_ok "Moved $VETH_SWITCH_NS into namespace '$NS_NAME'."
    fi

    # ------------------------------------------------------------------
    # 7. Configure addresses and routes inside ns1.
    # ------------------------------------------------------------------
    ip netns exec "$NS_NAME" ip addr add "$VETH_SWITCH_NS_IP"   dev "$VETH_SWITCH_NS"   2>/dev/null || true
    ip netns exec "$NS_NAME" ip addr add "$VETH_INTERNET_NS_IP" dev "$VETH_INTERNET_NS" 2>/dev/null || true
    ip netns exec "$NS_NAME" ip link set "$VETH_SWITCH_NS"   up
    ip netns exec "$NS_NAME" ip link set "$VETH_INTERNET_NS" up

    # Default route inside the namespace exits via the internet veth.
    local ns_internet_gw
    ns_internet_gw="${VETH_INTERNET_HOST_IP%/*}"   # strip prefix length
    if ! ip netns exec "$NS_NAME" ip route show default 2>/dev/null | grep -q .; then
        ip netns exec "$NS_NAME" ip route add default via "$ns_internet_gw" dev "$VETH_INTERNET_NS"
        log_ok "Default route inside '$NS_NAME' set via $ns_internet_gw."
    fi

    # ------------------------------------------------------------------
    # 8. NAT inside ns1: masquerade egress on the internet veth.
    # ------------------------------------------------------------------
    if ! ip netns exec "$NS_NAME" iptables -t nat -C POSTROUTING -o "$VETH_INTERNET_NS" -j MASQUERADE 2>/dev/null; then
        ip netns exec "$NS_NAME" iptables -t nat -A POSTROUTING -o "$VETH_INTERNET_NS" -j MASQUERADE
        log_ok "iptables MASQUERADE added inside '$NS_NAME' on $VETH_INTERNET_NS."
    fi

    # ------------------------------------------------------------------
    # 9. Policy routing: steer GRE client subnet traffic into ns1.
    # ------------------------------------------------------------------
    add_policy_table "$POLICY_TABLE_ID" "$POLICY_TABLE_NAME"

    # ip rule: packets from the GRE client subnet use our policy table.
    if ! ip rule list 2>/dev/null | grep -q "from $GRE_CLIENT_SUBNET.*$POLICY_TABLE_NAME"; then
        ip rule add from "$GRE_CLIENT_SUBNET" table "$POLICY_TABLE_NAME"
        log_ok "Policy rule added: from $GRE_CLIENT_SUBNET → table $POLICY_TABLE_NAME."
    fi

    # Default route in the policy table points into the switch-side veth.
    ip route add default dev "$VETH_SWITCH_HOST" table "$POLICY_TABLE_NAME" 2>/dev/null || true
    local ns_switch_gw
    ns_switch_gw="${VETH_SWITCH_NS_IP%/*}"
    ip route change default via "$ns_switch_gw" dev "$VETH_SWITCH_HOST" table "$POLICY_TABLE_NAME" 2>/dev/null || true
    log_ok "Policy table '$POLICY_TABLE_NAME' default route → $VETH_SWITCH_HOST via $ns_switch_gw."

    # ------------------------------------------------------------------
    # 10. Return path: route switch subnet back toward downstream server.
    # ------------------------------------------------------------------
    # Remove any auto-created connected route first so we can set the gateway.
    ip route del "$SWITCH_SUBNET" dev "$UPSTREAM_SWITCH_IFACE" 2>/dev/null || true
    add_route_if_missing "$SWITCH_SUBNET" dev "$UPSTREAM_SWITCH_IFACE"
    ip route change "$SWITCH_SUBNET" dev "$UPSTREAM_SWITCH_IFACE" via "$DOWNSTREAM_SWITCH_IP" 2>/dev/null || true
    log_ok "Return route: $SWITCH_SUBNET via $DOWNSTREAM_SWITCH_IP on $UPSTREAM_SWITCH_IFACE."

    # ------------------------------------------------------------------
    # 11. NAT in the main namespace: masquerade egress to the internet.
    # ------------------------------------------------------------------
    if ! iptables -t nat -C POSTROUTING -o "$UPSTREAM_INTERNET_IFACE" -j MASQUERADE 2>/dev/null; then
        iptables -t nat -A POSTROUTING -o "$UPSTREAM_INTERNET_IFACE" -j MASQUERADE
        log_ok "iptables MASQUERADE added on $UPSTREAM_INTERNET_IFACE."
    fi

    netfilter-persistent save 2>/dev/null || true

    log_ok "Upstream service started successfully."
}

##
# service_stop
#   Tears down all configuration created by service_start.
#   Leaves system packages and kernel modules in place.
##
service_stop() {
    require_root
    _validate_config

    log_info "Stopping upstream service …"

    # Remove iptables MASQUERADE rule in the main namespace.
    iptables -t nat -D POSTROUTING -o "$UPSTREAM_INTERNET_IFACE" -j MASQUERADE 2>/dev/null || true
    log_ok "Removed MASQUERADE rule on $UPSTREAM_INTERNET_IFACE."

    # Remove policy routing rule.
    ip rule del from "$GRE_CLIENT_SUBNET" table "$POLICY_TABLE_NAME" 2>/dev/null || true
    ip route flush table "$POLICY_TABLE_NAME" 2>/dev/null || true
    del_policy_table "$POLICY_TABLE_ID" "$POLICY_TABLE_NAME"

    # Remove the routing table entry for the switch subnet.
    ip route del "$SWITCH_SUBNET" dev "$UPSTREAM_SWITCH_IFACE" 2>/dev/null || true

    # Delete the namespace (this also destroys both veth pairs inside it).
    if _ns_exists; then
        ip netns del "$NS_NAME"
        log_ok "Deleted namespace '$NS_NAME'."
    fi

    # Remove any veth interfaces that survived (in case they weren't in the ns).
    for iface in "$VETH_INTERNET_HOST" "$VETH_SWITCH_HOST" \
                 "$VETH_INTERNET_NS"   "$VETH_SWITCH_NS"; do
        ip link del "$iface" 2>/dev/null || true
    done

    # Remove IP from the switch-facing interface.
    ip addr del "${UPSTREAM_SWITCH_IP}/24" dev "$UPSTREAM_SWITCH_IFACE" 2>/dev/null || true

    log_ok "Upstream service stopped."
}

##
# service_status
#   Prints a human-readable summary of the current upstream service state.
##
service_status() {
    echo "=== Upstream Service Status ==="
    echo ""
    echo "--- Namespace '$NS_NAME' ---"
    if _ns_exists; then
        echo "  EXISTS"
        ip netns exec "$NS_NAME" ip addr show 2>/dev/null | sed 's/^/  /'
        echo ""
        echo "  Routes inside namespace:"
        ip netns exec "$NS_NAME" ip route show 2>/dev/null | sed 's/^/  /'
        echo ""
        echo "  iptables NAT inside namespace:"
        ip netns exec "$NS_NAME" iptables -t nat -L -n --line-numbers 2>/dev/null | sed 's/^/  /'
    else
        echo "  NOT present"
    fi

    echo ""
    echo "--- Switch-facing interface ($UPSTREAM_SWITCH_IFACE) ---"
    ip addr show dev "$UPSTREAM_SWITCH_IFACE" 2>/dev/null | sed 's/^/  /' || echo "  (not found)"

    echo ""
    echo "--- Policy routing table '$POLICY_TABLE_NAME' ---"
    ip rule list 2>/dev/null | grep "$POLICY_TABLE_NAME" | sed 's/^/  /' || echo "  (no rules)"

    echo ""
    echo "--- iptables NAT (main namespace) ---"
    iptables -t nat -L POSTROUTING -n --line-numbers 2>/dev/null | sed 's/^/  /' || echo "  (requires root)"
}

##
# service_install
#   Writes a systemd unit file so the upstream service starts automatically
#   on every boot.
##
service_install() {
    require_root
    local script_path
    script_path="$(readlink -f "${BASH_SOURCE[0]}")"
    install_systemd_service \
        "$SERVICE_NAME" \
        "netReplica Upstream Server (NAT / Edge Router)" \
        "$script_path"
}

##
# service_uninstall
#   Removes the systemd unit installed by service_install.
##
service_uninstall() {
    require_root
    uninstall_systemd_service "$SERVICE_NAME"
}

# =============================================================================
# Entry point
# =============================================================================

usage() {
    cat <<EOF
Usage: sudo $0 <command>

Commands:
  deps       Install / verify system dependencies.
  start      Apply upstream network configuration (idempotent).
  stop       Tear down upstream network configuration.
  status     Show current state.
  install    Register as a systemd service (auto-starts on boot).
  uninstall  Remove the systemd service registration.
EOF
}

case "${1:-}" in
    deps)      service_deps      ;;
    start)     service_start     ;;
    stop)      service_stop      ;;
    status)    service_status    ;;
    install)   service_install   ;;
    uninstall) service_uninstall ;;
    *)         usage; exit 1     ;;
esac
