#!/usr/bin/env python3
"""One-time setup: get a Gmail API refresh token for the club's mail account.

Why this and not SMTP: Render blocks outbound SMTP entirely
(``smtp failed: [Errno 101] Network is unreachable``), so the only way to send
as ``simon.havlik@klubinvestoru.com`` from the deployed app is an HTTPS call to
googleapis.com.

Because klubinvestoru.com is a Google Workspace domain, the OAuth client is
"Internal": Google verification is not required, there is no unverified-app
warning, and the refresh token does not expire (unlike an External client left
in "Testing", whose refresh tokens die after 7 days).

Before running this
-------------------
1. https://console.cloud.google.com -> create a project (e.g. "ki-mail").
2. APIs & Services -> Library -> enable **Gmail API**.
3. APIs & Services -> OAuth consent screen:
       User type: Internal
       Add scope: https://www.googleapis.com/auth/gmail.send
       (no test users needed for an Internal app)
4. APIs & Services -> Credentials -> Create credentials -> OAuth client ID:
       Application type: Desktop app
   Copy the client ID and client secret.

Then
----
    python3 scripts/gmail_oauth_setup.py

It opens a browser, you click Allow, and it prints the three values to paste
into Render's environment. Run it from your own machine, never on the server.

Only stdlib is used, so any python3 works.
"""

from __future__ import annotations

import base64
import getpass
import http.server
import json
import os
import socketserver
import sys
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from email.message import EmailMessage

AUTH_URL = 'https://accounts.google.com/o/oauth2/v2/auth'
TOKEN_URL = 'https://oauth2.googleapis.com/token'
SEND_URL = 'https://gmail.googleapis.com/gmail/v1/users/me/messages/send'
SCOPE = 'https://www.googleapis.com/auth/gmail.send'
PORT = 8765
REDIRECT_URI = f'http://localhost:{PORT}/'

_code: dict[str, str] = {}


class _Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        query = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(query)
        _code.update({k: v[0] for k, v in params.items()})
        body = (b'<h2>Done - you can close this tab and return to the terminal.</h2>'
                if 'code' in _code else
                b'<h2>Something went wrong. Check the terminal.</h2>')
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # keep the output readable
        pass


def _post(url: str, data: dict, headers: dict | None = None) -> dict:
    req = urllib.request.Request(
        url,
        data=urllib.parse.urlencode(data).encode(),
        headers=headers or {'Content-Type': 'application/x-www-form-urlencoded'},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        detail = e.read().decode()[:400]
        raise SystemExit(f'\nGoogle returned HTTP {e.code}:\n{detail}\n')


def main() -> int:
    print(__doc__.split('Before running this')[0].strip().splitlines()[0])
    print()

    client_id = os.environ.get('GMAIL_CLIENT_ID') or input('OAuth client ID: ').strip()
    client_secret = os.environ.get('GMAIL_CLIENT_SECRET') or getpass.getpass('OAuth client secret: ').strip()
    if not client_id or not client_secret:
        print('both values are required', file=sys.stderr)
        return 1

    auth_url = AUTH_URL + '?' + urllib.parse.urlencode({
        'client_id': client_id,
        'redirect_uri': REDIRECT_URI,
        'response_type': 'code',
        'scope': SCOPE,
        'access_type': 'offline',
        'prompt': 'consent',          # force a refresh_token every run
    })

    print('\nOpening your browser. If it does not open, visit:\n')
    print(f'  {auth_url}\n')
    print('Sign in as the account that should send the mail, then click Allow.')
    webbrowser.open(auth_url)

    with socketserver.TCPServer(('127.0.0.1', PORT), _Handler) as httpd:
        httpd.timeout = 300
        httpd.handle_request()      # serve exactly one request

    if 'error' in _code:
        print(f"\nGoogle refused: {_code['error']}", file=sys.stderr)
        return 1
    if 'code' not in _code:
        print('\ntimed out waiting for the redirect', file=sys.stderr)
        return 1

    tokens = _post(TOKEN_URL, {
        'code': _code['code'],
        'client_id': client_id,
        'client_secret': client_secret,
        'redirect_uri': REDIRECT_URI,
        'grant_type': 'authorization_code',
    })
    refresh_token = tokens.get('refresh_token')
    if not refresh_token:
        print('\nno refresh_token in the response - re-run and make sure you clicked Allow',
              file=sys.stderr)
        print(json.dumps(tokens)[:300], file=sys.stderr)
        return 1

    # Prove it works before you paste anything into Render.
    sender = input('\nSend a test email to which address? ').strip()
    if sender:
        msg = EmailMessage()
        msg['To'] = sender
        msg['From'] = sender
        msg['Subject'] = 'KI Asset Management - Gmail API test'
        msg.set_content('If you received this, the Gmail API credentials work.')
        req = urllib.request.Request(
            SEND_URL,
            data=json.dumps({
                'raw': base64.urlsafe_b64encode(msg.as_bytes()).decode('ascii'),
            }).encode(),
            headers={
                'Authorization': f"Bearer {tokens['access_token']}",
                'Content-Type': 'application/json',
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                json.loads(resp.read().decode())
            print(f'test email accepted for {sender}')
        except urllib.error.HTTPError as e:
            print(f'test send failed: HTTP {e.code} {e.read().decode()[:300]}', file=sys.stderr)

    print('\n' + '=' * 72)
    print('Add these to Render (ki-asset-management -> Environment):')
    print('=' * 72)
    print(f'GMAIL_CLIENT_ID={client_id}')
    print(f'GMAIL_CLIENT_SECRET={client_secret}')
    print(f'GMAIL_REFRESH_TOKEN={refresh_token}')
    print('GMAIL_SENDER=simon.havlik@klubinvestoru.com')
    print('MAIL_PROVIDER=gmail_api')
    print('=' * 72)
    print('\nVerify afterwards with:  flask mail-status')
    return 0


if __name__ == '__main__':
    sys.exit(main())
