"""Type definitions and data models for the Agent Memory System (CoALA Framework)."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid
from pydantic import BaseModel, Field


class MemoryType(str, Enum):
    """Cognitive memory classifications based on the CoALA framework."""
    SEMANTIC = "semantic"      # Facts, profiles, user preferences, dictionary
    EPISODIC = "episodic"      # Past interactions, task outcomes, timestamped events
    PROCEDURAL = "procedural"  # Skills, rules, few-shot patterns, how-to knowledge
    WORKING = "working"        # Ephemeral active context for current task


class MemoryItem(BaseModel):
    """Core memory unit stored and retrieved across agents."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    agent_id: str = Field(default="global", description="Owner agent ID or 'global' for cross-agent shared memory")
    memory_type: MemoryType = Field(default=MemoryType.SEMANTIC)
    namespace: str = Field(default="general", description="Category partition (e.g. user_profile, skills, sessions)")
    content: str = Field(description="Raw text content of the memory")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Structured metadata, tags, and attributes")
    importance: float = Field(default=0.5, ge=0.0, le=1.0, description="Priority / importance weight (0.0 to 1.0)")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_accessed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    access_count: int = Field(default=0)
    embedding: Optional[List[float]] = Field(default=None, description="Optional dense embedding vector")
    archived: bool = Field(default=False)


class MemoryQuery(BaseModel):
    """Search query specification for memory retrieval."""
    query: str = Field(description="Natural language query or keywords to search")
    agent_id: Optional[str] = Field(default=None, description="Filter by agent ID (includes 'global' by default)")
    memory_type: Optional[MemoryType] = Field(default=None, description="Filter by specific memory type")
    namespace: Optional[str] = Field(default=None, description="Filter by namespace")
    tags: Optional[List[str]] = Field(default=None, description="Filter by tags in metadata")
    limit: int = Field(default=5, ge=1, le=50)
    min_score: float = Field(default=0.1, ge=0.0, le=1.0)
    include_archived: bool = Field(default=False)


class MemorySearchResult(BaseModel):
    """Result item returned from memory search with composite relevance score."""
    memory: MemoryItem
    score: float = Field(description="Composite relevance score combining semantic, keyword, and recency utility")
    match_reasons: List[str] = Field(default_factory=list)


class AgentContext(BaseModel):
    """Assembled cognitive memory context bundle ready for LLM prompt injection."""
    semantic_memories: List[MemorySearchResult] = Field(default_factory=list)
    episodic_memories: List[MemorySearchResult] = Field(default_factory=list)
    procedural_memories: List[MemorySearchResult] = Field(default_factory=list)
    summary_prompt: str = Field(default="", description="Formatted context string for LLM system prompt")
