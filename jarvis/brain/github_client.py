
import os
import threading

_AVAILABLE = False
try:
    from github import Github, Auth
    _AVAILABLE = True
except ImportError:
    pass


class GitHubClient:
    """Wrapper around PyGithub for JARVIS plugin use."""

    def __init__(self, token: str = ""):
        self._token = token or os.getenv("GITHUB_TOKEN", "")
        self._gh: "Github" | None = None
        self._lock = threading.Lock()

    def _client(self) -> "Github":
        if not _AVAILABLE:
            raise RuntimeError("PyGithub not installed: pip install PyGithub")
        if not self._token:
            raise RuntimeError(
                "Set GITHUB_TOKEN in your environment. "
                "Create one at github.com/settings/tokens"
            )
        with self._lock:
            if self._gh is None:
                self._gh = Github(auth=Auth.Token(self._token))
        return self._gh

    def list_prs(self, repo: str, state: str = "open") -> list[dict]:
        prs = self._client().get_repo(repo).get_pulls(state=state)
        return [
            {
                "number": pr.number,
                "title": pr.title,
                "author": pr.user.login,
                "state": pr.state,
                "url": pr.html_url,
                "draft": pr.draft,
                "created": pr.created_at.isoformat(),
            }
            for pr in list(prs)[:25]
        ]

    def get_pr(self, repo: str, number: int) -> dict:
        pr = self._client().get_repo(repo).get_pull(number)
        return {
            "number": pr.number,
            "title": pr.title,
            "author": pr.user.login,
            "state": pr.state,
            "body": (pr.body or "")[:800],
            "url": pr.html_url,
            "commits": pr.commits,
            "additions": pr.additions,
            "deletions": pr.deletions,
            "changed_files": pr.changed_files,
            "mergeable": pr.mergeable,
            "draft": pr.draft,
        }

    def list_issues(self, repo: str, state: str = "open") -> list[dict]:
        issues = self._client().get_repo(repo).get_issues(state=state)
        return [
            {
                "number": i.number,
                "title": i.title,
                "author": i.user.login,
                "state": i.state,
                "url": i.html_url,
                "labels": [la.name for la in i.labels],
            }
            for i in list(issues)[:25]
            if i.pull_request is None
        ]

    def create_issue(self, repo: str, title: str, body: str = "") -> dict:
        issue = self._client().get_repo(repo).create_issue(title=title, body=body)
        return {"number": issue.number, "url": issue.html_url}

    def ci_status(self, repo: str, ref: str = "") -> dict:
        r = self._client().get_repo(repo)
        sha = ref or r.get_branch(r.default_branch).commit.sha
        runs = list(r.get_commit(sha).get_check_runs())[:10]
        checks = [
            {"name": c.name, "status": c.status, "conclusion": c.conclusion}
            for c in runs
        ]
        overall = "success"
        for c in checks:
            if c["conclusion"] == "failure":
                overall = "failure"
                break
            if c["status"] != "completed":
                overall = "pending"
        return {"ref": sha[:10], "overall": overall, "checks": checks}


_inst: GitHubClient | None = None
_lock = threading.Lock()


def get_github() -> GitHubClient:
    global _inst
    if _inst is None:
        with _lock:
            if _inst is None:
                _inst = GitHubClient()
    return _inst
