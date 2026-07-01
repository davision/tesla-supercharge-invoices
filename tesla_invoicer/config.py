"""Configuration loaded from environment / .env file."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

FLEET_API_BASE = {
    "na": "https://fleet-api.prd.na.vn.cloud.tesla.com",
    "eu": "https://fleet-api.prd.eu.vn.cloud.tesla.com",
    "cn": "https://fleet-api.prd.cn.vn.cloud.tesla.cn",
}

TOKEN_URL = "https://fleet-auth.prd.vn.cloud.tesla.com/oauth2/v3/token"
AUTH_URL = "https://auth.tesla.com/oauth2/v3/authorize"
DEFAULT_REDIRECT_URI = "http://localhost:8585/callback"
TESLA_SCOPES = "openid offline_access vehicle_charging_cmds"


@dataclass(frozen=True)
class Config:
    tesla_client_id: str
    tesla_client_secret: str
    tesla_region: str
    tesla_vin: str | None
    invoices_dir: Path
    dropbox_access_token: str | None
    dropbox_folder: str
    state_file: Path
    log_file: Path | None
    redirect_uri: str

    @property
    def fleet_api_base(self) -> str:
        region = self.tesla_region.lower()
        if region not in FLEET_API_BASE:
            raise ValueError(f"Unsupported TESLA_REGION: {self.tesla_region!r} (use na, eu, or cn)")
        return FLEET_API_BASE[region]


def load_config(env_file: str | Path | None = None) -> Config:
    if env_file:
        load_dotenv(env_file)
    else:
        load_dotenv()

    def require(name: str) -> str:
        value = os.getenv(name, "").strip()
        if not value:
            raise ValueError(f"Missing required environment variable: {name}")
        return value

    state_file = Path(os.getenv("STATE_FILE", "./state.json")).expanduser()
    log_file_raw = os.getenv("LOG_FILE", "").strip()
    log_file = Path(log_file_raw).expanduser() if log_file_raw else None

    dropbox_folder = os.getenv("DROPBOX_FOLDER", "/Tesla/Invoices").strip()
    if not dropbox_folder.startswith("/"):
        dropbox_folder = f"/{dropbox_folder}"
    dropbox_folder = dropbox_folder.rstrip("/")

    vin = os.getenv("TESLA_VIN", "").strip() or None
    invoices_dir = Path(os.getenv("INVOICES_DIR", "./invoices")).expanduser()

    dropbox_token = os.getenv("DROPBOX_ACCESS_TOKEN", "").strip() or None

    return Config(
        tesla_client_id=require("TESLA_CLIENT_ID"),
        tesla_client_secret=require("TESLA_CLIENT_SECRET"),
        tesla_region=os.getenv("TESLA_REGION", "eu").strip().lower(),
        tesla_vin=vin,
        invoices_dir=invoices_dir,
        dropbox_access_token=dropbox_token,
        dropbox_folder=dropbox_folder,
        state_file=state_file,
        log_file=log_file,
        redirect_uri=os.getenv("TESLA_REDIRECT_URI", DEFAULT_REDIRECT_URI).strip(),
    )
