"""GET / (home page) and GET /install (how to add the extension).

Plain HTML with no scripts and no tracking. The home page is also what
Google's consent screen and the Chrome Web Store listing point to as the
product's home. Numbers (daily limit, retention) come from the settings so
the page never disagrees with what the server enforces.

The extension zip itself is hosted elsewhere (a GitHub Release, for example)
and linked through EXTENSION_DOWNLOAD_URL: the build contains the shared API
key, so it is never committed to the repository or bundled into the server.
"""

from html import escape

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from app.core.config import get_settings

router = APIRouter(tags=["landing"])

DEFAULT_CONTACT = "visionlearn.support@gmail.com"

_STYLE = """
  :root { --bg:#ffffff; --text:#1e293b; --muted:#64748b; --line:#e2e8f0; --accent:#4f46e5; --accent-soft:#eef2ff; --soft:#f8fafc; --on-accent:#ffffff; }
  @media (prefers-color-scheme: dark) {
    :root { --bg:#0f172a; --text:#e2e8f0; --muted:#94a3b8; --line:#1e293b; --accent:#818cf8; --accent-soft:#1e1b4b; --soft:#111c33; --on-accent:#0f172a; }
  }
  * { box-sizing: border-box; }
  body { margin:0; background:var(--bg); color:var(--text); font:16px/1.65 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif; }
  main { max-width: 880px; margin: 0 auto; padding: 0 20px 64px; }
  header.top { display:flex; align-items:center; justify-content:space-between; padding: 22px 0; }
  .brand { font-weight: 700; letter-spacing: -0.01em; color: var(--text); text-decoration: none; }
  .brand span { color: var(--accent); }
  nav a { color: var(--muted); text-decoration: none; font-size: 0.95rem; margin-left: 18px; }
  nav a:hover { color: var(--text); }
  .hero { padding: 48px 0 40px; }
  .pill { display:inline-block; background:var(--accent-soft); color:var(--accent); font-size:0.8rem; font-weight:600; padding:4px 12px; border-radius:999px; }
  h1 { font-size: clamp(2rem, 6vw, 3.1rem); line-height: 1.1; letter-spacing: -0.02em; margin: 18px 0 14px; }
  .lead { font-size: 1.15rem; color: var(--muted); max-width: 620px; margin: 0; }
  .cta { margin-top: 28px; display:flex; flex-wrap:wrap; gap:12px; align-items:center; }
  .btn { display:inline-block; background:var(--accent); color:var(--on-accent); text-decoration:none; font-weight:600; padding:12px 22px; border-radius:12px; }
  .note { color: var(--muted); font-size: 0.9rem; }
  h2 { font-size: 1.35rem; letter-spacing: -0.01em; margin: 56px 0 16px; }
  .grid { display:grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); gap: 14px; }
  .card { background:var(--soft); border:1px solid var(--line); border-radius:16px; padding:18px 20px; }
  .card h3 { margin: 0 0 6px; font-size: 1rem; }
  .card p { margin: 0; color: var(--muted); font-size: 0.95rem; }
  .step { display:flex; gap:14px; align-items:flex-start; margin: 16px 0; }
  .num { flex:none; width:30px; height:30px; border-radius:50%; background:var(--accent-soft); color:var(--accent); font-weight:700; display:flex; align-items:center; justify-content:center; }
  kbd, code { background:var(--soft); border:1px solid var(--line); border-radius:6px; padding:1px 7px; font-size:0.88em; }
  kbd { border-bottom-width:2px; }
  .box { background:var(--accent-soft); border-radius:16px; padding:22px 24px; }
  .box p { margin: 6px 0; }
  footer { margin-top: 64px; padding-top: 22px; border-top: 1px solid var(--line); color: var(--muted); font-size: 0.9rem; display:flex; flex-wrap:wrap; gap:8px 20px; }
  footer a, .box a, .step a { color: var(--accent); }
"""

_HEAD = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<meta name="description" content="A Chrome extension that reads the slide on your screen — equations, diagrams, code — and explains it. Ask follow-up questions about exactly what you see.">
<meta property="og:title" content="VisionLearn AI">
<meta property="og:description" content="Understand any lecture slide: equations, diagrams and code, explained from what's on your screen.">
<meta property="og:type" content="website">
<style>__STYLE__</style>
</head>
<body>
<main>
<header class="top">
  <a class="brand" href="/">Vision<span>Learn</span> AI</a>
  <nav><a href="/#how">How it works</a><a href="/install">Get it</a><a href="/privacy">Privacy</a></nav>
</header>
"""

_FOOT = """
<footer>
  <span>&copy; VisionLearn AI</span>
  <a href="/privacy">Privacy policy</a>
  <a href="mailto:__EMAIL__">__EMAIL__</a>
</footer>
</main>
</body>
</html>
"""

_HOME = """
<section class="hero">
  <span class="pill">A small student project</span>
  <h1>Understand any lecture slide.</h1>
  <p class="lead">VisionLearn reads the slide on your screen — equations, diagrams, graphs and code — explains it, and lets you ask follow-up questions about exactly what you're looking at.</p>
  <div class="cta">
    <a class="btn" href="/install">__CTA__</a>
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
    <div class="card"><h3>Free, with a daily limit</h3><p>__DAILY__ captures a day and __MONTHLY__ a month when you sign in with Google, so it stays free for everyone. Without signing in you get __ANON_DAILY__ a day.</p></div>
    <div class="card"><h3>Only when you press Capture</h3><p>No browsing history, no background reading, no ads or trackers.</p></div>
    <div class="card"><h3>Your data, your control</h3><p>History is kept __DAYS__ days. Thumbnails never leave your device. Delete anything, or your whole account, at any time.</p></div>
  </div>
