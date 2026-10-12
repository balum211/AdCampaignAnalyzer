#!/usr/bin/env bash
# One-click local run on macOS / Linux.
set -e
cd "$(dirname "$0")"
[ -d .venv ] || python3 -m venv .venv
source .venv/bin/activate
pip install -q --upgrade pip
pip install -q -r requirements.txt
streamlit run app.py
