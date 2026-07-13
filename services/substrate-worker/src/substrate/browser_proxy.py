"""Minimal forward HTTP/HTTPS proxy for shaped browser traffic.

Browserless launches Chrome with ``--proxy-server=$BROWSER_PROXY_HOST:$BROWSER_PROXY_PORT``
so that all browser traffic is routed through a proxy that lives *inside* the
shaped ``ns1`` namespace. Routing the browser through ns1 is what makes browser
(YouTube / Zoom / Twitch) traffic traverse the htb/netem-shaped veth path and
show up in the veth2 capture — exactly like the shell apps that run via
``ip netns exec ns1``.

Without this proxy running, Chrome is pointed at a dead address and every
navigation fails with "Failed to navigate to <url>". This module is therefore
started from ``setup_local.sh`` inside ns1:

    ip netns exec ns1 python3 -m substrate.browser_proxy --host 0.0.0.0 --port 8888

It is intentionally dependency-free (stdlib only) and supports both plain HTTP
forwarding and HTTPS via the CONNECT method (which is all a browser needs).
"""

from __future__ import annotations

import argparse
import select
import socket
import threading
from urllib.parse import urlsplit

BUFFER_SIZE = 65536
CONNECT_TIMEOUT = 15.0
IDLE_TIMEOUT = 120.0

# Per-proxy fwmark applied to every upstream socket via SO_MARK.
# 0 = no mark (default proxy, unchanged behaviour).
# Set from --mark CLI arg so each proxy instance can carry a distinct mark.
_FWMARK: int = 0

# Source IP to bind upstream sockets to — mirrors the proxy's own listen IP
# so that outgoing SYNs carry the app-specific alias address that ns2 uses
# for per-app classification (SO_MARK cannot cross namespace boundaries in
# newer kernels, but L3 source addresses can).
_BIND_HOST: str = "0.0.0.0"


def _marked_connection(host: str, port: int, timeout: float) -> socket.socket:
    """Create a TCP connection with SO_MARK set and source IP bound BEFORE the SYN.

    Two things happen before connect():
    1. If _FWMARK is set, SO_MARK stamps the fwmark on the socket so ns1's
       conntrack entry records the per-app mark.
    2. If the proxy listener is bound to a specific alias IP (not 0.0.0.0),
       the upstream socket is bound to that same IP so all SYNs carry the
       per-app source address that ns2 uses for classification.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    if _FWMARK:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_MARK, _FWMARK)
    # Bind to the alias IP if the proxy is not listening on the wildcard.
    if _BIND_HOST and _BIND_HOST != "0.0.0.0":
        sock.bind((_BIND_HOST, 0))
    sock.settimeout(timeout)
    try:
        sock.connect((host, port))
    except Exception:
        sock.close()
        raise
    return sock


def _recv_headers(conn: socket.socket) -> bytes:
    """Read until the end of the HTTP request headers (CRLFCRLF)."""
    data = b""
    conn.settimeout(CONNECT_TIMEOUT)
    while b"\r\n\r\n" not in data:
        chunk = conn.recv(BUFFER_SIZE)
        if not chunk:
            break
        data += chunk
        if len(data) > 1 << 20:  # 1 MB header guard
            break
    return data


def _pipe(a: socket.socket, b: socket.socket) -> None:
    """Bidirectionally relay bytes between two sockets until either closes."""
    sockets = [a, b]
    a.setblocking(False)
    b.setblocking(False)
    while True:
        try:
            readable, _, errored = select.select(sockets, [], sockets, IDLE_TIMEOUT)
        except (OSError, ValueError):
            break
        if errored or not readable:
            break
        for src in readable:
            dst = b if src is a else a
            try:
                data = src.recv(BUFFER_SIZE)
            except OSError:
                return
            if not data:
                return
            try:
                dst.sendall(data)
            except OSError:
                return


def _handle_connect(client: socket.socket, authority: str) -> None:
    """Handle an HTTPS CONNECT tunnel to host:port."""
    host, _, port_str = authority.partition(":")
    port = int(port_str) if port_str else 443
    print(f"[browser_proxy] CONNECT {host}:{port}", flush=True)
    try:
        upstream = _marked_connection(host, port, CONNECT_TIMEOUT)
    except OSError:
        client.sendall(b"HTTP/1.1 502 Bad Gateway\r\n\r\n")
        return
    client.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
    _pipe(client, upstream)
    upstream.close()


def _handle_plain(client: socket.socket, raw: bytes, method: str, target: str) -> None:
    """Handle a plain (non-CONNECT) HTTP request by forwarding it upstream."""
    split = urlsplit(target)
    host = split.hostname
    if not host:
        client.sendall(b"HTTP/1.1 400 Bad Request\r\n\r\n")
        return
    port = split.port or 80
    # Rewrite the absolute-form request-line target to origin-form.
    path = split.path or "/"
    if split.query:
        path += "?" + split.query
    rebuilt = raw.replace(
        f"{method} {target}".encode(), f"{method} {path}".encode(), 1
    )
    try:
        upstream = _marked_connection(host, port, CONNECT_TIMEOUT)
    except OSError:
        client.sendall(b"HTTP/1.1 502 Bad Gateway\r\n\r\n")
        return
    upstream.sendall(rebuilt)
    _pipe(client, upstream)
    upstream.close()


def _serve_client(client: socket.socket) -> None:
    try:
        raw = _recv_headers(client)
        if not raw:
            return
        request_line = raw.split(b"\r\n", 1)[0].decode("latin-1", "replace")
        parts = request_line.split(" ")
        if len(parts) < 2:
            return
        method, target = parts[0], parts[1]
        if method.upper() == "CONNECT":
            _handle_connect(client, target)
        else:
            _handle_plain(client, raw, method, target)
    except Exception:
        pass
    finally:
        try:
            client.close()
        except OSError:
            pass


def serve(host: str, port: int) -> None:
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((host, port))
    server.listen(128)
    print(f"[browser_proxy] listening on {host}:{port}", flush=True)
    while True:
        try:
            client, _ = server.accept()
        except OSError:
            continue
        threading.Thread(target=_serve_client, args=(client,), daemon=True).start()


def main() -> None:
    global _FWMARK, _BIND_HOST
    parser = argparse.ArgumentParser(description="Forward HTTP/HTTPS proxy")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8888)
    parser.add_argument(
        "--mark",
        type=int,
        default=0,
        help="fwmark (SO_MARK) applied to every upstream socket. "
        "0 = no mark (default).",
    )
    args = parser.parse_args()
    _FWMARK = args.mark
    _BIND_HOST = args.host
    serve(args.host, args.port)


if __name__ == "__main__":
    main()
