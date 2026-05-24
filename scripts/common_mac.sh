#!/usr/bin/env bash
# Shared helpers for macOS local server scripts (bash/zsh compatible).

set -euo pipefail

# shellcheck disable=SC2034
readonly MAC_COMMON_VERSION="1.0.0"

log_info()  { printf '\033[36m[INFO]\033[0m %s\n' "$*"; }
log_ok()    { printf '\033[32m[OK]\033[0m %s\n' "$*"; }
log_warn()  { printf '\033[33m[WARN]\033[0m %s\n' "$*"; }
log_error() { printf '\033[31m[ERROR]\033[0m %s\n' "$*" >&2; }

# Resolve KakaoEmoticonFactory root from scripts/ or repo root caller.
resolve_project_root() {
  local caller="${1:-}"
  if [[ -n "$caller" ]]; then
    local dir
    dir="$(cd "$(dirname "$caller")" && pwd)"
    if [[ "$(basename "$dir")" == "scripts" ]]; then
      (cd "$dir/.." && pwd)
      return 0
    fi
    echo "$dir"
    return 0
  fi
  if [[ -n "${PROJECT_ROOT:-}" && -f "${PROJECT_ROOT}/app.py" ]]; then
    echo "$PROJECT_ROOT"
    return 0
  fi
  local here="${BASH_SOURCE[0]:-$0}"
  local sdir
  sdir="$(cd "$(dirname "$here")" && pwd)"
  if [[ "$(basename "$sdir")" == "scripts" ]]; then
    (cd "$sdir/.." && pwd)
  else
    echo "$sdir"
  fi
}

port_in_use() {
  local port="$1"
  if command -v lsof >/dev/null 2>&1; then
    lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1
    return $?
  fi
  nc -z 127.0.0.1 "$port" >/dev/null 2>&1
}

pids_on_port() {
  local port="$1"
  if command -v lsof >/dev/null 2>&1; then
    lsof -t -nP -iTCP:"$port" -sTCP:LISTEN 2>/dev/null | sort -u
  fi
}

wait_http_ok() {
  local url="$1"
  local seconds="${2:-30}"
  local i=0
  while (( i < seconds )); do
    if curl -sf --max-time 2 "$url" >/dev/null 2>&1; then
      return 0
    fi
    sleep 0.5
    (( i++ )) || true
  done
  return 1
}

fetch_health_json() {
  local url="$1"
  curl -sf --max-time 3 "$url" 2>/dev/null || true
}

open_url() {
  local url="$1"
  if [[ "$(uname -s)" == "Darwin" ]] && command -v open >/dev/null 2>&1; then
    open "$url" >/dev/null 2>&1 || true
  fi
}

ensure_logs_dir() {
  local root="$1"
  mkdir -p "$root/logs" "$root/web/jobs"
}

# Export all variables from .env into the current shell (uvicorn / subprocess inherit).
source_project_dotenv() {
  local env_file="$1"
  [[ -f "$env_file" ]] || return 0
  set -a
  # shellcheck disable=SC1090
  source "$env_file"
  set +a
  log_info "Sourced env: $env_file"
}

load_dotenv_exports() {
  local env_file="$1"
  [[ -f "$env_file" ]] || return 0
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line%%#*}"
    line="$(echo "$line" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
    [[ -z "$line" || "$line" != *"="* ]] && continue
    local key="${line%%=*}"
    local val="${line#*=}"
    val="${val%\"}"
    val="${val#\"}"
    val="${val%\'}"
    val="${val#\'}"
    export "$key=$val"
  done < "$env_file"
}

venv_is_mac_ready() {
  local venv="$1"
  [[ -f "$venv/bin/activate" && -x "$venv/bin/python" ]] || return 1
  # Windows venv copied to Mac (Scripts/ + C:\ in pyvenv.cfg) — must recreate
  if [[ -d "$venv/Scripts" && ! -d "$venv/bin" ]]; then
    return 1
  fi
  if [[ -f "$venv/pyvenv.cfg" ]] && grep -qiE '^home = [A-Za-z]:\\' "$venv/pyvenv.cfg" 2>/dev/null; then
    return 1
  fi
  if ! "$venv/bin/python" -c 'import sys; sys.exit(0)' >/dev/null 2>&1; then
    return 1
  fi
  return 0
}

