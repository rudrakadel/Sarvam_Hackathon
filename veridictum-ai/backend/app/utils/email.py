"""
VeriDictum AI — Email Utility
Async transactional emails via aiosmtplib.
"""

import asyncio
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

import aiosmtplib

from app.config import settings


async def send_email(
    to_email: str,
    subject: str,
    html_body: str,
    text_body: Optional[str] = None,
) -> None:
    """Send a transactional email asynchronously. Silently no-ops if SMTP is not configured."""
    if not settings.SMTP_USER or not settings.SMTP_PASSWORD:
        return  # SMTP not configured — skip silently

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings.EMAIL_FROM
    msg["To"] = to_email

    if text_body:
        msg.attach(MIMEText(text_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    try:
        await aiosmtplib.send(
            msg,
            hostname=settings.SMTP_HOST,
            port=settings.SMTP_PORT,
            username=settings.SMTP_USER,
            password=settings.SMTP_PASSWORD,
            start_tls=True,
        )
    except Exception:
        pass  # Email delivery failed — silently ignore in dev/test


async def send_verification_email(to_email: str, full_name: str, token: str) -> None:
    verify_url = f"https://app.veridictum.ai/verify-email?token={token}"
    html = f"""
    <h2>Welcome to VeriDictum AI, {full_name}!</h2>
    <p>Please verify your email address to activate your account:</p>
    <a href="{verify_url}" style="background:#1B2B5E;color:white;padding:12px 24px;text-decoration:none;border-radius:6px;">
      Verify Email
    </a>
    <p>This link expires in 24 hours.</p>
    <p>If you did not create this account, please ignore this email.</p>
    """
    await send_email(to_email, "Verify your VeriDictum AI account", html)


async def send_password_reset_email(to_email: str, full_name: str, token: str) -> None:
    reset_url = f"https://app.veridictum.ai/reset-password?token={token}"
    html = f"""
    <h2>Password Reset Request</h2>
    <p>Hello {full_name},</p>
    <p>Click below to reset your VeriDictum AI password. This link expires in 1 hour.</p>
    <a href="{reset_url}" style="background:#1B2B5E;color:white;padding:12px 24px;text-decoration:none;border-radius:6px;">
      Reset Password
    </a>
    <p>If you did not request this, your account may have been compromised. Contact support immediately.</p>
    """
    await send_email(to_email, "Reset your VeriDictum AI password", html)


async def send_invitation_email(
    to_email: str,
    invited_by: str,
    org_name: str,
    role: str,
    token: str,
) -> None:
    accept_url = f"https://app.veridictum.ai/accept-invitation?token={token}"
    html = f"""
    <h2>You've been invited to VeriDictum AI</h2>
    <p>{invited_by} has invited you to join <strong>{org_name}</strong> as a <strong>{role}</strong>.</p>
    <a href="{accept_url}" style="background:#1B2B5E;color:white;padding:12px 24px;text-decoration:none;border-radius:6px;">
      Accept Invitation
    </a>
    <p>This invitation expires in 48 hours.</p>
    """
    await send_email(to_email, f"Invitation to join {org_name} on VeriDictum AI", html)


async def send_report_ready_email(
    to_email: str,
    full_name: str,
    case_title: str,
    download_url: str,
) -> None:
    html = f"""
    <h2>Your Contradiction Report is Ready</h2>
    <p>Hello {full_name},</p>
    <p>The contradiction intelligence report for <strong>{case_title}</strong> has been generated.</p>
    <a href="{download_url}" style="background:#C9A84C;color:white;padding:12px 24px;text-decoration:none;border-radius:6px;">
      Download Report
    </a>
    <p>This download link expires in 24 hours.</p>
    """
    await send_email(to_email, f"Report Ready: {case_title}", html)
