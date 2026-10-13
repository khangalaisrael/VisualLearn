# Publishing to the Chrome Web Store

Everything needed to submit VisionLearn AI, in the order you do it. The parts only the
account owner can do are marked **(you)**. The rest is already in this repository.

What is ready:

- A store build: `npm run package:store` in `extension/` (`extension/scripts/package-store.mjs`).
  It removes the manifest's `key` (the store refuses it), checks the zip and never prints the API key.
- Minimal permissions: `activeTab`, `identity`, `sidePanel`, `storage`, plus host access. The unused
  `tabs` and `scripting` permissions were removed, and the owner dashboard is no longer the
  extension's options page, so students never see it in Chrome's menu.
- Store images in [`chrome-web-store/`](chrome-web-store/): five 1280×800 screenshots and the
  440×280 promo tile (see [Images](#7-images)).
- Listing text, permission reasons and privacy answers below, ready to paste.

## 1. Developer account (you)

1. Open the [Chrome Web Store developer dashboard](https://chrome.google.com/webstore/devconsole)
   with the Google account that should own the listing.
2. Pay the one-time **$5** registration fee and verify the contact email.
3. Turn on 2-Step Verification for that Google account (the dashboard requires it to publish).
4. When asked about trader status (an EU requirement), choose **non-trader** while VisionLearn is free.
   Choose trader if you start charging.

## 2. Before you submit, check the server

- **Invite-only must be off.** If `ALLOWED_EMAILS` is set in Render, a reviewer cannot use the
  extension and the item will be rejected as not working. Clear it before submitting.
- **The server must be awake for review.** Render's free plan sleeps after 15 minutes and takes up
  to a minute to wake. The extension says so while it waits, and the test instructions below
  mention it, but a paid instance (or a keep-alive ping) avoids the risk.
- `https://visionlearn.fyi/privacy` must load: it is the privacy policy URL in the listing.

## 3. Build the zip (you, on your computer)

The build holds the server's shared API key, read from a file outside the repository, as
`scripts/make-friends-zip.ps1` already does. Put the key in `~/.visionlearn_key` once
(`C:\Users\<you>\.visionlearn_key` on Windows), then:

```bash
cd extension
npm install
npm run package:store
```

It writes `extension/visionlearn-chrome-web-store-2.0.0.zip`, built for `https://visionlearn.fyi`.
Options: `--backend <https url>`, `--key-file <path>`, `--client-id <id>` (step 5), `--out <path>`.
The zip is ignored by git. Never commit it.

## 4. Create the item and note its ID (you)

1. In the dashboard: **Add new item**, upload the zip.
2. The item gets its own **ID** (32 letters, shown on the item page and in its URL). The store
   chooses it, so it differs from the ID of unpacked copies.
3. Leave the item as a draft for now: Google sign-in needs that ID first (next step).

## 5. Google sign-in for the store ID (you)

Sign-in in the extension uses two OAuth clients in Google Cloud Console (project of client
`156756671908-…`). Both are tied to the extension ID, so the store ID needs its own setup.
Open [Google Cloud Console → APIs & Services → Credentials](https://console.cloud.google.com/apis/credentials):

1. **Create credentials → OAuth client ID**, application type **Chrome Extension**, item ID = the
   store item's ID. Copy the new client ID (it ends in `.apps.googleusercontent.com`).
2. Open the existing **Web application** client
   (`156756671908-4v0eut5p9l3qc5o6pnnnillhp1n3d0d1…`, used for "choose another account") and add
   the authorized redirect URI `https://<store item ID>.chromiumapp.org/`. Keep the existing one
   for unpacked copies.
3. **OAuth consent screen**: publishing status must be **In production**. In "Testing" only listed
   test users can sign in and their sign-in expires after 7 days. The scopes are only `openid`,
   email and profile, so Google's app verification is not needed.
4. Rebuild with the new client and upload it to the same item (**Package → Upload new package**):

   ```bash
   npm run package:store -- --client-id <new client ID>
   ```

The backend needs no change: it checks the Google token with Google, whichever client issued it.

## 6. Store listing (paste)

**Name:** VisionLearn AI

**Summary** (from the manifest, 120 characters):
> Capture a lecture slide to have it explained, then study it with quizzes, flashcards, study guides and code you can run.

**Category:** Education · **Language:** English

**Description:**

```text
VisionLearn turns the lecture slides you are already looking at into something you can ask questions about and study from.

CAPTURE AND ASK
Open a slide in any tab (a PDF, Google Slides, your university's lecture site) and press Capture, or Alt+Shift+S. VisionLearn reads what is on it, including equations, diagrams, graphs, tables and code, and answers your questions about it. Answers stick to what is on the slide and remember the earlier slides of the same lecture.

YOUR LECTURES, SORTED BY TOPIC
Sign in with Google and every capture is filed into a series for its topic, so a term's slides end up organised without any effort. Search them any time.

STUDY TOOLS
Each series can write you:
• multiple-choice quizzes from your own slides, with a tutor that explains any answer you got wrong
• a study guide and a cheat sheet to read before a test
• a deck of flashcards

RUN THE CODE
Code on a slide can be opened in the Code tab, made runnable with one click, edited and run in Python, Haskell, Java or C++. Try expressions as you would in GHCi or the Python shell, and ask the tutor about an error. When you press Run, your program is sent to an online compiler service (Wandbox) and its output is returned; it is not stored by VisionLearn.

NOTES AND OPEN CHAT
Save any answer as a note, write your own, or ask a question that is not about a slide.

PRIVATE AND FAIR
• Nothing is read until you press Capture. No browsing history, no ads, no trackers.
• Slides and chats are deleted after 30 days; notes stay until you delete them.
• Delete anything, or your whole account, at any time.
• Free, with a daily allowance so it stays free for everyone.

Signing in is optional for capturing and asking. Sorting, quizzes, study aids, notes and running code need a Google account.
```

## 7. Images

| Field | File |
|---|---|
| Store icon (128×128) | `extension/public/icons/icon-128.png` |
| Screenshots (1280×800, upload in this order) | `docs/chrome-web-store/screenshots/1-ask.png` … `5-guide.png` |
| Small promo tile (440×280) | `docs/chrome-web-store/promo-small-440x280.png` |

The screenshots are of the real extension and backend from this repository, running in Chromium
against sample lecture slides: capture and ask, the Code tab running a slide's Python, the library
sorted by topic, a quiz with the tutor, and a study guide. The model's answers in them were written
for the sample slides, because the environment that took them had no AI key. You can replace any
of them with screenshots from your own use at 1280×800 or 640×400.

## 8. Privacy practices tab (paste)

**Single purpose:**
> Helps students understand and study lecture slides: it reads the slide the student captures in the current tab, answers questions about it, and turns captured slides into study material.

**Permission justifications:**

| Permission | Justification |
|---|---|
| `activeTab` | Takes a screenshot of the current tab when the student presses Capture or the keyboard shortcut. |
| `sidePanel` | The extension's whole interface is Chrome's side panel, next to the lecture. |
| `storage` | Keeps settings, the sign-in session, code drafts and small thumbnails of captured slides on the user's device. |
| `identity` | Optional Google sign-in, so a student's series, quizzes and notes are private to them and available on their other devices. |
| Host permissions (`<all_urls>`) | Lecture slides live on many different sites (university portals, Google Slides, PDFs, course pages), so the extension must be able to capture whichever tab the student is studying when they press Capture, read that page's title to group captures by lecture, and draw outlines over the parts of the slide it read so the student can ask about one figure. Nothing is read until the student presses Capture. |

**Remote code:** No. All code is in the package; the server only returns data (text and analysis results).

**Data usage**, tick:

- **Personally identifiable information**: the Google account email, when the user signs in.
- **Web history**: the title and address of a page the user captures (without its query string).
- **Website content**: the screenshot of the captured tab and the text read from it.
- **Personal communications**: the questions the user types to the tutor, kept with the chat, and code they ask the tutor about.
- **User activity / website content**: if the dashboard offers a category for text the user types, such as the code they run, tick it too. The program is sent to a third-party compiler (Wandbox) and is not stored by VisionLearn.

If unsure about a box, tick it: declaring too much costs nothing, declaring too little can get the
item removed. Then tick all three certifications (no selling data, no use unrelated to the single
purpose, no use for creditworthiness or lending).

**Privacy policy URL:** `https://visionlearn.fyi/privacy`

## 9. Distribution and test instructions

- **Visibility:** start with **Unlisted** (only people with the link can install it) for your first
  class, then switch to **Public**.
- **Regions:** all. **Price:** free.
- **Test instructions** (Account and test instructions, for the reviewer):

  ```text
  No account is needed for the core feature.
  1. Open any page with lecture-style content, for example a PDF of slides.
  2. Click the VisionLearn toolbar icon to open the side panel, then "Skip for now".
  3. Press Capture, then ask a question about the slide.
  The server may take up to a minute to answer the first request after a quiet period; the panel says so while it waits.
  Signing in with Google unlocks sorting, quizzes, study aids, notes and running code.
  The Code tab runs code from captured slides (or code you type) in Python, Haskell, Java and C++.
  ```

## 10. Submit

Press **Submit for review**. Review usually takes a few days; broad host access can make it longer.
If it is rejected, the email names the policy. The usual causes and fixes:

| Rejection | Fix |
|---|---|
| Functionality not working | Invite-only on, or the server asleep or down during review (step 2). |
| Excessive permissions | Reply with the host-permission justification above. |
| Missing or mismatched privacy disclosures | Re-check step 8 against the privacy policy. |
| Keyword or description issues | Keep the description as written; no lists of other products' names. |

## 11. Updating

1. Raise `version` in `extension/manifest.json` (the store refuses a repeated version).
2. `npm run package:store -- --client-id <store client ID>`.
3. Dashboard → item → **Package → Upload new package**, then submit. Installed copies update automatically.

After the listing is public, the website's home and install pages still describe the zip download.
They are worth pointing at the store listing instead.
