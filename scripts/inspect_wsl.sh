#!/usr/bin/env bash
set -euo pipefail

printf 'host_uname=%s\n' "$(uname -a)"
printf 'host_arch=%s\n' "$(uname -m)"
printf 'wsl=%s\n' "${WSL_DISTRO_NAME:-no}"

for tool in codex conda cmake ninja pkg-config git curl wget file; do
  if command -v "$tool" >/dev/null 2>&1; then
    printf '%s=%s\n' "$tool" "$(command -v "$tool")"
  else
    printf '%s=MISSING\n' "$tool"
  fi
done

if command -v conda >/dev/null 2>&1; then
  conda env list
fi

printf 'RECAMERA_SYSROOT=%s\n' "${RECAMERA_SYSROOT:-UNSET}"
printf 'RECAMERA_CROSS_PREFIX=%s\n' "${RECAMERA_CROSS_PREFIX:-UNSET}"
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
bundled_rknnrt="$script_dir/../assets/recamera-pro-runtime/librknnrt.so"
printf 'bundled_RECAMERA_RKNNRT=%s\n' "$bundled_rknnrt"
printf 'target_RKNN_runtime=/oem/usr/lib/librknnrt.so\n'

if [[ -f "$bundled_rknnrt" ]]; then
  file "$bundled_rknnrt"
  (cd -- "$(dirname -- "$bundled_rknnrt")" && sha256sum --check SHA256SUMS)
else
  printf 'bundled_rknnrt=MISSING\n'
fi

if [[ -n "${RECAMERA_SYSROOT:-}" && -d "$RECAMERA_SYSROOT" ]]; then
  for pc in gstreamer-1.0 gstreamer-app-1.0 gstreamer-rtsp-server-1.0 alsa; do
    match="$(find "$RECAMERA_SYSROOT" -type f -name "$pc.pc" -print -quit 2>/dev/null || true)"
    printf 'sysroot_pc_%s=%s\n' "$pc" "${match:-MISSING}"
  done
fi

if [[ -n "${RECAMERA_CROSS_PREFIX:-}" ]]; then
  compiler="${RECAMERA_CROSS_PREFIX}g++"
  if [[ -x "$compiler" ]]; then
    "$compiler" --version | head -n 1
    "$compiler" -dumpmachine
  else
    printf 'cross_compiler=MISSING:%s\n' "$compiler"
  fi
fi
