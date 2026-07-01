"""Save invoice PDFs to a local folder."""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class LocalInvoiceStore:
    def __init__(self, directory: Path):
        self.directory = directory

    def ensure_exists(self) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)

    def save_pdf(self, filename: str, content: bytes) -> Path:
        path = self.directory / filename
        path.write_bytes(content)
        logger.info("Saved locally: %s", path)
        return path