</section>

<section>
  <h2>Get it</h2>
  <div class="box">__GET_BOX__</div>
</section>
"""

_INSTALL = """
<section class="hero">
  <span class="pill">Chrome, Edge or Brave on a computer</span>
  <h1>Add VisionLearn to Chrome</h1>
  <p class="lead">It takes about two minutes. The extension isn't in the Chrome Web Store yet, so you add it by hand once.</p>
  __DOWNLOAD__
</section>

<section>
  <h2>Steps</h2>
  <div class="step"><div class="num">1</div><div><strong>Download the zip</strong> with the button above, then right-click it and choose <em>Extract All</em> (on a Mac, double-click it). Keep the extracted folder somewhere permanent, such as Documents. Chrome runs the extension from that folder, so don't delete it.</div></div>
  <div class="step"><div class="num">2</div><div><strong>Open the extensions page.</strong> Type <code>chrome://extensions</code> into the address bar and press Enter.</div></div>
  <div class="step"><div class="num">3</div><div><strong>Turn on Developer mode</strong> with the switch in the top-right corner.</div></div>
  <div class="step"><div class="num">4</div><div>Click <strong>Load unpacked</strong> and choose the extracted folder (the one that contains a file called <code>manifest.json</code>).</div></div>
  <div class="step"><div class="num">5</div><div>Click the puzzle-piece icon in Chrome's toolbar and <strong>pin VisionLearn AI</strong>. Click it any time to open the side panel.</div></div>
  <div class="step"><div class="num">6</div><div><strong>Try it:</strong> open a lecture slide, press <em>Capture</em> (or <kbd>Alt</kbd>+<kbd>Shift</kbd>+<kbd>S</kbd>) and ask a question. Signing in with Google is optional; it keeps your history across devices.</div></div>
</section>

<section>
  <h2>Good to know</h2>
  <div class="grid">
    <div class="card"><h3>A startup message</h3><p>Chrome may remind you that a developer-mode extension is running each time it opens. That's normal for now; dismiss it and carry on.</p></div>
    <div class="card"><h3>Updating</h3><p>When there's a new version, download the new zip, replace the folder's contents, then press the circular reload arrow on VisionLearn at <code>chrome://extensions</code>.</p></div>
    <div class="card"><h3>Help</h3><p>Something not working? Email <a href="mailto:__EMAIL__">__EMAIL__</a>.</p></div>
  </div>
</section>
"""


def _clean_download_url(url: str | None) -> str | None:
    """Only a plain https link is ever put on the page (never javascript: or data:)."""
    if url and url.strip().lower().startswith("https://"):
        return escape(url.strip(), quote=True)
    return None


def _fill(template: str) -> str:
    settings = get_settings()
    email = escape(settings.privacy_contact_email or DEFAULT_CONTACT)
    return (
        template.replace("__DAILY__", str(settings.rate_limit_captures_per_day))
        .replace("__ANON_DAILY__", str(settings.rate_limit_anonymous_captures_per_day))
        .replace("__MONTHLY__", str(settings.rate_limit_captures_per_month))
        .replace("__DAYS__", str(settings.chat_retention_days))
        .replace("__EMAIL__", email)
    )


def _page(title: str, body: str) -> str:
    return _fill(_HEAD.replace("__TITLE__", title).replace("__STYLE__", _STYLE) + body + _FOOT)


def render_landing() -> str:
    download = _clean_download_url(get_settings().extension_download_url)
    if download:
        cta = "Add it to Chrome"
        box = (
            "<p><strong>Free to try, no payment needed.</strong></p>"
            '<p>Follow the <a href="/install">two-minute install guide</a> to add it to Chrome.</p>'
            '<p class="note">The Chrome Web Store listing is coming soon. Sign in with Google is optional, '
            "and only needed to keep your history across devices.</p>"
        )
    else:
        cta = "Get early access"
        box = (
            "<p><strong>The Chrome Web Store listing is coming soon.</strong></p>"
            "<p>VisionLearn is being shared with a few students first. Want to try it? Email "
            '<a href="mailto:__EMAIL__">__EMAIL__</a> and we\'ll send you the extension.</p>'
            '<p class="note">Sign in with Google is optional, and only needed to keep your history across devices.</p>'
        )
    return _page("VisionLearn AI — understand any lecture slide", _HOME.replace("__CTA__", cta).replace("__GET_BOX__", box))


def render_install() -> str:
    download = _clean_download_url(get_settings().extension_download_url)
    if download:
        button = (
            f'<div class="cta"><a class="btn" href="{download}" rel="noopener">Download the extension (.zip)</a>'
            '<span class="note">Free · about a minute to set up</span></div>'
        )
    else:
        button = (
            '<div class="box"><p><strong>The download isn\'t public yet.</strong></p>'
            '<p>Email <a href="mailto:__EMAIL__">__EMAIL__</a> and we\'ll send you the file.</p></div>'
        )
    return _page("Add VisionLearn to Chrome", _INSTALL.replace("__DOWNLOAD__", button))


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
async def landing() -> HTMLResponse:
    return HTMLResponse(render_landing())


@router.get("/install", response_class=HTMLResponse, include_in_schema=False)
async def install() -> HTMLResponse:
    return HTMLResponse(render_install())
