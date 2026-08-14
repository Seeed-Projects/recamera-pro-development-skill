#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
skill_dir="$(cd -- "$script_dir/.." && pwd)"
destination_root="$HOME/.agents/skills"
destination="$destination_root/recamera-rknn-dev"
mkdir -p "$destination_root"
if [[ -e "$destination" ]]; then
  printf 'Destination already exists: %s\nMove it aside or remove it explicitly, then rerun.\n' "$destination" >&2
  exit 2
fi
mkdir -p "$destination"
cp -a "$skill_dir/SKILL.md" "$skill_dir/agents" "$skill_dir/assets" \
  "$skill_dir/references" "$skill_dir/scripts" "$destination/"
chmod +x "$destination"/scripts/*.sh "$destination"/scripts/*.py
printf 'Installed Codex Skill at %s\nRestart Codex if needed, then invoke $recamera-rknn-dev.\n' "$destination"
