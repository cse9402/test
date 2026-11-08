@echo off
chcp 65001 > nul
cd /d "%~dp0"
if not exist .venv (
  echo [1/3] 가상환경 생성 중...
  py -3.11 -m venv .venv || python -m venv .venv
)
call .venv\Scripts\activate.bat
echo [2/3] 패키지 확인 중...
pip install -q -r requirements.txt
python -m playwright install chromium
if not exist .env copy .env.example .env > nul
echo [3/3] 프로그램을 시작합니다. 브라우저에 화면이 열립니다.
streamlit run app.py
pause
