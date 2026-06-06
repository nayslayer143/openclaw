"""OpenBrain adapter — Python interface to the local OB1 stack.

Two channels:
  * MCP HTTP (127.0.0.1:8765) for `capture` — the server runs LLM metadata
    extraction in-process, which we want.
  * Direct Postgres (127.0.0.1:5433) for reads (`search`, `list_recent`,
    `stats`, `fetch_by_id`) — the MCP tools return human-readable text only,
    which is wrong for programmatic use.

Embeddings for `search` are produced via Ollama's OpenAI-compat endpoint.
All endpoints are 127.0.0.1; constructor reads `<openclaw>/.env` for secrets.

Deferred (path A — see openbrain/SPIKE-NOTES.md):
  recall(), writeback(), usage_report() raise NotImplementedError.
  They land when the agent-memory-api port spec ships.
"""
from __future__ import annotations
import json
import os
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

import httpx
import psycopg
from psycopg.rows import dict_row

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"


def _load_env() -> dict[str, str]:
    if not ENV_PATH.exists():
        return {}
    out: dict[str, str] = {}
    for raw in ENV_PATH.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip()
    return out


@dataclass
class Thought:
    id: int
    content: str
    metadata: dict[str, Any]
    created_at: datetime
    similarity: float | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["created_at"] = self.created_at.isoformat() if isinstance(self.created_at, datetime) else self.created_at
        return d


class OpenBrainError(RuntimeError):
    pass


