from __future__ import annotations

import ctypes
import os
import shutil
from pathlib import Path

import psutil


class _MEMORYSTATUSEX(ctypes.Structure):
    _fields_ = [
        ("dwLength", ctypes.c_ulong),
        ("dwMemoryLoad", ctypes.c_ulong),
        ("ullTotalPhys", ctypes.c_ulonglong),
        ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong),
        ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong),
        ("ullAvailVirtual", ctypes.c_ulonglong),
        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]


class _PROCESS_MEMORY_COUNTERS(ctypes.Structure):
    _fields_ = [
        ("cb", ctypes.c_ulong),
        ("PageFaultCount", ctypes.c_ulong),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
    ]


def system_memory_percent() -> float | None:
    if os.name == "nt":
        stat = _MEMORYSTATUSEX()
        stat.dwLength = ctypes.sizeof(stat)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
            return None
        return float(stat.dwMemoryLoad)
    try:
        meminfo = Path("/proc/meminfo").read_text(encoding="utf-8")
    except OSError:
        return None
    values: dict[str, int] = {}
    for line in meminfo.splitlines():
        parts = line.split(":")
        if len(parts) != 2:
            continue
        key = parts[0].strip()
        amount = parts[1].strip().split()[0]
        values[key] = int(amount)
    total = values.get("MemTotal")
    available = values.get("MemAvailable")
    if not total or available is None:
        return None
    return round((1 - available / total) * 100, 2)


def disk_usage_percent(path: Path) -> tuple[float, float] | None:
    try:
        usage = shutil.disk_usage(path)
    except OSError:
        return None
    if usage.total <= 0:
        return None
    used_percent = round(((usage.total - usage.free) / usage.total) * 100, 2)
    free_gb = round(usage.free / (1024**3), 2)
    return used_percent, free_gb


def process_memory_mb(pid: int) -> float | None:
    if pid <= 0:
        return None
    if os.name == "nt":
        process_handle = ctypes.windll.kernel32.OpenProcess(0x1000 | 0x0400, False, pid)
        if not process_handle:
            return None
        try:
            counters = _PROCESS_MEMORY_COUNTERS()
            counters.cb = ctypes.sizeof(counters)
            if not ctypes.windll.psapi.GetProcessMemoryInfo(process_handle, ctypes.byref(counters), counters.cb):
                return None
            return round(counters.WorkingSetSize / (1024 * 1024), 2)
        finally:
            ctypes.windll.kernel32.CloseHandle(process_handle)
    proc_status = Path(f"/proc/{pid}/status")
    try:
        for line in proc_status.read_text(encoding="utf-8").splitlines():
            if line.startswith("VmRSS:"):
                kb = int(line.split()[1])
                return round(kb / 1024, 2)
    except OSError:
        return None
    return None


def system_cpu_percent() -> float | None:
    try:
        # non-blocking call for CPU usage over the time since last call
        return float(psutil.cpu_percent(interval=None))
    except Exception:
        return None
