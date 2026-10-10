"""GET / — the public home page at the site's address.

Plain HTML with no scripts and no tracking. It is also what Google's consent
screen and the Chrome Web Store listing point to as the product's home page.
Numbers (daily limit, retention) come from the settings so the page never
disagrees with what the server actually enforces.
"""

from html import escape

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from app.core.config import get_settings

router = APIRouter(tags=["landing"])

_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>VisionLearn AI — understand any lecture slide</title>
<meta name="description" content="A Chrome extension that reads the slide on your screen — equations, diagrams, code — and explains it. Ask follow-up questions about exactly what you see.">
<meta property="og:title" content="VisionLearn AI">
<meta property="og:description" content="Understand any lecture slide: equations, diagrams and code, explained from what's on your screen.">
<meta property="og:type" content="website">
<style>
  :root { --bg:#ffffff; --text:#1e293b; --muted:#64748b; --line:#e2e8f0; --accent:#4f46e5; --accent-soft:#eef2ff; --soft:#f8fafc; --on-accent:#ffffff; }
  @media (prefers-color-scheme: dark) {
    :root { --bg:#0f172a; --text:#e2e8f0; --muted:#94a3b8; --line:#1e293b; --accent:#818cf8; --accent-soft:#1e1b4b; --soft:#111c33; --on-accent:#0f172a; }
  }
  * { box-sizing: border-box; }
  body { margin:0; background:var(--bg); color:var(--text); font:16px/1.65 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif; }
  main { max-width: 880px; margin: 0 auto; padding: 0 20px 64px; }
  header.top { display:flex; align-items:center; justify-content:space-between; padding: 22px 0; }
  .brand { font-weight: 700; letter-spacing: -0.01em; }
  .brand span { color: var(--accent); }
  nav a { color: var(--muted); text-decoration: none; font-size: 0.95rem; margin-left: 18px; }
  nav a:hover { color: var(--text); }
  .hero { padding: 48px 0 40px; }
  .pill { display:inline-block; background:var(--accent-soft); color:var(--accent); font-size:0.8rem; font-weight:600; padding:4px 12px; border-radius:999px; }
  h1 { font-size: clamp(2rem, 6vw, 3.1rem); line-height: 1.1; letter-spacing: -0.02em; margin: 18px 0 14px; }
  .lead { font-size: 1.15rem; color: var(--muted); max-width: 620px; margin: 0; }
  .cta { margin-top: 28px; display:flex; flex-wrap:wrap; gap:12px; align-items:center; }
  .btn { display:inline-block; background:var(--accent); color:var(--on-accent); text-decoration:none; font-weight:600; padding:12px 22px; border-radius:12px; }
  .btn.ghost { background:transparent; color:var(--text); border:1px solid var(--line); }
  .note { color: var(--muted); font-size: 0.9rem; }
  h2 { font-size: 1.35rem; letter-spacing: -0.01em; margin: 56px 0 16px; }
  .grid { display:grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); gap: 14px; }
  .card { background:var(--soft); border:1px solid var(--line); border-radius:16px; padding:18px 20px; }
  .card h3 { margin: 0 0 6px; font-size: 1rem; }
  .card p { margin: 0; color: var(--muted); font-size: 0.95rem; }
  .step { display:flex; gap:14px; align-items:flex-start; margin: 14px 0; }
  .num { flex:none; width:30px; height:30px; border-radius:50%; background:var(--accent-soft); color:var(--accent); font-weight:700; display:flex; align-items:center; justify-content:center; }
  kbd { background:var(--soft); border:1px solid var(--line); border-bottom-width:2px; border-radius:6px; padding:1px 7px; font-size:0.85em; }
  .box { background:var(--accent-soft); border-radius:16px; padding:22px 24px; }
  .box p { margin: 6px 0; }
  footer { margin-top: 64px; padding-top: 22px; border-top: 1px solid var(--line); color: var(--muted); font-size: 0.9rem; display:flex; flex-wrap:wrap; gap:8px 20px; }
  footer a, .box a { color: var(--accent); }
</style>
</head>
<body>
<main>
<header class="top">
  <div class="brand">Vision<span>Learn</span> AI</div>
  <nav><a href="#how">How it works</a><a href="#get">Get it</a><a href="/privacy">Privacy</a></nav>
</header>

<section class="hero">
  <span class="pill">A small student project</span>
  <h1>Understand any lecture slide.</h1>
  <p class="lead">VisionLearn reads the slide on your screen — equations, diagrams, graphs and code — explains it, and lets you ask follow-up questions about exactly what you're looking at.</p>
  <div class="cta">
    <a class="btn" href="#get">Get early access</a>
    <span class="note">Free for students · Chrome extension</span>
  </div>
</section>

<section id="how">
  <h2>How it works</h2>
  <div class="step"><div class="num">1</div><div><strong>Open a lecture slide</strong> in a Chrome tab: a PDF, a Google Slides deck, your university's lecture site.</div></div>
  <div class="step"><div class="num">2</div><div><strong>Press Capture</strong> in the side panel, or <kbd>Alt</kbd>+<kbd>Shift</kbd>+<kbd>S</kbd>. Nothing is read until you do.</div></div>
  <div class="step"><div class="num">3</div><div><strong>Ask anything about it.</strong> "Why is this n log n?" "Walk me through the graph." Answers are grounded in what's on screen.</div></div>
</section>

<section>
  <h2>What it understands</h2>
  <div class="grid">
    <div class="card"><h3>Equations</h3><p>Read and typeset properly, with plain-language explanations alongside.</p></div>
    <div class="card"><h3>Diagrams and graphs</h3><p>Nodes, edges and structure picked out, so you can ask about a single figure.</p></div>
    <div class="card"><h3>Code and tables</h3><p>Syntax-highlighted code and tidy tables instead of a blob of text.</p></div>
    <div class="card"><h3>Your lectures, organised</h3><p>Captures are grouped by lecture, with thumbnails and the chats you had about each.</p></div>
  </div>
</section>

<section>
  <h2>Built to be fair and private</h2>
  <div class="grid">
    <div class="card"><h3>Free, with a daily limit</h3><p>__DAILY__ captures a day and __MONTHLY__ a month, so it stays free for everyone.</p></div>
    <div class="card"><h3>Only when you press Capture</h3><p>No browsing history, no background reading, no ads or trackers.</p></div>
    <div class="card"><h3>Your data, your control</h3><p>History is kept __DAYS__ days. Thumbnails never leave your device. Delete anything, or your whole account, at any time.</p></div>
  </div>
</section>

<section id="get">
  <h2>Get it</h2>
  <div class="box">
    <p><strong>The Chrome Web Store listing is coming soon.</strong></p>
    <p>VisionLearn is being shared with a few students first. Want to try it? Email <a href="mailto:__EMAIL__">__EMAIL__</a> and we'll send you the extension and a two-minute setup guide.</p>
    <p class="note">Sign in with Google is optional, and only needed to keep your history across devices.</p>
  </div>
</section>

<footer>
  <span>&copy; VisionLearn AI</span>
  <a href="/privacy">Privacy policy</a>
  <a href="mailto:__EMAIL__">__EMAIL__</a>
</footer>
</main>
</body>
</html>
"""


def render_landing() -> str:
    settings = get_settings()
    email = escape(settings.privacy_contact_email or "visionlearn.support@gmail.com")
    return (
        _PAGE.replace("__DAILY__", str(settings.rate_limit_captures_per_day))
        .replace("__MONTHLY__", str(settings.rate_limit_captures_per_month))
        .replace("__DAYS__", str(settings.chat_retention_days))
        .replace("__EMAIL__", email)
    )


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
async def landing() -> HTMLResponse:
    return HTMLResponse(render_landing())
