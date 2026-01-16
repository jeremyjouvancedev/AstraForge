from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable
from urllib.parse import urlparse

from .protocol import (
    ComputerCall,
    PendingSafetyCheck,
    new_safety_check_id,
)


_ALLOWED_SCHEMES = {"http", "https"}
_SAFE_SCHEMES = {"about", "data", "file", "chrome", "blob"}


@dataclass(slots=True)
class PolicyConfig:
    allowed_domains: list[str] = field(default_factory=list)
    blocked_domains: list[str] = field(default_factory=list)
    approval_mode: str = "auto"
    allow_login: bool = False
    allow_payments: bool = False
    allow_irreversible: bool = False
    allow_credentials: bool = False
    default_deny: bool = True
    prompt_injection_detection: bool = True


@dataclass(slots=True)
class PolicyDecision:
    decision: str
    checks: list[PendingSafetyCheck]
    reason: str | None = None

    def to_item(self) -> dict[str, Any]:
        return {
            "type": "policy_decision",
            "decision": self.decision,
            "reason": self.reason or "",
            "checks": [check.to_dict() for check in self.checks],
        }


def _normalize_domains(domains: Iterable[str]) -> list[str]:
    output = []
    for domain in domains:
        cleaned = (domain or "").strip().lower().lstrip(".")
        if not cleaned:
            continue
        output.append(cleaned)
    return output


def _domain_matches(hostname: str, domain: str) -> bool:
    if not hostname or not domain:
        return False
    if hostname == domain:
        return True
    return hostname.endswith("." + domain)


def is_domain_allowed(url: str, config: PolicyConfig) -> bool:
    parsed = urlparse(url)

    scheme = (parsed.scheme or "").lower()
    if scheme in _SAFE_SCHEMES:
        return True
    if scheme not in _ALLOWED_SCHEMES:
        return not config.default_deny

    hostname = (parsed.hostname or "").lower()
    if not hostname:
        return not config.default_deny

    blocked = _normalize_domains(config.blocked_domains)
    for domain in blocked:
        if _domain_matches(hostname, domain):
            return False

    allowed = _normalize_domains(config.allowed_domains)
    if not allowed:
        return not config.default_deny
    if "*" in allowed:
        return True
    return any(_domain_matches(hostname, domain) for domain in allowed)


def _looks_like_credential(text: str) -> bool:
    lowered = text.lower()
    if "password" in lowered or "passwd" in lowered:
        return True
    if "api" in lowered and "key" in lowered:
        return True
    if "secret" in lowered or "token" in lowered:
        return True
    if len(text) >= 20 and any(char.isdigit() for char in text):
        return True
    if "@" in text and "." in text and len(text) >= 6:
        return True
    return False


def _contains_sensitive_hint(text: str, keywords: Iterable[str]) -> bool:
    lowered = text.lower()
    return any(keyword in lowered for keyword in keywords)


def _detect_prompt_injection(summary: str | None) -> bool:
    if not summary:
        return False
    lowered = summary.lower()
    return any(
        phrase in lowered
        for phrase in (
            "ignore previous",
            "disregard instructions",
            "system prompt",
            "prompt injection",
        )
    )


def evaluate_policy(call: ComputerCall, config: PolicyConfig) -> PolicyDecision:
    checks: list[PendingSafetyCheck] = list(call.pending_safety_checks)

    action = call.action
    action_type = action.type
    meta_summary = call.meta.reasoning_summary

    if action_type == "visit_url":
        url = action.url or ""
        if url and not is_domain_allowed(url, config):
            checks.append(
                PendingSafetyCheck(
                    id=new_safety_check_id("sc_domain"),
                    category="external_domain",
                    severity="high",
                    message="Domain is not in allowlist",
                )
            )

    if action_type == "type" and action.text:
        if _looks_like_credential(action.text):
            checks.append(
                PendingSafetyCheck(
                    id=new_safety_check_id("sc_cred"),
                    category="credentials",
                    severity="high",
                    message="Typed text resembles credentials",
                )
            )

    if action_type == "visit_url":
        url = action.url or ""
        if url and _contains_sensitive_hint(url, ["login", "signin", "auth", "oauth"]):
            checks.append(
                PendingSafetyCheck(
                    id=new_safety_check_id("sc_auth"),
                    category="sensitive_action",
                    severity="high",
                    message="Login/auth flow detected",
                )
            )
        if url and _contains_sensitive_hint(
            url, ["checkout", "payment", "billing", "card", "purchase"]
        ):
            checks.append(
                PendingSafetyCheck(
                    id=new_safety_check_id("sc_payment"),
                    category="payment",
                    severity="high",
                    message="Payment flow detected",
                )
            )

    if call.meta.critical_point:
        checks.append(
            PendingSafetyCheck(
                id=new_safety_check_id("sc_irreversible"),
                category="irreversible",
                severity="high",
                message="Action marked as critical/irreversible",
            )
        )

    if config.prompt_injection_detection and _detect_prompt_injection(meta_summary):
        checks.append(
            PendingSafetyCheck(
                id=new_safety_check_id("sc_injection"),
                category="prompt_injection",
                severity="medium",
                message="Potential prompt injection signal",
            )
        )

    decision = "allow"
    reason = None

    for check in checks:
        if check.category == "external_domain":
            decision = "block"
            reason = "domain_blocked"
            break
        if check.category == "payment" and not config.allow_payments:
            decision = "block"
            reason = "payments_blocked"
            break
        if check.category == "sensitive_action" and not config.allow_login:
            decision = "block"
            reason = "login_blocked"
            break
        if check.category == "irreversible" and not config.allow_irreversible:
            decision = "block"
            reason = "irreversible_blocked"
            break

    if decision == "block":
        return PolicyDecision(decision=decision, checks=checks, reason=reason)

    if any(check.category == "credentials" for check in checks) and not config.allow_credentials:
        return PolicyDecision(
            decision="require_ack",
            checks=checks,
            reason="credentials_require_approval",
        )

    if action_type == "terminate":
        return PolicyDecision(decision="allow", checks=checks)

    if config.approval_mode == "always":
        return PolicyDecision(decision="require_ack", checks=checks, reason="approval_always")

    if config.approval_mode == "on_risk":
        for check in checks:
            if check.severity in {"medium", "high"}:
                return PolicyDecision(
                    decision="require_ack",
                    checks=checks,
                    reason="risk_requires_approval",
                )
        if call.meta.critical_point:
            return PolicyDecision(
                decision="require_ack",
                checks=checks,
                reason="critical_point_requires_approval",
            )

    return PolicyDecision(decision="allow", checks=checks)
