#!/usr/bin/env bash
set -euo pipefail

SOURCE_DIR="${1:-.}"
BUILD_DIR="${2:-$SOURCE_DIR/build-recamera}"
: "${RECAMERA_SYSROOT:?Set RECAMERA_SYSROOT to the target sysroot}"
: "${RECAMERA_CROSS_PREFIX:?Set RECAMERA_CROSS_PREFIX including the trailing dash}"
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
skill_dir="$(cd -- "$script_dir/.." && pwd)"
bundled_rknnrt="$skill_dir/assets/recamera-pro-runtime/librknnrt.so"
checksum_file="$skill_dir/assets/recamera-pro-runtime/SHA256SUMS"

if [[ -n "${RECAMERA_RKNNRT:-}" && "$RECAMERA_RKNNRT" != "$bundled_rknnrt" ]]; then
  printf 'RECAMERA_RKNNRT overrides are not permitted; use bundled RKNN Runtime 2.3.2.\n' >&2
  exit 2
fi
if [[ -n "${RECAMERA_RKNN_RUNTIME_DIR:-}" && "$RECAMERA_RKNN_RUNTIME_DIR" != /oem/usr/lib ]]; then
  printf 'RKNN runtime directory overrides are not permitted for production reCamera Pro.\n' >&2
  exit 2
fi
RECAMERA_RKNNRT="$bundled_rknnrt"
RECAMERA_RKNN_RUNTIME_DIR=/oem/usr/lib

for path in "$RECAMERA_SYSROOT" "$RECAMERA_RKNNRT" "$checksum_file"; do
  [[ -e "$path" ]] || { printf 'Missing required path: %s\n' "$path" >&2; exit 2; }
done
(cd -- "$(dirname -- "$checksum_file")" && sha256sum --check --status "$(basename -- "$checksum_file")") || {
  printf 'Bundled RKNN Runtime checksum mismatch. Refusing to build.\n' >&2
  exit 5
}

CXX="${RECAMERA_CROSS_PREFIX}g++"
READELF="${RECAMERA_CROSS_PREFIX}readelf"
command -v "$CXX" >/dev/null 2>&1 || { printf 'Compiler not found: %s\n' "$CXX" >&2; exit 3; }
[[ "$($CXX -dumpmachine)" == aarch64* ]] || { printf 'Compiler target is not aarch64: %s\n' "$($CXX -dumpmachine)" >&2; exit 4; }
file "$RECAMERA_RKNNRT" | grep -Eq 'ARM aarch64|ARM64' || { printf 'RKNN runtime is not an aarch64 ELF.\n' >&2; exit 5; }

export PKG_CONFIG_SYSROOT_DIR="$RECAMERA_SYSROOT"
export PKG_CONFIG_LIBDIR="$RECAMERA_SYSROOT/usr/lib/aarch64-linux-gnu/pkgconfig:$RECAMERA_SYSROOT/usr/lib64/pkgconfig:$RECAMERA_SYSROOT/usr/lib/pkgconfig:$RECAMERA_SYSROOT/usr/share/pkgconfig"
unset PKG_CONFIG_PATH

cmake -S "$SOURCE_DIR" -B "$BUILD_DIR" -G Ninja \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_SYSTEM_NAME=Linux \
  -DCMAKE_SYSTEM_PROCESSOR=aarch64 \
  -DCMAKE_SYSROOT="$RECAMERA_SYSROOT" \
  -DCMAKE_C_COMPILER="${RECAMERA_CROSS_PREFIX}gcc" \
  -DCMAKE_CXX_COMPILER="$CXX" \
  -DRECAMERA_RKNNRT="$RECAMERA_RKNNRT" \
  -DRECAMERA_RKNN_RUNTIME_DIR="$RECAMERA_RKNN_RUNTIME_DIR"
cmake --build "$BUILD_DIR"

binary="$BUILD_DIR/recamera_rknn_gst"
file "$binary"
"$READELF" -d "$binary"
"$READELF" -d "$binary" | grep -q 'librknnrt.so' || { printf 'Missing librknnrt.so dependency.\n' >&2; exit 6; }
"$READELF" -d "$binary" | grep -Fq "$RECAMERA_RKNN_RUNTIME_DIR" || { printf 'Missing RKNN runtime path: %s\n' "$RECAMERA_RKNN_RUNTIME_DIR" >&2; exit 7; }
if "$READELF" -d "$binary" | grep -Eqi 'x86_64|build-recamera|/home/|/mnt/[a-z]/'; then
  printf 'Host/build path leaked into dynamic section.\n' >&2
  exit 8
fi
printf 'Built and validated: %s\n' "$binary"
