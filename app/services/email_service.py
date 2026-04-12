"""
Email Service
─────────────
Handles all outbound email for Find me in the terminal:
  - Welcome email (Vim cheat sheet + Linux commands)
  - Daily Linux command drop
  - Arbitrary broadcast to all active subscribers

Uses aiosmtplib for async SMTP — no blocking the event loop.
"""
from __future__ import annotations

import logging
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from pathlib import Path
from typing import Optional, List

import aiosmtplib
from app.config import get_settings

log      = logging.getLogger(__name__)
settings = get_settings()


# ─────────────────────────────────────────────────────────────────────────────
#  Core send helper
# ─────────────────────────────────────────────────────────────────────────────
async def send_email(
  to_email:     str,
  subject:      str,
  html_content: str,
  text_content: Optional[str] = None,
  attachments:  Optional[List[str]] = None,
) -> tuple[bool, Optional[str]]:
  """Send a single HTML email.

  Returns (True, None) on success or (False, error_message) on failure.
  Supports attaching files by passing a list of file paths in `attachments`.
  """
  # Outer container must be 'mixed' when adding attachments
  msg = MIMEMultipart("mixed")
  msg["Subject"] = subject
  msg["From"] = f"{settings.FROM_NAME} <{settings.FROM_EMAIL}>"
  msg["To"] = to_email
  msg["List-Unsubscribe"] = f"<{settings.APP_URL}/unsubscribe?email={to_email}>"

  # Normalize SMTP host/port and perform basic validation to catch common .env mistakes
  smtp_host = (settings.SMTP_HOST or "").strip()
  smtp_port = settings.SMTP_PORT
  # If user accidentally put host:port in SMTP_HOST (e.g., smtp.gmail.com:587), split it.
  if ":" in smtp_host:
    host_candidate, port_candidate = smtp_host.rsplit(":", 1)
    if port_candidate.isdigit():
      smtp_host = host_candidate
      try:
        smtp_port = int(port_candidate)
      except Exception:
        pass
      log.warning("Parsed SMTP_HOST with port: using host=%s port=%s", smtp_host, smtp_port)
  # Common misconfiguration: SMTP_HOST set to an email address
  if not smtp_host:
    err_msg = "SMTP_HOST is not configured. Set SMTP_HOST to your SMTP server hostname (e.g. smtp.gmail.com)."
    log.error(err_msg)
    return False, err_msg
  if "@" in smtp_host:
    err_msg = (
      f"SMTP_HOST appears to be an email address ('{smtp_host}'). "
      "It should be your SMTP server host (e.g. smtp.gmail.com). Check your .env — you may have swapped SMTP_HOST and SMTP_USER."
    )
    log.error(err_msg)
    return False, err_msg
  # Validate port range
  try:
    smtp_port_int = int(smtp_port)
  except Exception:
    err_msg = f"SMTP_PORT is invalid: {smtp_port}"
    log.error(err_msg)
    return False, err_msg
  if smtp_port_int <= 0 or smtp_port_int > 65535:
    err_msg = f"SMTP_PORT is invalid: {smtp_port_int}"
    log.error(err_msg)
    return False, err_msg
  # DNS resolution quick check
  try:
    import socket
    socket.getaddrinfo(smtp_host, smtp_port_int)
  except Exception as e:
    err_msg = f"DNS resolution failed for SMTP_HOST '{smtp_host}': {e}"
    log.error(err_msg)
    return False, err_msg

  # Alternative part for plain / html
  alt = MIMEMultipart("alternative")
  if text_content:
    alt.attach(MIMEText(text_content, "plain", "utf-8"))
  alt.attach(MIMEText(html_content, "html", "utf-8"))
  msg.attach(alt)

  # Attach any provided files (silently skip missing files, but log)
  if attachments:
    for attach_path in attachments:
      try:
        p = Path(attach_path)
        if not p.exists():
          log.warning("Attachment not found, skipping: %s", attach_path)
          continue
        with p.open("rb") as f:
          part = MIMEApplication(f.read(), Name=p.name)
          part.add_header("Content-Disposition", "attachment", filename=p.name)
          msg.attach(part)
      except Exception as exc:
        log.warning("Failed to attach %s: %s", attach_path, exc)

  try:
    await aiosmtplib.send(
      msg,
      hostname=smtp_host,
      port=smtp_port_int,
      username=settings.SMTP_USER,
      password=settings.SMTP_PASSWORD,
      start_tls=True,
    )
    log.info("✅ Email sent → %s | %s", to_email, subject)
    return True, None
  except Exception as exc:
    log.error("❌ Email failed → %s | %s | %s", to_email, subject, exc, exc_info=True)

    # If running in DEBUG, persist the email to an outbox for inspection
    if settings.DEBUG:
      try:
        outdir = Path.cwd() / "outbox"
        outdir.mkdir(exist_ok=True)
        safe_name = f"{datetime.utcnow().strftime('%Y%m%dT%H%M%S')}_{to_email.replace('@', '_at_')}"
        html_file = outdir / f"{safe_name}.html"
        html_file.write_text(html_content, encoding="utf-8")
        log.info("Wrote failed email to outbox: %s", html_file)
      except Exception:
        log.exception("Failed to write outbox file")

    return False, str(exc)


