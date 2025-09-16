"""System information and monitoring utilities."""

import platform
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import psutil


@dataclass
class SystemInfo:
    """System information data class."""

    hostname: str
    platform: str
    python_version: str
    cpu_count: int
    cpu_percent: float
    memory_total_gb: float
    memory_used_percent: float
    disk_total_gb: float
    disk_used_percent: float
    boot_time: datetime


def get_system_info() -> SystemInfo:
    """Get comprehensive system information.

    Returns:
        SystemInfo object with current system metrics.
    """
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")

    return SystemInfo(
        hostname=platform.node(),
        platform=platform.platform(),
        python_version=platform.python_version(),
        cpu_count=psutil.cpu_count() or 1,
        cpu_percent=psutil.cpu_percent(interval=1),
        memory_total_gb=mem.total / (1024**3),
        memory_used_percent=mem.percent,
        disk_total_gb=disk.total / (1024**3),
        disk_used_percent=disk.percent,
        boot_time=datetime.fromtimestamp(psutil.boot_time()),
    )


@dataclass
class ProcessInfo:
    """Process information data class."""

    pid: int
    name: str
    cpu_percent: float
    memory_percent: float
    status: str
    username: Optional[str] = None
    create_time: Optional[float] = None


def get_process_list(
    sort_by: str = "cpu", limit: Optional[int] = None
) -> list[ProcessInfo]:
    """Get list of running processes.

    Args:
        sort_by: Sort criteria - 'cpu', 'memory', or 'name'.
        limit: Maximum number of processes to return.

    Returns:
        List of ProcessInfo objects.
    """
    processes = []

    for proc in psutil.process_iter(
        [
            "pid",
            "name",
            "cpu_percent",
            "memory_percent",
            "status",
            "username",
            "create_time",
        ]
    ):
        try:
            pinfo = proc.info
            processes.append(
                ProcessInfo(
                    pid=pinfo["pid"],
                    name=pinfo["name"] or "N/A",
                    cpu_percent=pinfo.get("cpu_percent", 0) or 0,
                    memory_percent=pinfo.get("memory_percent", 0) or 0,
                    status=pinfo.get("status", "N/A") or "N/A",
                    username=pinfo.get("username"),
                    create_time=pinfo.get("create_time"),
                )
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue

    # Sort processes
    if sort_by == "cpu":
        processes.sort(key=lambda x: x.cpu_percent, reverse=True)
    elif sort_by == "memory":
        processes.sort(key=lambda x: x.memory_percent, reverse=True)
    elif sort_by == "name":
        processes.sort(key=lambda x: x.name.lower())

    if limit:
        processes = processes[:limit]

    return processes


@dataclass
class NetworkInterface:
    """Network interface information."""

    name: str
    is_up: bool
    addresses: list[dict[str, str]]


def get_network_interfaces() -> list[NetworkInterface]:
    """Get list of network interfaces.

    Returns:
        List of NetworkInterface objects.
    """
    interfaces = []
    addrs = psutil.net_if_addrs()
    stats = psutil.net_if_stats()

    for iface_name, addr_list in addrs.items():
        is_up = stats[iface_name].isup if iface_name in stats else False

        addresses = []
        for addr in addr_list:
            if addr.family.name == "AF_INET":  # IPv4
                addresses.append(
                    {
                        "address": addr.address,
                        "netmask": addr.netmask or "N/A",
                        "broadcast": addr.broadcast or "N/A",
                    }
                )

        if addresses:  # Only include interfaces with IPv4 addresses
            interfaces.append(
                NetworkInterface(
                    name=iface_name,
                    is_up=is_up,
                    addresses=addresses,
                )
            )

    return interfaces


@dataclass
class NetworkStats:
    """Network I/O statistics."""

    bytes_sent_mb: float
    bytes_recv_mb: float
    packets_sent: int
    packets_recv: int
    errin: int
    errout: int
    dropin: int
    dropout: int


def get_network_stats() -> NetworkStats:
    """Get network I/O statistics.

    Returns:
        NetworkStats object with current metrics.
    """
    net_io = psutil.net_io_counters()

    return NetworkStats(
        bytes_sent_mb=net_io.bytes_sent / (1024**2),
        bytes_recv_mb=net_io.bytes_recv / (1024**2),
        packets_sent=net_io.packets_sent,
        packets_recv=net_io.packets_recv,
        errin=net_io.errin,
        errout=net_io.errout,
        dropin=net_io.dropin,
        dropout=net_io.dropout,
    )
