"""Markdown-aware inline diff rendering.

Produces latexdiff-style output for prose: added text blue + underlined,
removed text red + struck through, rendered as formatted HTML rather than
raw markdown. Block-level structure (paragraphs, headings, hrs,
blockquotes) is preserved; changes within a paragraph are marked at word
granularity.

Stdlib only.
"""

from __future__ import annotations

import difflib
import html
import re
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Tokenization / block splitting
# ---------------------------------------------------------------------------

_BLOCK_SPLIT_RE = re.compile(r"\n\s*\n")
_WORD_RE = re.compile(r"\S+")


def split_blocks(text: str) -> list[str]:
    """Split markdown into blank-line-separated blocks."""
    return [b.strip("\n") for b in _BLOCK_SPLIT_RE.split(text.strip()) if b.strip()]


def _tokens(text: str) -> list[str]:
    """Word tokens (whitespace normalized away; paragraph breaks kept)."""
    out: list[str] = []
    for para in _BLOCK_SPLIT_RE.split(text):
        words = _WORD_RE.findall(para)
        if words:
            if out:
                out.append("\n\n")
            out.extend(words)
    return out


# ---------------------------------------------------------------------------
# Minimal inline-markdown renderer (novel prose: em/strong/code)
# ---------------------------------------------------------------------------

def render_inline(text: str) -> str:
    s = html.escape(text, quote=False)
    s = re.sub(r"\*\*\*(.+?)\*\*\*", r"<strong><em>\1</em></strong>", s, flags=re.S)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s, flags=re.S)
    s = re.sub(r"(?<![\w*])\*([^*\n]+)\*(?![\w*])", r"<em>\1</em>", s)
    s = re.sub(r"_([^_\n]+)_", r"<em>\1</em>", s)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    return s


_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$", re.S)
_HR_RE = re.compile(r"^(\*\s*\*\s*\*[\s*]*|-{3,}|_{3,})$")


def render_block(block: str, inner: str | None = None) -> str:
    """Render one markdown block to HTML. If *inner* is given it is
    already-rendered inline HTML to place inside the block wrapper."""
    stripped = block.strip()
    m = _HEADING_RE.match(stripped)
    if m:
        level = len(m.group(1))
        body = inner if inner is not None else render_inline(m.group(2))
        return f"<h{level}>{body}</h{level}>"
    if _HR_RE.match(stripped):
        return "<hr>"
    if all(line.lstrip().startswith(">") for line in stripped.splitlines()):
        text = "\n".join(line.lstrip()[1:].lstrip() for line in stripped.splitlines())
        body = inner if inner is not None else render_inline(text)
        return f"<blockquote><p>{body}</p></blockquote>"
    body = inner if inner is not None else render_inline(re.sub(r"\s*\n\s*", " ", stripped))
    return f"<p>{body}</p>"


def _block_kind_and_text(block: str) -> tuple[str, str]:
    """Return (kind, plain-diffable-text) for a block."""
    stripped = block.strip()
    m = _HEADING_RE.match(stripped)
    if m:
        return f"h{len(m.group(1))}", m.group(2)
    if _HR_RE.match(stripped):
        return "hr", ""
    if all(line.lstrip().startswith(">") for line in stripped.splitlines()):
        return "bq", "\n".join(line.lstrip()[1:].lstrip() for line in stripped.splitlines())
    return "p", re.sub(r"\s*\n\s*", " ", stripped)


# ---------------------------------------------------------------------------
# Diff
# ---------------------------------------------------------------------------

@dataclass
class DiffResult:
    html: str
    changes: list[dict] = field(default_factory=list)  # [{id, excerpt}]
    words_added: int = 0
    words_removed: int = 0


