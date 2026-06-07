
_manager = None


def _get_manager():
    global _manager
    if _manager is None:
        from jarvis.ssh.ssh_manager import SSHManager
        _manager = SSHManager()
    return _manager


async def ssh_list_connections() -> str:
    """List all configured SSH connections and their status."""
    mgr = _get_manager()
    names = mgr.list_names()
    if not names:
        return (
            "No SSH connections configured. "
            "Add one via the SSH manager in JARVIS settings."
        )
    lines = []
    for name in names:
        client = mgr.get_client(name)
        status = "connected" if (client and client.is_connected) else "disconnected"
        cfg = next(c for c in mgr.get_configs() if c.name == name)
        lines.append(
            f"- {name}  ({cfg.username}@{cfg.host}:{cfg.port})  [{status}]"
        )
    return "SSH connections:\n" + "\n".join(lines)


async def ssh_connect(connection_name: str) -> str:
    """Connect to a configured SSH server by name."""
    mgr = _get_manager()
    client = mgr.get_client(connection_name)
    if client is None:
        names = mgr.list_names()
        avail = ", ".join(names) if names else "none configured"
        return f"No SSH connection named '{connection_name}'. Available: {avail}"
    if client.is_connected:
        return f"Already connected to '{connection_name}'."
    try:
        await client.connect()
        return f"Connected to '{connection_name}' successfully."
    except Exception as e:
        return f"Failed to connect to '{connection_name}': {e}"


async def ssh_disconnect(connection_name: str) -> str:
    """Disconnect from an SSH server."""
    mgr = _get_manager()
    client = mgr.get_client(connection_name)
    if client is None:
        return f"No SSH connection named '{connection_name}'."
    if not client.is_connected:
        return f"'{connection_name}' is not currently connected."
    try:
        await client.disconnect()
        return f"Disconnected from '{connection_name}'."
    except Exception as e:
        return f"Error disconnecting from '{connection_name}': {e}"


async def ssh_execute(
    connection_name: str,
    command: str,
    timeout: float = 30.0,
) -> str:
    """Execute a shell command on a remote SSH server and return output."""
    mgr = _get_manager()
    client = mgr.get_client(connection_name)
    if client is None:
        return (
            f"No SSH connection named '{connection_name}'. "
            "Use ssh_list_connections to see available servers."
        )
    try:
        result = await client.execute(command, timeout=timeout)
        out = str(result)
        prefix = f"[{connection_name}] $ {command}\n"
        return prefix + (out if out else "(no output)")
    except Exception as e:
        return f"SSH execute error on '{connection_name}': {e}"


async def ssh_read_file(connection_name: str, remote_path: str) -> str:
    """Read a file from a remote SSH server."""
    mgr = _get_manager()
    client = mgr.get_client(connection_name)
    if client is None:
        return f"No SSH connection named '{connection_name}'."
    try:
        content = await client.read_file(remote_path)
        lines = content.split("\n")
        if len(lines) > 100:
            content = "\n".join(lines[:100])
            content += f"\n... [{len(lines) - 100} more lines truncated]"
        return f"[{connection_name}:{remote_path}]\n{content}"
    except Exception as e:
        return f"Failed to read '{remote_path}' from '{connection_name}': {e}"


async def ssh_write_file(
    connection_name: str,
    remote_path: str,
    content: str,
) -> str:
    """Write content to a file on a remote SSH server."""
    mgr = _get_manager()
    client = mgr.get_client(connection_name)
    if client is None:
        return f"No SSH connection named '{connection_name}'."
    try:
        await client.write_file(remote_path, content)
        return f"Written to '{connection_name}:{remote_path}' successfully."
    except Exception as e:
        return f"Failed to write '{remote_path}' on '{connection_name}': {e}"


async def ssh_list_dir(
    connection_name: str,
    remote_path: str = ".",
) -> str:
    """List directory contents on a remote SSH server."""
    mgr = _get_manager()
    client = mgr.get_client(connection_name)
    if client is None:
        return f"No SSH connection named '{connection_name}'."
    try:
        entries = await client.list_dir(remote_path)
        return f"[{connection_name}:{remote_path}]\n" + "\n".join(entries)
    except Exception as e:
        return f"Failed to list '{remote_path}' on '{connection_name}': {e}"


async def ssh_get_system_info(connection_name: str) -> str:
    """Get OS, uptime, disk and memory info from a remote SSH server."""
    mgr = _get_manager()
    client = mgr.get_client(connection_name)
    if client is None:
        return f"No SSH connection named '{connection_name}'."
    try:
        cmds = ["uname -a", "uptime", "df -h /", "free -h"]
        parts = []
        for cmd in cmds:
            result = await client.execute(cmd, timeout=10.0)
            if result.success:
                parts.append(f"$ {cmd}\n{result.stdout.strip()}")
        return f"[{connection_name} system info]\n\n" + "\n\n".join(parts)
    except Exception as e:
        return f"Failed to get system info from '{connection_name}': {e}"


async def ssh_tail_log(
    connection_name: str,
    log_path: str,
    lines: int = 50,
) -> str:
    """Tail the last N lines of a log file on a remote SSH server."""
    return await ssh_execute(
        connection_name,
        f"tail -n {lines} {log_path}",
        timeout=15.0,
    )


async def ssh_check_service(
    connection_name: str,
    service_name: str,
) -> str:
    """Check the status of a systemd service on a remote SSH server."""
    return await ssh_execute(
        connection_name,
        f"systemctl status {service_name} --no-pager",
        timeout=10.0,
    )
