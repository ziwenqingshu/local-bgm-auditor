@echo off
setlocal
cd /d "%~dp0"
echo Windows - installing Python 3.12 local environment
where uv >nul 2>&1
if %errorlevel%==0 goto use_uv
py -3.12 --version >nul 2>&1
if %errorlevel%==0 goto use_python
where winget >nul 2>&1
if errorlevel 1 goto no_python
winget install --id Python.Python.3.12 -e --accept-package-agreements --accept-source-agreements
if errorlevel 1 goto fail
echo Please reopen the terminal and run install.bat again.
exit /b 0
:use_uv
uv python install 3.12
if errorlevel 1 goto fail
uv venv --python 3.12 .venv --allow-existing
if errorlevel 1 goto fail
set "PIP_CMD=uv pip install --python .venv\Scripts\python.exe"
goto ffmpeg
:use_python
py -3.12 -m venv .venv
if errorlevel 1 goto fail
.venv\Scripts\python.exe -m pip install --upgrade pip
if errorlevel 1 goto fail
set "PIP_CMD=.venv\Scripts\python.exe -m pip install"
:ffmpeg
where ffmpeg >nul 2>&1
if errorlevel 1 goto install_ffmpeg
where ffprobe >nul 2>&1
if errorlevel 1 goto install_ffmpeg
goto dependencies
:install_ffmpeg
where winget >nul 2>&1
if errorlevel 1 goto no_ffmpeg
winget install --id Gyan.FFmpeg -e --accept-package-agreements --accept-source-agreements
if errorlevel 1 goto fail
echo FFmpeg installed. Reopen the terminal and run install.bat again to refresh PATH.
exit /b 0
:dependencies
set "REQ=requirements.txt"
if /i "%~1"=="--with-shazam" set "REQ=requirements-shazam.txt"
%PIP_CMD% -r %REQ%
if errorlevel 1 goto fail
.venv\Scripts\python.exe scripts\check_environment.py
if errorlevel 1 goto fail
echo Installation complete. Run start.bat
exit /b 0
:no_python
echo Please install Python 3.12 from python.org or install uv, then retry.
exit /b 1
:no_ffmpeg
echo Please install FFmpeg including ffprobe and add its bin directory to PATH.
exit /b 1
:fail
echo Installation failed. Read the preceding error and retry.
exit /b 1
