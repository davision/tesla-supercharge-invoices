"""Dropbox upload helpers."""

from __future__ import annotations

import logging

import dropbox
from dropbox.files import WriteMode

logger = logging.getLogger(__name__)


class DropboxUploader:
    def __init__(self, access_token: str, folder: str):
        self._client = dropbox.Dropbox(access_token)
        self.folder = folder.rstrip("/")

    def upload_pdf(self, filename: str, content: bytes) -> str:
        dropbox_path = f"{self.folder}/{filename}"
        self._client.files_upload(
            content,
            dropbox_path,
            mode=WriteMode.overwrite,
            mute=True,
        )
        logger.info("Uploaded to Dropbox: %s", dropbox_path)
        return dropbox_path

    def ensure_folder_exists(self) -> None:
        if not self.folder or self.folder == "/":
            return
        try:
            self._client.files_create_folder_v2(self.folder)
            logger.info("Created Dropbox folder: %s", self.folder)
        except dropbox.exceptions.ApiError as exc:
            if exc.error.is_path() and exc.error.get_path().is_conflict():
                return
            raise
