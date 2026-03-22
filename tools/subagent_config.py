from tools.subagents import SubAgentDefinition


def get_subagent_definitions() -> list[SubAgentDefinition]:
    """Central place to define subagents registered at startup.

    Add, remove, or edit entries in this list to control available subagents.
    """
    return [
        SubAgentDefinition(
            name="explore",
            description="Explore the codebase and summarize findings with precise file references.",
            goal_prompt=(
                "You are an exploration specialist. Investigate the repository for the user's goal, "
                "collect concrete evidence from files, and return concise, structured findings."
            ),
            allowed_tools=["list_dir", "glob", "grep", "read_file"],
            max_turns=12,
            timeout_seconds=120,
        ),
        SubAgentDefinition(
            name="code_reviewer",
            description="Review code changes for bugs, regressions, and test gaps.",
            goal_prompt=(
                "You are a senior code reviewer. Prioritize correctness, security, regressions, and missing tests. "
                "Return findings ordered by severity with precise file/line references, then list assumptions and risks."
            ),
            allowed_tools=["list_dir", "glob", "grep", "read_file"],
            max_turns=15,
            timeout_seconds=180,
        ),
    ]
