"""Where the paid files live."""

import os

from django.conf import settings
from django.core.files.storage import FileSystemStorage


class ProductFilesStorage(FileSystemStorage):
    """
    `PRODUCT_FILES_ROOT`: outside MEDIA_ROOT, so no URL maps onto it.

    A product file is what the customer paid for, and the only way to it is `DownloadFileView`,
    behind a token. Keeping it out of the tree nginx serves means one misplaced `location` cannot
    give the catalogue away.

    `base_url` stays unset, so `product.file.url` raises instead of handing out a path, and the
    root is read from settings on every access rather than frozen at import - that is what lets a
    test redirect the uploads it makes.
    """

    @property
    def base_url(self):
        """Unset, and unlike the inherited one it does not fall back to MEDIA_URL."""

        return None

    @property
    def base_location(self):
        return settings.PRODUCT_FILES_ROOT

    @property
    def location(self):
        return os.path.abspath(self.base_location)