# ─────────────────────────────────────────────────────────────────────────────
#  Shared CSS / HTML skeleton used across all email templates
# ─────────────────────────────────────────────────────────────────────────────
_BASE_CSS = """
  @import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;600;700;800&family=JetBrains+Mono:wght@400;700&display=swap');
  *  { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: #121417; font-family: 'Manrope', sans-serif; color: #E8EDF0; -webkit-font-smoothing: antialiased; }
  .wrap     { max-width: 600px; margin: 0 auto; padding: 40px 24px; }
  .header   { padding-bottom: 24px; margin-bottom: 32px; border-bottom: 1px solid #2A2F34; }
  .logo     { font-size: 18px; font-weight: 800; color: #D8F3DC; letter-spacing: -0.02em; }
  .edition  { font-family: 'JetBrains Mono', monospace; font-size: 10px; color: #5A6370;
              letter-spacing: 3px; text-transform: uppercase; margin-top: 4px; }
  h1        { font-size: 28px; font-weight: 800; letter-spacing: -0.02em; color: #E8EDF0;
              margin: 0 0 14px; line-height: 1.1; }
  .accent   { color: #D8F3DC; }
  p         { font-size: 14px; color: #95A5A6; line-height: 1.75; margin: 0 0 16px; }
  .section  { background: #1D2023; border: 1px solid #2A2F34; border-radius: 10px;
              padding: 26px; margin: 26px 0; }
  .sec-title{ font-family: 'JetBrains Mono', monospace; font-size: 10px; color: #D8F3DC;
              letter-spacing: 3px; text-transform: uppercase; margin: 0 0 18px; }
  .cmd-row  { display: flex; align-items: flex-start; gap: 14px; padding: 10px 0;
              border-bottom: 1px solid #2A2F34; }
  .cmd-row:last-child { border-bottom: none; }
  .cmd      { font-family: 'JetBrains Mono', monospace; background: #0A0C0F; color: #D8F3DC;
              font-size: 12px; padding: 4px 10px; border-radius: 4px; white-space: nowrap;
              border: 1px solid #183824; min-width: 140px; }
  .cmd-desc { font-size: 13px; color: #95A5A6; line-height: 1.55; padding-top: 3px; }
  .code-block { background: #0A0C0F; border: 1px solid #2A2F34; border-left: 3px solid #D8F3DC;
                border-radius: 0 6px 6px 0; padding: 16px; font-family: 'JetBrains Mono', monospace;
                font-size: 12px; color: #95A5A6; line-height: 1.8; margin: 16px 0; }
  .cta      { display: inline-block; background: #D8F3DC; color: #0A2E18; font-weight: 700;
              font-size: 14px; padding: 14px 32px; border-radius: 8px; text-decoration: none;
              margin: 20px 0; letter-spacing: -0.01em; }
  .tip-box  { background: #183824; border: 1px solid #D8F3DC22; border-radius: 8px;
              padding: 18px 20px; margin: 20px 0; }
  .tip-label{ font-family: 'JetBrains Mono', monospace; font-size: 10px; color: #D8F3DC;
              letter-spacing: 3px; text-transform: uppercase; margin-bottom: 8px; }
  .tip-text { font-size: 13px; color: #95A5A6; line-height: 1.65; }
  .footer   { text-align: center; font-size: 11px; color: #2A2F34; padding-top: 28px;
              border-top: 1px solid #2A2F34; margin-top: 36px;
              font-family: 'JetBrains Mono', monospace; line-height: 1.8; }
  .footer a { color: #3a4a3a; text-decoration: none; }
"""


