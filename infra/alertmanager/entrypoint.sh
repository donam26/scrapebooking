#!/bin/sh
# Điền biến môi trường vào mẫu alertmanager.yml rồi chạy Alertmanager (image chạy user nobody,
# chỉ /tmp ghi được). Mật khẩu SMTP ghi ra file (smtp_auth_password_file) để không phải escape sed.
set -eu

TMPL=/etc/alertmanager/alertmanager.yml.tmpl
OUT_DIR=/tmp/alertmanager
OUT="$OUT_DIR/alertmanager.yml"

umask 077
mkdir -p "$OUT_DIR"
printf '%s' "${SMTP_PASSWORD:-}" > "$OUT_DIR/smtp_password"

sed -e "s|__SMTP_HOST__|${SMTP_HOST}|g" \
    -e "s|__SMTP_PORT__|${SMTP_PORT:-587}|g" \
    -e "s|__SMTP_USERNAME__|${SMTP_USERNAME:-}|g" \
    -e "s|__SMTP_FROM__|${SMTP_FROM}|g" \
    -e "s|__OPS_ALERT_EMAILS__|${OPS_ALERT_EMAILS}|g" \
    "$TMPL" > "$OUT"

exec /bin/alertmanager --config.file="$OUT" --storage.path=/alertmanager "$@"
