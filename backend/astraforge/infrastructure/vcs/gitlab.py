"""GitLab VCS provider implementation."""

from __future__ import annotations

from dataclasses import dataclass

from astraforge.domain.providers.interfaces import VCSProvider


@dataclass
class GitLabClient:  # pragma: no cover - stub
    token: str
    url: str

    def create_merge_request(
        self,
        repo: str,
        source_branch: str,
        target_branch: str,
        title: str,
        body: str,
        artifacts: list[str] | None = None,
    ):
        raise NotImplementedError

    def post_comment(self, mr_ref: str, comment: str):
        raise NotImplementedError


@dataclass
class GitLabProvider(VCSProvider):
    client: GitLabClient

    def open_mr(
        self,
        repo: str,
        source_branch: str,
        target_branch: str,
        title: str,
        body: str,
        artifacts,
    ):  # pragma: no cover
        response = self.client.create_merge_request(
            repo=repo,
            source_branch=source_branch,
            target_branch=target_branch,
            title=title,
            body=body,
            artifacts=list(artifacts),
        )
        return response["web_url"]

    def comment(self, mr_ref: str, comments: list[str]) -> None:  # pragma: no cover
        for comment in comments:
            self.client.post_comment(mr_ref, comment)


def from_env() -> GitLabProvider:
    token = "${GITLAB_TOKEN}"  # placeholder
    url = "https://gitlab.example.com"
    client = GitLabClient(token=token, url=url)
    return GitLabProvider(client=client)