def _shell(cmd: str) -> str:
    """Wrap a command in the standard shell prompt styling."""
    return f'<span style="color:#D8F3DC">~$</span>&nbsp;{cmd}'


# ─────────────────────────────────────────────────────────────────────────────
#  Welcome Email  (sent immediately on subscribe)
# ─────────────────────────────────────────────────────────────────────────────
def build_welcome_email(email: str, unsubscribe_token: str) -> tuple[str, str, list[str]]:
  """Returns (subject, html_body, attachments)

  Automatically includes the PDF Vim guide if present at `app/docs/vim_complete_guide_v2.pdf`.
  """
    unsubscribe_url = f"{settings.APP_URL}/unsubscribe?token={unsubscribe_token}"
    today           = datetime.now().strftime("%d %b %Y").upper()

    html = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"/>
<style>{_BASE_CSS}</style></head>
<body><div class="wrap">

  <div class="header">
    <div class="logo">Find me in the terminal</div>
    <div class="edition">// WELCOME EDITION &mdash; {today}</div>
  </div>

  <h1>You&rsquo;re in, <span class="accent">operator.</span></h1>
  <p>Welcome to <strong>Find me in the terminal</strong> &mdash; daily Linux commands,
  Vim tricks, and terminal productivity drops straight to your inbox.
  Here&rsquo;s your welcome pack to get you dangerous at the command line.</p>

  <!-- VIM CHEAT SHEET -->
  <div class="section">
    <div class="sec-title">// Vim Essentials &mdash; Survive &amp; Thrive</div>
    <div class="cmd-row"><span class="cmd">i / Esc</span><div class="cmd-desc">Enter Insert mode to type text / return to Normal mode. <strong>Always</strong> press Esc before any command.</div></div>
    <div class="cmd-row"><span class="cmd">:wq</span><div class="cmd-desc">Write (save) the file and quit. The most important command &mdash; this is how you escape Vim.</div></div>
    <div class="cmd-row"><span class="cmd">:q!</span><div class="cmd-desc">Force quit without saving. Your emergency exit when everything goes wrong.</div></div>
    <div class="cmd-row"><span class="cmd">gg / G</span><div class="cmd-desc">Jump to the very first / very last line of the file instantly.</div></div>
    <div class="cmd-row"><span class="cmd">dd / yy</span><div class="cmd-desc">Delete (cut) the current line / Yank (copy) the current line.</div></div>
    <div class="cmd-row"><span class="cmd">ciw</span><div class="cmd-desc">Change Inner Word &mdash; delete the word under cursor, enter insert mode. One of Vim&rsquo;s most powerful commands.</div></div>
    <div class="cmd-row"><span class="cmd">:%s/old/new/g</span><div class="cmd-desc">Find and replace every occurrence of &ldquo;old&rdquo; with &ldquo;new&rdquo; across the entire file.</div></div>
    <div class="cmd-row"><span class="cmd">Ctrl+v → I</span><div class="cmd-desc">Block visual mode &rarr; Insert: edit multiple lines simultaneously (great for bulk commenting code).</div></div>
  </div>

  <!-- LINUX TERMINAL COMMANDS -->
  <div class="section">
    <div class="sec-title">// Terminal Navigation &mdash; Core Commands</div>
    <div class="cmd-row"><span class="cmd">ls -lah</span><div class="cmd-desc">List directory contents with human-readable sizes, hidden files, and permissions. Know this by heart.</div></div>
    <div class="cmd-row"><span class="cmd">cd -</span><div class="cmd-desc">Return to the PREVIOUS directory. Like a browser back button for your terminal. Massively underused.</div></div>
    <div class="cmd-row"><span class="cmd">Ctrl+R</span><div class="cmd-desc">Reverse-search command history. Start typing to find any command you&rsquo;ve run before.</div></div>
    <div class="cmd-row"><span class="cmd">grep -r "text" .</span><div class="cmd-desc">Recursively search for text in all files in current directory. Essential for navigating codebases.</div></div>
    <div class="cmd-row"><span class="cmd">tail -f log.txt</span><div class="cmd-desc">Follow a log file in real-time. Indispensable for monitoring servers and debugging live systems.</div></div>
    <div class="cmd-row"><span class="cmd">chmod +x script.sh</span><div class="cmd-desc">Make a script executable. Required before running any shell script you create.</div></div>
    <div class="cmd-row"><span class="cmd">ps aux | grep app</span><div class="cmd-desc">Find a running process by name. Pipe ps output through grep to find exactly what you need.</div></div>
  </div>

  <div class="code-block">
    <span style="color:#D8F3DC">~$</span> echo "More drops incoming every morning..."<br/>
    Daily Linux command drops, Vim tricks, and deep dives &mdash; every day at 06:00 UTC.
  </div>

  <a class="cta" href="{settings.APP_URL}">Visit the Archive &rarr;</a>

  <div class="footer">
    Find me in the terminal &middot; You subscribed as {email}<br/>
    <a href="{unsubscribe_url}">Unsubscribe</a> &middot;
    <a href="{settings.APP_URL}/privacy">Privacy Policy</a>
  </div>

