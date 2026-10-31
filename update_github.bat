@echo off
setlocal enabledelayedexpansion
title J.A.R.V.I.S. GitHub Auto-Sync Engine
cd /d "%~dp0"

color 0A
echo ============================================================
echo         J.A.R.V.I.S. GITHUB AUTO-SYNC & BACKUP ENGINE
echo ============================================================
echo Repo: https://github.com/rkv3232-cell/JARVIS-AI-Workstation
echo.

echo [1/4] Checking repository status...
git status --short
echo.

echo [2/4] Staging all project changes...
git add -A
echo.

git diff --cached --quiet
if %errorlevel% equ 0 (
    echo [INFO] No new changes detected to commit.
    echo Checking for any unpushed commits...
    git push origin main
    goto finish
)

set /p custom_msg="Enter commit message (Press ENTER for auto-timestamp): "
if "!custom_msg!"=="" (
    for /f "tokens=2 delims==" %%I in ('wmic os get localdatetime /value 2^>nul') do set dt=%%I
    if "!dt!"=="" (
        set COMMIT_MSG=Auto-sync: %date% %time% - J.A.R.V.I.S. Workstation
    ) else (
        set YYYY=!dt:~0,4!
        set MM=!dt:~4,2!
        set DD=!dt:~6,2!
        set HH=!dt:~8,2!
        set Min=!dt:~10,2!
        set COMMIT_MSG=Update: !YYYY!-!MM!-!DD! !HH!:!Min! - J.A.R.V.I.S. Workstation Sync
    )
) else (
    set COMMIT_MSG=!custom_msg!
)

echo.
echo [3/4] Committing: "!COMMIT_MSG!"
git commit -m "!COMMIT_MSG!"
echo.

echo [4/4] Pushing changes to GitHub (origin/main)...
git push origin main
if %errorlevel% equ 0 (
    echo.
    echo ============================================================
    echo [SUCCESS] Code successfully updated on GitHub!
    echo Repo: https://github.com/rkv3232-cell/JARVIS-AI-Workstation
    echo ============================================================
) else (
    echo.
    echo [ERROR] Git push failed. Please check your internet connection or git credentials.
)

:finish
echo.
echo Press any key to exit...
pause >nul
