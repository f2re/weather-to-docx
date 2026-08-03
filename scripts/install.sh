#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT=weather-to-docx
SERVICE_USER=weatherdoc
SERVICE_GROUP=weatherdoc
OPT_ROOT=/opt/$PROJECT
RELEASES_DIR=$OPT_ROOT/releases
CURRENT_LINK=$OPT_ROOT/current
PREVIOUS_LINK=$OPT_ROOT/previous
ETC_DIR=/etc/$PROJECT
DATA_DIR=/var/lib/$PROJECT
BACKUP_DIR=$DATA_DIR/backups
BUNDLE_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
VERSION=$(tr -d '[:space:]' < "$BUNDLE_DIR/VERSION")
RELEASE_DIR=$RELEASES_DIR/$VERSION
STAGE_DIR=$RELEASES_DIR/.install-$VERSION-$$
OLD_TARGET=""
SWITCHED=0
SERVICES=(weather-to-docx-api.service weather-to-docx-worker.service)

fatal() {
  echo "Ошибка: $*" >&2
  exit 1
}

require_root() {
  [[ ${EUID} -eq 0 ]] || fatal "установка должна выполняться от root"
}

systemd_enabled() {
  [[ ${WTD_SKIP_SYSTEMD:-0} != 1 ]] && command -v systemctl >/dev/null 2>&1
}

restore_on_error() {
  code=$?
  trap - ERR
  echo "Установка прервана, выполняется безопасное восстановление." >&2
  if [[ $SWITCHED -eq 1 && -n "$OLD_TARGET" && -d "$OLD_TARGET" ]]; then
    ln -sfn "$OLD_TARGET" "$CURRENT_LINK.restore"
    mv -Tf "$CURRENT_LINK.restore" "$CURRENT_LINK"
  fi
  rm -rf "$STAGE_DIR"
  if systemd_enabled; then
    systemctl daemon-reload || true
    for service in "${SERVICES[@]}"; do
      systemctl restart "$service" >/dev/null 2>&1 || true
    done
  fi
  exit "$code"
}
trap restore_on_error ERR

verify_bundle() {
  [[ -f "$BUNDLE_DIR/SHA256SUMS" ]] || fatal "отсутствует SHA256SUMS"
  (
    cd "$BUNDLE_DIR"
    sha256sum -c SHA256SUMS
  )
  if [[ -f "$BUNDLE_DIR/SHA256SUMS.sig" ]]; then
    [[ -n ${WTD_GPG_KEYRING:-} ]] || fatal "комплект подписан; задайте WTD_GPG_KEYRING с доверенным keyring"
    command -v gpgv >/dev/null 2>&1 || fatal "для проверки подписи требуется gpgv"
    gpgv --keyring "$WTD_GPG_KEYRING" "$BUNDLE_DIR/SHA256SUMS.sig" "$BUNDLE_DIR/SHA256SUMS"
  fi
}

