# prose-diff-viewer

A local, inline diff viewer for **markdown book drafts** when I'm making books for [autofiction](https://www.autofiction.ai/). It's an easier way to visually see how
manuscript changed between any two versions:
added text blue + underlined, removed text red + struck through.

Inspired by [alpaylan/latex-diff-viewer](https://github.com/alpaylan/latex-diff-viewer),
reworked for my use!

## Quick start

```bash
PYTHONPATH=src python3 -m prosediff_viewer.cli serve --book /path/to/book/output
# -> http://127.0.0.1:8765
```

or install it:

```bash
pip install -e .
pdv serve --book /path/to/book/output
```

Pick a document, pick **Base** and **Compare** versions, hit **Show diff**.
`n` / `p` step through changes; **◀ step / step ▶** slides both selections
through history one version at a time; **Clean read** hides deletions so you
can read the new text straight through. Diffs are deep-linkable
(`?doc=…&base=…&compare=…`).

## Where versions come from

Two sources are auto-detected inside the `--book` directory:

1. **Revision snapshots** — a `revision_snapshots/<doc>/` layout where each
   file is `<doc>.<seq>.<UTCstamp>.<label>.md` (the autofiction-harness
   convention). Every labeled revision pass (`before_…`/`after_…`) becomes a
   version, plus the current working copy of the chapter.
2. **Git history** — if the book directory is inside a git repo, every
   tracked `.md` file gets one version per commit that touched it (built
   from a single `git log --name-status` pass, so it's fast even in repos
   with thousands of files), plus the working tree when dirty. Noise
   directories (`revision_snapshots/`, `drafts/`, `logs/`, `critiques/`,
   `model_prompts/`, …) are excluded by default — see
   `DEFAULT_GIT_EXCLUDE` in `sources.py`.

## CLI

```bash
pdv serve --book DIR [--port 8765] [--host 127.0.0.1]   # local web viewer
pdv list  --book DIR [-v]                               # documents + versions
pdv diff  --book DIR DOC BASE COMPARE -o out.html       # standalone HTML export
```

Version ids: snapshot sequence numbers (`0001`, …) or `current` for the
snapshot source; commit short-shas or `worktree` for the git source. Example:

```bash
pdv diff --book ~/book/output snap:chapter_01 0001 current -o ch01.html
pdv diff --book ~/book/output git:chapters/chapter_07.md 73a4af5 66a56f0 -o ch07.html
```

## How the diff works

Markdown is split into blank-line blocks; blocks are matched with
`difflib.SequenceMatcher`. Unchanged blocks render normally; changed regions
get a **word-level** inline diff (`<ins>`/`<del>`), so a one-word line edit
shows as exactly that — not a rewritten paragraph. Headings, `* * *` scene
breaks, blockquotes, and inline em/strong/code are rendered; everything else
is treated as prose.

## License

MIT. UI/workflow concept borrowed from
[latex-diff-viewer](https://github.com/alpaylan/latex-diff-viewer) (MIT).
