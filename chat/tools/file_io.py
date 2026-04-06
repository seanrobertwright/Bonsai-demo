"""File I/O tool — sandboxed file read/write/list."""

from pathlib import Path

from chat.config import SANDBOX_DIR


class FileIOTool:
    def __init__(self, sandbox_dir: str | None = None):
        self._sandbox = Path(sandbox_dir) if sandbox_dir else SANDBOX_DIR
        self._sandbox.mkdir(parents=True, exist_ok=True)

    @property
    def definition(self) -> dict:
        return {
            "name": "file_io",
            "description": f"Read, write, or list files in the sandbox directory ({self._sandbox}). Use action 'read', 'write', or 'list'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["read", "write", "list"],
                        "description": "The file operation to perform",
                    },
                    "path": {
                        "type": "string",
                        "description": "Relative path within the sandbox directory",
                    },
                    "content": {
                        "type": "string",
                        "description": "Content to write (only for 'write' action)",
                    },
                },
                "required": ["action", "path"],
            },
        }

    def _resolve_safe(self, rel_path: str) -> Path | None:
        target = (self._sandbox / rel_path).resolve()
        if not str(target).startswith(str(self._sandbox.resolve())):
            return None
        return target

    async def execute(self, params: dict) -> dict:
        action = params.get("action", "")
        rel_path = params.get("path", "")

        if action == "list":
            target = self._resolve_safe(rel_path)
            if target is None:
                return {"error": "Path outside sandbox"}
            if not target.exists():
                return {"error": f"Directory not found: {rel_path}"}
            if not target.is_dir():
                return {"error": f"Not a directory: {rel_path}"}
            files = [
                {"name": f.name, "type": "dir" if f.is_dir() else "file", "size": f.stat().st_size if f.is_file() else 0}
                for f in sorted(target.iterdir())
            ]
            return {"files": files}

        if action == "read":
            target = self._resolve_safe(rel_path)
            if target is None:
                return {"error": "Path outside sandbox"}
            if not target.exists():
                return {"error": f"File not found: {rel_path}"}
            try:
                return {"content": target.read_text(encoding="utf-8")}
            except Exception as e:
                return {"error": f"Could not read file: {e}"}

        if action == "write":
            content = params.get("content", "")
            target = self._resolve_safe(rel_path)
            if target is None:
                return {"error": "Path outside sandbox"}
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")
                return {"result": f"Written {len(content)} bytes to {rel_path}"}
            except Exception as e:
                return {"error": f"Could not write file: {e}"}

        return {"error": f"Unknown action: {action}. Use 'read', 'write', or 'list'."}
