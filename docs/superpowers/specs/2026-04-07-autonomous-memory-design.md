# Autonomous Memory for Bonsai Chat

**Date:** 2026-04-07
**Status:** Design approved, ready for implementation plan

## Problem

Bonsai Chat already has a memory store (`chat/db.py` `memories` table, capped at 20, FIFO), but it is entirely manual: the user clicks "Save Memory", types text, and the server stores it. On every turn, all stored memories are injected into the system prompt as `"Things you know about the user:\n- ..."` (`chat/app.py:324`).

The model itself has no agency. If the user says "I live in Boston" in session 1 and asks "where do I live?" in session 2, the model cannot answer — unless the user separately clicked "Save Memory" and typed it in.

The goal is to let the model decide what is worth remembering and save it autonomously, so durable facts persist across sessions without manual curation.

## Scope

The model should remember:

1. **Stable user facts** — name, location, job, family, pets, dietary/lifestyle preferences.
2. **Long-running context** — projects, goals, ongoing situations.
3. **Interaction preferences** — how the user wants the model to behave.

Explicitly out of scope:

- Episodic recall of past chats ("last week we debugged X"). The existing conversation history already covers this within a session, and cross-session episodic memory bloats fast.
- Semantic retrieval (embeddings). At single-user scale with a cap of 50, dump-all works fine.
- Per-conversation memories. Memories are global to the user.

## Architecture

One new tool, `remember`, wired into the existing agent loop. The model decides when to save; the server dedupes on write; all memories dump into every system prompt (cap raised to 50); the UI shows a subtle toast with undo when a save happens.

```
User msg ──► Agent loop ──► Model
                              │
                              ├─ normal reply (most turns)
                              │
                              └─ {"name":"remember","arguments":{"content":"..."}}
                                    │
                                    ▼
                              MemoryStore.add(content, source='model')
                                    │
                                    ├─ dedup check (skip/replace/insert)
                                    ├─ write to SQLite
                                    └─ tool_end event ──► WebSocket ──► toast + undo
```

No new processes, no embeddings, no background workers. Everything piggybacks on existing tool plumbing (`chat/tools/`), DB layer (`chat/db.py`), and WebSocket channel (`chat/app.py`).

## Data model

Minimal schema change to `memories`:

```sql
CREATE TABLE memories (
  id TEXT PRIMARY KEY,
  content TEXT NOT NULL,
  created_at REAL NOT NULL,
  source TEXT NOT NULL DEFAULT 'user'  -- NEW: 'user' | 'model'
);
```

**Migration:** `ALTER TABLE memories ADD COLUMN source TEXT NOT NULL DEFAULT 'user'`. Existing rows become `'user'`, which is accurate (they were all manually saved).

**Cap:** raised from 20 to 50. Enforced at write time via plain FIFO across all sources — autonomous saves are expected to be rare enough that they won't meaningfully push out manual ones.

## Backend: `remember` tool

New file `chat/tools/remember.py` following the existing tool-module pattern.

**Tool schema:**

```json
{
  "name": "remember",
  "description": "Save a durable fact about the user so you'll know it in future conversations. ONLY use for stable facts about who the user is (name, location, job, family, pets), long-running projects or goals, or explicit preferences about how they want you to behave. DO NOT use for passing remarks, questions the user asked, information about topics (only about the user), anything already in 'Things you know about the user', or anything you're not confident will still be true next week. When in doubt, don't save. Save at most one fact per turn. Write content as a short third-person sentence, e.g. 'User lives in Boston'.",
  "parameters": {
    "content": {"type": "string", "description": "One short sentence in third person."}
  }
}
```

**Execution** calls `db.add_memory(content, source='model')`, which now runs a dedup check before insert:

1. **Exact-match dedup** — `LOWER(TRIM(content))` equality. If hit, no-op, return `{"status": "duplicate"}`.
2. **Prefix dedup** — normalize to lowercase, strip punctuation, drop stopwords (*the, a, is, user, I, am*), take first 4 significant words. If an existing memory has the same prefix signature, *replace* it (delete old row, insert new) and return `{"status": "updated", "replaced_id": "...", "replaced_content": "..."}`. Catches "User lives in Boston" → "User lives in Seattle".
3. **Otherwise** insert fresh, return `{"status": "saved", "id": "...", "content": "..."}`.

Prefix dedup is an acknowledged heuristic. It will miss semantic duplicates like "I'm vegetarian" vs "I don't eat meat"; the worst case is a duplicate entry the user can delete manually via the existing memory panel.

**Input validation:** reject empty content and content longer than ~200 chars.

## Backend: recall injection

The existing code in `chat/app.py:324` already dumps all memories into `custom_context`. Only tweaks:

- Sort oldest-first in the injection so "most recent = last".
- Append one instruction to the injected block: *"If two facts contradict, trust the most recent one (listed last)."*
- Cap is enforced at write time, not read time; recall code itself doesn't change shape.

No embeddings, no retrieval step, no new code paths.

## Prompting strategy

The most failure-prone piece — small local models over-save if not coached carefully. Three changes to `chat/agent.py` `_build_system_prompt`:

