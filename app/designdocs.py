"""
Reads the design documents so the app can show them.
The decisions are parsed out by stage, so the bill page can put each one beside
the stage it belongs to instead of leaving it in a file nobody opens.
Leaves out: caching. The files are small and re-reading them keeps editing simple.
"""

import re

import markdown

from app import config

MD = markdown.Markdown(extensions=["tables", "sane_lists"])


def _render(text: str) -> str:
    MD.reset()
    return MD.convert(text)


def pages() -> list[dict]:
    """Every document in docs/, in file order, as rendered blocks."""
    out = []
    for path in sorted(config.DOCS_DIR.glob("*.md")):
        text = path.read_text()
        first = text.splitlines()[0] if text else path.stem
        title = first.lstrip("# ").strip() or path.stem
        body = "\n".join(text.splitlines()[1:]).strip()
        out.append(
            {
                "slug": path.stem,
                "title": title,
                "html": _render(body),
            }
        )
    return out


def decisions() -> list[dict]:
    """The decisions from 05, split up and tagged with the stage each belongs to."""
    path = config.DOCS_DIR / "05-decisions.md"
    if not path.exists():
        return []

    out = []
    blocks = re.split(r"\n## ", path.read_text())[1:]
    for block in blocks:
        lines = block.splitlines()
        heading = lines[0].strip()
        body = "\n".join(lines[1:]).strip()
        stage_match = re.search(r"\*\*Stage:\*\*\s*(.+)", body)
        stage = stage_match.group(1).strip() if stage_match else ""
        body = re.sub(r"\*\*Stage:\*\*\s*.+\n?", "", body).strip()
        number, _, title = heading.partition(". ")
        out.append(
            {
                "number": number.strip(),
                "title": title.strip() or heading,
                "stage": stage,
                "html": _render(body),
            }
        )
    return out


def decisions_for(stage: str) -> list[dict]:
    return [d for d in decisions() if d["stage"].lower() == stage.lower()]