def _word_diff_html(old_text: str, new_text: str, res: DiffResult) -> str:
    """Word-level inline diff of two prose strings -> inline HTML."""
    a, b = _tokens(old_text), _tokens(new_text)
    sm = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
    parts: list[str] = []

    def emit(tokens: list[str], tag: str | None) -> None:
        if not tokens:
            return
        # split runs at paragraph breaks so <ins>/<del> stay within paragraphs
        run: list[str] = []

        def flush() -> None:
            if not run:
                return
            body = render_inline(" ".join(run))
            parts.append(f"<{tag}>{body}</{tag}>" if tag else body)
            run.clear()

        for tok in tokens:
            if tok == "\n\n":
                flush()
                parts.append("\x00")  # paragraph-break sentinel
            else:
                run.append(tok)
        flush()

    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op in ("equal",):
            emit(a[i1:i2], None)
        if op in ("replace", "delete"):
            seg = [t for t in a[i1:i2]]
            res.words_removed += sum(1 for t in seg if t != "\n\n")
            emit(seg, "del")
        if op in ("replace", "insert"):
            seg = [t for t in b[j1:j2]]
            res.words_added += sum(1 for t in seg if t != "\n\n")
            emit(seg, "ins")

    # join word runs with spaces, paragraphs with </p><p>
    joined: list[str] = []
    for i, part in enumerate(parts):
        if part == "\x00":
            joined.append("</p><p>")
        else:
            if joined and joined[-1] != "</p><p>" and i > 0:
                joined.append(" ")
            joined.append(part)
    return "".join(joined)


def diff_documents(old_text: str, new_text: str) -> DiffResult:
    """Full-document markdown diff -> DiffResult with rendered HTML."""
    res = DiffResult(html="")
    old_blocks, new_blocks = split_blocks(old_text), split_blocks(new_text)
    # compare on normalized diffable text so pure-whitespace changes are equal
    old_keys = [" ".join(_block_kind_and_text(b)) for b in old_blocks]
    new_keys = [" ".join(_block_kind_and_text(b)) for b in new_blocks]
    sm = difflib.SequenceMatcher(a=old_keys, b=new_keys, autojunk=False)

    out: list[str] = []
    change_n = 0

    def add_change(html_str: str, excerpt_src: str, kind: str) -> str:
        nonlocal change_n
        change_n += 1
        cid = f"chg-{change_n}"
        words = _WORD_RE.findall(excerpt_src)
        excerpt = " ".join(words[:12]) + ("…" if len(words) > 12 else "")
        res.changes.append({"id": cid, "excerpt": excerpt, "kind": kind})
        return f'<div class="change" id="{cid}">{html_str}</div>'

    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            out.extend(render_block(b) for b in new_blocks[j1:j2])
        elif op == "delete":
            for b in old_blocks[i1:i2]:
                kind, text = _block_kind_and_text(b)
                res.words_removed += len(_WORD_RE.findall(text))
                inner = f"<del>{render_inline(text)}</del>" if text else None
                blk = render_block(b, inner) if text else f'<del class="block">{render_block(b)}</del>'
                out.append(add_change(blk, text or b, "removed"))
        elif op == "insert":
            for b in new_blocks[j1:j2]:
                kind, text = _block_kind_and_text(b)
                res.words_added += len(_WORD_RE.findall(text))
                inner = f"<ins>{render_inline(text)}</ins>" if text else None
                blk = render_block(b, inner) if text else f'<ins class="block">{render_block(b)}</ins>'
                out.append(add_change(blk, text or b, "added"))
        else:  # replace: word-level diff across the whole changed region
            old_seg = "\n\n".join(_block_kind_and_text(b)[1] for b in old_blocks[i1:i2])
            new_seg = "\n\n".join(_block_kind_and_text(b)[1] for b in new_blocks[j1:j2])
            # preserve heading structure when the region is a single same-kind block
            if (i2 - i1 == 1 and j2 - j1 == 1
                    and _block_kind_and_text(old_blocks[i1])[0] == _block_kind_and_text(new_blocks[j1])[0]
                    and _block_kind_and_text(new_blocks[j1])[0] != "p"):
                inner = _word_diff_html(old_seg, new_seg, res)
                out.append(add_change(render_block(new_blocks[j1], inner), new_seg, "edited"))
            else:
                inner = _word_diff_html(old_seg, new_seg, res)
                out.append(add_change(f"<p>{inner}</p>", new_seg, "edited"))

    res.html = "\n".join(out)
    return res


def render_document(text: str) -> str:
    """Render a single version (no diff) to HTML."""
    return "\n".join(render_block(b) for b in split_blocks(text))
