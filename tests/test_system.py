"""Tests for system module."""


from sysforge.core.system import (
    get_network_interfaces,
    get_network_stats,
    get_process_list,
    get_system_info,
)


def test_get_system_info() -> None:
    """Test get_system_info function."""
    info = get_system_info()

    assert info.hostname
    assert info.platform
    assert info.python_version
    assert info.cpu_count > 0
    assert 0 <= info.cpu_percent <= 100
    assert info.memory_total_gb > 0
    assert 0 <= info.memory_used_percent <= 100
    assert info.disk_total_gb > 0
    assert 0 <= info.disk_used_percent <= 100
    assert info.boot_time


def test_get_process_list() -> None:
    """Test get_process_list function."""
    processes = get_process_list(limit=5)

    assert len(processes) <= 5
    assert all(p.pid > 0 for p in processes)
    assert all(p.name for p in processes)
    # CPU percent can sometimes exceed 100% on multi-core systems
    assert all(p.cpu_percent >= 0 for p in processes)
    assert all(0 <= p.memory_percent <= 100 for p in processes)


def test_get_process_list_sort_by_memory() -> None:
    """Test process list sorting by memory."""
    processes = get_process_list(sort_by="memory", limit=10)

    if len(processes) > 1:
        # Check that processes are sorted by memory in descending order
        for i in range(len(processes) - 1):
            assert processes[i].memory_percent >= processes[i + 1].memory_percent


def test_get_process_list_sort_by_name() -> None:
    """Test process list sorting by name."""
    processes = get_process_list(sort_by="name", limit=10)

    if len(processes) > 1:
        # Check that processes are sorted by name alphabetically
        for i in range(len(processes) - 1):
            assert processes[i].name.lower() <= processes[i + 1].name.lower()


def test_get_network_interfaces() -> None:
    """Test get_network_interfaces function."""
    interfaces = get_network_interfaces()

    # Should have at least one interface (lo)
    assert len(interfaces) > 0

    for iface in interfaces:
        assert iface.name
        assert isinstance(iface.is_up, bool)
        assert len(iface.addresses) > 0

        for addr in iface.addresses:
            assert 'address' in addr
            assert 'netmask' in addr


def test_get_network_stats() -> None:
    """Test get_network_stats function."""
    stats = get_network_stats()

    assert stats.bytes_sent_mb >= 0
    assert stats.bytes_recv_mb >= 0
    assert stats.packets_sent >= 0
    assert stats.packets_recv >= 0
    assert stats.errin >= 0
    assert stats.errout >= 0
    assert stats.dropin >= 0
    assert stats.dropout >= 0
