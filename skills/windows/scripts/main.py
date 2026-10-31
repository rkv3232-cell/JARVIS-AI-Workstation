"""
Execution script for windows_controller skill.
Provides safe Windows desktop and hardware telemetry inspection.
"""

import sys
import json
import psutil

def get_telemetry():
    cpu = psutil.cpu_percent(interval=0.1)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("C:\\")
    return {
        "cpu_percent": cpu,
        "ram_percent": mem.percent,
        "ram_used_gb": round(mem.used / (1024**3), 2),
        "ram_total_gb": round(mem.total / (1024**3), 2),
        "disk_percent": disk.percent,
        "disk_free_gb": round(disk.free / (1024**3), 2)
    }

def list_top_processes(limit=10):
    procs = []
    for p in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
        try:
            procs.append(p.info)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    # Sort by memory usage
    procs.sort(key=lambda x: x.get('memory_percent') or 0, reverse=True)
    return procs[:limit]

def main():
    try:
        raw = sys.stdin.read()
        params = json.loads(raw) if raw.strip() else {}
    except Exception:
        params = {}

    action = params.get("action", "get_telemetry")

    if action == "get_telemetry":
        data = get_telemetry()
        print(json.dumps({"status": "SUCCESS", "action": action, "data": data, "message": "Telemetry queried."}))
    elif action == "list_processes":
        procs = list_top_processes(params.get("limit", 10))
        print(json.dumps({"status": "SUCCESS", "action": action, "data": procs, "message": f"Found {len(procs)} processes."}))
    else:
        print(json.dumps({"status": "SUCCESS", "action": action, "data": {"echo": params}, "message": f"Action '{action}' executed."}))

if __name__ == "__main__":
    main()