mac_python_for_venv() {
  local py ver minor
  local candidates=(
    python3.12
    python3.11
    /opt/homebrew/bin/python3.12
    /opt/homebrew/bin/python3.11
    /usr/local/bin/python3.12
    /usr/local/bin/python3.11
    python3
  )
  for py in "${candidates[@]}"; do
    command -v "$py" >/dev/null 2>&1 || continue
    ver="$("$py" -c 'import sys; print(sys.version_info.minor)' 2>/dev/null || echo 0)"
    if [[ "${ver:-0}" -ge 11 ]]; then
      echo "$py"
      return 0
    fi
  done
  for py in "${candidates[@]}"; do
    if command -v "$py" >/dev/null 2>&1; then
      echo "$py"
      return 0
    fi
  done
  return 1
}

strip_appledouble_in_venv() {
  local venv="$1"
  if [[ "$(uname -s)" != "Darwin" ]]; then
    return 0
  fi
  if command -v dot_clean >/dev/null 2>&1; then
    dot_clean -m "$venv" 2>/dev/null || true
  fi
  find "$venv" -name '._*' -type f -delete 2>/dev/null || true
}

# Remove macOS metadata under web/jobs (exFAT uploads create ._photo.jpeg etc.)
cleanup_jobs_appledouble() {
  local root="$1"
  local jobs="${root}/web/jobs"
  [[ -d "$jobs" ]] || return 0
  if command -v dot_clean >/dev/null 2>&1; then
    dot_clean -m "$jobs" 2>/dev/null || true
  fi
  local n
  n="$(find "$jobs" -name '._*' -type f 2>/dev/null | wc -l | tr -d ' ')"
  if [[ "${n:-0}" -gt 0 ]]; then
    find "$jobs" -name '._*' -type f -delete 2>/dev/null || true
    log_info "Removed $n AppleDouble file(s) under web/jobs"
  fi
}

# exFAT/msdos: shebang scripts (pip) often fail with "permission denied"; python -m pip works.
path_fs_type() {
  local path="$1"
  local dir
  dir="$(cd "$(dirname "$path")" 2>/dev/null && pwd || echo "$path")"
  if [[ "$(uname -s)" != "Darwin" ]]; then
    echo "unknown"
    return 0
  fi
  df -T "$dir" 2>/dev/null | awk 'NR==2 {print $2}' || df "$dir" 2>/dev/null | awk 'NR==2 {print $1}'
}

warn_if_exfat_path() {
  local path="$1"
  local label="${2:-path}"
  local fstype
  fstype="$(path_fs_type "$path")"
  case "$fstype" in
    exfat|msdos|fat32|FAT32|MS-DOS|ExFAT)
      log_warn "$label is on $fstype ($path)"
      log_warn "Use python -m pip (not pip). venv shebang scripts may fail."
      log_warn "Prefer APFS on Mac mini SSD, e.g. ~/ComfyUI or ~/Projects/ComfyUI"
      return 0
      ;;
  esac
  return 1
}

fix_venv_bin_permissions() {
  local venv="$1"
  [[ -d "$venv/bin" ]] || return 0
  chmod -R u+rwX "$venv/bin" 2>/dev/null || true
  # exFAT: chmod does not fix pip shebang execution; documented above.
}

pip_install_logged() {
  local req_file="$1"
  local log_file="$2"
  shift 2
  local extra=("$@")
  : >"$log_file"
  log_info "python -m pip install -r $req_file (log: $log_file)"
  if ! python -m pip install -U pip >>"$log_file" 2>&1; then
    log_error "pip upgrade failed — see $log_file"
    tail -n 20 "$log_file" >&2 || true
    return 1
  fi
  if ! python -m pip install -r "$req_file" "${extra[@]}" >>"$log_file" 2>&1; then
    log_error "requirements install failed — see $log_file"
    tail -n 30 "$log_file" >&2 || true
    return 1
  fi
  strip_appledouble_in_venv "${VIRTUAL_ENV:-}"
  return 0
}

ensure_venv_at() {
  local base_dir="$1"
  local venv_rel="${2:-.venv}"
  local venv="$base_dir/$venv_rel"
  local py
  if ! py="$(mac_python_for_venv)"; then
    log_error "python3 not found. Install: brew install python@3.11"
    return 1
  fi
  if [[ -d "$venv" ]] && ! venv_is_mac_ready "$venv"; then
    log_warn "Replacing broken venv at $venv"
    local backup="${venv}.broken.bak"
    rm -rf "$backup"
    mv "$venv" "$backup" 2>/dev/null || rm -rf "$venv"
  fi
  if [[ ! -d "$venv" ]]; then
    log_info "Creating venv at $venv ($py)"
    export COPYFILE_DISABLE=1
    (cd "$base_dir" && "$py" -m venv "$venv_rel") || {
      log_error "venv create failed at $venv"
      return 1
    }
    strip_appledouble_in_venv "$venv"
  fi
  if ! venv_is_mac_ready "$venv"; then
    log_error "venv not usable: $venv/bin/python"
    return 1
  fi
  fix_venv_bin_permissions "$venv"
  strip_appledouble_in_venv "$venv"
  # shellcheck disable=SC1091
  source "$venv/bin/activate"
  export VIRTUAL_ENV="$venv"
  export PATH="$venv/bin:$PATH"
  return 0
}

