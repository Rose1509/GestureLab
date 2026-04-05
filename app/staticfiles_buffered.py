"""Serve static files without Starlette FileResponse body streaming.

Starlette's FileResponse uses anyio async file reads, which often hit OSError errno 22
on OneDrive for Windows. We send bodies using sync reads only.

When direct reads still fail (OneDrive placeholders), we try shutil, ``CopyFileW``,
and PowerShell/.NET temp copies. If WinError 362 (*cloud file provider is not running*)
still applies, image requests return a tiny placeholder (200); other types return 503
with a short fix hint.
"""

from __future__ import annotations

import base64
import errno
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import anyio
from starlette.datastructures import Headers
from starlette.responses import FileResponse, PlainTextResponse, Response, StreamingResponse
from starlette.staticfiles import NotModifiedResponse, StaticFiles
from starlette.types import Scope

_MAX_BUFFER_BYTES = 512 * 1024 * 1024  # single read for typical static assets; avoids fragile range I/O
_STREAM_CHUNK = 1024 * 1024
_READ_RETRIES = 8

# 1x1 transparent PNG — used when image bytes cannot be read (e.g. OneDrive placeholders).
_MIN_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)
_MIN_SVG = b'<svg xmlns="http://www.w3.org/2000/svg" width="1" height="1"></svg>'
_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".bmp", ".svg"}


def _path_candidates(path_str: str) -> list[str]:
    abspath = os.path.abspath(path_str)
    norm = os.path.normpath(abspath)
    out: list[str] = []
    for p in (path_str, abspath, norm):
        if p and p not in out:
            out.append(p)
    if sys.platform == "win32" and not abspath.startswith("\\\\?\\"):
        longp = "\\\\?\\" + abspath
        if longp not in out:
            out.append(longp)
    return out


def _copyfile_w(src: str, dst: str) -> None:
    """Windows kernel32 CopyFileW — sometimes works when shutil.copyfile errno 22s."""
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    CopyFileW = kernel32.CopyFileW
    CopyFileW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.BOOL]
    CopyFileW.restype = wintypes.BOOL
    s = os.path.normpath(os.path.abspath(src))
    d = os.path.normpath(os.path.abspath(dst))
    if not CopyFileW(s, d, False):
        raise ctypes.WinError(ctypes.get_last_error())


def _dotnet_copy_into_temp(src: str, tmp: str) -> None:
    """Use .NET file APIs via PowerShell; paths passed in env to avoid quoting bugs."""
    env = {**os.environ, "GL_STATIC_SRC": os.path.abspath(src), "GL_STATIC_DST": os.path.abspath(tmp)}
    script = "[IO.File]::WriteAllBytes($env:GL_STATIC_DST, [IO.File]::ReadAllBytes($env:GL_STATIC_SRC))"
    r = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", script],
        env=env,
        capture_output=True,
        timeout=120,
    )
    if r.returncode != 0:
        msg = (r.stderr or r.stdout or b"").decode("utf-8", "replace").strip() or "PowerShell copy failed"
        raise OSError(msg)


def _read_via_temp_copy(src: str) -> bytes:
    """Copy source to a temp file on local disk, then read bytes from the temp file."""
    suffix = Path(src).suffix or ".bin"
    fd, tmp = tempfile.mkstemp(prefix="static_", suffix=suffix)
    os.close(fd)
    try:
        try:
            shutil.copyfile(src, tmp)
        except OSError:
            if sys.platform == "win32":
                try:
                    _copyfile_w(src, tmp)
                except OSError:
                    _dotnet_copy_into_temp(src, tmp)
            else:
                raise
        return Path(tmp).read_bytes()
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def _read_file_bytes(path_str: str) -> bytes:
    """Read full file: Path.read_bytes, buffered open, then tempfile copy fallback."""
    candidates = _path_candidates(path_str)
    last_err: OSError | None = None

    for attempt in range(_READ_RETRIES):
        for cand in candidates:
            try:
                return Path(cand).read_bytes()
            except OSError as e:
                last_err = e
            try:
                with open(cand, "rb") as f:
                    return f.read()
            except OSError as e:
                last_err = e
        for cand in candidates:
            try:
                return _read_via_temp_copy(cand)
            except OSError as e:
                last_err = e

        if attempt + 1 < _READ_RETRIES:
            # errno 22 (EINVAL) on Windows / OneDrive — backoff so hydration can finish
            errn = getattr(last_err, "errno", None) if last_err else None
            if errn == errno.EINVAL or errn == 22:
                time.sleep(min(0.25 * (2**attempt), 2.0))
            else:
                time.sleep(0.08 * (attempt + 1))

    raise last_err if last_err else OSError(errno.EIO, "read failed", path_str)


