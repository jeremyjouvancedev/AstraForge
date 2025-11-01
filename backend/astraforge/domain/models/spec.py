"""Domain models describing structured development specifications and merge proposals."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass(slots=True)
class DevelopmentSpec:
    """Normalized development specification produced from a natural language request."""

    title: str
    summary: str
    requirements: List[str] = field(default_factory=list)
    implementation_steps: List[str] = field(default_factory=list)
    risks: List[str] = field(default_factory=list)
    acceptance_criteria: List[str] = field(default_factory=list)
    raw_prompt: str | None = None

    def as_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "title": self.title,
            "summary": self.summary,
            "requirements": list(self.requirements),
            "implementation_steps": list(self.implementation_steps),
            "risks": list(self.risks),
            "acceptance_criteria": list(self.acceptance_criteria),
        }
        if self.raw_prompt:
            payload["raw_prompt"] = self.raw_prompt
        return payload


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
