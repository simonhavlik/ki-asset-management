#!/usr/bin/env python3
"""Drain the email_outbox table over SMTP.

Why this exists
---------------
Production runs on Render, which blocks outbound SMTP entirely
(``[Errno 101] Network is unreachable``), and the HTTPS API providers can run
out of credit (SendGrid returned 401 for months). Any email that no provider
could deliver is parked in ``email_outbox`` by ``app/email_service.py``.

This script runs *on the database host* (charizard), where SMTP is reachable,
and delivers those messages through Gmail. It is deliberately dependency-light
(psycopg2 + stdlib only, no Flask) so it can run from a systemd timer without
loading the whole application.

Usage
-----
    send_outbox.py                 # one pass, up to 20 messages
    send_outbox.py --limit 50      # larger pass
    send_outbox.py --dry-run       # show what would be sent
    send_outbox.py --status        # just report queue depth

Configuration
-------------
Read from the environment, falling back to ``/etc/kiam-mail.env`` (0600):

    DATABASE_URL          postgresql://***REMOVED***
    MAIL_SERVER           smtp.gmail.com
    MAIL_PORT             587
    MAIL_USERNAME         simon.havlik@klubinvestoru.com
    MAIL_PASSWORD         <gmail app password>
    MAIL_DEFAULT_SENDER   simon.havlik@klubinvestoru.com

Exit code is always 0 unless the database is unreachable, so a transient send
failure never makes systemd mark the unit failed.
"""

from __future__ import annotations

import argparse
import os
import smtplib
import ssl
import sys
import time
from email.message import EmailMessage
from pathlib import Path

ENV_FILE = Path('/etc/kiam-mail.env')
MAX_ATTEMPTS = 5
PRUNE_AFTER_DAYS = 30


def load_env() -> None:
    """Populate os.environ from the secrets file without overriding real env."""
    if not ENV_FILE.exists():
        return
    for raw in ENV_FILE.read_text(encoding='utf-8').splitlines():
        line = raw.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, _, value = line.partition('=')
        key, value = key.strip(), value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def log(msg: str) -> None:
    print(f'[send_outbox] {msg}', flush=True)


def connect_db():
    import psycopg2
    url = os.environ.get('DATABASE_URL')
    if not url:
        log('ERROR: DATABASE_URL is not set')
        sys.exit(1)
    return psycopg2.connect(url, connect_timeout=10)


def smtp_send(recipient: str, subject: str, text_body: str, html_body: str | None) -> None:
    """Send one message. Raises on failure."""
    host = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
    port = int(os.environ.get('MAIL_PORT', 587))
    user = os.environ.get('MAIL_USERNAME')
    password = os.environ.get('MAIL_PASSWORD')
    sender = os.environ.get('MAIL_DEFAULT_SENDER') or user
    timeout = int(os.environ.get('MAIL_TIMEOUT', 15))

    if not sender:
        raise RuntimeError('MAIL_DEFAULT_SENDER/MAIL_USERNAME not configured')

    msg = EmailMessage()
    msg['Subject'] = subject
    msg['From'] = sender
    msg['To'] = recipient
    msg.set_content(text_body or '')
    if html_body:
        msg.add_alternative(html_body, subtype='html')

    use_tls = os.environ.get('MAIL_USE_TLS', 'true').lower() in ('true', '1', 't')
    if use_tls:
        server = smtplib.SMTP(host, port, timeout=timeout)
        server.ehlo()
        server.starttls(context=ssl.create_default_context())
    else:
        server = smtplib.SMTP_SSL(host, port, timeout=timeout,
                                  context=ssl.create_default_context())
    try:
        if user and password:
            server.login(user, password)
        server.send_message(msg)
    finally:
        try:
            server.quit()
        except Exception:
            pass


def claim_next(conn, limit: int):
    """Claim up to `limit` pending rows, exclusively.

    The UPDATE ... WHERE status='pending' RETURNING makes the claim atomic: two
    overlapping runs can never deliver the same message twice.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id FROM email_outbox
             WHERE status = 'pending' AND attempts < %s
             ORDER BY created_at
             LIMIT %s
            """,
            (MAX_ATTEMPTS, limit),
        )
        ids = [r[0] for r in cur.fetchall()]
    conn.commit()

    claimed = []
    for row_id in ids:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE email_outbox
                   SET attempts = attempts + 1
                 WHERE id = %s AND status = 'pending'
             RETURNING id, recipient, subject, text_body, html_body, attempts
                """,
                (row_id,),
            )
            row = cur.fetchone()
        conn.commit()
        if row:
            claimed.append(row)
    return claimed


def mark_sent(conn, row_id: int) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE email_outbox SET status='sent', sent_at=now(), last_error=NULL WHERE id=%s",
            (row_id,),
        )
    conn.commit()


def mark_failed(conn, row_id: int, error: str, attempts: int) -> None:
    status = 'failed' if attempts >= MAX_ATTEMPTS else 'pending'
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE email_outbox SET status=%s, last_error=%s WHERE id=%s",
            (status, error[:500], row_id),
        )
    conn.commit()


def prune(conn) -> int:
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM email_outbox WHERE status='sent' "
            "AND sent_at < now() - interval '%s days'",
            (PRUNE_AFTER_DAYS,),
        )
        deleted = cur.rowcount
    conn.commit()
    return deleted


def queue_depth(conn) -> tuple[int, int]:
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM email_outbox WHERE status='pending'")
        pending = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM email_outbox WHERE status='failed'")
        failed = cur.fetchone()[0]
    return pending, failed


def main() -> int:
    parser = argparse.ArgumentParser(description='Deliver queued emails over SMTP')
    parser.add_argument('--limit', type=int, default=20)
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--status', action='store_true')
    args = parser.parse_args()

    load_env()
    try:
        conn = connect_db()
    except Exception as e:
        log(f'ERROR: cannot reach the database: {e}')
        return 1

    try:
        pending, failed = queue_depth(conn)
        if args.status:
            log(f'queue: {pending} pending, {failed} failed')
            return 0

        if args.dry_run:
            for row in claim_next(conn, args.limit):
                log(f'would send #{row[0]} to {row[1]}: {row[2]}')
            conn.rollback()
            log(f'dry run: {pending} pending, {failed} failed')
            return 0

        if not pending:
            log('nothing to send')
            return 0

        sent = errors = 0
        start = time.time()
        for row_id, recipient, subject, text_body, html_body, attempts in claim_next(conn, args.limit):
            try:
                smtp_send(recipient, subject, text_body, html_body)
                mark_sent(conn, row_id)
                sent += 1
                log(f'sent #{row_id} to {recipient}: {subject}')
            except Exception as e:
                errors += 1
                mark_failed(conn, row_id, str(e), attempts)
                log(f'FAILED #{row_id} to {recipient} (attempt {attempts}/{MAX_ATTEMPTS}): {e}')

        deleted = prune(conn)
        log(f'done in {time.time() - start:.1f}s: {sent} sent, {errors} failed'
            + (f', {deleted} old rows pruned' if deleted else ''))
        return 0
    finally:
        conn.close()


if __name__ == '__main__':
    sys.exit(main())
