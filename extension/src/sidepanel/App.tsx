/**
 * Side panel shell. Chrome's own title bar already shows the product name,
 * so there is no in-app header: one row of navigation with the places a
 * student works (Ask about a slide, Recent, Notes, Code, Chat without a slide),
 * today's capture count, and Settings. Ask, Chat and Code stay mounted while
 * another view is open so a conversation or a program in progress is not
 * lost. Code from an answer or a slide is handed to the Code tab through
 * shared/handoff.ts.
 */

import { useEffect, useState } from "react";

import { getSlide } from "../shared/api-client";
import { onHandoff } from "../shared/handoff";
import { AskTab, type RestoredChat } from "./tabs/AskTab";
import { ChatTab } from "./tabs/ChatTab";
import { CodeTab, type IncomingCode } from "./tabs/CodeTab";
import { NotesTab } from "./tabs/NotesTab";
import { RecentTab } from "./tabs/RecentTab";
import { SettingsTab } from "./tabs/SettingsTab";
import { UsageMeter } from "./components/UsageMeter";
import { WelcomeScreen } from "./WelcomeScreen";

type View = "ask" | "chat" | "code" | "recent" | "notes" | "settings";

const TABS: { view: View; label: string }[] = [
  { view: "ask", label: "Ask" },
  { view: "recent", label: "Recent" },
  { view: "notes", label: "Notes" },
  { view: "code", label: "Code" },
  { view: "chat", label: "Chat" },
];

const HAS_SEEN_WELCOME_KEY = "hasSeenWelcome";
// The release whose "what's new" note this install has already been shown.
const SEEN_WHATS_NEW_KEY = "seenWhatsNew";
const WHATS_NEW_RELEASE = "2.0";

function SettingsIcon(): JSX.Element {
  return (
    <svg viewBox="0 0 20 20" fill="none" className="h-[18px] w-[18px]" aria-hidden="true">
      <path d="M10 12.5a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5Z" stroke="currentColor" strokeWidth="1.5" />
      <path
        d="M16.17 12.5a1.38 1.38 0 0 0 .28 1.52l.05.05a1.67 1.67 0 1 1-2.36 2.36l-.05-.05a1.38 1.38 0 0 0-1.52-.28 1.38 1.38 0 0 0-.84 1.27v.14a1.67 1.67 0 1 1-3.33 0v-.07a1.38 1.38 0 0 0-.9-1.27 1.38 1.38 0 0 0-1.52.28l-.05.05a1.67 1.67 0 1 1-2.36-2.36l.05-.05a1.38 1.38 0 0 0 .28-1.52 1.38 1.38 0 0 0-1.27-.84h-.14a1.67 1.67 0 1 1 0-3.33h.07a1.38 1.38 0 0 0 1.27-.9 1.38 1.38 0 0 0-.28-1.52l-.05-.05A1.67 1.67 0 1 1 5.86 3.4l.05.05a1.38 1.38 0 0 0 1.52.28h.07a1.38 1.38 0 0 0 .84-1.27v-.14a1.67 1.67 0 1 1 3.33 0v.07a1.38 1.38 0 0 0 .84 1.27 1.38 1.38 0 0 0 1.52-.28l.05-.05a1.67 1.67 0 1 1 2.36 2.36l-.05.05a1.38 1.38 0 0 0-.28 1.52v.07a1.38 1.38 0 0 0 1.27.84h.14a1.67 1.67 0 1 1 0 3.33h-.07a1.38 1.38 0 0 0-1.27.84Z"
        stroke="currentColor"
        strokeWidth="1.5"
      />
    </svg>
  );
}

