#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_dir="$(cd -- "$script_dir/.." && pwd)"

for path in SKILL.md agents/openai.yaml assets references scripts \
  assets/recamera-pro-runtime/librknnrt.so \
  assets/recamera-pro-runtime/SHA256SUMS \
  scripts/inspect_onnx.py scripts/create_calibration_dataset.py \
  scripts/convert_onnx.py scripts/compare_onnx_rknn.py; do
  [[ -e "$repo_dir/$path" ]] || {
    printf 'Missing required release path: %s\n' "$path" >&2
    exit 2
  }
done

for script in "$repo_dir"/scripts/*.sh; do
  bash -n "$script"
done

python3 -c '
import pathlib
import sys
for name in sys.argv[1:]:
    path = pathlib.Path(name)
    compile(path.read_text(encoding="utf-8"), str(path), "exec")
' "$repo_dir"/scripts/*.py

(cd -- "$repo_dir/assets/recamera-pro-runtime" && sha256sum --check SHA256SUMS)
file "$repo_dir/assets/recamera-pro-runtime/librknnrt.so" |
  grep -Eq 'ELF 64-bit.*ARM aarch64|ELF 64-bit.*ARM64' || {
    printf 'Bundled RKNN Runtime is not an aarch64 ELF.\n' >&2
    exit 3
  }

grep -q '^name: recamera-rknn-dev$' "$repo_dir/SKILL.md" || {
  printf 'SKILL.md has an unexpected or missing skill name.\n' >&2
  exit 4
}

if grep -R -E -n -i \
  --exclude=README.md --exclude=validate_release.sh \
  --exclude-dir=.git \
  'recamera\.1|BEGIN (RSA |OPENSSH )?PRIVATE KEY|api[_-]?key[[:space:]]*=' \
  "$repo_dir"; then
  printf 'Possible credential material found. Review before publishing.\n' >&2
  exit 5
fi

printf 'Release validation passed: %s\n' "$repo_dir"