class OpenBrain:
    def __init__(
        self,
        *,
        mcp_url: str | None = None,
        access_key: str | None = None,
        db_dsn: str | None = None,
        embedding_api_base: str | None = None,
        embedding_model: str | None = None,
        embedding_api_key: str | None = None,
        timeout: float = 60.0,
    ) -> None:
        env = {**_load_env(), **os.environ}
        self.mcp_url = (mcp_url or env.get("OPENBRAIN_MCP_URL", "http://127.0.0.1:8765")).rstrip("/")
        self.access_key = access_key or env["OPENBRAIN_ACCESS_KEY"]
        # Host-side default — OPENBRAIN_EMBEDDING_API_BASE in .env points at
        # host.docker.internal which only resolves inside containers. The
        # adapter runs on the host, so use 127.0.0.1 unless explicitly told
        # otherwise via OPENBRAIN_HOST_EMBEDDING_API_BASE.
        self.embedding_api_base = (
            embedding_api_base
            or env.get("OPENBRAIN_HOST_EMBEDDING_API_BASE", "http://127.0.0.1:11434/v1")
        ).rstrip("/")
        self.embedding_model = embedding_model or env.get("OPENBRAIN_EMBEDDING_MODEL", "nomic-embed-text")
        self.embedding_api_key = embedding_api_key or env.get("OPENBRAIN_EMBEDDING_API_KEY", "ollama")
        self.db_dsn = db_dsn or (
            f"host=127.0.0.1 port=5433 dbname=openbrain user=openbrain "
            f"password={env['OPENBRAIN_DB_PASSWORD']}"
        )
        self._client = httpx.Client(timeout=timeout)
        self._db: psycopg.Connection | None = None

    def __enter__(self) -> "OpenBrain":
        return self

    def __exit__(self, *_a: Any) -> None:
        self.close()

    def close(self) -> None:
        try:
            self._client.close()
        except Exception:
            pass
        if self._db is not None:
            try:
                self._db.close()
            except Exception:
                pass
            self._db = None

    # ---- DB helpers ------------------------------------------------------

    def _conn(self) -> psycopg.Connection:
        if self._db is None or self._db.closed:
            self._db = psycopg.connect(self.db_dsn, row_factory=dict_row, autocommit=True)
        return self._db

    # ---- Embedding -------------------------------------------------------

    def _embed(self, text: str) -> list[float]:
        r = self._client.post(
            f"{self.embedding_api_base}/embeddings",
            headers={
                "Authorization": f"Bearer {self.embedding_api_key}",
                "Content-Type": "application/json",
            },
            content=json.dumps({"model": self.embedding_model, "input": text}),
        )
        r.raise_for_status()
        data = r.json()["data"]
        if not data:
            raise OpenBrainError("empty embedding response")
        return data[0]["embedding"]

    # ---- MCP helpers -----------------------------------------------------

    def _mcp_post(self, tool: str, arguments: dict) -> str:
        body = {
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "method": "tools/call",
            "params": {"name": tool, "arguments": arguments},
        }
        r = self._client.post(
            self.mcp_url,
            headers={
                "x-brain-key": self.access_key,
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
            },
            content=json.dumps(body),
        )
        r.raise_for_status()
        envelope: dict | None = None
        for line in r.text.splitlines():
            if line.startswith("data: "):
                envelope = json.loads(line[6:])
                break
        if envelope is None:
            raise OpenBrainError(f"no MCP envelope in response: {r.text[:200]}")
        if "error" in envelope:
            raise OpenBrainError(envelope["error"])
        result = envelope["result"]
        text = ""
        if "content" in result and result["content"]:
            text = result["content"][0].get("text", "")
        if result.get("isError"):
            raise OpenBrainError(f"MCP tool {tool} reported error: {text!r}")
        return text

    def _mcp_call(self, tool: str, arguments: dict) -> str:
        # Upstream MCP server's Postgres pool drops idle connections; the next
        # call after a long idle period fails with "Broken pipe (os error 32)".
        # One transparent retry covers this without papering over real errors.
        try:
            return self._mcp_post(tool, arguments)
        except OpenBrainError as exc:
            if "Broken pipe" in str(exc) or "os error 32" in str(exc):
                return self._mcp_post(tool, arguments)
            raise

    # ---- Public API ------------------------------------------------------

    def capture(
        self,
        content: str,
        *,
        source: str | None = None,
        scope: str | None = None,
        metadata: dict | None = None,
    ) -> int:
        """Capture a thought. Returns the new thought id.

        The MCP `capture_thought` tool only accepts {content}; the server runs
        Ollama for embeddings + metadata extraction. To preserve our explicit
        source/scope tags we prepend them as a structured prefix; the LLM's
        own extracted topics/type land in `metadata` server-side.
        """
        if source or scope or metadata:
            tag_bits: list[str] = []
            if source:
                tag_bits.append(f"source: {source}")
            if scope:
                tag_bits.append(f"scope: {scope}")
            if metadata:
                for k, v in metadata.items():
                    tag_bits.append(f"{k}: {v}")
            content = f"[{ ' | '.join(tag_bits) }]\n{content}"

        self._mcp_call("capture_thought", {"content": content})
        with self._conn().cursor() as cur:
            cur.execute("SELECT id FROM thoughts ORDER BY id DESC LIMIT 1")
            row = cur.fetchone()
        if row is None:
            raise OpenBrainError("capture appeared to succeed but no thought row found")
        return int(row["id"])

    def search(
        self,
        query: str,
        *,
        k: int = 10,
        threshold: float = 0.5,
    ) -> list[Thought]:
        emb = self._embed(query)
        emb_str = "[" + ",".join(str(x) for x in emb) + "]"
        with self._conn().cursor() as cur:
            cur.execute(
                "SELECT id, content, metadata, similarity, created_at "
                "FROM match_thoughts(%s::vector, %s, %s)",
                (emb_str, threshold, k),
            )
            rows = cur.fetchall()
        return [
            Thought(
                id=int(r["id"]),
                content=r["content"],
                metadata=r["metadata"] or {},
                similarity=float(r["similarity"]),
                created_at=r["created_at"],
            )
            for r in rows
        ]

    def list_recent(self, *, n: int = 20, source: str | None = None) -> list[Thought]:
        sql = "SELECT id, content, metadata, created_at FROM thoughts"
        params: list[Any] = []
        if source:
            sql += " WHERE content LIKE %s"
            params.append(f"[source: {source}%")
        sql += " ORDER BY created_at DESC LIMIT %s"
        params.append(n)
        with self._conn().cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
        return [
            Thought(
                id=int(r["id"]),
                content=r["content"],
                metadata=r["metadata"] or {},
                created_at=r["created_at"],
            )
            for r in rows
        ]

    def fetch(self, thought_id: int) -> Thought | None:
        with self._conn().cursor() as cur:
            cur.execute(
                "SELECT id, content, metadata, created_at FROM thoughts WHERE id = %s",
                (thought_id,),
            )
            r = cur.fetchone()
        if r is None:
            return None
        return Thought(
            id=int(r["id"]),
            content=r["content"],
            metadata=r["metadata"] or {},
            created_at=r["created_at"],
        )

    def stats(self) -> dict[str, Any]:
        with self._conn().cursor() as cur:
            cur.execute(
                """
                SELECT
                    COUNT(*) AS count,
                    MIN(created_at) AS oldest,
                    MAX(created_at) AS newest
                FROM thoughts
                """
            )
            base = cur.fetchone() or {"count": 0, "oldest": None, "newest": None}
            cur.execute(
                """
                SELECT metadata->>'type' AS type, COUNT(*) AS n
                FROM thoughts
                WHERE metadata ? 'type'
                GROUP BY metadata->>'type'
                ORDER BY n DESC
                """
            )
            types = {r["type"]: int(r["n"]) for r in cur.fetchall() if r["type"]}
        return {
            "count": int(base["count"]),
            "oldest": base["oldest"].isoformat() if base["oldest"] else None,
            "newest": base["newest"].isoformat() if base["newest"] else None,
            "types": types,
        }

    # ---- Sidecar layer (deferred) ---------------------------------------

    def recall(self, **_kw: Any) -> dict:
        raise NotImplementedError(
            "recall() requires the agent-memory-api service. Deferred under path A; "
            "see openbrain/SPIKE-NOTES.md and the follow-up spec for the direct-Postgres port."
        )

    def writeback(self, **_kw: Any) -> str:
        raise NotImplementedError(
            "writeback() requires the agent-memory-api service. Deferred under path A; "
            "use capture() with metadata={'kind': '...', 'use_policy': 'evidence'} as the "
            "interim coarse-grained substitute."
        )

    def usage_report(self, **_kw: Any) -> None:
        raise NotImplementedError(
            "usage_report() requires the agent-memory-api service. Deferred under path A."
        )


