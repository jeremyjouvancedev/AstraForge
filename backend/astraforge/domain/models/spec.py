"""Domain models describing structured development specifications and merge proposals."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class MergeRequestProposal:
    """Structured merge request payload ready for submission to a VCS provider."""

    title: str
    description: str
    target_branch: str
    source_branch: str

    def as_dict(self) -> dict[str, str]:
        return {
            "title": self.title,
            "description": self.description,
            "target_branch": self.target_branch,
            "source_branch": self.source_branch,
        }
