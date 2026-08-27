"""Memory decay, consolidation, and conflict resolution engine."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
from typing import List, Optional

from spic.memory.store import SQLiteMemoryStore
from spic.memory.types import MemoryItem, MemoryType

logger = logging.getLogger("spic.memory.decay")


class MemoryDecayEngine:
    """Manages memory life-cycle, temporal decay, pruning, and conflict resolution."""

    def __init__(self, store: SQLiteMemoryStore):
        self.store = store

    def decay_and_prune(self, max_age_days: int = 45, min_utility_threshold: float = 0.15) -> int:
        """Soft-archive old, low-utility memories to keep retrieval fast and uncluttered."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
        all_memories = self.store.list_all(limit=1000)
        archived_count = 0

        for mem in all_memories:
            # Never decay high-importance memories (>= 0.8)
            if mem.importance >= 0.8:
                continue

            if mem.last_accessed_at < cutoff and mem.access_count < 3:
                mem.archived = True
                self.store.upsert(mem)
                archived_count += 1
                logger.debug(f"Archived low-utility memory: '{mem.content[:40]}...'")

        logger.info(f"Memory decay sweep complete. Archived {archived_count} stale memory items.")
        return archived_count

    def resolve_conflicts_on_insert(self, new_memory: MemoryItem) -> None:
        """Check for direct contradictions or key updates in the same namespace and supersede older memories."""
        if new_memory.memory_type != MemoryType.SEMANTIC:
            return

        # Check existing memories in this namespace
        existing_memories = self.store.list_all(
            agent_id=new_memory.agent_id,
            memory_type=new_memory.memory_type,
            namespace=new_memory.namespace,
        )

        new_key = new_memory.metadata.get("key") or new_memory.metadata.get("preference_name")
        if not new_key:
            return

        for existing in existing_memories:
            if existing.id == new_memory.id:
                continue

            old_key = existing.metadata.get("key") or existing.metadata.get("preference_name")
            if old_key and str(old_key).lower() == str(new_key).lower():
                # Direct key update detected: archive the superseded memory
                existing.archived = True
                existing.metadata["superseded_by"] = new_memory.id
                self.store.upsert(existing)
                logger.info(f"Superseded older memory '{existing.id}' with new fact '{new_memory.id}' for key '{new_key}'")
