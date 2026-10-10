/**
 * Owner dashboard, opened from Settings (admin accounts only) as a full tab.
 * Read-only: spend, per-user usage with outliers, and Pro waitlist demand.
 * The server enforces who may read this (ADMIN_EMAILS); hiding the button
 * for everyone else is only a courtesy. Costs are estimates from a price
 * table, not the provider's bill.
 */

import { useCallback, useEffect, useState } from "react";

import type { AdminOverview, AdminUsersResponse, AdminWaitlistResponse } from "@shared/types";

import {
  ApiError,
  getAdminOverview,
  getAdminUsers,
  getAdminWaitlist,
  signInWithGoogle,
} from "../shared/api-client";
import { Button } from "../sidepanel/components/Button";

interface Data {
  overview: AdminOverview;
  users: AdminUsersResponse;
  waitlist: AdminWaitlistResponse;
}

type State =
  | { status: "loading" }
  | { status: "forbidden" }
  | { status: "error"; message: string }
  | { status: "ready"; data: Data };

function usd(amount: number): string {
  return amount > 0 && amount < 0.01 ? `$${amount.toFixed(4)}` : `$${amount.toFixed(2)}`;
}

function plural(count: number, one: string, many: string): string {
  return `${count} ${count === 1 ? one : many}`;
}

function when(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

/** A cell that starts with = + - @ would run as a formula when the CSV is opened in a spreadsheet. */
function csvCell(value: string): string {
  const safe = /^[=+\-@\t\r]/.test(value) ? `'${value}` : value;
  return `"${safe.replace(/"/g, '""')}"`;
}

function exportWaitlist(waitlist: AdminWaitlistResponse): void {
  const rows = [
    ["email", "clicks", "first_click", "last_click", "sources"],
    ...waitlist.entries.map((e) => [e.email ?? "", String(e.clicks), e.first_click, e.last_click, e.sources.join(" ")]),
  ];
  const csv = rows.map((row) => row.map(csvCell).join(",")).join("\n");
  const url = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = "visionlearn-waitlist.csv";
  link.click();
  URL.revokeObjectURL(url);
}

const DRAFT_SUBJECT = "Quick question about VisionLearn Pro (2 min)";
const DRAFT_BODY = `Hi! You joined the VisionLearn Pro waitlist, thank you. I'm a student building this on a small budget, so I want to price it fairly.

1. How many captures a day would you actually use?
2. What would you comfortably pay per month: R__ / $__?
3. What would you most want Pro to include (more captures, longer history, something else)?

Just reply to this email. Your answers decide what I build next.

Thanks,
Israel`;

/** Opens a Gmail compose window with everyone on the list in BCC (nobody sees anyone else). */
function draftWaitlistEmail(waitlist: AdminWaitlistResponse): void {
  const emails = waitlist.entries.map((e) => e.email).filter((e): e is string => Boolean(e));
  const params = new URLSearchParams({
    view: "cm",
    fs: "1",
    bcc: emails.slice(0, 60).join(","),
    su: DRAFT_SUBJECT,
    body: DRAFT_BODY,
  });
  window.open(`https://mail.google.com/mail/?${params.toString()}`, "_blank", "noopener");
}

function Stat({ label, value, hint }: { label: string; value: string; hint?: string }): JSX.Element {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-subtle">
      <p className="text-xs font-medium uppercase tracking-wide text-slate-400">{label}</p>
      <p className="mt-1 text-2xl font-semibold tabular-nums text-slate-800">{value}</p>
      {hint && <p className="mt-0.5 text-xs text-slate-400">{hint}</p>}
    </div>
  );
}