1. The `remember` tool gets the tight description above in the tool list.
2. Add to the "Specific tool rules" block:
   > **remember**: Use sparingly. Most turns should NOT save anything. Only save when the user has just shared a durable fact about themselves, a long-running project, or a behavior preference — and it is not already listed in "Things you know about the user". Never save trivia, passing remarks, or facts about topics the user asked about.
3. Add negative and positive examples:
   ```
   User: what's the capital of France?
   You: The capital of France is Paris.   ← do NOT save "user asked about France"

   User: I just moved to Seattle last month.
   You: {"name": "remember", "arguments": {"content": "User lives in Seattle"}}
   ```

The bias is aggressively toward *not* saving. Over-saving is the failure mode to avoid: false negatives are invisible, false positives accumulate visibly in the memory panel.

## Frontend: save toast + undo

The agent loop already emits `tool_start` / `tool_end` events over the WebSocket (`chat/agent.py:159-165`). The frontend piggybacks:

- Listen for `tool_end` where `name === "remember"`.
- On `status: "saved"`: render a small bottom-right toast `💾 Remembered: "<content>"` with an **Undo** link. Auto-dismiss after ~6s.
- On `status: "updated"`: toast reads `💾 Updated: "<new>"`; undo restores `replaced_content`.
- On `status: "duplicate"`: no toast.
- Undo calls `DELETE /api/memory/:id` (already exists, `chat/app.py:174`), then replaces toast text with `"Forgotten"` briefly before fading.

**Changes:**
- Extend `chat/static/js/memory.js` with a `showMemoryToast(result)` function wired into the existing tool-event handler.
- Add `.memory-toast` class to `chat/static/style.css`.
- No new dependencies, no new files.

## Testing

**Unit — dedup logic** (`chat/tests/test_memory_dedup.py`, new)
- Exact match returns `duplicate`, doesn't insert.
- Prefix match replaces (Boston → Seattle).
- Non-matching content inserts fresh.
- Stopword normalization ("I live in Boston" vs "User lives in Boston" collide on prefix).
- `source` column defaults correctly.
- FIFO eviction at cap=50.

**Unit — `remember` tool** (`chat/tests/test_remember_tool.py`, new)
- Returns `{status, id, content}` on save.
- Returns `{status: "duplicate"}` on duplicate.
- Returns `{status: "updated", replaced_id, replaced_content}` on prefix-match update.
- Rejects empty content and content >200 chars.

**Integration — agent loop with remember** (`chat/tests/test_agent_memory.py`, new)
- Synthetic conversation where the model emits a `remember` tool call; assert DB row exists and the agent continues to the next round with a normal reply.
- Duplicate save; assert no second row.
- On the next turn, `custom_context` contains the new fact.

**Manual smoke test** (documented here, not automated):
1. Tell the real model "I live in Boston." Confirm a toast appears and the memory panel shows the entry.
2. Start a new conversation, ask "where do I live?" Confirm the model answers "Boston" without being told again.
3. Tell it "actually I moved to Seattle." Confirm both entries coexist (Boston and Seattle), and that in chat the model answers "Seattle" because of the "trust the most recent" tie-breaker in Section *Backend: recall injection*. Note for the user: the stale Boston entry can be deleted from the memory panel.

Frontend toast behavior is manual-only — no JS test harness exists in the project, and adding one is out of scope.

## Implementation notes

**Prefix-signature dedup was dropped during implementation.** The original design included a second dedup layer (a 4-significant-word stem-prefix signature) meant to catch "User lives in Boston" → "User lives in Seattle" as a replacement rather than a duplicate. In practice the heuristic was unworkable at v1 quality: the naive version failed its own tests because cities stem to distinct tokens, and the minimum fix to make it pass (dropping the last significant word) over-generalized — two unrelated facts sharing a verb stem (e.g. "User prefers Python" vs "User prefers Vim") would collapse into one row and destroy a good memory. Implemented and reverted in commits `172a737` and `8989016`.

Consequence: the memory store now relies on exact-match dedup only (Task 3). Semantic updates like "moved to Seattle" leave both the old and new rows in place. The Task 8 "trust the most recent" tie-breaker in the injected system prompt handles contradictions at chat time, and stale rows can be pruned via the existing memory panel UI. If false-positive duplicates pile up in real use, the right escalation is embedding-based semantic dedup — real machinery, actually sound — not another handcrafted heuristic.

## Non-goals / deferred

- **Prefix-signature dedup.** Tried and reverted (see Implementation notes). Embedding-based semantic dedup is the proper v2 path if this becomes a real pain point.
- **Semantic dedup via embeddings.** Deferred until v1 reveals whether exact-match alone is sufficient.
- **Model-driven update/forget tools.** Revisit if exact-match dedup misses too often.
- **Per-conversation memory scoping.** Memories stay global.
- **Retrieval / top-K recall.** Revisit if cap=50 proves too small or too expensive.
- **Memory categories / tags.** The `source` column is the only metadata; further taxonomy is speculative.
