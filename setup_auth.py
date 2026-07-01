#!/usr/bin/env python3
"""One-time Tesla OAuth setup. Saves refresh token to state.json."""

from __future__ import annotations

import argparse
import logging
import secrets
import socket
import sys
import webbrowser
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from tesla_invoicer.config import load_config
from tesla_invoicer.state import load_state, save_state
from tesla_invoicer.tesla_client import apply_token_response, build_authorize_url, exchange_code_for_tokens


def configure_logging(log_file: Path | None) -> None:
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if log_file:
        handlers.append(logging.FileHandler(log_file))
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=handlers,
    )


def parse_auth_code_from_callback(
    callback: str,
    expected_state: str | None = None,
) -> str:
    """Extract the auth code from a pasted callback URL or raw code."""
    callback = callback.strip()
    if "://" in callback:
        query = parse_qs(urlparse(callback).query)
        returned_state = query.get("state", [None])[0]
        auth_code = query.get("code", [None])[0]
    else:
        returned_state = expected_state
        auth_code = callback

    if expected_state is not None and returned_state != expected_state:
        raise RuntimeError("OAuth callback failed: state mismatch")
    if not auth_code:
        raise RuntimeError("No authorization code found in callback")
    return auth_code


def wait_for_auth_code(redirect_uri: str, expected_state: str, timeout_seconds: int = 300) -> str:
    parsed = urlparse(redirect_uri)
    host = parsed.hostname or "localhost"
    port = parsed.port or 80

    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_sock.bind((host, port))
    server_sock.listen(1)
    server_sock.settimeout(timeout_seconds)

    try:
        conn, _addr = server_sock.accept()
    except socket.timeout as exc:
        raise RuntimeError("Timed out waiting for Tesla OAuth callback") from exc
    finally:
        server_sock.close()

    request_data = conn.recv(4096).decode("utf-8", errors="ignore")
    request_line = request_data.splitlines()[0] if request_data else ""
    path = request_line.split(" ", 2)[1] if "GET" in request_line else ""
    callback_url = f"{redirect_uri}?{urlparse(path).query}" if "?" in path else path
    response = (
        "HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n\r\n"
        "<html><body><h1>Authorization complete</h1>"
        "<p>You can close this window and return to the terminal.</p></body></html>"
    )
    conn.send(response.encode("utf-8"))
    conn.close()

    return parse_auth_code_from_callback(callback_url, expected_state)


def print_tesla_portal_checklist(config) -> None:
    parsed_redirect = urlparse(config.redirect_uri)
    origin_url = f"{parsed_redirect.scheme}://{parsed_redirect.netloc}"

    print("In https://developer.tesla.com → your app → Client Details, set ALL of:")
    print(f"  Allowed Origin URL(s):     {origin_url}")
    print(f"  Allowed Redirect URI(s):   {config.redirect_uri}")
    print(f"  Allowed Returned URL(s):   {config.redirect_uri}")
    print()
    print("Important:")
    print("  - Enable API scopes first (Vehicle Charging Management), save, wait ~2 min")
    print("  - Do not edit the app while the browser login is in progress")
    print("  - localhost and 127.0.0.1 are different hosts")
    print()


def main() -> int:
    parser = argparse.ArgumentParser(description="Authorize Tesla Fleet API access")
    parser.add_argument("--env-file", default=".env", help="Path to .env file")
    parser.add_argument(
        "--paste-url",
        metavar="CALLBACK_URL",
        help="Paste the full callback URL from the browser address bar after login",
    )
    args = parser.parse_args()

    config = load_config(args.env_file)
    configure_logging(config.log_file)
    print_tesla_portal_checklist(config)

    oauth_state = secrets.token_urlsafe(16)
    auth_url = build_authorize_url(config, oauth_state)

    if args.paste_url:
        print("Using pasted callback URL.")
        auth_code = parse_auth_code_from_callback(args.paste_url)
    else:
        print("Opening Tesla login in your browser...")
        print(f"If it does not open automatically, visit:\n{auth_url}\n")
        print("If login succeeds but the browser cannot reach localhost, copy the")
        print("full address bar URL and rerun with:")
        print("  python setup_auth.py --paste-url 'http://localhost:8585/callback?code=...&state=...'")
        print()
        webbrowser.open(auth_url)

        try:
            auth_code = wait_for_auth_code(config.redirect_uri, oauth_state)
        except RuntimeError as exc:
            if "Timed out" in str(exc):
                print()
                print("Timed out waiting for callback. If Tesla redirected in the browser,")
                print("copy the URL from the address bar and rerun with --paste-url.")
            raise
    token_data = exchange_code_for_tokens(config, auth_code)

    state = load_state(config.state_file)
    apply_token_response(state, token_data)
    save_state(config.state_file, state)

    logging.info("Tesla authorization saved to %s", config.state_file)
    print("Success. You can now run sync_invoices.py on a schedule.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        logging.exception("%s", exc)
        raise SystemExit(1) from exc
