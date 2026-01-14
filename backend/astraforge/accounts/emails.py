from __future__ import annotations

from django.conf import settings
from django.core.mail import send_mail
from django.utils.html import escape

WAITLIST_SUBJECT = "You're on the AstraForge waitlist"
EARLY_ACCESS_USER_SUBJECT = "You're on the AstraForge early access list"
EARLY_ACCESS_OWNER_SUBJECT = "New AstraForge early access request"


def send_waitlist_email(*, recipient: str, username: str):
    """Send a styled waitlist confirmation email."""
    if not recipient:
        return

    html_message = f"""
<html>
  <body style="margin:0;padding:0;background:radial-gradient(circle at 20% 20%, #312e81, #0b1021);font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;color:#e5e7eb;">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="padding:32px 0;">
      <tr>
        <td align="center">
          <table role="presentation" width="560" cellspacing="0" cellpadding="0" style="background:rgba(15,23,42,0.85);border:1px solid rgba(255,255,255,0.08);border-radius:18px;padding:32px 28px;box-shadow:0 25px 80px rgba(79,70,229,0.25);backdrop-filter:blur(10px);">
            <tr>
              <td style="padding-bottom:12px;">
                <div style="display:inline-flex;align-items:center;gap:12px;">
                  <div style="width:40px;height:40px;border-radius:14px;background:linear-gradient(135deg,#6366f1,#a855f7);box-shadow:0 10px 25px rgba(99,102,241,0.35);"></div>
                  <div>
                    <div style="font-size:14px;font-weight:700;color:#fff;">AstraForge</div>
                    <div style="font-size:12px;color:#c7d2fe;">Sandbox factory for DeepAgents</div>
                  </div>
                </div>
              </td>
            </tr>
            <tr>
              <td style="padding:12px 0 4px;">
                <div style="font-size:13px;letter-spacing:0.2em;color:#c7d2fe;text-transform:uppercase;">Waitlist confirmed</div>
                <div style="font-size:24px;font-weight:700;color:#fff;margin-top:8px;">Thanks for joining, {username}.</div>
              </td>
            </tr>
            <tr>
              <td style="padding:10px 0 16px;color:#e5e7eb;font-size:15px;line-height:1.6;">
                You're on the AstraForge access list. We'll email you as soon as an administrator approves your account so you can launch secure sandboxes and ship faster.
              </td>
            </tr>
            <tr>
              <td style="padding-top:8px;">
                <div style="display:inline-block;padding:12px 18px;border-radius:12px;background:linear-gradient(135deg,#818cf8,#a855f7);color:#0b1021;font-weight:700;font-size:14px;text-decoration:none;">
                  You're in the queue
                </div>
              </td>
            </tr>
            <tr>
              <td style="padding-top:18px;font-size:13px;color:#94a3b8;line-height:1.5;">
                If this wasn't you, ignore this email. For help, reply to this message and we'll take a look.
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>
"""
    plain_message = (
        "You're on the AstraForge waitlist. We'll email you once your account is approved."
    )

    send_mail(
        WAITLIST_SUBJECT,
        plain_message,
        getattr(settings, "DEFAULT_FROM_EMAIL", None) or "noreply@astraforge.dev",
        [recipient],
        html_message=html_message,
    )


def _format_multiline(value: str | None) -> str:
    if not value:
        return "—"
    lines = [escape(line) for line in value.strip().splitlines() if line]
    return "<br/>".join(lines) or "—"


