import psutil
import time
from .models import SystemTelemetry

_last_net = psutil.net_io_counters()
_last_time = time.time()

def get_system_telemetry() -> SystemTelemetry:
    global _last_net, _last_time
    
    # CPU
    cpu_percent = psutil.cpu_percent(interval=None)
    cpu_freq = psutil.cpu_freq()
    cpu_freq_val = cpu_freq.current if cpu_freq else 0.0
    
    # RAM
    ram = psutil.virtual_memory()
    ram_percent = ram.percent
    ram_used_gb = round(ram.used / (1024 ** 3), 2)
    ram_total_gb = round(ram.total / (1024 ** 3), 2)
    
    # Disk (Root drive C: or current root)
    disk = psutil.disk_usage('/')
    disk_percent = disk.percent
    disk_free_gb = round(disk.free / (1024 ** 3), 1)
    
    # Battery (if available on laptop)
    battery = psutil.sensors_battery()
    battery_pct = round(battery.percent, 1) if battery else None
    is_charging = battery.power_plugged if battery else None
    
    # Network I/O
    now = time.time()
    net = psutil.net_io_counters()
    net_sent_mb = round((net.bytes_sent - _last_net.bytes_sent) / (1024 * 1024), 2)
    net_recv_mb = round((net.bytes_recv - _last_net.bytes_recv) / (1024 * 1024), 2)
    _last_net = net
    _last_time = now
    
    return SystemTelemetry(
        cpu_percent=cpu_percent,
        cpu_freq_current=round(cpu_freq_val, 1),
        ram_percent=ram_percent,
        ram_used_gb=ram_used_gb,
        ram_total_gb=ram_total_gb,
        disk_percent=disk_percent,
        disk_free_gb=disk_free_gb,
        battery_percent=battery_pct,
        is_charging=is_charging,
        network_sent_mb=max(0.0, net_sent_mb),
        network_recv_mb=max(0.0, net_recv_mb)
    )
