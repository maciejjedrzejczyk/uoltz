"""Guarded shell command execution tool."""

import subprocess
import shlex
from strands import tool

# Commands that are never allowed
BLOCKED_PREFIXES = ("rm -rf /", "mkfs", "dd if=", ":(){ :|:& };:", "shutdown", "reboot")


@tool
def run_shell_command(command: str) -> str:
    """Run a shell command on the local machine and return its output.

    Use this for tasks like checking disk space, listing files, running scripts,
    or any local system operation the user requests.

    IMPORTANT: Dangerous commands (rm -rf /, shutdown, etc.) are blocked.

    Args:
        command: The shell command to execute.
    """
    cmd_lower = command.strip().lower()
    for blocked in BLOCKED_PREFIXES:
        if cmd_lower.startswith(blocked):
            return f"Blocked: '{command}' is not allowed for safety reasons."

    try:
        result = subprocess.run(
            shlex.split(command),
            capture_output=True,
            text=True,
            timeout=30,
        )
        output = result.stdout or ""
        if result.stderr:
            output += f"\nSTDERR: {result.stderr}"
        if result.returncode != 0:
            output += f"\n(exit code {result.returncode})"
        return output.strip() or "(no output)"
    except subprocess.TimeoutExpired:
        return "Command timed out after 30 seconds."
    except Exception as e:
        return f"Error running command: {e}"
