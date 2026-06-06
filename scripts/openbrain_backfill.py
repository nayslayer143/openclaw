"""One-shot backfill of existing openclaw memory into OB1.

Sources:
  - memory/MEMORY.md     (one thought per dated entry — split on `^## YYYY-MM-DD`)
  - improvements/*.md    (one thought per file, skipping CONTEXT.md)
  - autoresearch/outputs/briefs/*.md  (one thought per file)

Idempotency: each captured thought is tagged with `fingerprint: <sha256-16>` so
a re-run won't double-import (we check for the marker before capturing).

Long files are summarized to a 4000-char head + 1000-char tail to keep the
embedding input bounded; the full path is recorded as origin_path for retrieval.
"""
from __future__ import annotations
import hashlib
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.openbrain import OpenBrain

ROOT = Path(__file__).resolve().parent.parent
ENTRY_HEADING = re.compile(r"^##\s+\d{4}-\d{2}-\d{2}", re.MULTILINE)
MAX_HEAD = 4000
MAX_TAIL = 1000


def split_memory_md(text: str) -> list[str]:
    matches = list(ENTRY_HEADING.finditer(text))
    if not matches:
        body = text.strip()
        return [body] if body else []
    chunks: list[str] = []
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        chunk = text[m.start():end].strip()
        if chunk:
            chunks.append(chunk)
    return chunks


def fingerprint(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()[:16]


def shrink(text: str) -> str:
    if len(text) <= MAX_HEAD + MAX_TAIL + 100:
        return text
    return f"{text[:MAX_HEAD]}\n\n…[shrunk for embedding]…\n\n{text[-MAX_TAIL:]}"


def gather() -> list[tuple[str, Path, str]]:
    items: list[tuple[str, Path, str]] = []

    mem = ROOT / "memory" / "MEMORY.md"
    if mem.exists():
        for chunk in split_memory_md(mem.read_text()):
            if chunk and len(chunk) > 30:  # skip the bare header
                items.append(("memory-md-entry", mem, chunk))

    for p in sorted((ROOT / "improvements").glob("*.md")):
        if p.name == "CONTEXT.md":
            continue
        items.append(("improvement", p, p.read_text().strip()))

    briefs = ROOT / "autoresearch" / "outputs" / "briefs"
    if briefs.exists():
        for p in sorted(briefs.glob("*.md")):
            items.append(("research-brief", p, p.read_text().strip()))

    return items


def already_present(ob: OpenBrain, fp: str) -> bool:
    with ob._conn().cursor() as cur:  # type: ignore[attr-defined]
        cur.execute(
            "SELECT 1 FROM thoughts WHERE content LIKE %s LIMIT 1",
            (f"%fingerprint: {fp}%",),
        )
        return cur.fetchone() is not None


def main() -> int:
    items = gather()
    if not items:
        print("nothing to backfill", file=sys.stderr)
        return 1

    captured = 0
    skipped = 0
    with OpenBrain() as ob:
        for source, path, text in items:
            if not text:
                continue
            fp = fingerprint(text)
            if already_present(ob, fp):
                skipped += 1
                print(f"  SKIP {source:18s} {path.name:60s} (fingerprint {fp})")
                continue
            try:
                tid = ob.capture(
                    shrink(text),
                    source=source,
                    scope="workspace",
                    metadata={
                        "origin_path": str(path.relative_to(ROOT)),
                        "fingerprint": fp,
                        "size_bytes": len(text.encode("utf-8")),
                    },
                )
                captured += 1
                print(f"  ADD  {source:18s} {path.name:60s} -> id {tid}")
            except Exception as e:
                print(f"  FAIL {source:18s} {path.name:60s}: {e}", file=sys.stderr)

    print(f"\nbackfill: {captured} captured, {skipped} skipped, {len(items)} candidates")
    return 0


if __name__ == "__main__":
    sys.exit(main())
