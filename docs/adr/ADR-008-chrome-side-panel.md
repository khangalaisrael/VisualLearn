# ADR-008: Chrome Side Panel API for the Sidebar (Not an Injected iframe)

## Status
Accepted

## Context
The extension needs a persistent sidebar UI (React + TypeScript + Tailwind) alongside the lecture slide, per the Premium UI Guide's layout ("Never hide the slide," sidebar 350–420px, default 380px, collapsible/resizable, remembers last width) and Manifest V3 constraints.

## Decision
Render the sidebar using Chrome's native `chrome.sidePanel` API rather than injecting a content-script iframe into the host page.

## Rationale
- **Layout guarantee without fighting the host page's CSS.** An injected iframe has to coexist with (and not be clipped, covered, or resized unpredictably by) whatever CSS the host lecture page or slide viewer uses. The side panel API renders in its own browser-native UI surface, guaranteeing the "never hide/cover the slide" requirement holds regardless of host-page markup.
- **Persistence across navigation and matches user expectations for MV3 extensions.** The side panel persists as the user navigates within a tab in a way that's more robust than re-injecting and rehydrating an iframe on every page load, and it's the platform-recommended pattern for exactly this "persistent companion UI" use case under Manifest V3.
- **Simpler resize/collapse behavior.** Width, resizing, and remembering the last width (per the UI guide) are native side-panel behaviors rather than something the content script must implement and defend against host-page interference.

## Alternatives Considered
- **Injected iframe sidebar.** Works on some pages, but is fragile against host-page CSS (z-index wars, unexpected clipping, host-page scripts that manipulate the DOM), and requires re-implementing resize/collapse/width-persistence that the side panel API provides natively. Rejected as higher long-term maintenance cost for no compensating benefit.
- **Separate popup window.** Would avoid host-page interference entirely, but breaks the "slide and sidebar visible together" core UX requirement — a popup is not persistently docked alongside the tab content.

## Consequences
- The bounding-box overlay layer (`ObjectOverlay`, etc.) still must be a content-script injection over the slide itself, since overlays need to sit directly on top of the slide's DOM/canvas — only the sidebar chrome moves to the side panel API. This split (overlay via content script, chat/tabs UI via side panel) is reflected in the two-part extension architecture in [ARCHITECTURE.md](../ARCHITECTURE.md) §3.
- Side panel availability depends on a reasonably current Chrome version (API introduced in Chrome 114) — acceptable given the target audience (students/researchers on a maintained Chrome install) but worth a minimum-version check in the extension's manifest.
