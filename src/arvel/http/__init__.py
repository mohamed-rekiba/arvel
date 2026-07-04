"""arvel.http — HTTP kernel, Request/Response, middleware, OpenAPI (on Litestar).

Built on **Litestar** (the `[http]` extra), lazy-imported in the serve path so
`import arvel` stays light. Importing this module pulls in no heavy libraries.
Grounded in knowledge/port/04-http-kernel-middleware.md.
"""

from __future__ import annotations

from arvel.http.exceptions import HttpException, abort
from arvel.http.kernel import HttpKernel
from arvel.http.middleware import reset_rate_limiter, reset_sessions
from arvel.http.redirect import Redirect, redirect
from arvel.http.request import Request, UploadedFile, current_request, current_user
from arvel.http.response import FileDownload, Response, StreamValue, response

__all__ = [
    "FileDownload",
    "HttpException",
    "HttpKernel",
    "Redirect",
    "Request",
    "Response",
    "StreamValue",
    "UploadedFile",
    "abort",
    "current_request",
    "current_user",
    "redirect",
    "reset_rate_limiter",
    "reset_sessions",
    "response",
]