ensure_python_venv() {
  local root="$1"
  if [[ -d "$root/.venv" ]] && ! venv_is_mac_ready "$root/.venv"; then
    log_warn "Replacing non-macOS .venv (Windows copy or incomplete)"
    local backup="$root/.venv.windows.bak"
    rm -rf "$backup"
    mv "$root/.venv" "$backup" 2>/dev/null || rm -rf "$root/.venv"
  fi
  ensure_venv_at "$root" ".venv"
}

install_python_deps() {
  local root="$1"
  local backend="$root/web/backend"
  log_info "Installing Python dependencies"
  export COPYFILE_DISABLE=1
  python -m pip install -q -U pip
  if [[ -f "$root/requirements.txt" ]]; then
    python -m pip install -q -r "$root/requirements.txt"
  fi
  if [[ -f "$backend/requirements.txt" ]]; then
    python -m pip install -q -r "$backend/requirements.txt"
  fi
  strip_appledouble_in_venv "${VIRTUAL_ENV:-$root/.venv}"
  python -c "import uvicorn" 2>/dev/null || {
    log_error "uvicorn not available after pip install"
    return 1
  }
}

find_comfyui_dir() {
  if [[ -n "${COMFYUI_DIR:-}" && -f "${COMFYUI_DIR}/main.py" ]]; then
    echo "$(cd "${COMFYUI_DIR}" && pwd)"
    return 0
  fi
  local candidates=(
    "$HOME/ComfyUI"
    "$HOME/Documents/ComfyUI"
    "$HOME/Projects/ComfyUI"
  )
  if [[ -n "${PROJECT_ROOT:-}" ]]; then
    candidates+=(
      "${PROJECT_ROOT}/../ComfyUI"
      "$(cd "${PROJECT_ROOT}/.." 2>/dev/null && pwd)/ComfyUI"
    )
  fi
  local c
  for c in "${candidates[@]}"; do
    if [[ -d "$c" && -f "$c/main.py" ]]; then
      echo "$(cd "$c" && pwd)"
      return 0
    fi
  done
  return 1
}

comfyui_health_ok() {
  local url="${1:-http://127.0.0.1:8188}"
  curl -sf --max-time 3 "$url" >/dev/null 2>&1
}

comfyui_venv_rel() {
  local comfy_dir="$1"
  if [[ -f "$comfy_dir/.venv/bin/activate" ]] || [[ -d "$comfy_dir/.venv" ]]; then
    echo ".venv"
  elif [[ -f "$comfy_dir/venv/bin/activate" ]] || [[ -d "$comfy_dir/venv" ]]; then
    echo "venv"
  else
    echo ".venv"
  fi
}

ensure_comfyui_venv() {
  local comfy_dir="$1"
  local venv_rel
  venv_rel="$(comfyui_venv_rel "$comfy_dir")"
  warn_if_exfat_path "$comfy_dir" "ComfyUI" || true
  ensure_venv_at "$comfy_dir" "$venv_rel"
}

install_comfyui_deps() {
  local comfy_dir="$1"
  local log_file="$2"
  local req="$comfy_dir/requirements.txt"
  if [[ ! -f "$req" ]]; then
    log_warn "No requirements.txt in $comfy_dir — skipping pip install"
    return 0
  fi
  if ! pip_install_logged "$req" "$log_file"; then
    return 1
  fi
  if ! python -c "import sqlalchemy" 2>/dev/null; then
    log_error "sqlalchemy missing after install — see $log_file"
    return 1
  fi
  log_ok "ComfyUI requirements OK (sqlalchemy, etc.)"
  return 0
}

activate_comfyui_venv() {
  ensure_comfyui_venv "$1"
}

show_log_tail() {
  local log_file="$1"
  local lines="${2:-40}"
  if [[ -f "$log_file" ]]; then
    echo "--- tail $log_file (last $lines) ---"
    tail -n "$lines" "$log_file" 2>/dev/null || true
  fi
}

stop_pid_file() {
  local pid_file="$1"
  local label="$2"
  if [[ -f "$pid_file" ]]; then
    local pid
    pid="$(cat "$pid_file" 2>/dev/null || true)"
    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
      log_info "Stopping $label (PID $pid)"
      kill "$pid" 2>/dev/null || true
      sleep 1
      kill -9 "$pid" 2>/dev/null || true
    fi
    rm -f "$pid_file"
  fi
}
