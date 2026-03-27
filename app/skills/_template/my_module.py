"""Template skill module. Copy and modify for your own skill."""

from strands import tool


@tool
def my_tool_function(input_text: str) -> str:
    """Describe what this tool does — the LLM reads this docstring.

    Explain WHEN the agent should use this tool so it picks it appropriately.

    Args:
        input_text: Description of the parameter.
    """
    return f"Processed: {input_text}"
