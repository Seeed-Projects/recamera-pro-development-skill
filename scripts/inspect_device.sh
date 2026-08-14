#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  printf 'usage: %s [USER@]HOST\n' "$0" >&2
  exit 2
fi

target="$1"
ssh "$target" 'sh -s' <<'REMOTE'
set -u
printf '== system ==\n'
uname -a
cat /etc/os-release 2>/dev/null || true
ldd --version 2>&1 | head -n 2 || true

printf '\n== RKNN runtime ==\n'
find /oem /userdata /usr /lib \( -type f -o -type l \) 2>/dev/null |
  grep -E '/librknn(rt)?\.so([.0-9]*)?$' | sort || true

printf '\n== video ==\n'
v4l2-ctl --list-devices 2>&1 || true
v4l2-ctl -d /dev/video13 --list-formats-ext 2>&1 || true

printf '\n== ALSA ==\n'
cat /proc/asound/cards 2>&1 || true
cat /proc/asound/pcm 2>&1 || true
arecord -L 2>&1 || true
aplay -L 2>&1 || true
amixer -c 0 scontrols 2>&1 || true

printf '\n== audio device owners ==\n'
for process in /proc/[0-9]*; do
  for descriptor in "$process"/fd/*; do
    target_path="$(readlink "$descriptor" 2>/dev/null || true)"
    case "$target_path" in
      /dev/snd/*) printf '%s %s\n' "${process#/proc/}" "$target_path" ;;
    esac
  done
done

printf '\n== GStreamer ==\n'
gst-launch-1.0 --version 2>&1 || true
for element in v4l2src videoconvert appsink alsasrc alsasink audioconvert audioresample \
  opusenc rtpopuspay h264parse rtph264pay rtspsrc rtspclientsink; do
  if gst-inspect-1.0 "$element" >/dev/null 2>&1; then
    printf '%s=available\n' "$element"
  else
    printf '%s=MISSING\n' "$element"
  fi
done
find /oem /usr /lib \( -type f -o -type l \) 2>/dev/null |
  grep -E '/libgstrtspserver-1\.0\.so([.0-9]*)?$' | sort || true

printf '\n== media listeners ==\n'
ss -lntup 2>/dev/null | grep -E ':(554|5554|8554|8555)[[:space:]]' || true
REMOTE