check_platform() {
  [[ -r /etc/os-release ]] || fatal "не найден /etc/os-release"
  # shellcheck disable=SC1091
  . /etc/os-release
  if [[ ${WTD_ALLOW_NON_ASTRA:-0} != 1 ]]; then
    local identity="${ID:-} ${ID_LIKE:-} ${NAME:-}"
    [[ ${identity,,} == *astra* ]] || fatal "целевая система не распознана как Astra Linux; для стенда задайте WTD_ALLOW_NON_ASTRA=1"
  fi
  local bundle_arch
  bundle_arch=$(sed -n 's/.*"architecture"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$BUNDLE_DIR/build-info.json" | head -1)
  local host_arch
  host_arch=$(dpkg --print-architecture 2>/dev/null || uname -m)
  [[ -z "$bundle_arch" || "$bundle_arch" == "$host_arch" ]] \
    || fatal "архитектура комплекта $bundle_arch не совпадает с системой $host_arch"
}

install_local_apt_repository() {
  [[ -d "$BUNDLE_DIR/apt-repository" && -f "$BUNDLE_DIR/apt-repository/Packages" ]] || return 0
  command -v apt-get >/dev/null 2>&1 || fatal "в комплекте есть APT-репозиторий, но apt-get недоступен"
  local list_file
  list_file=$(mktemp -t weather-to-docx-sources-XXXXXX.list)
  printf 'deb [trusted=yes] file:%s ./\n' "$BUNDLE_DIR/apt-repository" > "$list_file"
  local packages=""
  if [[ -f "$BUNDLE_DIR/apt-repository/requested-packages.txt" ]]; then
    packages=$(tr '\n' ' ' < "$BUNDLE_DIR/apt-repository/requested-packages.txt")
  fi
  echo "==> Установка системных пакетов только из вложенного APT-репозитория"
  apt-get \
    -o Dir::Etc::sourcelist="$list_file" \
    -o Dir::Etc::sourceparts="-" \
    -o APT::Get::List-Cleanup="0" \
    update
  if [[ -n "$packages" ]]; then
    # shellcheck disable=SC2086
    DEBIAN_FRONTEND=noninteractive apt-get -y --no-install-recommends \
      -o Dir::Etc::sourcelist="$list_file" \
      -o Dir::Etc::sourceparts="-" \
      install $packages
  fi
  rm -f "$list_file"
}

install_runtime() {
  if [[ -d "$BUNDLE_DIR/runtime" ]]; then
    echo "==> Установка частного Python runtime"
    mkdir -p "$OPT_ROOT"
    rm -rf "$OPT_ROOT/runtime.new"
    cp -a "$BUNDLE_DIR/runtime" "$OPT_ROOT/runtime.new"
    rm -rf "$OPT_ROOT/runtime"
    mv "$OPT_ROOT/runtime.new" "$OPT_ROOT/runtime"
  fi
}

select_python() {
  local candidates=()
  [[ -n ${WTD_PYTHON:-} ]] && candidates+=("$WTD_PYTHON")
  while IFS= read -r candidate; do candidates+=("$candidate"); done < <(
    find "$OPT_ROOT/runtime" -type f \( -name python3.11 -o -name python3 \) -perm -0100 2>/dev/null | sort
  )
  command -v python3.11 >/dev/null 2>&1 && candidates+=("$(command -v python3.11)")
  command -v python3 >/dev/null 2>&1 && candidates+=("$(command -v python3)")

  local candidate
  for candidate in "${candidates[@]}"; do
    [[ -x "$candidate" ]] || continue
    if "$candidate" - <<'PY' >/dev/null 2>&1
import sys
raise SystemExit(0 if sys.version_info >= (3, 11) else 1)
PY
    then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  fatal "не найден совместимый Python 3.11+; добавьте python3.11 в APT-комплект или задайте RUNTIME_DIR при сборке"
}

create_account_and_directories() {
  getent group "$SERVICE_GROUP" >/dev/null || groupadd --system "$SERVICE_GROUP"
  id "$SERVICE_USER" >/dev/null 2>&1 || useradd \
    --system --gid "$SERVICE_GROUP" --home-dir "$DATA_DIR" \
    --shell /usr/sbin/nologin "$SERVICE_USER"

  install -d -m 0755 "$OPT_ROOT" "$RELEASES_DIR" "$ETC_DIR" "$ETC_DIR/keys"
  install -d -o "$SERVICE_USER" -g "$SERVICE_GROUP" -m 0750 \
    "$DATA_DIR" "$DATA_DIR/database" "$DATA_DIR/cache" "$DATA_DIR/documents" \
    "$DATA_DIR/incoming" "$BACKUP_DIR"
}

stop_services_and_backup() {
  if systemd_enabled; then
    for service in "${SERVICES[@]}"; do
      systemctl stop "$service" >/dev/null 2>&1 || true
    done
  fi
  local database=$DATA_DIR/database/weather-to-docx.sqlite3
  if [[ -f "$database" ]]; then
    local stamp
    stamp=$(date -u +%Y%m%dT%H%M%SZ)
    tar -C "$DATA_DIR" -czf "$BACKUP_DIR/database-$stamp.tar.gz" database
    chown "$SERVICE_USER:$SERVICE_GROUP" "$BACKUP_DIR/database-$stamp.tar.gz"
    chmod 0640 "$BACKUP_DIR/database-$stamp.tar.gz"
  fi
}

install_release() {
  [[ -d "$BUNDLE_DIR/wheelhouse" ]] || fatal "отсутствует wheelhouse"
  if [[ -e "$RELEASE_DIR" ]]; then
    [[ ${WTD_REINSTALL:-0} == 1 ]] || fatal "релиз $VERSION уже существует; для осознанной переустановки задайте WTD_REINSTALL=1"
    [[ "$(readlink -f "$CURRENT_LINK" 2>/dev/null || true)" != "$RELEASE_DIR" ]] \
      || fatal "нельзя удалить текущий релиз при переустановке"
    rm -rf "$RELEASE_DIR"
  fi
  rm -rf "$STAGE_DIR"
  mkdir -p "$STAGE_DIR/share" "$STAGE_DIR/bin"

  local python_bin
  python_bin=$(select_python)
  echo "==> Python: $python_bin"
  "$python_bin" -m venv --copies "$STAGE_DIR/venv"
  local package_spec="weather-to-docx==$VERSION"
  if [[ -f "$BUNDLE_DIR/wheelhouse/grib.enabled" ]]; then
    package_spec="weather-to-docx[grib]==$VERSION"
  fi
  "$STAGE_DIR/venv/bin/python" -m pip install \
    --no-index --disable-pip-version-check \
    --find-links "$BUNDLE_DIR/wheelhouse" \
    "$package_spec"

  cp -a "$BUNDLE_DIR/docs" "$BUNDLE_DIR/config" "$BUNDLE_DIR/examples" "$STAGE_DIR/share/"
  cp "$BUNDLE_DIR/README.md" "$BUNDLE_DIR/CHANGELOG.md" "$BUNDLE_DIR/THIRD_PARTY_NOTICES.md" "$STAGE_DIR/share/"
  cp "$BUNDLE_DIR/rollback.sh" "$STAGE_DIR/bin/rollback-release"
  chmod 0755 "$STAGE_DIR/bin/rollback-release"
  printf '%s\n' "$VERSION" > "$STAGE_DIR/VERSION"
  chown -R root:root "$STAGE_DIR"
  chmod -R go-w "$STAGE_DIR"
  mv "$STAGE_DIR" "$RELEASE_DIR"
}

install_configuration() {
  if [[ ! -f "$ETC_DIR/weather-to-docx.env" ]]; then
    cp "$BUNDLE_DIR/weather-to-docx.env.example" "$ETC_DIR/weather-to-docx.env"
  fi
  chown root:"$SERVICE_GROUP" "$ETC_DIR/weather-to-docx.env"
  chmod 0640 "$ETC_DIR/weather-to-docx.env"
  chmod 0750 "$ETC_DIR/keys"
}

switch_release() {
  OLD_TARGET=$(readlink -f "$CURRENT_LINK" 2>/dev/null || true)
  if [[ -n "$OLD_TARGET" && -d "$OLD_TARGET" ]]; then
    ln -sfn "$OLD_TARGET" "$PREVIOUS_LINK.new"
    mv -Tf "$PREVIOUS_LINK.new" "$PREVIOUS_LINK"
  fi
  ln -sfn "$RELEASE_DIR" "$CURRENT_LINK.new"
  mv -Tf "$CURRENT_LINK.new" "$CURRENT_LINK"
  SWITCHED=1
}

install_services() {
  if ! systemd_enabled; then
    echo "==> Установка systemd-служб пропущена (WTD_SKIP_SYSTEMD=1 или systemctl недоступен)"
    return 0
  fi
  install -m 0644 "$BUNDLE_DIR/systemd/weather-to-docx-api.service" /etc/systemd/system/
  install -m 0644 "$BUNDLE_DIR/systemd/weather-to-docx-worker.service" /etc/systemd/system/
  systemctl daemon-reload
  systemctl enable weather-to-docx-api.service weather-to-docx-worker.service
}

initialise_and_validate() {
  local command=("$CURRENT_LINK/venv/bin/weather-to-docx")
  runuser -u "$SERVICE_USER" -- env \
    WTD_DATA_DIR="$DATA_DIR" \
    "${command[@]}" init
  runuser -u "$SERVICE_USER" -- env \
    WTD_DATA_DIR="$DATA_DIR" \
    "${command[@]}" doctor --deep
}

start_services() {
  if systemd_enabled; then
    systemctl restart weather-to-docx-api.service weather-to-docx-worker.service
  fi
}

require_root
verify_bundle
check_platform
install_local_apt_repository
install_runtime
create_account_and_directories
stop_services_and_backup
install_release
install_configuration
switch_release
install_services
initialise_and_validate
start_services
trap - ERR

echo "==> Weather to DOCX $VERSION установлен"
echo "    Текущий релиз: $CURRENT_LINK -> $(readlink -f "$CURRENT_LINK")"
echo "    Данные: $DATA_DIR"
echo "    Настройки: $ETC_DIR/weather-to-docx.env"
