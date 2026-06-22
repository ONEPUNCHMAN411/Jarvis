
import asyncio

from loguru import logger
from jarvis.plugins.base import Plugin
from jarvis.models import ToolDefinition


class GitHubPlugin(Plugin):
    """GitHub tools: list PRs/issues, PR details, CI status, create issues."""

    def __init__(self):
        super().__init__("github")
        self._gh = None

    def _get(self):
        if self._gh is None:
            from jarvis.brain.github_client import get_github
            self._gh = get_github()
        return self._gh

    async def initialize(self) -> None:
        from jarvis.brain.github_client import _AVAILABLE
        if not _AVAILABLE:
            logger.warning("GitHubPlugin: PyGithub not installed — tools disabled")
        else:
            logger.info("GitHubPlugin ready")

    def get_tools(self):
        _repo = {"repo": {"type": "string", "description": "owner/repo"}}
        _state = {"state": {"type": "string", "description": "'open' or 'closed'"}}

        return [
            (
                ToolDefinition(
                    name="github_list_prs",
                    description=(
                        "List pull requests for a GitHub repository. "
                        "Format: owner/repo (e.g. octocat/Hello-World). "
                        "Defaults to open PRs."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {**_repo, **_state},
                        "required": ["repo"],
                    },
                ),
                self.list_prs,
            ),
            (
                ToolDefinition(
                    name="github_get_pr",
                    description=(
                        "Get full details of a pull request: diff stats, "
                        "commit count, description, and mergeable status."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            **_repo,
                            "number": {
                                "type": "integer",
                                "description": "PR number",
                            },
                        },
                        "required": ["repo", "number"],
                    },
                ),
                self.get_pr,
            ),
            (
                ToolDefinition(
                    name="github_list_issues",
                    description=(
                        "List issues for a GitHub repository (excludes PRs). "
                        "Returns number, title, author, and labels."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {**_repo, **_state},
                        "required": ["repo"],
                    },
                ),
                self.list_issues,
            ),
            (
                ToolDefinition(
                    name="github_create_issue",
                    description="Create a new issue in a GitHub repository.",
                    parameters={
                        "type": "object",
                        "properties": {
                            **_repo,
                            "title": {
                                "type": "string",
                                "description": "Issue title",
                            },
                            "body": {
                                "type": "string",
                                "description": "Issue description (optional)",
                            },
                        },
                        "required": ["repo", "title"],
                    },
                ),
                self.create_issue,
            ),
            (
                ToolDefinition(
                    name="github_ci_status",
                    description=(
                        "Check CI/CD check status for the latest commit on a branch. "
                        "Leave ref blank to check the default branch."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            **_repo,
                            "ref": {
                                "type": "string",
                                "description": "branch, tag, or commit SHA (optional)",
                            },
                        },
                        "required": ["repo"],
                    },
                ),
                self.ci_status,
            ),
        ]

    async def _run(self, fn, *args, **kwargs):
        loop = asyncio.get_running_loop()
        try:
            return await loop.run_in_executor(None, lambda: fn(*args, **kwargs))
        except Exception as e:
            return f"GitHub error: {e}"

    async def list_prs(self, repo: str, state: str = "open") -> str:
        prs = await self._run(self._get().list_prs, repo, state)
        if isinstance(prs, str):
            return prs
        if not prs:
            return f"No {state} PRs in {repo}."
        lines = [f"Pull Requests — {repo} ({state}):"]
        for pr in prs:
            draft = " [DRAFT]" if pr["draft"] else ""
            lines.append(f"  #{pr['number']} {pr['title']}{draft}  ({pr['author']})")
        return "\n".join(lines)

    async def get_pr(self, repo: str, number: int) -> str:
        pr = await self._run(self._get().get_pr, repo, number)
        if isinstance(pr, str):
            return pr
        body_section = (
            f"\n\nDescription:\n{pr['body'][:400]}"
            if pr["body"].strip()
            else ""
        )
        draft_tag = "  [DRAFT]" if pr["draft"] else ""
        return (
            f"PR #{pr['number']}: {pr['title']}{draft_tag}\n"
            f"Author: {pr['author']}  |  State: {pr['state']}\n"
            f"Changes: +{pr['additions']} -{pr['deletions']}"
            f" across {pr['changed_files']} files\n"
            f"Commits: {pr['commits']}  |  Mergeable: {pr['mergeable']}\n"
            f"URL: {pr['url']}"
            + body_section
        )

    async def list_issues(self, repo: str, state: str = "open") -> str:
        issues = await self._run(self._get().list_issues, repo, state)
        if isinstance(issues, str):
            return issues
        if not issues:
            return f"No {state} issues in {repo}."
        lines = [f"Issues — {repo} ({state}):"]
        for i in issues:
            tags = f" [{', '.join(i['labels'])}]" if i["labels"] else ""
            lines.append(f"  #{i['number']} {i['title']}{tags}  ({i['author']})")
        return "\n".join(lines)

    async def create_issue(self, repo: str, title: str, body: str = "") -> str:
        result = await self._run(self._get().create_issue, repo, title, body)
        if isinstance(result, str):
            return result
        return f"Issue #{result['number']} created: {result['url']}"

    async def ci_status(self, repo: str, ref: str = "") -> str:
        s = await self._run(self._get().ci_status, repo, ref)
        if isinstance(s, str):
            return s
        icons = {"success": "✅", "failure": "❌", "pending": "⏳"}
        icon = icons.get(s["overall"], "❓")
        lines = [f"CI — {repo} @ {s['ref']}: {icon} {s['overall'].upper()}"]
        for c in s["checks"]:
            conclusion = c.get("conclusion") or c.get("status", "?")
            lines.append(f"  • {c['name']}: {conclusion}")
        return "\n".join(lines)
