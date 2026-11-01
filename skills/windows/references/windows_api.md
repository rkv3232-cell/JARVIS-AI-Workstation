# Windows Controller Safety Reference

1. Never terminate critical Windows kernel or system processes (csrss.exe, wininit.exe, lsass.exe).
2. Always log hardware mutations to ActivityLogger.
3. High-impact operations must route through CentralPermissionManager.

