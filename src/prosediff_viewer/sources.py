"""Version sources for a book directory.

Two sources are auto-detected:

* **SnapshotSource** — an ``revision_snapshots/<doc>/`` layout where each
  snapshot file is named ``<doc>.<seq>.<UTC timestamp>.<label>.md`` (the
  autofiction-harness convention). The current working file (e.g.
  ``chapters/<doc>.md`` or ``final/<doc>.md``) is appended as a synthetic
  ``current`` version when it exists.

* **GitSource** — any git-*tracked* ``.md`` file under the book directory
  gets one version per commit that touched it, plus the working tree.

Both produce the same shape: documents with ordered versions, and a
``get_text(doc_id, version_id)`` accessor.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

_SNAP_RE = re.compile(
    r"^(?P<doc>.+)\.(?P<seq>\d{3,6})\.(?P<ts>\d{8}T\d{6}Z)\.(?P<label>.+)\.md$"
)

# Where a doc's current working copy may live, relative to the book dir.
_CURRENT_CANDIDATES = ("chapters", "final", ".", "exports")


def _fmt_ts(ts: str) -> str:
    # 20260705T092714Z -> 2026-07-05 09:27 UTC
    return f"{ts[0:4]}-{ts[4:6]}-{ts[6:8]} {ts[9:11]}:{ts[11:13]} UTC"


class SnapshotSource:
    name = "snapshots"

    def __init__(self, book_dir: Path):
        self.book_dir = book_dir
        self.snap_dir = book_dir / "revision_snapshots"
        self._paths: dict[tuple[str, str], Path] = {}

    def available(self) -> bool:
        return self.snap_dir.is_dir()

    def documents(self) -> list[dict]:
        docs = []
        for doc_dir in sorted(p for p in self.snap_dir.iterdir() if p.is_dir()):
            versions = []
            for f in sorted(doc_dir.glob("*.md")):
                m = _SNAP_RE.match(f.name)
                if not m:
                    continue
                vid = m.group("seq")
                versions.append({
                    "id": vid,
                    "label": f"#{int(m.group('seq'))} {m.group('label')}",
                    "detail": _fmt_ts(m.group("ts")),
                    "sort": (m.group("ts"), m.group("seq")),
                })
                self._paths[(doc_dir.name, vid)] = f
            if not versions:
                continue
            versions.sort(key=lambda v: v.pop("sort"))
            current = self._find_current(doc_dir.name)
            if current is not None:
                versions.append({
                    "id": "current",
                    "label": "current working copy",
                    "detail": str(current.relative_to(self.book_dir)),
                })
                self._paths[(doc_dir.name, "current")] = current
            docs.append({
                "id": f"snap:{doc_dir.name}",
                "title": doc_dir.name.replace("_", " "),
                "source": self.name,
                "versions": versions,
            })
        return docs

    def _find_current(self, doc: str) -> Path | None:
        for sub in _CURRENT_CANDIDATES:
            p = self.book_dir / sub / f"{doc}.md"
            if p.is_file():
                return p
        return None

    def get_text(self, doc_id: str, version_id: str) -> str:
        doc = doc_id.split(":", 1)[1]
        path = self._paths.get((doc, version_id))
        if path is None:
            self.documents()  # rescan
            path = self._paths[(doc, version_id)]
        return path.read_text(encoding="utf-8", errors="replace")


# Version-history noise: dirs the snapshot source already covers, plus
# machine artifacts. Matched against the first path component.
DEFAULT_GIT_EXCLUDE = {
    "revision_snapshots", "drafts", "logs", "critiques", "model_prompts",
    "rolling_summaries", "imagegen", "exports",
}


class GitSource:
    name = "git"

    def __init__(self, book_dir: Path, exclude: set[str] | None = None):
        self.book_dir = book_dir
        self.exclude = DEFAULT_GIT_EXCLUDE if exclude is None else exclude
        self.repo_root: Path | None = None
        self._docs_cache: list[dict] | None = None
        try:
            out = self._git("rev-parse", "--show-toplevel", cwd=book_dir)
            self.repo_root = Path(out.strip())
        except Exception:
            pass

    @staticmethod
    def _git(*args: str, cwd: Path) -> str:
        return subprocess.run(
            ["git", *args], cwd=cwd, check=True,
            capture_output=True, text=True,
        ).stdout

    def available(self) -> bool:
        return self.repo_root is not None

    def _included(self, rel: str) -> bool:
        if not rel.endswith(".md"):
            return False
        top = rel.split("/", 1)[0]
        return top not in self.exclude

    def documents(self) -> list[dict]:
        """Build every file's commit list from ONE `git log --name-status`
        pass — per-file `git log` is far too slow on large repos."""
        assert self.repo_root is not None
        if self._docs_cache is not None:
            return self._docs_cache
        tracked = {
            rel for rel in self._git("ls-files", cwd=self.repo_root).splitlines()
            if self._included(rel)
        }
        # oldest-first commit stream with the files each commit touched
        raw = self._git(
            "log", "--reverse", "--name-status", "--format=\x1e%h\x1f%cs\x1f%s",
            cwd=self.repo_root,
        )
        history: dict[str, list[dict]] = {}
        for entry in raw.split("\x1e"):
            if not entry.strip():
                continue
            header, _, body = entry.partition("\n")
            sha, date, subject = header.split("\x1f", 2)
            for line in body.splitlines():
                if not line.strip():
                    continue
                parts = line.split("\t")
                status = parts[0]
                # renames/copies: R100\told\tnew -> the new path gets the version
                path = parts[-1]
                if path not in tracked or status.startswith("D"):
                    continue
                history.setdefault(path, []).append({
                    "id": sha,
                    "label": f"{date} {subject[:60]}",
                    "detail": sha,
                })
        dirty = {
            line[3:].strip().strip('"')
            for line in self._git("status", "--porcelain", cwd=self.repo_root).splitlines()
        }
        docs = []
        for rel in sorted(history):
            versions = list(history[rel])
            if rel in dirty:
                versions.append({"id": "worktree", "label": "working tree (uncommitted)", "detail": rel})
            if len(versions) < 2:
                continue  # nothing to diff
            docs.append({
                "id": f"git:{rel}",
                "title": Path(rel).stem.replace("_", " "),
                "source": self.name,
                "versions": versions,
            })
        self._docs_cache = docs
        return docs

    def get_text(self, doc_id: str, version_id: str) -> str:
        assert self.repo_root is not None
        rel = doc_id.split(":", 1)[1]
        if version_id == "worktree":
            return (self.repo_root / rel).read_text(encoding="utf-8", errors="replace")
        return self._git("show", f"{version_id}:{rel}", cwd=self.repo_root)


class Book:
    """All detected version sources for one book directory."""

    def __init__(self, book_dir: str | Path):
        self.book_dir = Path(book_dir).expanduser().resolve()
        if not self.book_dir.is_dir():
            raise FileNotFoundError(f"book directory not found: {self.book_dir}")
        self.sources = [s for s in (SnapshotSource(self.book_dir), GitSource(self.book_dir)) if s.available()]

    def manifest(self) -> dict:
        docs: list[dict] = []
        for src in self.sources:
            docs.extend(src.documents())
        return {"book_dir": str(self.book_dir), "documents": docs}

    def get_text(self, doc_id: str, version_id: str) -> str:
        prefix = doc_id.split(":", 1)[0]
        for src in self.sources:
            if (prefix == "snap" and src.name == "snapshots") or (prefix == "git" and src.name == "git"):
                return src.get_text(doc_id, version_id)
        raise KeyError(f"unknown document: {doc_id}")
