#!/usr/bin/env bash
# =============================================================================
# downstream.sh — netReplica Downstream Server (Core Router / Aggregator) Service
#
# DESCRIPTION:
#   Configures the downstream server to:
#     1. Assign an IP to the switch-facing interface and establish routing toward
#        the upstream server (through LibreQoS).
#     2. Load the ip_gre kernel module and create a GRE tunnel for each Pinot
#        node / client listed in PINOT_IPS (space-separated in config.env).
#        Each tunnel gets a /30 address from the GRE_TUNNEL_BASE block.
#     3. Create a Docker bridge network for netReplica containers and disable
#        the automatic NAT rule so container traffic can be shaped by LibreQoS.
#
#   Network flow:
#     [Pinot nodes] ──GRE tunnels──> gre1..greN → [policy routing] → ens2f1 → switch → LibreQoS → upstream
#
# USAGE:
#   sudo ./downstream.sh <command>
#
#   Commands:
#     start      — Apply all network configuration (idempotent).
#     stop       — Tear down all configuration created by 'start'.
#     status     — Show current state.
#     install    — Install a systemd service unit (auto-start on boot).
#     uninstall  — Remove the systemd service unit.
#     deps       — Install/check system-level dependencies.
#
# REQUIREMENTS:
#   - Must be run as root (or via sudo).
#   - Docker must already be installed (not installed by this script).
#   - Packages: iproute2, iptables, iproute2 (auto-checked by deps command).
#
# SEE ALSO:
#   config.env  — All configurable parameters.
#   common.sh   — Shared utility functions.
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"

# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"
load_config "${SCRIPT_DIR}/config.env"

readonly SERVICE_NAME="netreplica-downstream"

# =============================================================================
# Internal helpers
# =============================================================================

##
# _validate_config
#   Verifies all required variables are set and interfaces exist.
##
_validate_config() {
    local required_vars=(
        DOWNSTREAM_SWITCH_IFACE DOWNSTREAM_INTERNET_IFACE
        DOWNSTREAM_SWITCH_IP UPSTREAM_SWITCH_IP SWITCH_SUBNET
        SERVER_INTERNET_IP PINOT_IPS
        GRE_TUNNEL_BASE GRE_TUNNEL_PREFIX
        GRE_CLIENT_SUBNET
        POLICY_TABLE_NAME POLICY_TABLE_ID
        DOCKER_NETWORK_NAME DOCKER_SUBNET DOCKER_MTU
    )

    for var in "${required_vars[@]}"; do
        if [[ -z "${!var:-}" ]]; then
            log_error "Required config variable '$var' is not set in config.env."
            exit 1
        fi
    done

    require_iface "$DOWNSTREAM_SWITCH_IFACE"
    require_iface "$DOWNSTREAM_INTERNET_IFACE"
}

##
# _gre_tunnel_name <index>
#   Returns the tunnel interface name for the given 1-based index.
#   Example: index=1 → "gre1", index=2 → "gre2"
##
_gre_tunnel_name() {
    echo "${GRE_TUNNEL_PREFIX}${1}"
}

##
# _gre_server_ip <index>
#   Calculates the server-side /30 address for tunnel number <index>.
#   Tunnel 1: <base>.1/30 (network), <base>.2/30 (server), <base>.3/30 (client)
#   Tunnel 2: <base>.5/30, <base>.6/30, <base>.7/30
##
_gre_server_ip() {
    local idx="$1"
    local octet=$(( (idx - 1) * 4 + 2 ))
    echo "${GRE_TUNNEL_BASE}.${octet}/30"
}

##
# _docker_bridge_name
#   Resolves the Linux bridge interface that Docker assigned to DOCKER_NETWORK_NAME.
#   Returns an empty string if the network does not exist yet.
##
_docker_bridge_name() {
    docker network inspect "$DOCKER_NETWORK_NAME" \
        --format '{{index .Options "com.docker.network.bridge.name"}}' 2>/dev/null || true
}

# =============================================================================
# Service lifecycle functions
# =============================================================================

##
# service_deps
#   Installs required packages and kernel modules.
##
service_deps() {
    require_root
    log_info "Checking / installing dependencies for downstream service …"

    DEBIAN_FRONTEND=noninteractive apt-get install -y iproute2 iptables

    # GRE kernel module.
    if ! lsmod | grep -q ip_gre; then
        modprobe ip_gre
        log_ok "Loaded ip_gre kernel module."
    else
        log_info "ip_gre module already loaded."
    fi

    # Persist the module across reboots.
    if ! grep -q '^ip_gre$' /etc/modules 2>/dev/null; then
        echo 'ip_gre' >> /etc/modules
        log_ok "ip_gre added to /etc/modules (persists on reboot)."
    fi

    require_cmd docker "docker.io"

    log_ok "Dependencies satisfied."
}

