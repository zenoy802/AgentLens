from __future__ import annotations

AGENT_GUIDE = """# AgentLens Agent Guide

AgentLens is a SQL-first LLM trajectory analysis tool. Users query their own database in
AgentLens UI, then agents inspect the resulting rows, trajectory views, labels, and annotations.

## Workflow

1. Discover query ids with `list_queries`, or use the query_id from the user prompt.
2. For small live data, use `get_rows` or `get_selection`.
3. For trajectory-shaped data, use `get_trajectories`.
4. For large analysis or local file processing, use `export_context` instead of fetching thousands
   of rows through MCP.
5. Write analysis findings back to the UI with `add_annotation` or `highlight_rows`.

## Live Access Vs Context Export

Live access tools read current backend state by reference and return bounded MCP results.
`export_context` materializes the current query or selection into local files and returns file
paths. Use the exported files with shell tools, Python, jq, grep, or direct file reads.

## Annotation Colors

- red: hard failures / errors
- yellow: suspicious / warning
- green: verified correct / success
- blue: informational
- gray: neutral

## Write-Back Rules

Annotation text is limited to 2000 characters. The annotation author is fixed by the server
startup `--author` argument, so agent tool calls cannot spoof another author.
"""

__all__ = ["AGENT_GUIDE"]
