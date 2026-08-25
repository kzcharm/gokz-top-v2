#!/usr/bin/env bash

confirm_action() {
  local prompt="$1"
  local default_answer="${2:-no}"
  local response=""
  local prompt_suffix="[y/N]"

  if [[ "$default_answer" == "yes" ]]; then
    prompt_suffix="[Y/n]"
  fi

  while true; do
    read -r -p "$prompt $prompt_suffix " response
    case "$response" in
      [yY]|[yY][eE][sS])
        return 0
        ;;
      "")
        [[ "$default_answer" == "yes" ]] && return 0
        return 1
        ;;
      [nN]|[nN][oO])
        return 1
        ;;
      *)
        echo "Please answer y or n."
        ;;
    esac
  done
}

describe_pid_command() {
  local pid="$1"
  ps -p "$pid" -o command= 2>/dev/null | sed 's/^[[:space:]]*//' || true
}

kill_port_processes_with_confirmation() {
  local port="$1"
  local address_label="$2"
  local pids=()
  local pid=""

  if ! command -v lsof >/dev/null 2>&1; then
    echo "Warning: lsof is unavailable, cannot inspect port $port usage."
    return 0
  fi

  while IFS= read -r pid; do
    [[ -n "$pid" ]] && pids+=("$pid")
  done < <(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null | sort -u)

  if [[ "${#pids[@]}" -eq 0 ]]; then
    return 0
  fi

  echo "Address already in use for $address_label."
  for pid in "${pids[@]}"; do
    local command=""
    command="$(describe_pid_command "$pid")"
    if [[ -n "$command" ]]; then
      echo "  PID $pid: $command"
    else
      echo "  PID $pid"
    fi
  done

  if ! confirm_action "Kill the process(es) listening on $address_label?" yes; then
    echo "Aborting because $address_label is already in use."
    exit 1
  fi

  for pid in "${pids[@]}"; do
    if kill "$pid" 2>/dev/null; then
      echo "Sent SIGTERM to PID $pid."
    fi
  done

  for _ in {1..10}; do
    local remaining=0
    for pid in "${pids[@]}"; do
      if kill -0 "$pid" 2>/dev/null; then
        remaining=1
        break
      fi
    done
    [[ "$remaining" -eq 0 ]] && return 0
    sleep 1
  done

  local stubborn_pids=()
  for pid in "${pids[@]}"; do
    if kill -0 "$pid" 2>/dev/null; then
      stubborn_pids+=("$pid")
    fi
  done

  if [[ "${#stubborn_pids[@]}" -eq 0 ]]; then
    return 0
  fi

  echo "Process(es) still listening on $address_label after SIGTERM."
  for pid in "${stubborn_pids[@]}"; do
    local command=""
    command="$(describe_pid_command "$pid")"
    if [[ -n "$command" ]]; then
      echo "  PID $pid: $command"
    else
      echo "  PID $pid"
    fi
  done

  if ! confirm_action "Force kill the remaining process(es) on $address_label?" yes; then
    echo "Aborting because $address_label is still in use."
    exit 1
  fi

  for pid in "${stubborn_pids[@]}"; do
    if kill -9 "$pid" 2>/dev/null; then
      echo "Sent SIGKILL to PID $pid."
    fi
  done
}

add_project_candidate() {
  local candidate="$1"
  [[ -z "$candidate" ]] && return 0
  for existing in "${PROJECT_CANDIDATES[@]-}"; do
    [[ "$existing" == "$candidate" ]] && return 0
  done
  PROJECT_CANDIDATES+=("$candidate")
}

read_dotenv_value() {
  local key="$1"
  [[ ! -f "$ROOT_DIR/.env" ]] && return 0
  local value=""
  value="$(awk -F= -v key="$key" '$1==key {print substr($0, index($0, "=") + 1)}' "$ROOT_DIR/.env" | head -n1)"
  value="${value#\"}"
  value="${value%\"}"
  printf '%s' "$value"
}

