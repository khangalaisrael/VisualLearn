/**
 * Side panel shell — tab navigation (docs/ROADMAP.md, Milestone 2:
 * "Ask/Concepts/Notes/Quiz tab shells, non-functional except Ask"). The
 * full sidebar nav in docs/ARCHITECTURE.md §3 also includes History;
 * that isn't scoped to any milestone yet and is deliberately left out
 * here rather than added speculatively. Settings was added ahead of its
 * milestone by direct request, to replace the devtools-console config
 * workaround with a real UI — see extension/README.md.
 */

import { useState } from "react";

import { AskTab } from "./tabs/AskTab";
import { ComingSoonTab } from "./tabs/ComingSoonTab";
import { SettingsTab } from "./tabs/SettingsTab";

type TabId = "ask" | "concepts" | "notes" | "quiz" | "settings";

const TABS: { id: TabId; label: string }[] = [
  { id: "ask", label: "Ask" },
  { id: "concepts", label: "Concepts" },
  { id: "notes", label: "Notes" },
  { id: "quiz", label: "Quiz" },
  { id: "settings", label: "Settings" },
];

export function App(): JSX.Element {
  const [activeTab, setActiveTab] = useState<TabId>("ask");

  return (
    <div className="flex h-screen w-full flex-col bg-white">
      <header className="border-b border-slate-200 px-4 py-3">
        <h1 className="text-base font-semibold tracking-tight text-slate-900">VisionLearn AI</h1>
      </header>

      <nav className="flex border-b border-slate-200" role="tablist">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            type="button"
            role="tab"
            aria-selected={activeTab === tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`flex-1 px-3 py-2.5 text-sm font-medium transition-colors duration-[120ms] ${
              activeTab === tab.id
                ? "border-b-2 border-indigo-600 text-slate-900"
                : "border-b-2 border-transparent text-slate-500 hover:text-slate-700"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </nav>

      <div className="flex flex-1 flex-col overflow-hidden">
        {activeTab === "ask" && <AskTab />}
        {activeTab === "concepts" && <ComingSoonTab tabName="Concepts" milestone="Milestone 5" />}
        {activeTab === "notes" && <ComingSoonTab tabName="Notes" milestone="Milestone 5" />}
        {activeTab === "quiz" && <ComingSoonTab tabName="Quiz" milestone="Milestone 5" />}
        {activeTab === "settings" && <SettingsTab />}
      </div>
    </div>
  );
}
