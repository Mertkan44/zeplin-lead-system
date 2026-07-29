#!/usr/bin/env bash
set -euo pipefail

REPO="${1:-Mertkan44/zeplin-lead-system}"
ENV_FILE="${ENV_FILE:-.env}"

if ! command -v gh >/dev/null 2>&1; then
  echo "gh CLI bulunamadı. Önce GitHub CLI kurulu olmalı." >&2
  exit 1
fi

if ! gh auth status >/dev/null 2>&1; then
  echo "GitHub CLI login değil. Önce şunu çalıştır:" >&2
  echo "  gh auth login" >&2
  exit 1
fi

if [[ ! -f "$ENV_FILE" ]]; then
  echo "$ENV_FILE bulunamadı." >&2
  exit 1
fi

read_env_value() {
  local key="$1"
  local line
  line="$(grep -E "^${key}=" "$ENV_FILE" | tail -n 1 || true)"
  if [[ -z "$line" ]]; then
    return 1
  fi
  local value="${line#*=}"
  value="${value%$'\r'}"
  value="${value#\"}"
  value="${value%\"}"
  value="${value#\'}"
  value="${value%\'}"
  printf '%s' "$value"
}

set_secret_from_env() {
  local key="$1"
  local value
  if ! value="$(read_env_value "$key")" || [[ -z "$value" ]]; then
    echo "$key eksik, atlandı." >&2
    return 1
  fi
  printf '%s' "$value" | gh secret set "$key" --repo "$REPO"
  echo "$key yüklendi."
}

set_secret_from_env SUPABASE_URL
set_secret_from_env SUPABASE_SERVICE_ROLE_KEY
set_secret_from_env DEEPSEEK_API_KEY

echo "GitHub Actions secrets hazır: $REPO"
