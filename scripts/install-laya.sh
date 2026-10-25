#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -m venv .venv-laya
.venv-laya/bin/python -m pip install 'torch==2.14.1' --index-url https://download.pytorch.org/whl/cpu
.venv-laya/bin/python -m pip install 'laya[serve]==0.4.7'
touch .venv-laya/.genesis-installed