ensure_docker_cli() {
  if command -v docker >/dev/null 2>&1; then
    return 0
  fi

  local docker_candidate=""
  for docker_candidate in \
    /usr/local/bin/docker \
    /opt/homebrew/bin/docker \
    /Applications/Docker.app/Contents/Resources/bin/docker
  do
    if [[ -x "$docker_candidate" ]]; then
      export PATH="$(dirname "$docker_candidate"):$PATH"
      return 0
    fi
  done

  return 1
}

ensure_compose_local_defaults() {
  if [[ -n "${FRONTEND_HOST_RULE-}" ]]; then
    return 0
  fi

  local frontend_hostname=""
  frontend_hostname="${FRONTEND_HOSTNAME-}"
  if [[ -z "$frontend_hostname" ]]; then
    frontend_hostname="$(read_dotenv_value FRONTEND_HOSTNAME)"
  fi

  if [[ -n "$frontend_hostname" ]]; then
    export FRONTEND_HOST_RULE="Host(\`$frontend_hostname\`)"
  fi
}

is_local_db_container() {
  local container_id="$1"
  local service_label=""
  local working_dir_label=""
  local project_label=""

  service_label="$(docker inspect --format '{{ index .Config.Labels "com.docker.compose.service" }}' "$container_id" 2>/dev/null || true)"
  [[ "$service_label" != "db" ]] && return 1

  working_dir_label="$(docker inspect --format '{{ index .Config.Labels "com.docker.compose.project.working_dir" }}' "$container_id" 2>/dev/null || true)"
  if [[ -n "$working_dir_label" && "$working_dir_label" == "$ROOT_DIR" ]]; then
    return 0
  fi

  project_label="$(docker inspect --format '{{ index .Config.Labels "com.docker.compose.project" }}' "$container_id" 2>/dev/null || true)"
  for candidate in "${PROJECT_CANDIDATES[@]-}"; do
    [[ -n "$candidate" && "$project_label" == "$candidate" ]] && return 0
  done

  return 1
}

