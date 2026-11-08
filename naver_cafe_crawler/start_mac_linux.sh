#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
[ -d .venv ] || python3 -m venv .venv
source .venv/bin/activate
pip install -q -r requirements.txt
python -m playwright install chromium
[ -f .env ] || cp .env.example .env
streamlit run app.py
