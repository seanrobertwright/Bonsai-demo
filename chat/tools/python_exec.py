"""Python execution tool — runs code in a sandboxed subprocess."""

import asyncio
import sys
from pathlib import Path

from chat.config import SANDBOX_DIR, PYTHON_EXEC_TIMEOUT


class PythonExecTool:
    def __init__(self, sandbox_dir: str | None = None):
        self._sandbox = Path(sandbox_dir) if sandbox_dir else SANDBOX_DIR
        self._sandbox.mkdir(parents=True, exist_ok=True)

    @property
    def definition(self) -> dict:
        return {
            "name": "python_exec",
            "description": "Execute Python code and return the output. The code runs in an isolated subprocess with a 30-second timeout. Use print() to produce output.",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "Python code to execute",
                    }
                },
                "required": ["code"],
            },
        }

    async def execute(self, params: dict) -> dict:
        code = params.get("code", "").strip()
        if not code:
            return {"error": "Empty code"}

        try:
            proc = await asyncio.create_subprocess_exec(
                sys.executable, "-c", code,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self._sandbox),
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=PYTHON_EXEC_TIMEOUT
            )

            return {
                "stdout": stdout.decode("utf-8", errors="replace"),
                "stderr": stderr.decode("utf-8", errors="replace"),
                "returncode": proc.returncode,
            }
        except asyncio.TimeoutError:
            proc.kill()
            return {"error": f"Execution timed out after {PYTHON_EXEC_TIMEOUT} seconds"}
        except Exception as e:
            return {"error": f"Execution failed: {e}"}
