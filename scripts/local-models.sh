#!/usr/bin/env bash
set -euo pipefail
# Isolated server inherits this shell's network settings; existing Ollama stays intact.
export OLLAMA_HOST="127.0.0.1:11435"
export OLLAMA_NUM_PARALLEL=1
export OLLAMA_MAX_LOADED_MODELS=1
export CUDA_VISIBLE_DEVICES=-1
export ROCR_VISIBLE_DEVICES=-1
exec ollama serve
