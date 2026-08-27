"""Unit tests for the Agent Memory System (CoALA Framework)."""

import shutil
import tempfile
import unittest
from pathlib import Path

from spic.memory.types import MemoryType, MemoryQuery
from spic.memory.store import SQLiteMemoryStore
from spic.memory.decay import MemoryDecayEngine
from spic.memory.coordinator import AgentMemoryCoordinator


class TestAgentMemorySystem(unittest.TestCase):
    """Comprehensive test suite for multi-agent memory storage and retrieval."""

    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp())
        self.db_path = self.test_dir / "test_memory.db"
        self.store = SQLiteMemoryStore(db_path=self.db_path)
        self.coordinator = AgentMemoryCoordinator(store=self.store)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_semantic_memory_upsert_and_search(self):
        """Verify storing and searching semantic user preferences and facts."""
        mem = self.coordinator.remember_fact(
            content="User prefers Python for backend development and FastAPI.",
            agent_id="code_assistant",
            namespace="user_profile",
            key="backend_pref",
            importance=0.9,
        )
        self.assertIsNotNone(mem.id)

        # Search by query
        results = self.store.search(MemoryQuery(query="Python backend"))
        self.assertGreaterEqual(len(results), 1)
        self.assertIn("Python", results[0].memory.content)
        self.assertEqual(results[0].memory.memory_type, MemoryType.SEMANTIC)

    def test_episodic_memory_record(self):
        """Verify recording and querying episodic session histories."""
        self.coordinator.record_episode(
            summary="User asked to format an SQL query and it was pasted successfully.",
            agent_id="voice_agent",
            outcome="success",
            key_insights=["User prefers UPPERCASE SQL keywords"],
        )

        results = self.store.search(MemoryQuery(
            query="SQL query",
            memory_type=MemoryType.EPISODIC,
        ))
        self.assertGreaterEqual(len(results), 1)
        self.assertEqual(results[0].memory.memory_type, MemoryType.EPISODIC)

    def test_procedural_memory_learn_skill(self):
        """Verify storing procedural rules, prompt templates, and skills."""
        self.coordinator.learn_skill(
            task_type="git_commit_formatting",
            steps_or_instructions="Always format git commits in conventional commit style: feat/fix/refactor.",
            agent_id="git_agent",
            few_shot_example={"input": "added login", "output": "feat(auth): add user login"},
        )

        results = self.store.search(MemoryQuery(
            query="git commit style",
            memory_type=MemoryType.PROCEDURAL,
        ))
        self.assertGreaterEqual(len(results), 1)
        self.assertEqual(results[0].memory.metadata["task_type"], "git_commit_formatting")

    def test_conflict_resolution_supersedes_older_fact(self):
        """Verify that updating a key archives the superseded older memory."""
        # 1. Old fact
        self.coordinator.remember_fact(
            content="User prefers dark mode theme.",
            key="theme_preference",
            namespace="preferences",
        )

        # 2. Updated fact with same key
        self.coordinator.remember_fact(
            content="User prefers light mode theme with high contrast.",
            key="theme_preference",
            namespace="preferences",
        )

        # Active memories should only return the new fact
        active_memories = self.store.list_all(namespace="preferences")
        self.assertEqual(len(active_memories), 1)
        self.assertIn("light mode", active_memories[0].content)

    def test_prepare_agent_context_synthesis(self):
        """Verify multi-tier cognitive context bundle synthesis for LLMs."""
        self.coordinator.remember_fact(content="User is a Senior Python Developer.", namespace="profile")
        self.coordinator.learn_skill(task_type="code_style", steps_or_instructions="Use PEP8 with type hints.")
        self.coordinator.record_episode(summary="Assisted user with FastAPI async routes.")

        context = self.coordinator.prepare_agent_context(query="Python FastAPI async code", limit_per_type=2)

        self.assertIsNotNone(context.summary_prompt)
        self.assertIn("Known Facts & User Preferences", context.summary_prompt)
        self.assertIn("Learned Skills & Guidelines", context.summary_prompt)

    def test_working_memory_ephemeral_cache(self):
        """Verify ephemeral working memory."""
        self.coordinator.set_working_context("agent_1", "active_file", "main.py")
        val = self.coordinator.get_working_context("agent_1", "active_file")
        self.assertEqual(val, "main.py")

        self.coordinator.clear_working_context("agent_1")
        self.assertIsNone(self.coordinator.get_working_context("agent_1", "active_file"))


if __name__ == "__main__":
    unittest.main()
