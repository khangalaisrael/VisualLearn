/**
 * Side panel shell. Chrome's own title bar already shows the product name,
 * so there is no in-app header. Ask is the default view; Recent, Notes and
 * Settings are reached from icons in the corner. Ask stays mounted
 * while another view is open so a chat in progress is not lost.
 */

import { useEffect, useState } from "react";

import { AskTab, type RestoredChat } from "./tabs/AskTab";
import { NotesTab } from "./tabs/NotesTab";
import { RecentTab } from "./tabs/RecentTab";
import { SettingsTab } from "./tabs/SettingsTab";
import { UsageMeter } from "./components/UsageMeter";
import { WelcomeScreen } from "./WelcomeScreen";

type View = "ask" | "recent" | "notes" | "settings";

const HAS_SEEN_WELCOME_KEY = "hasSeenWelcome";

function RecentIcon(): JSX.Element {
  return (
    <svg viewBox="0 0 20 20" fill="none" className="h-[18px] w-[18px]" aria-hidden="true">
      <circle cx="10" cy="10" r="7.25" stroke="currentColor" strokeWidth="1.5" />
      <path d="M10 6v4.25l2.75 1.75" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function NotesIcon(): JSX.Element {
  return (
    <svg viewBox="0 0 20 20" fill="none" className="h-[18px] w-[18px]" aria-hidden="true">
      <path
        d="M5.5 2.75h6.25L15.25 6.25v9.5a1.5 1.5 0 0 1-1.5 1.5h-8.25a1.5 1.5 0 0 1-1.5-1.5v-11.5a1.5 1.5 0 0 1 1.5-1.5Z"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinejoin="round"
      />
      <path d="M7 9.5h6M7 12.75h4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}

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

function NavButton({
  label,
  active,
  onClick,
  children,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
  children: JSX.Element;
}): JSX.Element {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      title={label}
      aria-pressed={active}
      className={`flex h-8 w-8 items-center justify-center rounded-md transition-colors duration-[120ms] ${
        active ? "bg-indigo-50 text-indigo-600 dark:text-indigo-300" : "text-slate-400 hover:bg-slate-50 hover:text-slate-600"
      }`}
    >
      {children}
    </button>
  );
}

export function App(): JSX.Element {
  const [view, setView] = useState<View>("ask");
  const [restore, setRestore] = useState<RestoredChat | null>(null);
  // null until chrome.storage answers, so the normal UI never flashes
  // before the welcome screen on a first-ever open.
  const [showWelcome, setShowWelcome] = useState<boolean | null>(null);

  useEffect(() => {
    chrome.storage.local.get(HAS_SEEN_WELCOME_KEY).then((stored) => {
      setShowWelcome(!stored[HAS_SEEN_WELCOME_KEY]);
    });
  }, []);

  const dismissWelcome = () => {
    chrome.storage.local.set({ [HAS_SEEN_WELCOME_KEY]: true }).catch(() => undefined);
    setShowWelcome(false);
  };

  if (showWelcome === null) {
    return <div className="h-screen w-full bg-white" />;
  }

  if (showWelcome) {
    return <WelcomeScreen onDone={dismissWelcome} />;
  }

  const toggle = (target: View) => setView(view === target ? "ask" : target);

  return (
    <div className="flex h-screen w-full flex-col bg-white">
      <div className="flex flex-none items-center justify-between border-b border-slate-100 px-3.5 py-2.5">
        {view === "ask" ? (
          <UsageMeter />
        ) : (
          <button
            type="button"
            onClick={() => setView("ask")}
            className="rounded-md px-2 py-1 text-sm font-medium text-slate-500 transition-colors duration-[120ms] hover:bg-slate-50 hover:text-slate-700"
          >
            ← Back
          </button>
        )}
        <div className="flex items-center gap-1">
          <NavButton label="Recent" active={view === "recent"} onClick={() => toggle("recent")}>
            <RecentIcon />
          </NavButton>
          <NavButton label="Notes" active={view === "notes"} onClick={() => toggle("notes")}>
            <NotesIcon />
          </NavButton>
          <NavButton label="Settings" active={view === "settings"} onClick={() => toggle("settings")}>
            <SettingsIcon />
          </NavButton>
        </div>
      </div>

      <div className={view === "ask" ? "flex flex-1 flex-col overflow-hidden" : "hidden"}>
        <AskTab restore={restore} />
      </div>
      {view === "recent" && (
        <div className="flex flex-1 flex-col overflow-hidden">
          <RecentTab
            onOpen={(chat) => {
              setRestore(chat);
              setView("ask");
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