##
# service_start
#   Full downstream network bring-up.
##
service_start() {
    require_root
    _validate_config

    log_info "Starting downstream service …"

    # ------------------------------------------------------------------
    # 1. Switch-facing interface: IP + route toward upstream.
    # ------------------------------------------------------------------
    bring_up "$DOWNSTREAM_SWITCH_IFACE"
    add_ip_addr "$DOWNSTREAM_SWITCH_IP/24" "$DOWNSTREAM_SWITCH_IFACE"
    add_route_if_missing "$SWITCH_SUBNET" dev "$DOWNSTREAM_SWITCH_IFACE"

    # ------------------------------------------------------------------
    # 2. Enable IPv4 forwarding.
    # ------------------------------------------------------------------
    enable_ip_forward

    # ------------------------------------------------------------------
    # 3. Policy routing: send GRE-originated traffic toward upstream
    #    through the switch-facing interface.
    # ------------------------------------------------------------------
    add_policy_table "$POLICY_TABLE_ID" "$POLICY_TABLE_NAME"

    if ! ip rule list 2>/dev/null | grep -q "from $GRE_CLIENT_SUBNET.*$POLICY_TABLE_NAME"; then
        ip rule add from "$GRE_CLIENT_SUBNET" table "$POLICY_TABLE_NAME"
        log_ok "Policy rule: from $GRE_CLIENT_SUBNET → table $POLICY_TABLE_NAME."
    fi

    ip route add default dev "$DOWNSTREAM_SWITCH_IFACE" table "$POLICY_TABLE_NAME" 2>/dev/null || true
    ip route change default dev "$DOWNSTREAM_SWITCH_IFACE" \
        via "$UPSTREAM_SWITCH_IP" table "$POLICY_TABLE_NAME" 2>/dev/null || true
    log_ok "Policy table default route: $DOWNSTREAM_SWITCH_IFACE via $UPSTREAM_SWITCH_IP."

    # ------------------------------------------------------------------
    # 4. Load GRE kernel module.
    # ------------------------------------------------------------------
    if ! lsmod | grep -q ip_gre; then
        modprobe ip_gre
        log_ok "Loaded ip_gre module."
    fi

    # ------------------------------------------------------------------
    # 5. Create one GRE tunnel per Pinot/client IP.
    # ------------------------------------------------------------------
    local idx=1
    for pinot_ip in $PINOT_IPS; do
        local tun_name server_ip
        tun_name="$(_gre_tunnel_name "$idx")"
        server_ip="$(_gre_server_ip "$idx")"

        if ip link show "$tun_name" &>/dev/null; then
            log_info "Tunnel $tun_name already exists – skipping."
        else
            # iptunnel (legacy) falls back to ip tunnel if unavailable.
            if command -v iptunnel &>/dev/null; then
                iptunnel add "$tun_name" mode gre \
                    remote "$pinot_ip" local "$SERVER_INTERNET_IP" ttl 255
            else
                ip tunnel add "$tun_name" mode gre \
                    remote "$pinot_ip" local "$SERVER_INTERNET_IP" ttl 255
            fi
            log_ok "Created GRE tunnel $tun_name: $SERVER_INTERNET_IP ↔ $pinot_ip."
        fi

        add_ip_addr "$server_ip" "$tun_name"
        bring_up "$tun_name"
        log_ok "Tunnel $tun_name (index $idx): server-side IP $server_ip."

        idx=$(( idx + 1 ))
    done

    # ------------------------------------------------------------------
    # 6. Docker network for netReplica containers.
    # ------------------------------------------------------------------
    if docker network inspect "$DOCKER_NETWORK_NAME" &>/dev/null 2>&1; then
        log_info "Docker network '$DOCKER_NETWORK_NAME' already exists – skipping."
    else
        docker network create \
            --subnet "$DOCKER_SUBNET" \
            --opt "com.docker.network.driver.mtu=$DOCKER_MTU" \
            "$DOCKER_NETWORK_NAME"
        log_ok "Created Docker network '$DOCKER_NETWORK_NAME' (subnet $DOCKER_SUBNET, MTU $DOCKER_MTU)."
    fi

    # ------------------------------------------------------------------
    # 7. Remove the automatic Docker MASQUERADE rule for this subnet so
    #    that LibreQoS can shape each container's traffic individually.
    # ------------------------------------------------------------------
    local bridge
    bridge="$(_docker_bridge_name)"
    if [[ -n "$bridge" ]]; then
        if iptables -t nat -C POSTROUTING \
               -s "$DOCKER_SUBNET" ! -o "$bridge" -j MASQUERADE 2>/dev/null; then
            iptables -t nat -D POSTROUTING \
               -s "$DOCKER_SUBNET" ! -o "$bridge" -j MASQUERADE
            log_ok "Removed automatic Docker MASQUERADE for $DOCKER_SUBNET (bridge $bridge)."
        else
            log_info "Docker MASQUERADE rule for $DOCKER_SUBNET not present – nothing to remove."
        fi
    else
        log_warn "Could not determine Docker bridge name; skipping MASQUERADE removal."
        log_warn "Run 'docker network inspect $DOCKER_NETWORK_NAME' and remove the MASQUERADE rule manually."
    fi

    log_ok "Downstream service started successfully."
}

