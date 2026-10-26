#!/usr/bin/env bash
cd "$(dirname "$0")"
[ -x .venv/bin/python ] || python3 -m venv .venv || exit 1
.venv/bin/python -m pip install -r requirements.txt || exit 1
.venv/bin/python app.py
