"""GET /privacy — the public privacy policy the Chrome Web Store listing
links to. Served by the backend (no login, no API key) so it is always the
version that matches the deployed behavior. Every statement here describes
what the code actually does; when behavior changes, change this page in the
same commit.
"""

from html import escape

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from app.core.config import get_settings

router = APIRouter(tags=["privacy"])

LAST_UPDATED = "10 October 2026"

_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>VisionLearn AI — Privacy Policy</title>
<style>
  :root { --bg:#ffffff; --text:#1e293b; --muted:#64748b; --line:#e2e8f0; --accent:#4f46e5; --soft:#f8fafc; }
  @media (prefers-color-scheme: dark) {
    :root { --bg:#0f172a; --text:#e2e8f0; --muted:#94a3b8; --line:#1e293b; --accent:#818cf8; --soft:#111c33; }
  }
  * { box-sizing: border-box; }
  body { margin:0; background:var(--bg); color:var(--text); font:16px/1.65 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif; }
  main { max-width: 720px; margin: 0 auto; padding: 40px 20px 80px; }
  h1 { font-size: 1.75rem; margin: 0 0 4px; letter-spacing: -0.01em; }
  h2 { font-size: 1.15rem; margin: 36px 0 8px; }
  p, li { color: var(--text); }
  .muted { color: var(--muted); font-size: 0.9rem; }
  ul { padding-left: 1.25rem; }
  li { margin: 6px 0; }
  table { width:100%; border-collapse: collapse; font-size: 0.95rem; margin: 8px 0; }
  th, td { text-align:left; padding: 8px 10px; border-bottom: 1px solid var(--line); vertical-align: top; }
  th { color: var(--muted); font-weight: 600; font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.04em; }
  .box { background: var(--soft); border: 1px solid var(--line); border-radius: 12px; padding: 14px 16px; }
  a { color: var(--accent); }
</style>
</head>
<body>
<main>
<h1>Privacy Policy</h1>
<p class="muted">VisionLearn AI browser extension &middot; Last updated __UPDATED__</p>

<div class="box">
<p><strong>In short:</strong> VisionLearn only looks at your screen when you press <em>Capture</em>. It sends that screenshot to an AI service to read the slide, keeps the extracted text and your chat for __DAYS__ days, never sells or shares your data for advertising, and lets you delete everything yourself at any time.</p>
</div>

<h2>What VisionLearn does</h2>
<p>VisionLearn has one purpose: to help you understand lecture slides. When you press <em>Capture</em>, it takes a screenshot of the visible part of your current tab, reads what is on it (text, equations, diagrams, code), and lets you ask questions about it.</p>

<h2>What we collect, and why</h2>
<table>
<tr><th>Data</th><th>Why</th></tr>
<tr><td><strong>Screenshot of your current tab</strong>, only when you press Capture</td><td>To read the slide. The image is sent to our server and on to the AI provider, then discarded. <strong>We do not store the image</strong>; we keep only a one-way fingerprint (hash) so an identical slide isn't analysed twice.</td></tr>
<tr><td><strong>What the slide contains</strong> (extracted text, equations, summaries)</td><td>To show you the result and to answer your questions about it. This may include whatever appears on the slide, including course material.</td></tr>
<tr><td><strong>Your questions and the answers</strong></td><td>To hold the conversation and, if you are signed in, to show it again in <em>Recent chats</em>.</td></tr>
<tr><td><strong>Google account email and Google's account identifier</strong>, only if you sign in</td><td>To keep your chats private to you and available across devices. We receive nothing else from your Google account.</td></tr>
<tr><td><strong>IP address</strong></td><td>To limit how many captures one person can make per day and per month (kept 31 days), and it appears in our hosting provider's standard request logs.</td></tr>
</table>
<p>Signing in is optional. VisionLearn does not read your browsing history, the content of pages other than the screenshot you capture, or anything while you are not pressing Capture. It has no analytics, advertising or tracking code.</p>

<h2>Who processes your data</h2>
<ul>
<li><strong>Anthropic</strong> — the AI service that reads captured slides and writes answers. Your screenshot, the extracted content and your questions are sent to it. Its use of that data is governed by Anthropic's own terms and privacy policy.</li>
<li><strong>Google</strong> — only for sign-in.</li>
<li><strong>Render</strong> hosts the server and <strong>Neon</strong> hosts the database.</li>
</ul>
<p>We do not sell your data, use it for advertising, or share it with anyone else, and we use it only to provide the features described here.</p>

<h2>How long we keep it</h2>
<ul>
<li>Chats and the slide content behind them: deleted <strong>__DAYS__ days</strong> after your last message in that chat. Captures made without a chat are deleted __DAYS__ days after capture.</li>
<li>Sign-in sessions: expire after 30 days.</li>
<li>Usage counters used to enforce the daily and monthly limits (including the IP address for people who are not signed in): 31 days.</li>
<li>Shared analysis results (keyed by the slide fingerprint, not linked to you): __DAYS__ days.</li>
<li>Hosting request logs follow Render's own log retention.</li>
</ul>

<h2>Your choices</h2>
<ul>
<li><strong>Delete a chat</strong> from the <em>Recent chats</em> screen at any time.</li>
<li><strong>Delete your account and all your data</strong> from <em>Settings</em> in the extension. This is immediate and cannot be undone.</li>
<li><strong>Use it without signing in.</strong> Without an account there are no saved chats, and anonymous captures expire on the schedule above.</li>
<li>Uninstalling the extension removes everything stored in your browser.</li>
</ul>

<h2>Security</h2>
<p>All traffic uses HTTPS. Access to the database is restricted to the server. No system is perfectly secure, so please don't capture slides containing information you wouldn't want processed by an AI service.</p>

<h2>Children</h2>
<p>VisionLearn is not directed at children under 13 and we do not knowingly collect their data.</p>

<h2>Changes</h2>
<p>If we change how data is handled, we will update this page and the date above, and tell you in the extension before the change takes effect.</p>

<h2>Contact</h2>
<p>__CONTACT__</p>
</main>
</body>
</html>
"""


def render_policy() -> str:
    settings = get_settings()
    email = settings.privacy_contact_email
    contact = (
        f'Questions or deletion requests: <a href="mailto:{escape(email)}">{escape(email)}</a>.'
        if email
        else "Questions or deletion requests: use the support contact on the VisionLearn AI Chrome Web Store listing."
    )
    return (
        _PAGE.replace("__UPDATED__", LAST_UPDATED)
        .replace("__DAYS__", str(settings.chat_retention_days))
        .replace("__CONTACT__", contact)
    )


@router.get("/privacy", response_class=HTMLResponse, include_in_schema=False)
async def privacy_policy() -> HTMLResponse:
    return HTMLResponse(render_policy())
