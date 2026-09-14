#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
python3 -m venv .venv
.venv/bin/pip install --timeout 120 -r requirements.txt
VOICE_ATC_MOCK=1 .venv/bin/python smoke_test.py
