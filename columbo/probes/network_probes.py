"""Network-related probes for testing connectivity, DNS resolution, and HTTP endpoints."""

import socket
import time
import requests


def dns_resolution_probe(hostname: str, probe_name: str = "dns_resolution"):
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
        return {
            "hostname": hostname,
            "resolved_ips": ips,
            "ok": True,
            "probe_name": probe_name,
        }
    except Exception as e:
        return {
            "hostname": hostname,
            "resolved_ips": [],
            "ok": False,
            "probe_name": probe_name,
            "error": str(e),
        }


def tcp_connection_probe(
    host: str, port: int, timeout: float = 5.0, probe_name: str = "tcp_connection"
):
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
            return {"host": host, "port": port, "ok": True, "probe_name": probe_name}
    except Exception as e:
        return {
            "host": host,
            "port": port,
            "ok": False,
            "probe_name": probe_name,
            "error": str(e),
            "error_type": type(e).__name__,
        }


def http_connection_probe(
    url: str, timeout: float = 5.0, probe_name: str = "http_connection"
):
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
        return {
            "url": url,
            "status_code": r.status_code,
            "ok": ok,
            "latency_ms": elapsed_ms,
            "body_excerpt": text,
            "probe_name": probe_name,
        }
    except Exception as e:
        elapsed_ms = int((time.time() - start) * 1000)
        return {
            "url": url,
            "status_code": None,
            "ok": False,
            "latency_ms": elapsed_ms,
            "probe_name": probe_name,
            "error": str(e),
            "error_type": type(e).__name__,
        }
