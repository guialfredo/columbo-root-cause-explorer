"""Network-related probes for testing connectivity, DNS resolution, and HTTP endpoints."""

import socket
import time
import requests

from columbo.schemas import ProbeResult
from .spec import probe


@probe(
    name="dns_resolution",
    description="Resolve a hostname to IP addresses",
    scope="network",
    tags={"dns", "connectivity"},
    args={
        "hostname": "Hostname to resolve (required)"
    },
    required_args={"hostname"},
    example='{"hostname": "localhost"}'
)
def dns_resolution_probe(hostname: str, probe_name: str = "dns_resolution") -> ProbeResult:
    """Resolve a hostname to IP addresses.
    
    Args:
        hostname: Hostname to resolve (required)
        probe_name: Identifier for this probe execution
        
    Returns:
        dict: Contains resolved IPs and success status
    """
    try:
        infos = socket.getaddrinfo(hostname, None)
        ips = sorted({info[4][0] for info in infos})
        return ProbeResult(
            probe_name=probe_name,
            success=True,
            data={
                "hostname": hostname,
                "resolved_ips": ips,
                "ok": True,
            }
        )
    except Exception as e:
        return ProbeResult(
            probe_name=probe_name,
            success=False,
            error=f"{type(e).__name__}: {str(e)}",
            data={
                "hostname": hostname,
                "resolved_ips": [],
                "ok": False,
            }
        )


@probe(
    name="tcp_connection",
    description="Test TCP connection to a host and port",
    scope="network",
    tags={"tcp", "connectivity"},
    args={
        "host": "Target host (required)",
        "port": "Target port number (required)",
        "timeout": "Connection timeout in seconds (default: 5.0)"
    },
    required_args={"host", "port"},
    example='{"host": "localhost", "port": 8000}'
)
def tcp_connection_probe(
    host: str, port: int, timeout: float = 5.0, probe_name: str = "tcp_connection"
) -> ProbeResult:
    """Test TCP connection to a host and port.
    
    Args:
        host: Target host (required)
        port: Target port number (required)
        timeout: Connection timeout in seconds (default: 5.0)
        probe_name: Identifier for this probe execution
        
    Returns:
        dict: Connection success status and error details if failed
    """
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return ProbeResult(
                probe_name=probe_name,
                success=True,
                data={"host": host, "port": port, "ok": True}
            )
    except Exception as e:
        return ProbeResult(
            probe_name=probe_name,
            success=False,
            error=f"{type(e).__name__}: {str(e)}",
            data={"host": host, "port": port, "ok": False}
        )


@probe(
    name="http_connection",
    description="Test HTTP connection to a URL",
    scope="network",
    tags={"http", "connectivity"},
    args={
        "url": "Full URL to test (required)",
        "timeout": "Request timeout in seconds (default: 5.0)"
    },
    required_args={"url"},
    example='{"url": "http://localhost:8000/health"}'
)
def http_connection_probe(
    url: str, timeout: float = 5.0, probe_name: str = "http_connection"
) -> ProbeResult:
    """Test HTTP connection to a URL.
    
    Args:
        url: Full URL to test (required)
        timeout: Request timeout in seconds (default: 5.0)
        probe_name: Identifier for this probe execution
        
    Returns:
        dict: HTTP status code, latency, response excerpt, and success status
    """
    start = time.time()
    try:
        r = requests.get(url, timeout=timeout)
        elapsed_ms = int((time.time() - start) * 1000)
        text = (r.text or "")[:300]
        ok = 200 <= r.status_code < 300
        return ProbeResult(
            probe_name=probe_name,
            success=True,
            data={
                "url": url,
                "status_code": r.status_code,
                "ok": ok,
                "latency_ms": elapsed_ms,
                "body_excerpt": text,
            }
        )
    except Exception as e:
        elapsed_ms = int((time.time() - start) * 1000)
        return ProbeResult(
            probe_name=probe_name,
            success=False,
            error=f"{type(e).__name__}: {str(e)}",
            data={
                "url": url,
                "status_code": None,
                "ok": False,
                "latency_ms": elapsed_ms,
            }
        )
