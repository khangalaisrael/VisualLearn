# Sharing the extension (until the Chrome Web Store listing exists)

The site's `/install` page offers a downloadable zip and the steps to add it to Chrome.
The zip is **not** in this repository and must never be: the build contains the server's
shared API key (`VITE_LOCAL_API_KEY`), read from a key file outside the repo.

## Publish a new version

1. Build the zip (reads the key from `~\.visionlearn_key`, never prints it):

   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts\make-friends-zip.ps1
   ```

   It writes `Desktop\VisionLearn-extension.zip`.

2. Upload it as a **GitHub Release asset**: repository, Releases, "Draft a new release",
   tag (for example `v0.1.1`), attach the zip, publish. Copy the asset's download link
   (it ends in `/VisionLearn-extension.zip`).

3. In Render, set `EXTENSION_DOWNLOAD_URL` to that link and save. The home page and `/install`
   then show the download button (only `https://` links are ever shown).

Friends update by downloading the new zip, replacing the folder's contents and pressing the
reload arrow on the extension at `chrome://extensions`.

## Why this is safe enough

The key ships inside every copy of the extension (a Web Store install too), so a public zip
exposes nothing new. The real protection is the per-IP and per-account daily limits and the
global daily cap on the server. If the key is ever abused, rotate `LOCAL_API_KEY` in Render
and publish a new zip.

The extension's ID is fixed by the `key` in `extension/manifest.json`, so Google sign-in works
for unpacked copies too.
