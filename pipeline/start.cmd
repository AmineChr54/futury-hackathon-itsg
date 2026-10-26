@echo off
rem Starts the AI test-case pipeline and opens the page. Needs Python 3.10+ and pipeline\.env with HAI_API_KEY.
cd /d "%~dp0.."
set PY=python
where python >nul 2>nul || set PY="%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
%PY% -c "import pypdf" 2>nul || %PY% -m pip install -q -r pipeline\requirements.txt
start "" http://localhost:8787
%PY% pipeline\server.py %*
