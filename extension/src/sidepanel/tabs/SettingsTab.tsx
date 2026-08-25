/**
 * Settings tab — configure the backend URL and X-API-Key from the side
 * panel UI instead of a devtools console command. Values are stored in
 * chrome.storage.local (see shared/api-client.ts getConfig/setConfig);
 * this doesn't need a backend endpoint, everything here is local.
 */

import { useEffect, useState } from "react";

import { checkHealth, getConfig, setConfig } from "../../shared/api-client";
import { Button } from "../components/Button";

type ConnectionState =
  | { status: "idle" }
  | { status: "checking" }
  | { status: "ok"; modelProvider: boolean }
  | { status: "error"; message: string };

export function SettingsTab(): JSX.Element {
  const [backendUrl, setBackendUrl] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [vlmModel, setVlmModel] = useState("gpt-4o");
  const [chatModel, setChatModel] = useState("gpt-4o");
  const [saved, setSaved] = useState(false);
  const [connection, setConnection] = useState<ConnectionState>({ status: "idle" });

  useEffect(() => {
    getConfig().then((config) => {
      setBackendUrl(config.backendUrl);
      setApiKey(config.apiKey);
      setVlmModel(config.vlmModel);
      setChatModel(config.chatModel);
    });
  }, []);

  const save = async () => {
    await setConfig({ backendUrl: backendUrl.trim(), apiKey: apiKey.trim(), vlmModel, chatModel });
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  const testConnection = async () => {
    setConnection({ status: "checking" });
    try {
      const health = await checkHealth(backendUrl.trim());
      setConnection({ status: "ok", modelProvider: health.model_provider });
    } catch (error) {
      setConnection({ status: "error", message: error instanceof Error ? error.message : String(error) });
    }
  };

  const inputClass =
    "rounded-sm border border-slate-300 px-3 py-2 text-sm transition-colors duration-[120ms] focus:border-indigo-400";

  return (
    <div className="scrollbar-thin flex flex-1 flex-col gap-4 overflow-y-auto p-4">
      <p className="text-sm text-slate-500">
        Connect the extension to your VisionLearn backend. Both values must match your backend's{" "}
        <code className="rounded-sm bg-slate-100 px-1 font-mono text-[13px]">.env</code> (
        <code className="rounded-sm bg-slate-100 px-1 font-mono text-[13px]">LOCAL_API_KEY</code>).
      </p>

      <label className="flex flex-col gap-1.5 text-sm">
        <span className="font-medium text-slate-700">Backend URL</span>
        <input
          type="text"
          value={backendUrl}
          onChange={(event) => setBackendUrl(event.target.value)}
          placeholder="http://127.0.0.1:8001"
          className={inputClass}
        />
      </label>

      <label className="flex flex-col gap-1.5 text-sm">
        <span className="font-medium text-slate-700">API Key</span>
        <input
          type="password"
          value={apiKey}
          onChange={(event) => setApiKey(event.target.value)}
          placeholder="LOCAL_API_KEY from .env"
          className={`${inputClass} font-mono`}
        />
      </label>

      <label className="flex flex-col gap-1.5 text-sm">
        <span className="font-medium text-slate-700">Slide Analysis Model</span>
        <select value={vlmModel} onChange={(event) => setVlmModel(event.target.value)} className={inputClass}>
          <option value="gpt-4o">gpt-4o — Accurate, higher cost</option>
          <option value="gpt-4o-mini">gpt-4o-mini — Fast, lower cost</option>
        </select>
        <span className="text-xs text-slate-500">
          Used for "Capture Current Slide". Equations and diagrams read best with gpt-4o.
        </span>
      </label>

      <label className="flex flex-col gap-1.5 text-sm">
        <span className="font-medium text-slate-700">Chat Model</span>
        <select value={chatModel} onChange={(event) => setChatModel(event.target.value)} className={inputClass}>
          <option value="gpt-4o">gpt-4o — Accurate, higher cost</option>
          <option value="gpt-4o-mini">gpt-4o-mini — Fast, lower cost</option>
        </select>
        <span className="text-xs text-slate-500">Used for questions asked in the Ask tab.</span>
      </label>

      <div className="flex items-center gap-3">
        <Button onClick={() => void save()}>Save</Button>
        <Button variant="secondary" onClick={() => void testConnection()} disabled={connection.status === "checking"}>
          Test Connection
        </Button>
        {saved && <span className="text-sm text-emerald-600">Saved</span>}
      </div>

      {connection.status === "checking" && <p className="text-sm text-slate-500">Checking…</p>}

      {connection.status === "ok" && (
        <div className="rounded-md bg-emerald-50 p-3 text-sm text-emerald-800 shadow-subtle">
          Connected.{" "}
          {connection.modelProvider
            ? "A model provider is configured — analysis and chat will work."
            : "No model provider is configured on the backend (OPENAI_API_KEY/ANTHROPIC_API_KEY) — analysis will use a placeholder and chat will fail."}
        </div>
      )}

      {connection.status === "error" && (
        <div className="rounded-md bg-red-50 p-3 text-sm text-red-700 shadow-subtle">
          <p className="font-medium">Couldn't reach the backend.</p>
          <p>{connection.message}</p>
          <p className="mt-1 text-red-500">
            Check that Docker Compose is running (<code className="font-mono">docker compose ps</code>) and the URL
            above is correct.
          </p>
        </div>
      )}
    </div>
  );
}
