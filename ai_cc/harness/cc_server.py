#!/usr/bin/env python3
"""Minimal static HTTP origin whose SENDER-side TCP congestion control is
pinned via setsockopt(TCP_CONGESTION) on the listening socket. Accepted
connections inherit the CCA, so the file we serve is sent under the chosen
algorithm. Unprivileged: works for any CCA in tcp_allowed_congestion_control.

Usage: cc_server.py <dir> <port> <cca>
"""
import http.server
import socket
import socketserver
import sys

TCP_CONGESTION = 13  # from <netinet/tcp.h>


class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    allow_reuse_address = True

    def __init__(self, addr, handler, cca):
        self.cca = cca.encode()
        super().__init__(addr, handler)

    def server_bind(self):
        # set BEFORE bind/listen so accepted sockets inherit it
        self.socket.setsockopt(socket.IPPROTO_TCP, TCP_CONGESTION, self.cca)
        got = self.socket.getsockopt(socket.IPPROTO_TCP, TCP_CONGESTION, 16)
        got = got.split(b"\x00")[0].decode()
        if got != self.cca.decode():
            raise SystemExit(f"CCA mismatch: wanted {self.cca} got {got}")
        sys.stderr.write(f"[cc_server] listening CCA={got}\n")
        sys.stderr.flush()
        super().server_bind()


class Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass  # quiet


if __name__ == "__main__":
    directory, port, cca = sys.argv[1], int(sys.argv[2]), sys.argv[3]
    handler = lambda *a, **k: Handler(*a, directory=directory, **k)
    Server(("0.0.0.0", port), handler, cca).serve_forever()