function DayChart({ days }: { days: AdminOverview["days"] }): JSX.Element {
  const peak = Math.max(1, ...days.map((d) => d.captures));
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-subtle">
      <h2 className="text-sm font-semibold text-slate-800">Captures per day</h2>
      <div className="mt-4 flex h-32 items-end gap-1.5">
        {days.map((day) => (
          <div
            key={day.date}
            className="flex h-full flex-1 flex-col items-center justify-end gap-1"
            title={`${day.date}: ${day.captures} captures, ${day.chats} chats, ${usd(day.cost_usd)}, ${day.limit_hits} limit hits`}
          >
            <span className="text-[10px] tabular-nums text-slate-400">{day.captures || ""}</span>
            <div
              className={`w-full rounded-t ${day.limit_hits > 0 ? "bg-amber-400" : "bg-indigo-400"}`}
              style={{ height: `${(day.captures / peak) * 100}%`, minHeight: day.captures ? 3 : 0 }}
            />
            <span className="text-[10px] text-slate-400">{day.date.slice(8)}</span>
          </div>
        ))}
      </div>
      <p className="mt-3 text-xs text-slate-400">Amber bars are days when someone hit a limit.</p>
    </div>
  );
}

export function AdminApp(): JSX.Element {
  const [state, setState] = useState<State>({ status: "loading" });

  const load = useCallback(async () => {
    setState({ status: "loading" });
    try {
      const [overview, users, waitlist] = await Promise.all([getAdminOverview(), getAdminUsers(), getAdminWaitlist()]);
      setState({ status: "ready", data: { overview, users, waitlist } });
    } catch (error) {
      if (error instanceof ApiError && (error.status === 403 || error.status === 401)) {
        setState({ status: "forbidden" });
      } else {
        setState({ status: "error", message: error instanceof Error ? error.message : String(error) });
      }
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const signIn = async () => {
    try {
      await signInWithGoogle();
      await load();
    } catch (error) {
      setState({ status: "error", message: error instanceof Error ? error.message : String(error) });
    }
  };

  return (
    <main className="mx-auto flex max-w-5xl flex-col gap-6 px-6 py-8">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-slate-800">VisionLearn admin</h1>
          {state.status === "ready" && (
            <p className="text-xs text-slate-400">
              Updated {when(state.data.overview.generated_at)} · days reset at midnight ({state.data.overview.timezone})
            </p>
          )}
        </div>
        <Button variant="secondary" onClick={() => void load()} disabled={state.status === "loading"}>
          Refresh
        </Button>
      </header>

      {state.status === "loading" && <p className="text-sm text-slate-400">Loading…</p>}

      {state.status === "forbidden" && (
        <div className="flex flex-col items-start gap-3 rounded-lg border border-slate-200 bg-white p-5 shadow-subtle">
          <p className="text-sm text-slate-600">
            This page is only for the admin account. Sign in with the Google account listed in ADMIN_EMAILS.
          </p>
          <Button onClick={() => void signIn()}>Sign in with Google</Button>
        </div>
      )}

      {state.status === "error" && (
        <div className="rounded-md bg-red-50 p-3 text-sm text-red-700 dark:text-red-300">
          <p>{state.message}</p>
          <button type="button" onClick={() => void load()} className="mt-2 font-medium underline underline-offset-2">
            Try again
          </button>
        </div>
      )}

      {state.status === "ready" && (
        <>
          <section className="grid grid-cols-2 gap-3 md:grid-cols-3">
            <Stat
              label="Captures today"
              value={`${state.data.overview.global_captures_today} / ${state.data.overview.global_cap}`}
              hint="Counts toward the global cap (admins excluded)"
            />
            <Stat label="Spend today" value={usd(state.data.overview.cost_today_usd)} hint="Estimate" />
            <Stat
              label="Spend this month"
              value={usd(state.data.overview.cost_month_usd)}
              hint={`Last 30 days: ${usd(state.data.overview.cost_30d_usd)}`}
            />
            <Stat
              label="Active today"
              value={String(state.data.overview.active_users_today)}
              hint={`${plural(state.data.overview.total_users, "signed-up user", "signed-up users")}`}
            />
            <Stat label="Limit hits today" value={String(state.data.overview.limit_hits_today)} hint="Demand signal" />
            <Stat
              label="Pro waitlist"
              value={plural(state.data.overview.waitlist_users, "person", "people")}
              hint={plural(state.data.overview.waitlist_clicks, "click", "clicks")}
            />
          </section>

          <DayChart days={state.data.overview.days} />

          <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-subtle">
            <div className="flex items-baseline justify-between">
              <h2 className="text-sm font-semibold text-slate-800">Users, last 30 days</h2>
              <p className="text-xs text-slate-400">Median spender: {usd(state.data.users.median_cost_usd)}</p>
            </div>
            <div className="mt-3 overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="text-xs uppercase tracking-wide text-slate-400">
                  <tr>
                    <th className="py-2 pr-4 font-medium">User</th>
                    <th className="py-2 pr-4 text-right font-medium">Captures</th>
                    <th className="py-2 pr-4 text-right font-medium">Chats</th>
                    <th className="py-2 pr-4 text-right font-medium">Tokens in / out</th>
                    <th className="py-2 pr-4 text-right font-medium">Est. cost</th>
                    <th className="py-2 pr-4 text-right font-medium">Limit hits</th>
                    <th className="py-2 font-medium">Last active</th>
                  </tr>
                </thead>
                <tbody>
                  {state.data.users.users.map((user) => (
                    <tr key={user.user_id ?? "pooled"} className="border-t border-slate-100">
                      <td className="py-2 pr-4 text-slate-700">
                        {user.email ?? "Signed out / deleted accounts"}
                        {user.is_admin && (
                          <span className="ml-2 rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-500">
                            admin
                          </span>
                        )}
                        {user.is_outlier && (
                          <span className="ml-2 rounded-full bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-700 dark:text-amber-300">
                            outlier
                          </span>
                        )}
                      </td>
                      <td className="py-2 pr-4 text-right tabular-nums">{user.captures_30d}</td>
                      <td className="py-2 pr-4 text-right tabular-nums">{user.chats_30d}</td>
                      <td className="py-2 pr-4 text-right tabular-nums text-slate-500">
                        {user.input_tokens.toLocaleString()} / {user.output_tokens.toLocaleString()}
                      </td>
                      <td className="py-2 pr-4 text-right tabular-nums">{usd(user.cost_30d_usd)}</td>
                      <td className="py-2 pr-4 text-right tabular-nums">{user.limit_hits_30d}</td>
                      <td className="py-2 text-slate-500">{when(user.last_active)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="mt-3 text-xs text-slate-400">
              An outlier spent more than twice the median spender and at least 5 cents. Admin accounts are left out of
              that comparison. Costs are estimates from a price table.
            </p>
          </section>

          <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-subtle">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold text-slate-800">
                Pro waitlist · {plural(state.data.waitlist.unique_users, "person", "people")},{" "}
                {plural(state.data.waitlist.total_clicks, "click", "clicks")}
              </h2>
              <div className="flex items-center gap-2">
                <Button
                  variant="secondary"
                  className="text-xs"
                  onClick={() =>
                    void navigator.clipboard.writeText(
                      state.data.waitlist.entries.map((e) => e.email).filter(Boolean).join(", ")
                    )
                  }
                >
                  Copy emails
                </Button>
                <Button variant="secondary" className="text-xs" onClick={() => draftWaitlistEmail(state.data.waitlist)}>
                  Draft email
                </Button>
                <Button variant="secondary" className="text-xs" onClick={() => exportWaitlist(state.data.waitlist)}>
                  Export CSV
                </Button>
              </div>
            </div>
            {state.data.waitlist.entries.length === 0 ? (
              <p className="mt-3 text-sm text-slate-400">Nobody has clicked yet.</p>
            ) : (
              <table className="mt-3 w-full text-left text-sm">
                <thead className="text-xs uppercase tracking-wide text-slate-400">
                  <tr>
                    <th className="py-2 pr-4 font-medium">Email</th>
                    <th className="py-2 pr-4 text-right font-medium">Clicks</th>
                    <th className="py-2 pr-4 font-medium">From</th>
                    <th className="py-2 font-medium">Last click</th>
                  </tr>
                </thead>
                <tbody>
                  {state.data.waitlist.entries.map((entry) => (
                    <tr key={`${entry.email}-${entry.first_click}`} className="border-t border-slate-100">
                      <td className="py-2 pr-4 text-slate-700">{entry.email ?? "—"}</td>
                      <td className="py-2 pr-4 text-right tabular-nums">{entry.clicks}</td>
                      <td className="py-2 pr-4 text-slate-500">{entry.sources.join(", ")}</td>
                      <td className="py-2 text-slate-500">{when(entry.last_click)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>
        </>
      )}
    </main>
  );
}
