"""Test helpers shared across apps."""

import tempfile
from pathlib import Path

from django.test import override_settings


class TempUploadsMixin:
    """
    Points both upload roots at throwaway directories for the duration of a test.

    Uploads are split in two (see `settings.MEDIA_ROOT` / `settings.PRODUCT_FILES_ROOT`), and a
    test that writes a product file or a preview must reach neither the working tree nor whatever
    the last run left behind. Both directories are removed when the test ends.
    """

    def setUp(self):
        super().setUp()

        self.media = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.private = Path(self.enterContext(tempfile.TemporaryDirectory()))

        self.enterContext(override_settings(MEDIA_ROOT=self.media, PRODUCT_FILES_ROOT=self.private))
