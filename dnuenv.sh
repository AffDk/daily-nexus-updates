dnuenv() {
  local key="$1"
  local val="$2"
  local env_file="/srv/daily_nexus_update/.env"

  if [ -z "$key" ] || [ -z "$val" ]; then
    echo "Usage: dnuenv SETTING_KEY NEW_VALUE"
    return 1
  fi

  if [ ! -f "$env_file" ]; then
    echo "ERROR: env file not found at $env_file"
    return 1
  fi

  if grep -q "^${key}=" "$env_file"; then
    sed -i "s|^${key}=.*|${key}=${val}|" "$env_file"
  else
    echo "${key}=${val}" >> "$env_file"
  fi

  local line
  line=$(grep -m1 "^${key}=" "$env_file")
  if [ -n "$line" ]; then
    echo "UPDATED: $line"
    return 0
  fi

  echo "ERROR: failed to update ${key}"
  return 1
}

# dnuenvr = update .env then restart active runtime if detected.
dnuenvr() {
  local key="$1"
  local val="$2"
  local app_dir="/srv/daily_nexus_update"

  dnuenv "$key" "$val" || return 1

  if command -v systemctl >/dev/null 2>&1 && systemctl list-unit-files | grep -q '^daily-nexus\.service'; then
    echo "RESTART: systemd daily-nexus.service"
    if systemctl restart daily-nexus.service; then
      systemctl --no-pager --full status daily-nexus.service | head -n 8
      return 0
    fi
    echo "WARN: systemd restart failed"
  fi

  if command -v docker >/dev/null 2>&1 && command -v docker-compose >/dev/null 2>&1; then
    if [ -f "$app_dir/docker-compose.yml" ]; then
      echo "RESTART: docker-compose web"
      (cd "$app_dir" && docker-compose up -d web) && (cd "$app_dir" && docker-compose ps)
      return 0
    fi
  fi

  if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    if [ -f "$app_dir/docker-compose.yml" ]; then
      echo "RESTART: docker compose web"
      (cd "$app_dir" && docker compose up -d web) && (cd "$app_dir" && docker compose ps)
      return 0
    fi
  fi

  echo "INFO: no managed service detected."
  echo "INFO: cron runs will pick up new settings automatically on next run."
  echo "INFO: run manually now -> cd /srv/daily_nexus_update && /root/.local/bin/uv run python -m app.cli --topics tech finance crypto geopolitics"
  return 0
}