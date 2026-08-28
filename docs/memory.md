# 🧠 Multi-Agent Cognitive Memory System (CoALA)

Spic incorporates a cognitive memory architecture built upon the **CoALA (Cognitive Architectures for Language Agents)** framework. This provides Spic and connected agents with persistent, context-aware memory across restarts and dictation sessions.

---

## 1. The 4 Memory Tiers

```
┌─────────────────────────────────────────────────────────────┐
│ 1. SEMANTIC MEMORY (Long-Term Knowledge & Facts)            │
│    - User preferences, naming conventions, coding styles.   │
│    - Example: "Prefers snake_case in Python, uses PyTorch"   │
├─────────────────────────────────────────────────────────────┤
│ 2. EPISODIC MEMORY (Past Interactions & Events)             │
│    - Transcripts, past edits, meeting notes, project logs.  │
│    - Automatically decays over time based on recency.       │
├─────────────────────────────────────────────────────────────┤
│ 3. PROCEDURAL MEMORY (Skills & Action Templates)            │
│    - Spoken macros, recurring voice workflows, templates.   │
├─────────────────────────────────────────────────────────────┤
│ 4. WORKING MEMORY (Active Session Scratchpad)               │
│    - Current active window context, ongoing draft thoughts. │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. Dynamic Hybrid Retrieval Scoring

When a query is received, Spic computes a multi-factor cognitive utility score:

$$\text{Final Score} = 0.50 \cdot S_{\text{lexical}} + 0.25 \cdot S_{\text{recency}} + 0.15 \cdot S_{\text{importance}} + 0.10 \cdot S_{\text{frequency}}$$

- **$S_{\text{lexical}}$ (50%):** SQLite FTS5 full-text BM25 token matching.
- **$S_{\text{recency}}$ (25%):** Exponential temporal decay: $e^{-\lambda \Delta t}$, where $\lambda = \frac{\ln(2)}{\text{half\_life\_days}}$.
- **$S_{\text{importance}}$ (15%):** Assigned priority (0.0 to 1.0).
- **$S_{\text{frequency}}$ (10%):** Bounded access count utility: $\min(1.0, \frac{\text{access\_count}}{10})$.

---

## 3. CLI Commands for Memory Management

### Adding a Fact
```bash
python3 -m spic.cli memory --add "I prefer TypeScript over JavaScript" --type semantic --key "lang_pref" --importance 0.9
```

### Searching Memories
```bash
python3 -m spic.cli memory --search "TypeScript preferences" --limit 5
```

### Pruning Expired / Stale Memories
```bash
python3 -m spic.cli memory --prune --max-age-days 90 --min-utility 0.1
```

---

## 4. Security & Storage Specifications

- **File Path:** `~/.config/spic/memory/agent_memory.db`
- **File Permissions:** Strictly enforced `0600` (user read/write only).
- **Directory Permissions:** Strictly enforced `0700` (user access only).
- **Transactions:** SQLite Write-Ahead Logging (WAL) for safe concurrent reads and thread isolation.
