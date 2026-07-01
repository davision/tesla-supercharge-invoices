"""Tesla Fleet API client for charging history and invoice PDFs."""

from __future__ import annotations

import logging
import re
import time
from typing import Any

import requests

from tesla_invoicer.config import AUTH_URL, TOKEN_URL, Config, TESLA_SCOPES
from tesla_invoicer.state import State, save_state

logger = logging.getLogger(__name__)


class TeslaApiError(Exception):
    pass


def _request_with_retry(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    params: dict[str, Any] | None = None,
    data: dict[str, Any] | None = None,
    retries: int = 3,
) -> requests.Response:
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            response = requests.request(method, url, headers=headers, params=params, data=data, timeout=60)
        except requests.RequestException as exc:
            last_error = exc
            time.sleep(attempt)
            continue

        if response.status_code == 429:
            wait = int(response.headers.get("Retry-After", attempt * 2))
            logger.warning("Tesla API rate limited, waiting %ss", wait)
            time.sleep(wait)
            continue

        return response

    raise TeslaApiError(f"Request failed after {retries} attempts: {last_error}")


def _parse_history_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []

    for key in ("data", "results", "response", "chargingHistory", "records", "history"):
        value = payload.get(key)
        if isinstance(value, list):
            return value
    return []


def exchange_code_for_tokens(config: Config, code: str) -> dict[str, Any]:
    response = _request_with_retry(
        "POST",
        TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "client_id": config.tesla_client_id,
            "client_secret": config.tesla_client_secret,
            "code": code,
            "redirect_uri": config.redirect_uri,
            "audience": config.fleet_api_base,
        },
    )
    if not response.ok:
        raise TeslaApiError(f"Token exchange failed ({response.status_code}): {response.text}")
    return response.json()


def refresh_access_token(config: Config, refresh_token: str) -> dict[str, Any]:
    response = _request_with_retry(
        "POST",
        TOKEN_URL,
        data={
            "grant_type": "refresh_token",
            "client_id": config.tesla_client_id,
            "refresh_token": refresh_token,
        },
    )
    if not response.ok:
        raise TeslaApiError(f"Token refresh failed ({response.status_code}): {response.text}")
    return response.json()


def build_authorize_url(config: Config, state: str) -> str:
    from urllib.parse import quote

    return (
        f"{AUTH_URL}?response_type=code"
        f"&client_id={quote(config.tesla_client_id)}"
        f"&redirect_uri={quote(config.redirect_uri)}"
        f"&scope={quote(TESLA_SCOPES)}"
        f"&state={quote(state)}"
        f"&prompt=login"
    )


def ensure_access_token(config: Config, state: State) -> str:
    if state.is_token_valid():
        return state.access_token  # type: ignore[return-value]

    if not state.refresh_token:
        raise TeslaApiError(
            "No Tesla refresh token found. Run setup_auth.py once to authorize the app."
        )

    token_data = refresh_access_token(config, state.refresh_token)
    state.access_token = token_data["access_token"]
    if token_data.get("refresh_token"):
        state.refresh_token = token_data["refresh_token"]
    state.expires_at = int(time.time()) + int(token_data.get("expires_in", 3600))
    save_state(config.state_file, state)
    logger.info("Refreshed Tesla access token")
    return state.access_token


def apply_token_response(state: State, token_data: dict[str, Any]) -> None:
    state.access_token = token_data["access_token"]
    state.refresh_token = token_data.get("refresh_token") or state.refresh_token
    state.expires_at = int(time.time()) + int(token_data.get("expires_in", 3600))


def fetch_charging_history(
    config: Config,
    access_token: str,
    *,
    page_size: int = 50,
    max_pages: int = 20,
) -> list[dict[str, Any]]:
    headers = {"Authorization": f"Bearer {access_token}"}
    all_records: list[dict[str, Any]] = []
    seen_session_ids: set[str] = set()

    for page in range(1, max_pages + 1):
        params: dict[str, Any] = {"pageNo": page, "pageSize": page_size}
        if config.tesla_vin:
            params["vin"] = config.tesla_vin

        url = f"{config.fleet_api_base}/api/1/dx/charging/history"
        response = _request_with_retry("GET", url, headers=headers, params=params)

        if response.status_code == 401:
            raise TeslaApiError("Tesla access token expired or invalid")
        if not response.ok:
            raise TeslaApiError(f"Charging history failed ({response.status_code}): {response.text}")

        records = _parse_history_payload(response.json())
        if not records:
            break

        new_on_page = 0
        for record in records:
            session_id = str(record.get("sessionId") or "")
            if session_id and session_id in seen_session_ids:
                continue
            if session_id:
                seen_session_ids.add(session_id)
            all_records.append(record)
            new_on_page += 1

        logger.info("Fetched page %s: %s charging session(s)", page, new_on_page)
        if len(records) < page_size or new_on_page == 0:
            break

    return all_records


def download_invoice_pdf(config: Config, access_token: str, content_id: str) -> bytes:
    url = f"{config.fleet_api_base}/api/1/dx/charging/invoice/{content_id}"
    response = _request_with_retry(
        "GET",
        url,
        headers={"Authorization": f"Bearer {access_token}"},
    )
    if not response.ok:
        raise TeslaApiError(f"Invoice download failed ({response.status_code}): {response.text[:200]}")
    return response.content


def safe_filename(name: str) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|]', "", name).strip()
    return cleaned or "invoice.pdf"


def invoice_filename(record: dict[str, Any]) -> str:
    invoices = record.get("invoices") or record.get("Invoices") or []
    if invoices:
        tesla_name = invoices[0].get("fileName")
        if tesla_name:
            return safe_filename(tesla_name)

    start = str(record.get("chargeStartDateTime") or "unknown")[:10].replace("-", "")
    location = safe_filename(str(record.get("siteLocationName") or "Unknown"))
    session_id = str(record.get("sessionId") or "session")
    return safe_filename(f"{start}_{location}_{session_id}.pdf")


def iter_invoice_items(record: dict[str, Any]) -> list[tuple[str, str]]:
    """Return (content_id, filename) pairs for invoices on a charging record."""
    invoices = record.get("invoices") or record.get("Invoices") or []
    items: list[tuple[str, str]] = []
    for invoice in invoices:
        content_id = invoice.get("contentId") or invoice.get("id")
        if not content_id:
            continue
        filename = safe_filename(invoice.get("fileName") or invoice_filename(record))
        items.append((str(content_id), filename))
    return items