# ----------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------

def _cli() -> None:
    import argparse
    import sys as _sys

    p = argparse.ArgumentParser(prog="openbrain")
    sub = p.add_subparsers(dest="cmd", required=True)

    pc = sub.add_parser("capture")
    pc.add_argument("content")
    pc.add_argument("--source")
    pc.add_argument("--scope")

    ps = sub.add_parser("search")
    ps.add_argument("query")
    ps.add_argument("-k", type=int, default=10)
    ps.add_argument("--threshold", type=float, default=0.5)

    pl = sub.add_parser("list")
    pl.add_argument("-n", type=int, default=20)
    pl.add_argument("--source")

    pf = sub.add_parser("fetch")
    pf.add_argument("id", type=int)

    sub.add_parser("stats")

    args = p.parse_args()
    with OpenBrain() as ob:
        if args.cmd == "capture":
            print(ob.capture(args.content, source=args.source, scope=args.scope))
        elif args.cmd == "search":
            results = ob.search(args.query, k=args.k, threshold=args.threshold)
            print(json.dumps([t.to_dict() for t in results], indent=2, default=str))
        elif args.cmd == "list":
            results = ob.list_recent(n=args.n, source=args.source)
            print(json.dumps([t.to_dict() for t in results], indent=2, default=str))
        elif args.cmd == "fetch":
            t = ob.fetch(args.id)
            print(json.dumps(t.to_dict() if t else None, indent=2, default=str))
        elif args.cmd == "stats":
            print(json.dumps(ob.stats(), indent=2, default=str))
        else:
            _sys.exit(2)


if __name__ == "__main__":
    _cli()
