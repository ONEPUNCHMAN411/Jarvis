
import platform
import socket
import subprocess
import threading

from loguru import logger

# Common ports to scan
_COMMON_PORTS = [21, 22, 23, 25, 53, 80, 110, 143, 443, 445, 3306, 3389, 5432, 6379, 8080, 8443]


def get_local_ip() -> str:
    """Get the local machine's primary IP address."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"


def get_public_ip() -> str:
    """Get the public IP via httpx."""
    try:
        import httpx
        r = httpx.get("https://api.ipify.org", timeout=8)
        return r.text.strip()
    except Exception as e:
        logger.warning(f"get_public_ip error: {e}")
        return f"Error: {e}"


def ping_host(host: str, count: int = 3) -> dict:
    """Ping a host and return latency info."""
    is_win = platform.system().lower() == "windows"
    flag = "-n" if is_win else "-c"
    cmd = ["ping", flag, str(count), host]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=15,
        )
        output = result.stdout + result.stderr
        alive = result.returncode == 0
        # Parse average latency
        latency_ms: float | None = None
        for line in output.splitlines():
            line_l = line.lower()
            if "average" in line_l or "avg" in line_l:
                parts = line.replace("=", " ").split()
                for p in parts:
                    try:
                        latency_ms = float(p.rstrip("ms"))
                        break
                    except ValueError:
                        continue
                break
        return {"host": host, "alive": alive, "latency_ms": latency_ms, "output": output.strip()}
    except subprocess.TimeoutExpired:
        return {"host": host, "alive": False, "latency_ms": None, "output": "Timed out"}
    except Exception as e:
        return {"host": host, "alive": False, "latency_ms": None, "output": str(e)}


def check_port(host: str, port: int, timeout: float = 2.0) -> dict:
    """Check if a single port is open on a host."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return {"host": host, "port": port, "open": True}
    except Exception:
        return {"host": host, "port": port, "open": False}


def scan_ports(
    host: str,
    ports: list[int] | None = None,
    timeout: float = 1.5,
) -> list[dict]:
    """Scan a list of ports on a host using threads."""
    ports = ports or _COMMON_PORTS
    results: list[dict | None] = [None] * len(ports)

    def _check(idx: int, port: int) -> None:
        results[idx] = check_port(host, port, timeout)

    threads = [threading.Thread(target=_check, args=(i, p)) for i, p in enumerate(ports)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=timeout + 1)

    return [r for r in results if r is not None and r["open"]]


def scan_network(subnet: str | None = None, timeout: float = 1.0) -> list[str]:
    """
    Ping-sweep a /24 subnet and return list of alive hosts.
    If subnet is None, derives it from the local IP.
    """
    if subnet is None:
        local_ip = get_local_ip()
        parts = local_ip.split(".")
        subnet = ".".join(parts[:3])

    alive: list[str] = []
    alive_lock = threading.Lock()

    def _ping(host_suffix: int) -> None:
        ip = f"{subnet}.{host_suffix}"
        result = ping_host(ip, count=1)
        if result["alive"]:
            with alive_lock:
                alive.append(ip)

    threads = [threading.Thread(target=_ping, args=(i,)) for i in range(1, 255)]
    for t in threads:
        t.daemon = True
        t.start()
    for t in threads:
        t.join(timeout=20)

    alive.sort(key=lambda ip: int(ip.split(".")[-1]))
    return alive