def send_early_access_confirmation(
    *,
    recipient: str,
    team_role: str | None,
    project_summary: str | None,
):
    """Send a confirmation email to the requester."""
    if not recipient:
        return

    team_value = escape(team_role.strip()) if team_role else "—"
    summary_value = _format_multiline(project_summary)
    html_message = f"""
<html>
  <body style="margin:0;padding:0;background:radial-gradient(circle at 25% 20%, #1f1b4b, #050914);font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;color:#e5e7eb;">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="padding:32px 0;">
      <tr>
        <td align="center">
          <table role="presentation" width="560" cellspacing="0" cellpadding="0" style="background:rgba(8,12,24,0.92);border:1px solid rgba(255,255,255,0.08);border-radius:20px;padding:36px 32px;box-shadow:0 30px 80px rgba(99,102,241,0.3);backdrop-filter:blur(12px);">
            <tr>
              <td style="padding-bottom:16px;">
                <div style="display:inline-flex;align-items:center;gap:12px;">
                  <div style="width:44px;height:44px;border-radius:16px;background:linear-gradient(135deg,#6366f1,#a855f7);box-shadow:0 15px 30px rgba(99,102,241,0.35);"></div>
                  <div>
                    <div style="font-size:14px;font-weight:700;color:#fff;">AstraForge</div>
                    <div style="font-size:12px;color:#c7d2fe;">Production sandboxes for DeepAgents</div>
                  </div>
                </div>
              </td>
            </tr>
            <tr>
              <td style="padding:6px 0 4px;">
                <div style="font-size:12px;letter-spacing:0.35em;color:#c7d2fe;text-transform:uppercase;">Early access</div>
                <div style="font-size:26px;font-weight:700;color:#fff;margin-top:8px;">You're on the list.</div>
              </td>
            </tr>
            <tr>
              <td style="padding:12px 0 16px;color:#d1d5db;font-size:15px;line-height:1.65;">
                We received your early access request and will follow up with demos, roadmap, and onboarding windows. Expect more details soon — meanwhile, here’s a snapshot of what you shared.
              </td>
            </tr>
            <tr>
              <td style="padding:12px 0 8px;">
                <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="border-radius:16px;background:rgba(20,24,38,0.85);border:1px solid rgba(255,255,255,0.05);">
                  <tr>
                    <td style="padding:18px 24px;border-bottom:1px solid rgba(255,255,255,0.04);">
                      <div style="font-size:12px;text-transform:uppercase;letter-spacing:0.3em;color:#94a3b8;">Team / role</div>
                      <div style="margin-top:6px;font-size:15px;color:#f8fafc;">{team_value}</div>
                    </td>
                  </tr>
                  <tr>
                    <td style="padding:18px 24px;">
                      <div style="font-size:12px;text-transform:uppercase;letter-spacing:0.3em;color:#94a3b8;">What you're building</div>
                      <div style="margin-top:6px;font-size:15px;color:#f8fafc;line-height:1.6;">{summary_value}</div>
                    </td>
                  </tr>
                </table>
              </td>
            </tr>
            <tr>
              <td style="padding-top:18px;font-size:13px;color:#94a3b8;line-height:1.5;">
                Reply to this email if you want to share more context. We prioritize real DeepAgent workloads (repos, infra, SLAs) so we can get you running with confidence.
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>
"""
    plain_message = (
        "Thanks for requesting AstraForge early access. We'll reach out with a demo and onboarding window soon."
    )
    send_mail(
        EARLY_ACCESS_USER_SUBJECT,
        plain_message,
        getattr(settings, "DEFAULT_FROM_EMAIL", None) or "noreply@astraforge.dev",
        [recipient],
        html_message=html_message,
    )


def send_early_access_owner_alert(
    *,
    recipient: str,
    requester_email: str,
    team_role: str | None,
    project_summary: str | None,
):
    """Notify the owner inbox about a new early access request."""
    if not recipient:
        return
    team_value = escape(team_role.strip()) if team_role else "—"
    summary_value = _format_multiline(project_summary)
    requester_value = escape(requester_email)
    html_message = f"""
<html>
  <body style="margin:0;padding:0;background:#05070f;font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;color:#e5e7eb;">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="padding:28px 0;">
      <tr>
        <td align="center">
          <table role="presentation" width="540" cellspacing="0" cellpadding="0" style="background:#0a0f1e;border:1px solid rgba(255,255,255,0.08);border-radius:18px;padding:30px;">
            <tr>
              <td>
                <div style="font-size:13px;letter-spacing:0.3em;color:#818cf8;text-transform:uppercase;">New early access request</div>
                <div style="font-size:24px;font-weight:700;color:#fff;margin-top:6px;">Someone wants to try AstraForge.</div>
              </td>
            </tr>
            <tr>
              <td style="padding-top:20px;">
                <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="border-radius:14px;background:rgba(12,19,35,0.85);border:1px solid rgba(255,255,255,0.05);">
                  <tr>
                    <td style="padding:16px 20px;border-bottom:1px solid rgba(255,255,255,0.04);">
                      <div style="font-size:12px;text-transform:uppercase;letter-spacing:0.3em;color:#94a3b8;">Email</div>
                      <div style="margin-top:6px;font-size:15px;color:#f8fafc;">{requester_value}</div>
                    </td>
                  </tr>
                  <tr>
                    <td style="padding:16px 20px;border-bottom:1px solid rgba(255,255,255,0.04);">
                      <div style="font-size:12px;text-transform:uppercase;letter-spacing:0.3em;color:#94a3b8;">Team / role</div>
                      <div style="margin-top:6px;font-size:15px;color:#f8fafc;">{team_value}</div>
                    </td>
                  </tr>
                  <tr>
                    <td style="padding:16px 20px;">
                      <div style="font-size:12px;text-transform:uppercase;letter-spacing:0.3em;color:#94a3b8;">What they're building</div>
                      <div style="margin-top:6px;font-size:15px;color:#f8fafc;line-height:1.6;">{summary_value}</div>
                    </td>
                  </tr>
                </table>
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>
"""
    plain_message = (
        "New AstraForge early access request.\n"
        f"Email: {requester_email}\n"
        f"Team / role: {team_role or '—'}\n"
        f"What they're building: {project_summary or '—'}\n"
    )
    send_mail(
        EARLY_ACCESS_OWNER_SUBJECT,
        plain_message,
        getattr(settings, "DEFAULT_FROM_EMAIL", None) or "noreply@astraforge.dev",
        [recipient],
        html_message=html_message,
    )