prepare_backend_dev() {
  local geoipupdate_account_id_value=""
  local geoipupdate_license_key_value=""
  local local_db_container_id=""
  local db_status=""

  ensure_compose_local_defaults

  if ! ensure_docker_cli; then
    echo "Error: docker is required to run the local database."
    exit 1
  fi

  if ! docker info >/dev/null 2>&1; then
    echo "Error: docker daemon is not running. Start Docker and retry."
    exit 1
  fi

  PROJECT_CANDIDATES=()

  if [[ -n "${COMPOSE_PROJECT_NAME-}" ]]; then
    add_project_candidate "$COMPOSE_PROJECT_NAME"
  fi

  if [[ -f "$ROOT_DIR/.env" ]]; then
    local stack_name=""
    stack_name="$(awk -F= '$1=="STACK_NAME"{print $2}' "$ROOT_DIR/.env" | head -n1)"
    stack_name="${stack_name#\"}"
    stack_name="${stack_name%\"}"
    add_project_candidate "$stack_name"
  fi

  add_project_candidate "$(basename "$ROOT_DIR")"

  local_db_container_id="$(docker compose ps -q db 2>/dev/null || true)"
  if [[ -z "$local_db_container_id" ]]; then
    local_db_container_id="$(docker ps -q --filter "label=com.docker.compose.service=db" --filter "label=com.docker.compose.project.working_dir=$ROOT_DIR" | head -n1 || true)"
  fi
  if [[ -z "$local_db_container_id" ]]; then
    local candidate=""
    for candidate in "${PROJECT_CANDIDATES[@]-}"; do
      [[ -z "$candidate" ]] && continue
      local_db_container_id="$(docker ps -q --filter "label=com.docker.compose.service=db" --filter "label=com.docker.compose.project=$candidate" | head -n1 || true)"
      [[ -n "$local_db_container_id" ]] && break
    done
  fi

  local container_id=""
  while IFS= read -r container_id; do
    [[ -z "$container_id" ]] && continue
    if [[ -n "$local_db_container_id" && "$container_id" == "$local_db_container_id" ]]; then
      continue
    fi
    if is_local_db_container "$container_id"; then
      continue
    fi

    local container_name=""
    container_name="$(docker inspect --format '{{.Name}}' "$container_id" | sed 's#^/##')"
    if ! confirm_action "Port 5432 is already used by container $container_name. Stop it?"; then
      echo "Aborting because port 5432 is already in use."
      exit 1
    fi
    echo "Stopping container on port 5432: $container_name"
    docker stop --time 20 "$container_id" >/dev/null
  done < <(docker ps -q --filter "publish=5432")

  local start_db="true"
  if [[ -n "$local_db_container_id" ]]; then
    db_status="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$local_db_container_id" 2>/dev/null || true)"
    if [[ "$db_status" == "healthy" || "$db_status" == "running" ]]; then
      start_db="false"
      echo "Local db already running."
    fi
  fi

  if [[ "$start_db" == "true" ]]; then
    kill_port_processes_with_confirmation "5432" "127.0.0.1:5432"
  fi

  local services=(db)
  geoipupdate_account_id_value="${GEOIPUPDATE_ACCOUNT_ID-}"
  if [[ -z "$geoipupdate_account_id_value" ]]; then
    geoipupdate_account_id_value="$(read_dotenv_value GEOIPUPDATE_ACCOUNT_ID)"
  fi

  geoipupdate_license_key_value="${GEOIPUPDATE_LICENSE_KEY-}"
  if [[ -z "$geoipupdate_license_key_value" ]]; then
    geoipupdate_license_key_value="$(read_dotenv_value GEOIPUPDATE_LICENSE_KEY)"
  fi

  if [[ -n "$geoipupdate_account_id_value" && -n "$geoipupdate_license_key_value" ]]; then
    services+=(geoipupdate)
  else
    echo "GeoIP updater disabled locally; set GEOIPUPDATE_ACCOUNT_ID and GEOIPUPDATE_LICENSE_KEY to enable it."
  fi

  if [[ "$start_db" == "true" ]]; then
    echo "Starting local services: ${services[*]}..."
    docker compose up -d "${services[@]}" >/dev/null
  elif [[ "${#services[@]}" -gt 1 ]]; then
    echo "Ensuring local services are running: ${services[*]}..."
    docker compose up -d "${services[@]}" >/dev/null
  fi

  if [[ "$start_db" == "true" || "${#services[@]}" -gt 1 ]]; then
    local_db_container_id="$(docker compose ps -q db 2>/dev/null || true)"
  fi
  if [[ -z "$local_db_container_id" ]]; then
    echo "Error: failed to start local db container."
    exit 1
  fi

  echo "Waiting for local db to become healthy..."
  local attempt=""
  for attempt in {1..30}; do
    db_status="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$local_db_container_id")"
    if [[ "$db_status" == "healthy" || "$db_status" == "running" ]]; then
      echo "Local db is ready."
      break
    fi
    sleep 2
  done

  db_status="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$local_db_container_id")"
  if [[ "$db_status" != "healthy" && "$db_status" != "running" ]]; then
    echo "Error: local db did not become ready (status: $db_status)."
    docker compose logs --tail=30 db || true
    exit 1
  fi

  kill_port_processes_with_confirmation "8000" "127.0.0.1:8000"
}

run_backend_devserver() {
  local log_level_override="$1"
  cd "$ROOT_DIR/backend"
  export LOG_LEVEL="$log_level_override"
  exec uv run fastapi dev app/main.py
}

prepare_frontend_dev() {
  FRONTEND_DIR="$ROOT_DIR/frontend"
  if [[ ! -d "$FRONTEND_DIR" ]]; then
    echo "Error: frontend directory not found at $FRONTEND_DIR"
    exit 1
  fi

  if command -v bun >/dev/null 2>&1; then
    return 0
  fi

  if ! command -v npm >/dev/null 2>&1; then
    echo "Error: neither bun nor npm is installed."
    exit 1
  fi

  if [[ ! -x "$ROOT_DIR/node_modules/.bin/vite" && ! -x "$FRONTEND_DIR/node_modules/.bin/vite" ]]; then
    cat <<'EOF'
Error: frontend dependencies are not installed.
Run one of:
  npm install --workspace frontend
  (or) bun install
EOF
    exit 1
  fi
}

run_frontend_devserver() {
  cd "$ROOT_DIR"
  if command -v bun >/dev/null 2>&1; then
    exec bun run dev
  fi

  exec npm run dev --workspace frontend
}
