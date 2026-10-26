@echo off
rem Starts the AI test-case pipeline and opens the page. Needs Python 3.10+ and pipeline\.env with HAI_API_KEY.
cd /d "%~dp0.."
set PY=python
where python >nul 2>nul || set PY="%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
%PY% --version >nul 2>nul || (echo Python 3.10+ is needed: https://www.python.org/downloads/ & pause & exit /b 1)
if not exist pipeline\.env (
  copy pipeline\.env.example pipeline\.env >nul
  echo pipeline\.env was created. Put the team's API key after HAI_API_KEY= , save, then start again.
  notepad pipeline\.env
  exit /b 1
)
%PY% -c "import pypdf" 2>nul || %PY% -m pip install -q -r pipeline\requirements.txt
start "" http://localhost:8787
%PY% pipeline\server.py %*
