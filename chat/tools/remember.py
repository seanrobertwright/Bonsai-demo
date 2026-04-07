"""Remember tool — lets the model save durable facts about the user."""

from chat.db import ChatDB


class RememberTool:
    """Saves a durable fact about the user to the memory store.

    The model decides when to call this; server-side dedup in db.add_memory
    handles duplicate cases. Stores with source='model' to distinguish
    autonomous saves from manual ones.
    """

    def __init__(self, db: ChatDB):
        self.db = db

    @property
    def definition(self) -> dict:
        return {
            "name": "remember",
            "description": (
                "Save a durable fact about the user so you'll know it in future "
                "conversations. ONLY use for stable facts about who the user is "
                "(name, location, job, family, pets), long-running projects or "
                "goals, or explicit preferences about how they want you to behave. "
                "DO NOT use for passing remarks, questions the user asked, "
                "information about topics (only about the user), anything already "
                "in 'Facts you already know about the user', or anything you're not "
                "confident will still be true next week. When in doubt, don't "
                "save. Save at most one fact per turn. Write content as a short "
                "third-person sentence, e.g. 'User lives in Boston'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "One short third-person sentence describing the fact.",
                    },
                },
                "required": ["content"],
            },
        }

    async def execute(self, params: dict) -> dict:
        content = (params.get("content") or "").strip()
        if not content:
            return {"error": "Empty content — nothing to remember."}
        if len(content) > 200:
            return {"error": "Content too long (max 200 chars)."}

        return self.db.add_memory(content, source="model")
