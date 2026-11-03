"""An egress guard for tests: a local HTTP proxy that writes down every
outside host a process tries to reach, and lets through only the package
index (the agent's harness installs its own few packages with uv).

Run anything with HTTP_PROXY / HTTPS_PROXY pointing here and NO_PROXY set
to localhost: local traffic (the stack, the model, verifiers' own servers)
goes direct, and anything bound elsewhere, such as an upload to Prime,
shows up in `refused_hosts`. Python's httpx, which Prime's SDK uses,
honours these variables; tests/stack/test_no_upload.py checks that it does."""

import select
import socket
import socketserver
import threading
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass, field

PACKAGE_HOSTS = frozenset({"pypi.org", "files.pythonhosted.org"})
BUFFER_BYTES = 65536


@dataclass
class EgressLog:
    refused_hosts: set[str] = field(default_factory=set[str])
    allowed_hosts: set[str] = field(default_factory=set[str])
    lock: threading.Lock = field(default_factory=threading.Lock)


def _relay(client: socket.socket, upstream: socket.socket) -> None:
    sockets = [client, upstream]
    while True:
        readable, _, _ = select.select(sockets, [], [], 30)
        if not readable:
            return
        for source in readable:
            data = source.recv(BUFFER_BYTES)
            if not data:
                return
            (upstream if source is client else client).sendall(data)


def _handler(log: EgressLog) -> type[socketserver.BaseRequestHandler]:
    class Handler(socketserver.BaseRequestHandler):
        def handle(self) -> None:
            client: socket.socket = self.request
            request_line = client.recv(BUFFER_BYTES).split(b"\r\n", 1)[0].decode()
            method, target = request_line.split(" ")[:2]
            host, _, port = target.removeprefix("http://").split("/", 1)[0].partition(":")
            with log.lock:
                is_allowed = method == "CONNECT" and host in PACKAGE_HOSTS
                (log.allowed_hosts if is_allowed else log.refused_hosts).add(host)
            if not is_allowed:
                client.sendall(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n")
                return
            with socket.create_connection((host, int(port or 443)), timeout=30) as upstream:
                client.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
                _relay(client, upstream)

    return Handler


@contextmanager
def egress_guard() -> Generator[tuple[str, EgressLog]]:
    """Yields the proxy's URL and the log it fills."""
    log = EgressLog()
    server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), _handler(log))
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}", log
    finally:
        server.shutdown()
        server.server_close()


def proxy_environment(proxy_url: str) -> dict[str, str]:
    variables = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy")
    environment = {name: proxy_url for name in variables}
    environment["NO_PROXY"] = environment["no_proxy"] = "127.0.0.1,localhost,::1"
    return environment
