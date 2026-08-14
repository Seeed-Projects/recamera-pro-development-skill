#!/usr/bin/env bash
set -euo pipefail

ENV_NAME="${RKNN_CONDA_ENV:-recamera-rknn-2.3.2}"
CONDA_ROOT="${CONDA_ROOT:-$HOME/.local/miniforge3}"
MINIFORGE_URL="${MINIFORGE_URL:-https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-x86_64.sh}"
BASE_URL="https://raw.githubusercontent.com/airockchip/rknn-toolkit2/v2.3.2/rknn-toolkit2/packages/x86_64"
REQ_URL="$BASE_URL/requirements_cp310-2.3.2.txt"
WHEEL_URL="$BASE_URL/rknn_toolkit2-2.3.2-cp310-cp310-manylinux_2_17_x86_64.manylinux2014_x86_64.whl"
MODE="${1:-setup}"

if [[ "$MODE" != setup && "$MODE" != --check ]]; then
  printf 'usage: %s [--check]\n' "$0" >&2
  exit 2
fi

if [[ "$(uname -m)" != "x86_64" ]]; then
  printf 'RKNN-Toolkit2 conversion wheel requires an x86_64 Linux/WSL host.\n' >&2
  exit 2
fi

load_conda() {
  if command -v conda >/dev/null 2>&1; then
    return
  fi
  for root in "$CONDA_ROOT" "$HOME/miniconda3" "$HOME/anaconda3"; do
    if [[ -f "$root/etc/profile.d/conda.sh" ]]; then
      # shellcheck disable=SC1090
      source "$root/etc/profile.d/conda.sh"
      return
    fi
  done
}

load_conda
if [[ "$MODE" == --check ]]; then
  command -v conda >/dev/null 2>&1 || { printf 'Conda is not available.\n' >&2; exit 4; }
  conda env list | awk '{print $1}' | grep -Fxq "$ENV_NAME" || {
    printf 'Conda environment is missing: %s\n' "$ENV_NAME" >&2
    exit 4
  }
  conda run -n "$ENV_NAME" python -c "
import importlib.metadata as metadata
expected = {'rknn-toolkit2': '2.3.2', 'onnx': '1.18.0', 'onnxruntime': '1.18.0'}
actual = {name: metadata.version(name) for name in expected}
print(actual)
if actual != expected:
    raise SystemExit(f'version mismatch: expected {expected}, got {actual}')
from rknn.api import RKNN
r = RKNN(verbose=False)
r.release()
print('RKNN conversion environment check passed')
"
  exit 0
fi

if ! command -v conda >/dev/null 2>&1; then
  tmp="$(mktemp -d)"
  trap 'rm -rf "$tmp"' EXIT
  printf 'Conda not found; installing Miniforge under %s\n' "$CONDA_ROOT"
  if command -v curl >/dev/null 2>&1; then
    curl -fL "$MINIFORGE_URL" -o "$tmp/miniforge.sh"
  elif command -v wget >/dev/null 2>&1; then
    wget -O "$tmp/miniforge.sh" "$MINIFORGE_URL"
  else
    printf 'Install curl or wget first.\n' >&2
    exit 3
  fi
  bash "$tmp/miniforge.sh" -b -p "$CONDA_ROOT"
  # shellcheck disable=SC1090
  source "$CONDA_ROOT/etc/profile.d/conda.sh"
fi

if ! conda env list | awk '{print $1}' | grep -Fxq "$ENV_NAME"; then
  conda create -y -n "$ENV_NAME" python=3.10 pip
fi

conda run -n "$ENV_NAME" python -m pip install --upgrade pip
conda run -n "$ENV_NAME" python -m pip install -r "$REQ_URL"
conda run -n "$ENV_NAME" python -m pip install "setuptools<81" "onnx==1.18.0" "onnxruntime==1.18.0"
conda run -n "$ENV_NAME" python -m pip install --force-reinstall --no-deps "$WHEEL_URL"
"$0" --check

printf '\nEnvironment ready. Activate with:\n  conda activate %s\n' "$ENV_NAME"
