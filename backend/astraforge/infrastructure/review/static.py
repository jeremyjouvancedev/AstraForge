"""Review bot implementation leveraging executors for code review."""

from __future__ import annotations

from dataclasses import dataclass

from astraforge.domain.providers.interfaces import ReviewBot


@dataclass
class StaticReviewBot(ReviewBot):
    def review(self, mr_ref: str, context: dict) -> dict:  # pragma: no cover
        return {"mr_ref": mr_ref, "score": 1.0, "comments": []}
