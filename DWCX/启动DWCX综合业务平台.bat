@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "PYTHONDONTWRITEBYTECODE=1"

set "PYTHON_EXE="
where python >nul 2>nul && set "PYTHON_EXE=python"
if not defined PYTHON_EXE if exist "%LocalAppData%\Programs\Python\Python311\python.exe" set "PYTHON_EXE=%LocalAppData%\Programs\Python\Python311\python.exe"

if not defined PYTHON_EXE (
    echo 未找到 Python 3.11，请先双击“安装DWCX运行环境.bat”。
    pause
    exit /b 1
)

%PYTHON_EXE% "%~dp0dwcx_unified_app.py"
if errorlevel 1 pause
