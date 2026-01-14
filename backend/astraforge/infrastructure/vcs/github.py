"""GitHub VCS provider implementation."""

from __future__ import annotations

from dataclasses import dataclass

from astraforge.domain.providers.interfaces import VCSProvider


@dataclass
class GitHubClient:  # pragma: no cover - stub
    token: str

    def create_pull_request(
        self,
        repo: str,
        source_branch: str,
        target_branch: str,
        title: str,
        body: str,
        artifacts: list[str] | None = None,
    ):
        raise NotImplementedError

    def post_comment(self, pr_ref: str, comment: str):
        raise NotImplementedError


@dataclass
class GitHubProvider(VCSProvider):
    client: GitHubClient

    def open_mr(
        self,
        repo: str,
        source_branch: str,
        target_branch: str,
        title: str,
        body: str,
        artifacts,
    ):  # pragma: no cover
        response = self.client.create_pull_request(
            repo=repo,
            source_branch=source_branch,
            target_branch=target_branch,
            title=title,
            body=body,
            artifacts=list(artifacts),
        )
        return response["html_url"]

    def comment(self, mr_ref: str, comments: list[str]) -> None:  # pragma: no cover
        for comment in comments:
            self.client.post_comment(mr_ref, comment)


def from_env() -> GitHubProvider:
    token = "${GITHUB_TOKEN}"
    return GitHubProvider(client=GitHubClient(token=token))
