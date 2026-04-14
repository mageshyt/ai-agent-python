#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BOOTSTRAP_PYTHON="${BOOTSTRAP_PYTHON:-python3}"
PIPX_BIN="${PIPX_BIN:-}"
PACKAGE_NAME="ai-agent-python"
APP_NAME="cyberowl"

print_usage() {
  cat <<'EOF'
Usage:
  scripts/local_cli.sh [command]

Commands:
  sync       Force-refresh editable install and verify command (default)
  install    Install editable package with pipx
  reinstall  Reinstall existing pipx package (falls back to install)
  force      Force install editable package with pipx
  verify     Show pipx state and confirm CLI command is available
  help       Show this help

Examples:
  scripts/local_cli.sh
  scripts/local_cli.sh reinstall
  scripts/local_cli.sh verify
EOF
}

ensure_pipx() {
  if [[ -z "$PIPX_BIN" ]]; then
    if command -v pipx >/dev/null 2>&1; then
      PIPX_BIN="$(command -v pipx)"
    elif [[ -x "$HOME/.local/bin/pipx" ]]; then
      PIPX_BIN="$HOME/.local/bin/pipx"
    fi
  fi

  if [[ -z "$PIPX_BIN" ]]; then
    echo "pipx not found. Installing pipx for user..."
    if ! "$BOOTSTRAP_PYTHON" -m pip --version >/dev/null 2>&1; then
      "$BOOTSTRAP_PYTHON" -m ensurepip --upgrade >/dev/null 2>&1 || true
    fi
    "$BOOTSTRAP_PYTHON" -m pip install --user pipx

    if command -v pipx >/dev/null 2>&1; then
      PIPX_BIN="$(command -v pipx)"
    elif [[ -x "$HOME/.local/bin/pipx" ]]; then
      PIPX_BIN="$HOME/.local/bin/pipx"
    fi
  fi

  if [[ -z "$PIPX_BIN" ]]; then
    echo "Could not find pipx after installation."
    echo "Install manually: $BOOTSTRAP_PYTHON -m pip install --user pipx"
    exit 1
  fi

  "$PIPX_BIN" ensurepath >/dev/null || true
}

is_installed() {
  "$PIPX_BIN" list | grep -q "package ${PACKAGE_NAME} "
}

install_editable() {
  echo "Installing editable package from: $ROOT_DIR"
  "$PIPX_BIN" install -e "$ROOT_DIR"
}

reinstall_package() {
  if is_installed; then
    echo "Reinstalling ${PACKAGE_NAME}..."
    "$PIPX_BIN" reinstall "$PACKAGE_NAME"
  else
    echo "${PACKAGE_NAME} is not installed in pipx. Running install instead..."
    install_editable
  fi
}

force_refresh() {
  echo "Force-refreshing editable install from: $ROOT_DIR"
  "$PIPX_BIN" install --force -e "$ROOT_DIR"
}

verify_cli() {
  echo "Checking pipx packages..."
  "$PIPX_BIN" list

  if command -v "$APP_NAME" >/dev/null 2>&1; then
    echo "CLI found: $(command -v "$APP_NAME")"
    "$APP_NAME" --help | sed -n '1,25p'
  else
    echo "CLI '${APP_NAME}' is not in PATH. Open a new terminal or run:"
    echo "  $PIPX_BIN ensurepath"
    exit 1
  fi
}

sync_all() {
  ensure_pipx
  force_refresh
  verify_cli
}

main() {
  local cmd="${1:-sync}"

  case "$cmd" in
    sync)
      sync_all
      ;;
    install)
      ensure_pipx
      install_editable
      ;;
    reinstall)
      ensure_pipx
      reinstall_package
      ;;
    force)
      ensure_pipx
      force_refresh
      ;;
    verify)
      ensure_pipx
      verify_cli
      ;;
    help|-h|--help)
      print_usage
      ;;
    *)
      echo "Unknown command: $cmd"
      print_usage
      exit 2
      ;;
  esac
}

main "$@"
