@echo off
title JARVIS-APEX // Autonomous Desktop & Trading Command Center
color 0b

echo =====================================================================
echo                JARVIS-APEX // PERSONAL AI ASSISTANT
echo =====================================================================
echo [INFO] Initializing Jarvis Core Engine...
echo [INFO] Host: http://127.0.0.1:8000
echo [INFO] Press Ctrl+C to terminate the assistant.
echo.

python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload

pause
