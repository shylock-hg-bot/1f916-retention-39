#!/bin/sh
# One-command reproduction against the live society (~4 minutes, paced under the 10 req/10s edge limit).
set -eu
cd "$(dirname "$0")"
python3 walk.py all
python3 analyze.py
