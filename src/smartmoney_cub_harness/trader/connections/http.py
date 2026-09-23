"""Small HTTP primitive for credential-bearing connector requests."""
from __future__ import annotations

import urllib.request


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Refuse redirects so bearer tokens cannot cross to another origin."""

    def redirect_request(self, request, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


_OPENER = urllib.request.build_opener(_NoRedirect)


def open_without_redirect(request: urllib.request.Request, *, timeout: int | float):
    return _OPENER.open(request, timeout=timeout)
