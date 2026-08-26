"""Static files storage for the project."""

from django.contrib.staticfiles.storage import ManifestStaticFilesStorage


class StorefrontStaticFilesStorage(ManifestStaticFilesStorage):
    """
    Hashed static storage that leaves JS `//# sourceMappingURL=` comments alone.

    We vendor minified bundles (Chart.js for the admin dashboard) whose sourcemap comment points at
    a `.map` we deliberately do not ship. The base storage tries to hash that missing map on
    collectstatic and the whole build fails. Dropping only the `*.js` sourcemap pattern skips that
    rewrite; the CSS `url()` / `@import` patterns stay strict, so a genuinely broken asset reference
    in our own stylesheet still breaks the build - which is the point of the manifest here.
    """

    patterns = tuple(group for group in ManifestStaticFilesStorage.patterns if group[0] != "*.js")
