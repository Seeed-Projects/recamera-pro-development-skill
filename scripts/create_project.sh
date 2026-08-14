#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  printf 'usage: %s PROJECT_DIR\n' "$0" >&2
  exit 2
fi

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
skill_dir="$(cd -- "$script_dir/.." && pwd)"
destination="$1"
header_url="https://raw.githubusercontent.com/airockchip/rknn-toolkit2/v2.3.2/rknpu2/runtime/Linux/librknn_api/include/rknn_api.h"

if [[ -e "$destination" ]]; then
  printf 'Destination already exists: %s\n' "$destination" >&2
  exit 3
fi

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
header="$tmp/rknn_api.h"
if command -v curl >/dev/null 2>&1; then
  curl -fL "$header_url" -o "$header"
elif command -v wget >/dev/null 2>&1; then
  wget -O "$header" "$header_url"
else
  printf 'curl or wget is required to fetch rknn_api.h from RKNN-Toolkit2 v2.3.2.\n' >&2
  exit 4
fi
cp -a "$skill_dir/assets/rknn-gst-app" "$destination"
mv "$header" "$destination/include/rknn_api.h"
printf 'Created project at %s\n' "$destination"
