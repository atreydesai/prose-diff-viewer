"""Command-line interface: serve the viewer, or export one diff to HTML."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .diff import diff_documents
from .server import STATIC_DIR, serve
from .sources import Book


def _cmd_serve(args: argparse.Namespace) -> int:
    serve(args.book, host=args.host, port=args.port)
    return 0


def _cmd_list(args: argparse.Namespace) -> int:
    book = Book(args.book)
    for doc in book.manifest()["documents"]:
        print(f"{doc['id']}  ({len(doc['versions'])} versions)")
        if args.verbose:
            for v in doc["versions"]:
                print(f"    {v['id']:>8}  {v['label']}  [{v.get('detail', '')}]")
    return 0


_EXPORT_TEMPLATE = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>{css}
body {{ display: block; }}
.doc {{ margin: 0 auto; }}
header.meta {{ max-width: 44rem; margin: 24px auto 0; padding: 0 32px;
  font: 13px/1.5 -apple-system, sans-serif; color: var(--muted); }}
</style></head><body>
<header class="meta">{title} · base {base} → compare {compare} ·
<span style="color: var(--ins)">+{added} words</span> ·
<span style="color: var(--del)">−{removed} words</span></header>
<div class="doc">{body}</div>
</body></html>
"""


def _cmd_diff(args: argparse.Namespace) -> int:
    book = Book(args.book)
    old = book.get_text(args.doc, args.base)
    new = book.get_text(args.doc, args.compare)
    r = diff_documents(old, new)
    html = _EXPORT_TEMPLATE.format(
        title=args.doc,
        css=(STATIC_DIR / "viewer.css").read_text(),
        base=args.base,
        compare=args.compare,
        added=r.words_added,
        removed=r.words_removed,
        body=r.html,
    )
    out = Path(args.output)
    out.write_text(html, encoding="utf-8")
    print(f"wrote {out}  (+{r.words_added} / -{r.words_removed} words, "
          f"{len(r.changes)} changed passages)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="prose-diff-viewer",
        description="Inline word-level diff viewer for markdown book drafts.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_serve = sub.add_parser("serve", help="run the local web viewer")
    p_serve.add_argument("--book", required=True, help="book output directory")
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8765)
    p_serve.set_defaults(func=_cmd_serve)

    p_list = sub.add_parser("list", help="list documents and versions")
    p_list.add_argument("--book", required=True)
    p_list.add_argument("-v", "--verbose", action="store_true")
    p_list.set_defaults(func=_cmd_list)

    p_diff = sub.add_parser("diff", help="export one diff as a standalone HTML file")
    p_diff.add_argument("--book", required=True)
    p_diff.add_argument("doc", help="document id (see `list`)")
    p_diff.add_argument("base", help="base version id")
    p_diff.add_argument("compare", help="compare version id")
    p_diff.add_argument("-o", "--output", default="diff.html")
    p_diff.set_defaults(func=_cmd_diff)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
