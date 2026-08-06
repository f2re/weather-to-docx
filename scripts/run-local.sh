#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
VENV_DIR=${WTD_VENV_DIR:-"$ROOT_DIR/.venv"}
HOST=${WTD_API_HOST:-127.0.0.1}
PORT=${WTD_API_PORT:-8080}
DATA_DIR=${WTD_DATA_DIR:-"$ROOT_DIR/var/runtime"}
POLL_INTERVAL=${WTD_WORKER_POLL_INTERVAL:-5}
START_WORKER=1
WORKER_PID=""

usage() {
  cat <<'EOF'
Использование:
  ./scripts/run-local.sh [--host АДРЕС] [--port ПОРТ] [--data-dir КАТАЛОГ] [--no-worker]

Запускает API в текущем терминале и worker в фоне. Данные локального запуска
по умолчанию сохраняются в var/runtime; остановка API останавливает и worker.

Переменные окружения:
  WTD_VENV_DIR               виртуальное окружение (по умолчанию .venv)
  WTD_WORKER_POLL_INTERVAL   интервал опроса worker, секунды (по умолчанию 5)
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --host)
      [[ $# -ge 2 ]] || { echo "После --host нужен адрес." >&2; exit 2; }
      HOST=$2
      shift 2
      ;;
    --port)
      [[ $# -ge 2 ]] || { echo "После --port нужен порт." >&2; exit 2; }
      PORT=$2
      shift 2
      ;;
    --data-dir)
      [[ $# -ge 2 ]] || { echo "После --data-dir нужен каталог." >&2; exit 2; }
      DATA_DIR=$2
      shift 2
      ;;
    --no-worker)
      START_WORKER=0
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Неизвестный параметр: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

COMMAND="$VENV_DIR/bin/weather-to-docx"
[[ -x "$COMMAND" ]] || {
  echo "Не найдено виртуальное окружение: $VENV_DIR" >&2
  echo "Создайте его командой: python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'" >&2
  exit 1
}

mkdir -p "$DATA_DIR/cache/matplotlib"
export WTD_DATA_DIR="$DATA_DIR"
export WTD_API_HOST="$HOST"
export WTD_API_PORT="$PORT"
export MPLBACKEND=Agg
export MPLCONFIGDIR="$DATA_DIR/cache/matplotlib"

stop_worker() {
  [[ -n "$WORKER_PID" ]] || return 0
  if kill -0 "$WORKER_PID" 2>/dev/null; then
    kill "$WORKER_PID" 2>/dev/null || true
    wait "$WORKER_PID" 2>/dev/null || true
  fi
}
trap stop_worker EXIT INT TERM

"$COMMAND" init

if [[ $START_WORKER -eq 1 ]]; then
  "$COMMAND" worker --poll-interval "$POLL_INTERVAL" &
  WORKER_PID=$!
  echo "Worker запущен (PID $WORKER_PID)."
fi

echo "API: http://$HOST:$PORT/"
"$COMMAND" api --host "$HOST" --port "$PORT"
