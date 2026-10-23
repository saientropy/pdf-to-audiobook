#!/usr/bin/env python3
"""Serve the read-along player and one audiobook folder to phones on the same Wi-Fi.

    python3 player/serve.py out/            # the folder that `audiobook` wrote
    python3 player/serve.py --demo          # the demo paper that ships with the player

Open the printed http://<your-computer>:8000/... address on the phone.

Python's built-in http.server does not answer HTTP Range requests, and Safari on iPhone
does not play audio without them, so this server adds Range support. Standard library only.
"""

from __future__ import annotations

import argparse
import http.server
import json
import os
import re
import socket
import sys
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit

PLAYER = Path(__file__).resolve().parent


class Handler(http.server.SimpleHTTPRequestHandler):
    book_dir: Path | None = None

    def translate_path(self, path: str) -> str:
        path = unquote(urlsplit(path).path)
        if self.book_dir and path.startswith("/book/"):
            root, rel = self.book_dir, path[len("/book/"):]
        else:
            root, rel = PLAYER, path.lstrip("/")
        parts = [p for p in rel.split("/") if p not in ("", ".")]
        if ".." in parts:
            return str(root / "__forbidden__")
        return str(root.joinpath(*parts))

    def send_head(self):
        path = self.translate_path(self.path)
        rng = self.headers.get("Range")
        if not rng or not os.path.isfile(path):
            return super().send_head()
        m = re.fullmatch(r"bytes=(\d*)-(\d*)", rng.strip())
        size = os.path.getsize(path)
        if not m or (not m[1] and not m[2]):
            return super().send_head()
        if m[1]:
            start, end = int(m[1]), int(m[2]) if m[2] else size - 1
        else:  # suffix range: the last N bytes
            start, end = max(0, size - int(m[2])), size - 1
        end = min(end, size - 1)
        if start > end:
            self.send_response(416)
            self.send_header("Content-Range", f"bytes */{size}")
            self.end_headers()
            return None
        f = open(path, "rb")
        f.seek(start)
        self.send_response(206)
        self.send_header("Content-Type", self.guess_type(path))
        self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Content-Length", str(end - start + 1))
        self.send_header("Accept-Ranges", "bytes")
        self.end_headers()
        self._remaining = end - start + 1
        return f

    def copyfile(self, source, outputfile):
        remaining = getattr(self, "_remaining", None)
        if remaining is None:
            return super().copyfile(source, outputfile)
        self._remaining = None
        while remaining > 0:
            chunk = source.read(min(64 * 1024, remaining))
            if not chunk:
                break
            outputfile.write(chunk)
            remaining -= len(chunk)

    def end_headers(self):
        if self.command in ("GET", "HEAD") and not self.headers.get("Range"):
            self.send_header("Accept-Ranges", "bytes")
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()


def lan_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))  # no packet is sent; this only picks the outgoing interface
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("book_dir", nargs="?", help="folder with book.json, the chapter audio and the PDF")
    ap.add_argument("--demo", action="store_true", help="serve the demo paper")
    ap.add_argument("--pdf", help="path to the PDF if it is not in the book folder")
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args()

    if args.demo or not args.book_dir:
        query = "?demo=1"
    else:
        book_dir = Path(args.book_dir).resolve()
        if not (book_dir / "book.json").is_file():
            sys.exit(f"No book.json in {book_dir}")
        Handler.book_dir = book_dir
        query = "?book=book/book.json"
        source = json.loads((book_dir / "book.json").read_text(encoding="utf-8")).get("source_pdf") or ""
        pdf = Path(args.pdf) if args.pdf else Path(source)
        if not pdf.is_file():
            pdf = book_dir / Path(source).name
        if not pdf.is_file():
            sys.exit(f"Cannot find the PDF ({source}). Give its path with --pdf.")
        pdf = pdf.resolve()
        if pdf.parent != book_dir:
            # The player reads files from the book folder only, so link the PDF in.
            link = book_dir / pdf.name
            if not link.exists():
                link.symlink_to(pdf)
        query += "&pdf=" + quote(pdf.name)

    httpd = http.server.ThreadingHTTPServer(("0.0.0.0", args.port), Handler)
    print("Open this address on your phone (same Wi-Fi as this computer):")
    print(f"  http://{lan_ip()}:{args.port}/{query}")
    print(f"On this computer: http://localhost:{args.port}/{query}")
    print("Press Ctrl+C to stop.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