</div></body></html>"""

    # Attach the full Vim guide PDF if it exists in app/docs/
    docs_file = Path(__file__).resolve().parents[1] / "docs" / "vim_complete_guide_v2.pdf"
    attachments: list[str] = []
    if docs_file.exists():
      attachments.append(str(docs_file))

    return (
      "⚡ Welcome to Find me in the terminal — Your Vim and Linux Cheat Sheet",
      html,
      attachments,
    )


# ─────────────────────────────────────────────────────────────────────────────
#  Daily Command Drop Email
# ─────────────────────────────────────────────────────────────────────────────
def build_daily_drop_email(
    command:          str,
    description:      str,
    example:          str,
    tip:              str,
    unsubscribe_token: str,
) -> tuple[str, str]:
    """Returns (subject, html_body)"""
    unsubscribe_url = f"{settings.APP_URL}/unsubscribe?token={unsubscribe_token}"
    day             = datetime.now().strftime("%A, %d %B %Y").upper()
    cmd_name        = command.split()[0]

    html = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"/>
<style>{_BASE_CSS}
  .cmd-hero {{ font-family:'JetBrains Mono',monospace; font-size:24px; font-weight:700;
               color:#D8F3DC; padding:20px 0 4px; letter-spacing:-0.01em; }}
</style></head>
<body><div class="wrap">

  <div class="header">
    <div class="logo">Find me in the terminal</div>
    <div class="edition">// DAILY DROP &mdash; {day}</div>
  </div>

  <h1>Today&rsquo;s Command</h1>

  <div class="section">
    <div class="cmd-hero">$ {command}</div>
    <p style="margin-top:14px">{description}</p>
  </div>

  <div class="sec-title" style="margin:24px 0 10px">// Real-World Example</div>
  <div class="code-block">{example}</div>

  <div class="tip-box">
    <div class="tip-label">// Pro Tip</div>
    <div class="tip-text">{tip}</div>
  </div>

  <a class="cta" href="{settings.APP_URL}">Read More in the Archive &rarr;</a>

  <div class="footer">
    Find me in the terminal &mdash; Daily Drop<br/>
    <a href="{unsubscribe_url}">Unsubscribe</a> &middot;
    <a href="{settings.APP_URL}/privacy">Privacy Policy</a>
  </div>

</div></body></html>"""

    return (
        f"⚡ Daily Drop: {cmd_name} — Find me in the terminal",
        html,
    )


# ─────────────────────────────────────────────────────────────────────────────
#  Generic Broadcast Email (custom HTML from admin)
# ─────────────────────────────────────────────────────────────────────────────
def build_broadcast_email(
    subject:          str,
    html_body:        str,
    unsubscribe_token: str,
) -> tuple[str, str]:
    """Wraps arbitrary HTML in the standard header/footer shell."""
    unsubscribe_url = f"{settings.APP_URL}/unsubscribe?token={unsubscribe_token}"

    html = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"/>
<style>{_BASE_CSS}</style></head>
<body><div class="wrap">

  <div class="header">
    <div class="logo">Find me in the terminal</div>
    <div class="edition">// {datetime.now().strftime("%d %b %Y").upper()}</div>
  </div>

  {html_body}

  <div class="footer">
    Find me in the terminal<br/>
    <a href="{unsubscribe_url}">Unsubscribe</a> &middot;
    <a href="{settings.APP_URL}/privacy">Privacy Policy</a>
  </div>

</div></body></html>"""

    return subject, html