##
# service_stop
#   Tears down everything created by service_start.
##
service_stop() {
    require_root
    _validate_config

    log_info "Stopping downstream service …"

    # Remove GRE tunnels.
    local idx=1
    for _pinot_ip in $PINOT_IPS; do
        local tun_name
        tun_name="$(_gre_tunnel_name "$idx")"
        if ip link show "$tun_name" &>/dev/null; then
            ip link set "$tun_name" down
            ip tunnel del "$tun_name" 2>/dev/null || \
                ip link del "$tun_name" 2>/dev/null || true
            log_ok "Removed tunnel $tun_name."
        fi
        idx=$(( idx + 1 ))
    done

    # Remove policy routing.
    ip rule del from "$GRE_CLIENT_SUBNET" table "$POLICY_TABLE_NAME" 2>/dev/null || true
    ip route flush table "$POLICY_TABLE_NAME" 2>/dev/null || true
    del_policy_table "$POLICY_TABLE_ID" "$POLICY_TABLE_NAME"

    # Remove switch-subnet route and IP.
    ip route del "$SWITCH_SUBNET" dev "$DOWNSTREAM_SWITCH_IFACE" 2>/dev/null || true
    ip addr del "${DOWNSTREAM_SWITCH_IP}/24" dev "$DOWNSTREAM_SWITCH_IFACE" 2>/dev/null || true

    # Remove Docker network (only if no containers are using it).
    if docker network inspect "$DOCKER_NETWORK_NAME" &>/dev/null 2>&1; then
        docker network rm "$DOCKER_NETWORK_NAME" 2>/dev/null && \
            log_ok "Removed Docker network '$DOCKER_NETWORK_NAME'." || \
            log_warn "Could not remove Docker network '$DOCKER_NETWORK_NAME' (containers still attached?)."
    fi

    log_ok "Downstream service stopped."
}

##
# service_status
#   Prints a human-readable summary of the downstream state.
##
service_status() {
    echo "=== Downstream Service Status ==="
    echo ""
    echo "--- Switch-facing interface ($DOWNSTREAM_SWITCH_IFACE) ---"
    ip addr show dev "$DOWNSTREAM_SWITCH_IFACE" 2>/dev/null | sed 's/^/  /' || echo "  (not found)"

    echo ""
    echo "--- GRE tunnels ---"
    local idx=1
    for pinot_ip in $PINOT_IPS; do
        local tun_name
        tun_name="$(_gre_tunnel_name "$idx")"
        printf "  %s (peer %s): " "$tun_name" "$pinot_ip"
        if ip link show "$tun_name" &>/dev/null; then
            ip -br addr show dev "$tun_name" 2>/dev/null
        else
            echo "NOT present"
        fi
        idx=$(( idx + 1 ))
    done

    echo ""
    echo "--- Policy routing table '$POLICY_TABLE_NAME' ---"
    ip rule list 2>/dev/null | grep "$POLICY_TABLE_NAME" | sed 's/^/  /' || echo "  (no rules)"

    echo ""
    echo "--- Docker network '$DOCKER_NETWORK_NAME' ---"
    docker network inspect "$DOCKER_NETWORK_NAME" \
        --format "  Subnet: {{range .IPAM.Config}}{{.Subnet}}{{end}}  Bridge: {{index .Options \"com.docker.network.bridge.name\"}}" \
        2>/dev/null || echo "  (not found)"
}

##
# service_install / service_uninstall
##
service_install() {
    require_root
    local script_path
    script_path="$(readlink -f "${BASH_SOURCE[0]}")"
    install_systemd_service \
        "$SERVICE_NAME" \
        "netReplica Downstream Server (Core Router / GRE Aggregator)" \
        "$script_path"
}

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
  start      Apply downstream network configuration (idempotent).
  stop       Tear down downstream network configuration.
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
