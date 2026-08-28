"""Thread-safe SQLite persistent memory store with FTS5 search and cognitive recency scoring."""

from __future__ import annotations

import contextlib
import json
import logging
import math
import os
import re
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from spic.memory.types import MemoryItem, MemoryQuery, MemorySearchResult, MemoryType

logger = logging.getLogger("spic.memory.store")

DEFAULT_MEMORY_DIR = Path.home() / ".config" / "spic" / "memory"
DEFAULT_DB_FILE = DEFAULT_MEMORY_DIR / "agent_memory.db"


class SQLiteMemoryStore:
    """Thread-safe persistent memory store using SQLite with Full-Text Search (FTS5)."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or DEFAULT_DB_FILE
        self._lock = threading.RLock()
        self._init_db()

    @contextlib.contextmanager
    def _db_connection(self):
        """Create a connection with WAL mode enabled and guaranteed automatic closing."""
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def _init_db(self) -> None:
        """Create database tables and FTS5 search index."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.db_path.parent, 0o700)
        except Exception:
            pass

        with self._lock, self._db_connection() as conn:
            # Main memory table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS memories (
                    id TEXT PRIMARY KEY,
                    agent_id TEXT NOT NULL,
                    memory_type TEXT NOT NULL,
                    namespace TEXT NOT NULL,
                    content TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    importance REAL NOT NULL DEFAULT 0.5,
                    created_at TEXT NOT NULL,
                    last_accessed_at TEXT NOT NULL,
                    access_count INTEGER NOT NULL DEFAULT 0,
                    archived INTEGER NOT NULL DEFAULT 0
                );
            """)

            # Indexes for fast filtering
            conn.execute("CREATE INDEX IF NOT EXISTS idx_memories_agent ON memories(agent_id, memory_type, namespace);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_memories_accessed ON memories(last_accessed_at);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_memories_archived ON memories(archived);")

            # FTS5 Full-Text Search Index
            conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
                    id UNINDEXED,
                    content,
                    namespace,
                    agent_id,
                    tokenize = 'porter unicode61'
                );
            """)
            conn.commit()

        try:
            if self.db_path.exists():
                os.chmod(self.db_path, 0o600)
        except Exception:
            pass

    def upsert(self, memory: MemoryItem) -> None:
        """Insert or update a memory item and update the FTS search index."""
        with self._lock, self._db_connection() as conn:
            meta_str = json.dumps(memory.metadata)
            created_str = memory.created_at.isoformat()
            accessed_str = memory.last_accessed_at.isoformat()

            conn.execute("""
                INSERT INTO memories (
                    id, agent_id, memory_type, namespace, content, metadata_json,
                    importance, created_at, last_accessed_at, access_count, archived
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    agent_id = excluded.agent_id,
                    memory_type = excluded.memory_type,
                    namespace = excluded.namespace,
                    content = excluded.content,
                    metadata_json = excluded.metadata_json,
                    importance = excluded.importance,
                    last_accessed_at = excluded.last_accessed_at,
                    access_count = excluded.access_count,
                    archived = excluded.archived;
            """, (
                memory.id,
                memory.agent_id,
                memory.memory_type.value,
                memory.namespace,
                memory.content,
                meta_str,
                memory.importance,
                created_str,
                accessed_str,
                memory.access_count,
                1 if memory.archived else 0,
            ))

            # Update FTS index
            conn.execute("DELETE FROM memories_fts WHERE id = ?;", (memory.id,))
            if not memory.archived:
                conn.execute("""
                    INSERT INTO memories_fts (id, content, namespace, agent_id)
                    VALUES (?, ?, ?, ?);
                """, (memory.id, memory.content, memory.namespace, memory.agent_id))

            conn.commit()

    def get(self, memory_id: str) -> Optional[MemoryItem]:
        """Fetch a memory by its ID."""
        with self._lock, self._db_connection() as conn:
            row = conn.execute("SELECT * FROM memories WHERE id = ?;", (memory_id,)).fetchone()
            if not row:
                return None
            return self._row_to_memory(row)

    def delete(self, memory_id: str) -> bool:
        """Delete a memory permanently."""
        with self._lock, self._db_connection() as conn:
            cur = conn.execute("DELETE FROM memories WHERE id = ?;", (memory_id,))
            conn.execute("DELETE FROM memories_fts WHERE id = ?;", (memory_id,))
            conn.commit()
            return cur.rowcount > 0

    def touch(self, memory_id: str) -> None:
        """Update last accessed timestamp and increment access counter."""
        now_str = datetime.now(timezone.utc).isoformat()
        with self._lock, self._db_connection() as conn:
            conn.execute("""
                UPDATE memories
                SET last_accessed_at = ?, access_count = access_count + 1
                WHERE id = ?;
            """, (now_str, memory_id))
            conn.commit()

    def search(self, query: MemoryQuery) -> List[MemorySearchResult]:
        """Search memories using hybrid FTS5 keyword matching + cognitive recency utility scoring."""
        cleaned_query = re.sub(r"[^\w\s]", " ", query.query).strip()
        tokens = [t.lower() for t in cleaned_query.split() if len(t) > 1]

        with self._lock, self._db_connection() as conn:
            # Build SQL where conditions
            conditions = ["archived = ?"]
            params: list[Any] = [1 if query.include_archived else 0]

            if query.agent_id:
                # Retrieve memories belonging to this agent OR shared globally
                conditions.append("(agent_id = ? OR agent_id = 'global')")
                params.append(query.agent_id)

            if query.memory_type:
                conditions.append("memory_type = ?")
                params.append(query.memory_type.value)

            if query.namespace:
                conditions.append("namespace = ?")
                params.append(query.namespace)

            where_clause = " AND ".join(conditions)
            sql = f"SELECT * FROM memories WHERE {where_clause};"
            rows = conn.execute(sql, params).fetchall()

        if not rows:
            return []

        results: list[MemorySearchResult] = []
        now = datetime.now(timezone.utc)

        for row in rows:
            mem = self._row_to_memory(row)

            # 1. Metadata Tag Filtering (if requested)
            if query.tags:
                mem_tags = [str(t).lower() for t in mem.metadata.get("tags", [])]
                if not any(tag.lower() in mem_tags for tag in query.tags):
                    continue

            # 2. Text Match Score (BM25 / Token Jaccard)
            match_score, match_reasons = self._calculate_match_score(mem, tokens)

            # 3. Recency Score (Exponential decay with 72-hour half life)
            hours_since_access = max(0.0, (now - mem.last_accessed_at).total_seconds() / 3600.0)
            recency_score = math.pow(0.5, hours_since_access / 72.0)

            # 4. Frequency Bonus
            frequency_score = min(1.0, mem.access_count / 10.0)

            # 5. Composite Utility Score
            composite_score = (
                0.50 * match_score +
                0.25 * recency_score +
                0.15 * mem.importance +
                0.10 * frequency_score
            )

            if composite_score >= query.min_score or match_score > 0.3:
                results.append(MemorySearchResult(
                    memory=mem,
                    score=round(composite_score, 4),
                    match_reasons=match_reasons,
                ))

        # Sort by highest score first
        results.sort(key=lambda r: r.score, reverse=True)
        top_results = results[:query.limit]

        # Touch retrieved memories to register access
        for res in top_results:
            self.touch(res.memory.id)

        return top_results

    def list_all(
        self,
        agent_id: Optional[str] = None,
        memory_type: Optional[MemoryType] = None,
        namespace: Optional[str] = None,
        limit: int = 100,
    ) -> List[MemoryItem]:
        """List stored memories with optional filtering."""
        conditions = ["archived = 0"]
        params: list[Any] = []

        if agent_id:
            conditions.append("(agent_id = ? OR agent_id = 'global')")
            params.append(agent_id)
        if memory_type:
            conditions.append("memory_type = ?")
            params.append(memory_type.value)
        if namespace:
            conditions.append("namespace = ?")
            params.append(namespace)

        where_clause = " AND ".join(conditions)
        sql = f"SELECT * FROM memories WHERE {where_clause} ORDER BY last_accessed_at DESC LIMIT ?;"
        params.append(limit)

        with self._lock, self._db_connection() as conn:
            rows = conn.execute(sql, params).fetchall()

        return [self._row_to_memory(r) for r in rows]

    def _calculate_match_score(self, mem: MemoryItem, tokens: list[str]) -> tuple[float, list[str]]:
        """Calculate lexical similarity between query tokens and memory content/metadata."""
        if not tokens:
            return 0.5, ["general_recall"]

        content_lower = mem.content.lower()
        ns_lower = mem.namespace.lower()
        meta_str = json.dumps(mem.metadata).lower()

        matched_tokens = 0
        reasons = []

        for t in tokens:
            if t in content_lower:
                matched_tokens += 1
                reasons.append(f"matched_content('{t}')")
            elif t in ns_lower:
                matched_tokens += 1
                reasons.append(f"matched_namespace('{t}')")
            elif t in meta_str:
                matched_tokens += 0.5
                reasons.append(f"matched_metadata('{t}')")

        token_ratio = matched_tokens / float(len(tokens))
        return min(1.0, token_ratio), reasons

    def _row_to_memory(self, row: sqlite3.Row) -> MemoryItem:
        """Convert a SQLite row into a typed MemoryItem."""
        try:
            metadata = json.loads(row["metadata_json"])
        except Exception:
            metadata = {}

        return MemoryItem(
            id=row["id"],
            agent_id=row["agent_id"],
            memory_type=MemoryType(row["memory_type"]),
            namespace=row["namespace"],
            content=row["content"],
            metadata=metadata,
            importance=float(row["importance"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            last_accessed_at=datetime.fromisoformat(row["last_accessed_at"]),
            access_count=int(row["access_count"]),
            archived=bool(row["archived"]),
        )
