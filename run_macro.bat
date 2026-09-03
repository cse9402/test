@echo off
cd /d "%~dp0"
call .venv\Scripts\activate.bat
python main.py --task demolition_report_case --input data\demolition_report_case_sample.csv --attach
echo.
echo 끝났습니다. 창을 닫으려면 아무 키나 누르세요.
pause >nul