def _is_image_path(path_str: str) -> bool:
    return Path(path_str).suffix.lower() in _IMAGE_EXTS


def _placeholder_image_response(path_str: str) -> Response:
    ext = Path(path_str).suffix.lower()
    if ext == ".svg":
        body, media = _MIN_SVG, "image/svg+xml"
    else:
        body, media = _MIN_PNG, "image/png"
    return Response(
        content=body,
        status_code=200,
        media_type=media,
        headers={
            "Content-Length": str(len(body)),
            "Cache-Control": "no-store",
            "X-GestureLab-Static-Fallback": "1",
            "X-GestureLab-Static-Hint": (
                "Cloud-only file could not be read. Start OneDrive, or pin this folder "
                "to 'Always keep on this device', or move the project out of OneDrive."
            ),
        },
    )


def _nonimage_unavailable_response(exc: OSError) -> PlainTextResponse:
    win = getattr(exc, "winerror", None)
    low = str(exc).lower()
    if win == 362 or "cloud file provider" in low or "362" in low:
        text = (
            "This file is only in the cloud and OneDrive is not running (or files are not "
            "available offline). Start OneDrive, or in File Explorer right‑click the project "
            "folder → OneDrive → Always keep on this device, or move the project to a folder "
            "outside OneDrive (for example C:\\dev\\GestureLab)."
        )
    else:
        text = "Static file temporarily unavailable."
    return PlainTextResponse(text, status_code=503)


async def _stream_from_buffered_read(path_str: str, total: int):
    """Large non-image files: full read in a worker thread, then chunk outbound."""
    body = await anyio.to_thread.run_sync(_read_file_bytes, path_str)
    if len(body) != total and total > 0:
        pass  # stat vs read mismatch (rare); still serve what we read
    offset = 0
    n = len(body)
    while offset < n:
        yield body[offset : offset + _STREAM_CHUNK]
        offset += _STREAM_CHUNK


class BufferedStaticFiles(StaticFiles):
    def file_response(
        self,
        full_path: str | os.PathLike[str],
        stat_result: os.stat_result,
        scope: Scope,
        status_code: int = 200,
    ) -> Response:
        request_headers = Headers(scope=scope)
        path_str = os.fspath(full_path)
        size = int(stat_result.st_size or 0)

        header_only = FileResponse(full_path, status_code=status_code, stat_result=stat_result)
        if self.is_not_modified(header_only.headers, request_headers):
            return NotModifiedResponse(header_only.headers)

        if scope["method"] == "HEAD":
            return Response(content=b"", status_code=status_code, headers=header_only.headers)

        if size > _MAX_BUFFER_BYTES:
            # Huge images: still try one full read (rare); placeholder keeps Content-Length correct.
            if _is_image_path(path_str):
                try:
                    body = _read_file_bytes(path_str)
                except OSError:
                    return _placeholder_image_response(path_str)
                return Response(content=body, status_code=status_code, headers=header_only.headers)
            return StreamingResponse(
                _stream_from_buffered_read(path_str, size),
                status_code=status_code,
                headers=header_only.headers,
                media_type=header_only.media_type,
            )

        try:
            body = _read_file_bytes(path_str)
        except OSError as e:
            if _is_image_path(path_str):
                return _placeholder_image_response(path_str)
            return _nonimage_unavailable_response(e)

        return Response(content=body, status_code=status_code, headers=header_only.headers)