export function App(): JSX.Element {
  const [view, setView] = useState<View>("ask");
  const [restore, setRestore] = useState<RestoredChat | null>(null);
  // A series to open straight away when Recent is next shown (from the Ask start screen).
  const [seriesToOpen, setSeriesToOpen] = useState<string | null>(null);
  // Bumped on each press of the Recent tab, so pressing it while inside a
  // series goes back to the list, as a tab is expected to.
  const [recentVisit, setRecentVisit] = useState(0);
  // null until chrome.storage answers, so the normal UI never flashes
  // before the welcome screen on a first-ever open.
  const [showWelcome, setShowWelcome] = useState<boolean | null>(null);
  const [showWhatsNew, setShowWhatsNew] = useState(false);
  // The latest code handed over from an answer or a slide.
  const [incomingCode, setIncomingCode] = useState<IncomingCode | null>(null);

  useEffect(
    () =>
      onHandoff((handoff) => {
        setIncomingCode({ id: Date.now(), language: handoff.language, code: handoff.code });
        setView("code");
      }),
    []
  );

  useEffect(() => {
    chrome.storage.local.get([HAS_SEEN_WELCOME_KEY, SEEN_WHATS_NEW_KEY]).then((stored) => {
      const returning = Boolean(stored[HAS_SEEN_WELCOME_KEY]);
      setShowWelcome(!returning);
      // Only someone who used an earlier version has anything "new" to be told.
      setShowWhatsNew(returning && stored[SEEN_WHATS_NEW_KEY] !== WHATS_NEW_RELEASE);
    });
  }, []);

  const dismissWelcome = () => {
    chrome.storage.local
      .set({ [HAS_SEEN_WELCOME_KEY]: true, [SEEN_WHATS_NEW_KEY]: WHATS_NEW_RELEASE })
      .catch(() => undefined);
    setShowWelcome(false);
  };

  const dismissWhatsNew = () => {
    chrome.storage.local.set({ [SEEN_WHATS_NEW_KEY]: WHATS_NEW_RELEASE }).catch(() => undefined);
    setShowWhatsNew(false);
  };

  if (showWelcome === null) {
    return <div className="h-screen w-full bg-white" />;
  }

  if (showWelcome) {
    return <WelcomeScreen onDone={dismissWelcome} />;
  }

  const go = (target: View) => {
    setSeriesToOpen(null);
    if (target === "recent") setRecentVisit((visit) => visit + 1);
    setView(target);
  };

  return (
    <div className="flex h-screen w-full flex-col bg-white">
      <nav className="flex flex-none items-center gap-1 border-b border-slate-100 px-2 py-2" aria-label="Sections">
        {TABS.map((tab) => (
          <button
            key={tab.view}
            type="button"
            onClick={() => go(tab.view)}
            aria-current={view === tab.view ? "page" : undefined}
            className={`rounded-sm px-2.5 py-1.5 text-sm font-medium transition-colors duration-[120ms] max-[350px]:px-1.5 ${
              view === tab.view
                ? "bg-indigo-50 text-indigo-700 dark:text-indigo-300"
                : "text-slate-500 hover:bg-slate-50 hover:text-slate-700"
            }`}
          >
            {tab.label}
          </button>
        ))}
        <div className="ml-auto flex items-center gap-1">
          {/* Five tabs need the room in a narrow panel; the count is also on the Ask screen's limit card. */}
          <span className="max-[400px]:hidden">
            <UsageMeter />
          </span>
          <button
            type="button"
            onClick={() => go("settings")}
            aria-label="Settings"
            title="Settings"
            aria-current={view === "settings" ? "page" : undefined}
            className={`flex h-8 w-8 items-center justify-center rounded-sm transition-colors duration-[120ms] ${
              view === "settings"
                ? "bg-indigo-50 text-indigo-700 dark:text-indigo-300"
                : "text-slate-400 hover:bg-slate-50 hover:text-slate-600"
            }`}
          >
            <SettingsIcon />
          </button>
        </div>
      </nav>

      <div className={view === "ask" ? "flex flex-1 flex-col overflow-hidden" : "hidden"}>
        <AskTab
          restore={restore}
          active={view === "ask"}
          whatsNew={showWhatsNew}
          onDismissWhatsNew={dismissWhatsNew}
          onOpenRecent={() => {
            dismissWhatsNew();
            go("recent");
          }}
          onOpenSeries={(seriesId) => {
            setSeriesToOpen(seriesId);
            setView("recent");
          }}
        />
      </div>
      <div className={view === "chat" ? "flex flex-1 flex-col overflow-hidden" : "hidden"}>
        <ChatTab
          onOpenSlide={(slideId) => {
            void getSlide(slideId)
              .then((slide) => {
                setRestore({ conversationId: null, slide, messages: [] });
                go("ask");
              })
              // Deleted since (or past the 30 days): the library is the next best place.
              .catch(() => go("recent"));
          }}
          onOpenNotes={() => go("notes")}
        />
      </div>
      <div className={view === "code" ? "flex flex-1 flex-col overflow-hidden" : "hidden"}>
        <CodeTab incoming={incomingCode} active={view === "code"} />
      </div>
      {view === "recent" && (
        <div className="flex flex-1 flex-col overflow-hidden">
          <RecentTab
            key={recentVisit}
            initialSeriesId={seriesToOpen}
            onOpen={(chat) => {
              setRestore(chat);
              go("ask");
            }}
          />
        </div>
      )}
      {view === "notes" && (
        <div className="flex flex-1 flex-col overflow-hidden">
          <NotesTab />
        </div>
      )}
      {view === "settings" && (
        <div className="flex flex-1 flex-col overflow-hidden">
          <SettingsTab />
        </div>
      )}
    </div>
  );
}
