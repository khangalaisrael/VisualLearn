/**
 * ObjectOverlay / HoverOutline / SelectionBox / FloatingToolbar
 * (VisionLearn_Premium_UI_Guide.md "Figure UX": hover -> blue outline,
 * click -> selection; "Never cover the slide" under Responsive Rules).
 *
 * Renders one outline box per detected object, positioned over the actual
 * slide content on the page, so the student can click a specific figure
 * to ask about it in Figure mode instead of the whole slide.
 *
 * Positioning is viewport-relative: capture uses
 * chrome.tabs.captureVisibleTab (the visible viewport, not a specific DOM
 * element — see service-worker/index.ts), so each object's 0-1 normalized
 * bounding_box maps directly to `x * window.innerWidth` /
 * `y * window.innerHeight` px, valid only until the page scrolls or
 * resizes. On scroll/resize the overlay is cleared rather than
 * repositioned, since there's no new bounding-box data to reposition it
 * with without a fresh capture.
 *
 * Runs inside a closed Shadow DOM so its styles can't leak into (or be
 * broken by) the arbitrary page it's injected into — this content script
 * runs on <all_urls>.
 */

import type { OpenFigureChatMessage } from "../service-worker/messages";
import type { SlideAnalysisResponse, SlideObject } from "@shared/types";

const HOST_ID = "visionlearn-overlay-host";
const INDIGO_600 = "#4f46e5";
const INDIGO_50 = "#eef2ff";
const SLATE_900 = "#0f172a";

// The full analysis result, not just ids — carried in OPEN_FIGURE_CHAT so
// the side panel can rebuild its state even if it wasn't open (and so
// never saw the original SLIDE_ANALYZED broadcast) when a figure is clicked.
let currentSlide: SlideAnalysisResponse | null = null;
let selectedObjectId: string | null = null;
let shadowRoot: ShadowRoot | null = null;
let boxesContainer: HTMLDivElement | null = null;
let toolbar: HTMLButtonElement | null = null;

function ensureShadowRoot(): ShadowRoot {
  if (shadowRoot) return shadowRoot;

  const host = document.createElement("div");
  host.id = HOST_ID;
  // Fixed positioning below is relative to the viewport only if no
  // ancestor sets a transform/filter/perspective — <html> essentially
  // never does on real pages, unlike <body>, which is why this is
  // appended there rather than to document.body.
  document.documentElement.appendChild(host);

  // "open" rather than "closed" — style/DOM isolation from the host page
  // is the same either way; open just means the host page's own scripts
  // could in principle inspect host.shadowRoot, which isn't a real
  // security boundary we depend on, and open is far easier to debug/test.
  shadowRoot = host.attachShadow({ mode: "open" });

  const style = document.createElement("style");
  style.textContent = `
    :host { all: initial; }
    .vl-container {
      position: fixed;
      inset: 0;
      pointer-events: none;
      z-index: 2147483647;
      font-family: ui-sans-serif, system-ui, sans-serif;
    }
    .vl-box {
      position: fixed;
      pointer-events: auto;
      box-sizing: border-box;
      border: 2px solid transparent;
      border-radius: 8px;
      transition: border-color 120ms ease, background-color 120ms ease;
      cursor: pointer;
    }
    .vl-box:hover {
      border-color: ${INDIGO_600};
    }
    .vl-box.vl-selected {
      border-color: ${INDIGO_600};
      background-color: ${INDIGO_50}55;
    }
    .vl-toolbar {
      position: fixed;
      pointer-events: auto;
      display: flex;
      align-items: center;
      gap: 6px;
      background: white;
      color: ${SLATE_900};
      border-radius: 12px;
      padding: 6px 12px;
      font-size: 13px;
      font-weight: 500;
      box-shadow: 0 1px 2px 0 rgb(15 23 42 / 0.08), 0 2px 8px -2px rgb(15 23 42 / 0.16);
      cursor: pointer;
      border: none;
    }
    .vl-toolbar:hover {
      background: ${INDIGO_50};
    }
  `;
  shadowRoot.appendChild(style);

  boxesContainer = document.createElement("div");
  boxesContainer.className = "vl-container";
  shadowRoot.appendChild(boxesContainer);

  window.addEventListener("scroll", clearOverlay, { passive: true });
  window.addEventListener("resize", clearOverlay, { passive: true });
  // Escape-to-deselect only — deliberately not a page-wide "click
  // anywhere deselects" listener: this content script runs on <all_urls>,
  // and a capture-phase document click listener would fire before our
  // own toolbar button's bubble-phase click handler, removing the button
  // from the DOM mid-dispatch and silently swallowing the click (caught
  // in review before this ever shipped). Deselection instead happens by
  // clicking the same box again (see the box click handler below).
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") deselect();
  });

  return shadowRoot;
}

function labelFor(object: SlideObject): string {
  return object.summary?.trim() || object.extracted_text?.slice(0, 40)?.trim() || object.type;
}

function renderBoxes(): void {
  if (!boxesContainer || !currentSlide) return;
  boxesContainer.innerHTML = "";

  for (const object of currentSlide.objects) {
    const box = document.createElement("div");
    box.className = "vl-box" + (object.id === selectedObjectId ? " vl-selected" : "");
    box.style.left = `${object.bounding_box.x * window.innerWidth}px`;
    box.style.top = `${object.bounding_box.y * window.innerHeight}px`;
    box.style.width = `${object.bounding_box.width * window.innerWidth}px`;
    box.style.height = `${object.bounding_box.height * window.innerHeight}px`;
    box.title = labelFor(object);
    box.addEventListener("click", (event) => {
      event.stopPropagation();
      event.preventDefault();
      if (object.id === selectedObjectId) {
        deselect();
      } else {
        select(object);
      }
    });
    boxesContainer.appendChild(box);
  }
}

function renderToolbar(object: SlideObject): void {
  if (!shadowRoot) return;
  toolbar?.remove();

  const box = shadowRoot.querySelector<HTMLDivElement>(".vl-box.vl-selected");
  const rect = box?.getBoundingClientRect();
  if (!rect) return;

  const button = document.createElement("button");
  button.className = "vl-toolbar";
  button.type = "button";
  button.textContent = `Ask about this ${object.type} →`;
  // Clamp so the toolbar (placed just above the box) never renders off
  // the top of the viewport for a box near the top edge.
  button.style.left = `${Math.max(8, rect.left)}px`;
  button.style.top = `${Math.max(8, rect.top - 40)}px`;
  button.addEventListener("click", (event) => {
    event.stopPropagation();
    if (!currentSlide) return;
    const message: OpenFigureChatMessage = {
      type: "OPEN_FIGURE_CHAT",
      slide: currentSlide,
      objectId: object.id,
    };
    chrome.runtime.sendMessage(message).catch(() => undefined);
    deselect();
  });

  shadowRoot.appendChild(button);
  toolbar = button;
}

function select(object: SlideObject): void {
  selectedObjectId = object.id;
  renderBoxes();
  renderToolbar(object);
}

function deselect(): void {
  if (selectedObjectId === null) return;
  selectedObjectId = null;
  toolbar?.remove();
  toolbar = null;
  renderBoxes();
}

function clearOverlay(): void {
  currentSlide = null;
  selectedObjectId = null;
  toolbar?.remove();
  toolbar = null;
  if (boxesContainer) boxesContainer.innerHTML = "";
}

export function showSlideOverlay(slide: SlideAnalysisResponse): void {
  ensureShadowRoot();
  currentSlide = slide;
  selectedObjectId = null;
  renderBoxes();
}
