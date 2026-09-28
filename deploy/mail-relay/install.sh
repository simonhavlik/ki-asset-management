#!/usr/bin/env bash
#
# Install the KI Asset Management email relay on the database host (charizard).
#
# Render cannot reach SMTP and the API providers run out of credit, so emails
# that no provider could deliver are parked in the `email_outbox` table by the
# app. This host *can* reach SMTP (and holds the database), so a timer drains
# that queue through Gmail every minute.
#
# Usage (as root, on the database host):
#     ./install.sh
#
# Requires /etc/kiam-mail.env to exist first - see kiam-mail.env.example.
#
set -euo pipefail

SCRIPT_SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)/scripts/send_outbox.py"
SCRIPT_DST=/usr/local/bin/kiam-send-outbox.py
ENV_FILE=/etc/kiam-mail.env
UNIT_DIR=/etc/systemd/system

if [[ $EUID -ne 0 ]]; then
    echo "run me as root" >&2
    exit 1
fi

if [[ ! -f $SCRIPT_SRC ]]; then
    echo "cannot find $SCRIPT_SRC - run this from a checkout of the repo" >&2
    exit 1
fi

if [[ ! -f $ENV_FILE ]]; then
    echo "$ENV_FILE is missing - copy kiam-mail.env.example there and fill it in" >&2
    exit 1
fi

# Least privilege: the relay only needs to read its env file and talk to
# Postgres over localhost, so it does not run as root.
if ! id kiammail >/dev/null 2>&1; then
    useradd --system --no-create-home --shell /usr/sbin/nologin kiammail
    echo "created system user kiammail"
fi

install -m 0755 "$SCRIPT_SRC" "$SCRIPT_DST"
chown root:kiammail "$ENV_FILE"
chmod 0640 "$ENV_FILE"

install -m 0644 "$(dirname "${BASH_SOURCE[0]}")/kiam-send-outbox-listener.service" "$UNIT_DIR/"
install -m 0644 "$(dirname "${BASH_SOURCE[0]}")/kiam-send-outbox.service" "$UNIT_DIR/"
install -m 0644 "$(dirname "${BASH_SOURCE[0]}")/kiam-send-outbox.timer" "$UNIT_DIR/"

# psycopg2 is imported lazily by connect_db(); make sure it is present.
if ! python3 -c 'import psycopg2' 2>/dev/null; then
    echo "installing python3-psycopg2..."
    apt-get update -qq && apt-get install -y -qq python3-psycopg2
fi

systemctl daemon-reload
# Instant delivery: the listener is woken by the table's pg_notify() trigger.
systemctl enable --now kiam-send-outbox-listener.service
# Backstop in case a notification is ever missed (PostgreSQL does not replay
# notifications across a reconnect that happened when nothing was listening).
systemctl enable --now kiam-send-outbox.timer

echo
echo "installed. queue depth:"
sudo -u kiammail "$SCRIPT_DST" --status || true
echo
echo "watch it with:  journalctl -u kiam-send-outbox-listener -f"
echo "run it now with: systemctl start kiam-send-outbox.service"
