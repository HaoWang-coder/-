@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

set "PYTHON_EXE=%LocalAppData%\Programs\Python\Python311\python.exe"
if not exist "%PYTHON_EXE%" (
    echo 尚未安装 Python 3.11。
    echo 请先从 Python 官方网站安装 64 位 Python 3.11，并勾选 Add Python to PATH。
    start "" "https://www.python.org/downloads/windows/"
    pause
    exit /b 1
)

echo 正在安装综合平台依赖，请稍候……
"%PYTHON_EXE%" -m pip install --upgrade pip
"%PYTHON_EXE%" -m pip install -r "%~dp0requirements-unified.txt"
if errorlevel 1 (
    echo 依赖安装失败，请检查网络后重试。
    pause
    exit /b 1
)
echo.
echo 运行环境安装完成。
pause
