"""Local web server for the prose diff viewer. Stdlib only."""

from __future__ import annotations

import json
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .diff import diff_documents, render_document
from .sources import Book

STATIC_DIR = Path(__file__).parent / "static"


def make_handler(book: Book):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):  # quieter logs
            pass

        def _send(self, code: int, body: bytes, ctype: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, obj, code: int = 200) -> None:
            self._send(code, json.dumps(obj).encode(), "application/json")

        def do_GET(self):  # noqa: N802
            url = urlparse(self.path)
            q = {k: v[0] for k, v in parse_qs(url.query).items()}
            try:
                if url.path == "/api/manifest":
                    self._json(book.manifest())
                elif url.path == "/api/diff":
                    old = book.get_text(q["doc"], q["base"])
                    new = book.get_text(q["doc"], q["compare"])
                    r = diff_documents(old, new)
                    self._json({
                        "html": r.html,
                        "changes": r.changes,
                        "words_added": r.words_added,
                        "words_removed": r.words_removed,
                    })
                elif url.path == "/api/version":
                    text = book.get_text(q["doc"], q["id"])
                    self._json({"html": render_document(text)})
                else:
                    self._static(url.path)
            except (KeyError, FileNotFoundError) as e:
                self._json({"error": str(e)}, 404)
            except Exception as e:  # surface errors to the UI
                self._json({"error": f"{type(e).__name__}: {e}"}, 500)

        def _static(self, path: str) -> None:
            rel = "index.html" if path in ("/", "") else path.lstrip("/")
            f = (STATIC_DIR / rel).resolve()
            if not f.is_file() or STATIC_DIR.resolve() not in f.parents:
                self._json({"error": "not found"}, 404)
                return
            ctype = mimetypes.guess_type(f.name)[0] or "application/octet-stream"
            self._send(200, f.read_bytes(), ctype)

    return Handler


def serve(book_dir: str, host: str = "127.0.0.1", port: int = 8765) -> None:
    book = Book(book_dir)
    httpd = ThreadingHTTPServer((host, port), make_handler(book))
    n_docs = len(book.manifest()["documents"])
    print(f"prose-diff-viewer: {n_docs} document(s) from {book.book_dir}")
    print(f"  -> http://{host}:{port}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
