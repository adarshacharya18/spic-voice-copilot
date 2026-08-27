"""Multi-agent cognitive memory coordinator implementing the CoALA framework."""

from __future__ import annotations

from datetime import datetime
import logging
from typing import Any, Dict, List, Optional

from spic.memory.store import SQLiteMemoryStore
from spic.memory.decay import MemoryDecayEngine
from spic.memory.types import (
    AgentContext,
    MemoryItem,
    MemoryQuery,
    MemorySearchResult,
    MemoryType,
)

logger = logging.getLogger("spic.memory.coordinator")


class AgentMemoryCoordinator:
    """High-level cognitive memory manager for single and multi-agent coordination."""

    def __init__(self, store: Optional[SQLiteMemoryStore] = None):
        self.store = store or SQLiteMemoryStore()
        self.decay_engine = MemoryDecayEngine(self.store)
        self._working_memory: Dict[str, Dict[str, Any]] = {}

    # =========================================================================
    # 1. Semantic Memory (Facts, Profiles, Knowledge, Preferences)
    # =========================================================================
    def remember_fact(
        self,
        content: str,
        agent_id: str = "global",
        namespace: str = "user_profile",
        key: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        importance: float = 0.7,
    ) -> MemoryItem:
        """Store a semantic fact, user preference, or project knowledge."""
        meta = metadata or {}
        if key:
            meta["key"] = key

        memory = MemoryItem(
            agent_id=agent_id,
            memory_type=MemoryType.SEMANTIC,
            namespace=namespace,
            content=content,
            metadata=meta,
            importance=importance,
        )

        # Automatically check and supersede conflicting keys
        self.decay_engine.resolve_conflicts_on_insert(memory)
        self.store.upsert(memory)
        logger.info(f"🧠 [Semantic Memory Stored] [{namespace}] {content[:60]}")
        return memory

    # =========================================================================
    # 2. Episodic Memory (Experiences, Sessions, Command History)
    # =========================================================================
    def record_episode(
        self,
        summary: str,
        agent_id: str = "global",
        namespace: str = "conversations",
        outcome: str = "success",
        key_insights: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        importance: float = 0.5,
    ) -> MemoryItem:
        """Store an episodic event, past conversation summary, or task execution outcome."""
        meta = metadata or {}
        meta["outcome"] = outcome
        if key_insights:
            meta["key_insights"] = key_insights

        memory = MemoryItem(
            agent_id=agent_id,
            memory_type=MemoryType.EPISODIC,
            namespace=namespace,
            content=summary,
            metadata=meta,
            importance=importance,
        )

        self.store.upsert(memory)
        logger.info(f"📜 [Episodic Memory Recorded] [{namespace}] {summary[:60]}")
        return memory

    # =========================================================================
    # 3. Procedural Memory (Skills, Workflows, How-To Knowledge, Few-Shots)
    # =========================================================================
    def learn_skill(
        self,
        task_type: str,
        steps_or_instructions: str,
        agent_id: str = "global",
        namespace: str = "skills",
        few_shot_example: Optional[Dict[str, str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        importance: float = 0.8,
    ) -> MemoryItem:
        """Store a procedural rule, skill pattern, or few-shot example."""
        meta = metadata or {}
        meta["task_type"] = task_type
        if few_shot_example:
            meta["few_shot_example"] = few_shot_example

        memory = MemoryItem(
            agent_id=agent_id,
            memory_type=MemoryType.PROCEDURAL,
            namespace=namespace,
            content=steps_or_instructions,
            metadata=meta,
            importance=importance,
        )

        self.store.upsert(memory)
        logger.info(f"⚡ [Procedural Skill Learned] [{task_type}] {steps_or_instructions[:60]}")
        return memory

    # =========================================================================
    # 4. Working Memory (Short-Term Ephemeral Task State)
    # =========================================================================
    def set_working_context(self, agent_id: str, key: str, value: Any) -> None:
        """Set an active ephemeral variable in working memory."""
        if agent_id not in self._working_memory:
            self._working_memory[agent_id] = {}
        self._working_memory[agent_id][key] = value

    def get_working_context(self, agent_id: str, key: str, default: Any = None) -> Any:
        """Retrieve an ephemeral variable from working memory."""
        return self._working_memory.get(agent_id, {}).get(key, default)

    def clear_working_context(self, agent_id: str) -> None:
        """Clear ephemeral working memory for an agent."""
        self._working_memory.pop(agent_id, None)

    # =========================================================================
    # 5. Cognitive Context Retrieval & Synthesis for LLMs
    # =========================================================================
    def prepare_agent_context(
        self,
        query: str,
        agent_id: str = "global",
        limit_per_type: int = 3,
    ) -> AgentContext:
        """Retrieve relevant semantic, episodic, and procedural memories and format them into an LLM prompt bundle."""
        # 1. Retrieve Semantic Memories (User preferences, domain knowledge)
        semantic_results = self.store.search(MemoryQuery(
            query=query,
            agent_id=agent_id,
            memory_type=MemoryType.SEMANTIC,
            limit=limit_per_type,
            min_score=0.15,
        ))

        # 2. Retrieve Episodic Memories (Past sessions, previous outcomes)
        episodic_results = self.store.search(MemoryQuery(
            query=query,
            agent_id=agent_id,
            memory_type=MemoryType.EPISODIC,
            limit=limit_per_type,
            min_score=0.15,
        ))

        # 3. Retrieve Procedural Memories (Skills, rules, instructions)
        procedural_results = self.store.search(MemoryQuery(
            query=query,
            agent_id=agent_id,
            memory_type=MemoryType.PROCEDURAL,
            limit=limit_per_type,
            min_score=0.15,
        ))

        # 4. Synthesize into Structured Markdown Context
        prompt_sections = []

        if semantic_results:
            prompt_sections.append("### 🧠 Known Facts & User Preferences (Semantic Memory):")
            for res in semantic_results:
                prompt_sections.append(f"- {res.memory.content}")

        if procedural_results:
            prompt_sections.append("\n### ⚡ Learned Skills & Guidelines (Procedural Memory):")
            for res in procedural_results:
                task = res.memory.metadata.get("task_type", "General")
                prompt_sections.append(f"- [{task}] {res.memory.content}")

        if episodic_results:
            prompt_sections.append("\n### 📜 Relevant Past Experiences (Episodic Memory):")
            for res in episodic_results:
                prompt_sections.append(f"- {res.memory.content}")

        summary_prompt = "\n".join(prompt_sections).strip()

        return AgentContext(
            semantic_memories=semantic_results,
            episodic_memories=episodic_results,
            procedural_memories=procedural_results,
            summary_prompt=summary_prompt,
        )
