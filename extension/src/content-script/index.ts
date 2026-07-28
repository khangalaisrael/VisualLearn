/**
 * Content script entrypoint.
 *
 * Capture is manual-only (the side panel's "Capture Current Slide"
 * button, see sidepanel/tabs/AskTab.tsx, sends CAPTURE_REQUEST directly
 * via chrome.runtime). An earlier version of this file auto-triggered
 * captures on DOM-mutation bursts, which fired on ordinary page churn,
 * not just slide changes, silently burning analysis calls while browsing
 * any page. Removed by direct request rather than tuned.
 *
 * This entrypoint is still declared in manifest.json (injected on every
 * page) for the overlay renderer (docs/ROADMAP.md Milestone 3:
 * ObjectOverlay/HoverOutline/SelectionBox/FloatingToolbar), which isn't
 * built yet and will need page-level DOM access to draw bounding boxes.
 */
