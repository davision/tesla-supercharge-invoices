"""Sync new Tesla charging invoices to local disk and optionally Dropbox."""

from __future__ import annotations

import logging

from tesla_invoicer.config import Config
from tesla_invoicer.dropbox_client import DropboxUploader
from tesla_invoicer.local_storage import LocalInvoiceStore
from tesla_invoicer.state import load_state, save_state
from tesla_invoicer.tesla_client import (
    TeslaApiError,
    download_invoice_pdf,
    ensure_access_token,
    fetch_charging_history,
    iter_invoice_items,
)

logger = logging.getLogger(__name__)


def sync_invoices(config: Config) -> int:
    """Download new invoice PDFs to local disk and optionally upload to Dropbox.

    Returns the number of new invoices downloaded.
    """
    state = load_state(config.state_file)
    access_token = ensure_access_token(config, state)
    records = fetch_charging_history(config, access_token)
    logger.info("Found %s charging session(s) in history", len(records))

    local = LocalInvoiceStore(config.invoices_dir)
    local.ensure_exists()

    dropbox: DropboxUploader | None = None
    if config.dropbox_access_token:
        dropbox = DropboxUploader(config.dropbox_access_token, config.dropbox_folder)
        dropbox.ensure_folder_exists()
    else:
        logger.info("DROPBOX_ACCESS_TOKEN not set — saving locally only")

    downloaded = 0
    for record in records:
        for content_id, filename in iter_invoice_items(record):
            if state.is_processed(content_id):
                continue

            logger.info("Downloading invoice %s (%s)", content_id, filename)
            pdf_bytes = download_invoice_pdf(config, access_token, content_id)
            local.save_pdf(filename, pdf_bytes)

            if dropbox:
                dropbox.upload_pdf(filename, pdf_bytes)

            state.mark_processed(content_id)
            downloaded += 1

    save_state(config.state_file, state)
    logger.info("Sync complete: %s new invoice(s) downloaded", downloaded)
    return downloaded


def run_sync(config: Config) -> int:
    try:
        return sync_invoices(config)
    except TeslaApiError:
        logger.exception("Tesla API error during sync")
        raise
