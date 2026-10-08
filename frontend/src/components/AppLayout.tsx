import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Bell,
  Boxes,
  LogOut,
  Mail,
  Settings,
  Truck,
  X,
} from "lucide-react";
import { useState } from "react";
import type { ReactNode } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { api } from "../api";
import type { Alert, StatusUpdate } from "../types";
import { formatClock } from "../utils";

const tabs = [
  { to: "/inbox", label: "Inbox", icon: Mail, key: "inbox" },
  { to: "/truckstop", label: "TruckStop", icon: Truck, key: "truckstop" },
  { to: "/status", label: "Delivery Status", icon: Boxes, key: "delivery" },
];

function AlertsPanel({
  alerts,
  pending,
  onClose,
}: {
  alerts: Alert[];
  pending: StatusUpdate[];
  onClose: () => void;
}) {
  return (
    <div className="absolute right-0 top-14 z-40 w-[min(92vw,390px)] overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-xl">
      <div className="flex items-center justify-between border-b border-slate-100 px-4 py-3">
        <div>
          <p className="font-bold text-ink">Needs attention</p>
          <p className="text-xs text-slate-500">
            {alerts.length + pending.length} open item{alerts.length + pending.length === 1 ? "" : "s"}
          </p>
        </div>
        <button
          onClick={onClose}
          className="grid h-10 w-10 place-items-center rounded-lg text-slate-500 hover:bg-slate-100"
          aria-label="Close alerts"
        >
          <X className="h-4 w-4" />
        </button>
      </div>
      <div className="max-h-[60vh] overflow-y-auto p-2">
        {alerts.map((alert) => (
            <NavLink
              to={`/status?load=${alert.load.id}`}
              onClick={onClose}
              key={`alert-${alert.id}`}
              className="block rounded-xl px-3 py-3 hover:bg-slate-50"
            >
              <p className="text-sm font-semibold text-slate-800">
                {alert.state === "no_reply"
                  ? `No reply to ${alert.kind} check-in sent ${formatClock(alert.checkin_sent_at)}`
                  : `${alert.parsed_status ?? "Unclear"} reply · ${alert.load.reference}`}
              </p>
              <p className="mt-1 line-clamp-2 text-xs text-slate-500">
                {alert.reply_raw_text || alert.parsed_summary || `${alert.load.reference} · ${alert.kind} check-in`}
              </p>
            </NavLink>
        ))}
        {pending.map((item) => (
          <NavLink
            to={`/status?load=${item.load_id}`}
            onClick={onClose}
            key={`draft-${item.id}`}
            className="block rounded-xl px-3 py-3 hover:bg-slate-50"
          >
            <p className="text-sm font-semibold text-slate-800">
              Review {item.status.replace("_", " ")} update
            </p>
            <p className="mt-1 text-xs text-slate-500">
              {item.source === "checkin" ? "Driver reply" : "Status draft"} · Load #{item.load_id}
            </p>
          </NavLink>
        ))}
        {alerts.length + pending.length === 0 && (
          <p className="px-3 py-6 text-center text-sm text-slate-500">
            You’re all caught up.
          </p>
        )}
      </div>
    </div>
  );
}

export default function AppLayout({ children }: { children: ReactNode }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [alertsOpen, setAlertsOpen] = useState(false);
  const inbox = useQuery({
    queryKey: ["inbox"],
    queryFn: api.inbox,
    refetchInterval: 30_000,
  });
  const truckstop = useQuery({
    queryKey: ["loads", "truckstop", false],
    queryFn: () => api.loads("truckstop"),
    refetchInterval: 30_000,
  });
  const delivery = useQuery({
    queryKey: ["loads", "delivery", false],
    queryFn: () => api.loads("delivery"),
    refetchInterval: 30_000,
  });
  const alerts = useQuery({
    queryKey: ["alerts"],
    queryFn: api.alerts,
    refetchInterval: 30_000,
  });
  const pending = useQuery({
    queryKey: ["status-updates", "pending_approval"],
    queryFn: api.pendingUpdates,
    refetchInterval: 30_000,
  });
  const alertItems = alerts.data ?? [];
  const pendingItems = pending.data ?? [];
  const totalAttention = alertItems.length + pendingItems.length;
  const countFor = (key: string) => {
    if (key === "inbox") return inbox.data?.length ?? 0;
    if (key === "truckstop") return truckstop.data?.length ?? 0;
    return delivery.data?.length ?? 0;
  };
  async function logout() {
    await api.logout();
    await queryClient.clear();
    navigate("/login");
  }
  return (
    <div className="min-h-screen bg-canvas pb-24 text-ink md:pb-0">
      <header className="sticky top-0 z-30 border-b border-slate-200 bg-white/95 backdrop-blur">
        <div className="mx-auto flex h-[68px] max-w-6xl items-center justify-between px-4 sm:px-6">
          <NavLink to="/inbox" className="flex min-w-0 items-center gap-2.5">
            <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-blue-600 text-white shadow-sm shadow-blue-200">
              <Truck className="h-5 w-5" />
            </span>
            <span className="truncate text-[17px] font-extrabold tracking-tight text-slate-900">
              KingOfFreight
            </span>
          </NavLink>
          <nav className="hidden h-full items-center gap-1 md:flex">
            {tabs.map(({ to, label, key }) => (
              <NavLink
                key={to}
                to={to}
                className={({ isActive }) =>
                  `flex h-10 items-center gap-2 rounded-xl px-3 text-sm font-semibold transition ${
                    isActive
                      ? "bg-blue-50 text-blue-700"
                      : "text-slate-600 hover:bg-slate-50 hover:text-slate-900"
                  }`
                }
              >
                {label}
                <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-bold text-slate-500">
                  {countFor(key)}
                </span>
              </NavLink>
            ))}
          </nav>
          <div className="flex items-center gap-1.5">
            <div className="relative">
              <button
                onClick={() => setAlertsOpen((open) => !open)}
                className="relative grid h-11 w-11 place-items-center rounded-xl text-slate-600 hover:bg-slate-100"
                aria-label={`Alerts, ${totalAttention} open`}
              >
                <Bell className="h-5 w-5" />
                {totalAttention > 0 && (
                  <span className="absolute right-1 top-1 grid min-h-5 min-w-5 place-items-center rounded-full bg-rose-600 px-1 text-[10px] font-bold text-white">
                    {totalAttention > 9 ? "9+" : totalAttention}
                  </span>
                )}
              </button>
              {alertsOpen && (
                <AlertsPanel
                  alerts={alertItems}
                  pending={pendingItems}
                  onClose={() => setAlertsOpen(false)}
                />
              )}
            </div>
            <NavLink
              to="/settings"
              className={({ isActive }) =>
                `grid h-11 w-11 place-items-center rounded-xl ${
                  isActive
                    ? "bg-blue-50 text-blue-700"
                    : "text-slate-600 hover:bg-slate-100"
                }`
              }
              aria-label="Settings"
              title="Settings"
            >
              <Settings className="h-5 w-5" />
            </NavLink>
            <button
              onClick={() => void logout()}
              className="flex h-11 items-center gap-2 rounded-xl px-3 text-sm font-semibold text-slate-600 hover:bg-slate-100"
              aria-label="Log out"
              title="Log out"
            >
              <LogOut className="h-4 w-4" />
              <span className="hidden sm:inline">Log out</span>
            </button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-4 pb-10 pt-6 sm:px-6 sm:pt-8">
        {children}
      </main>
      <nav className="fixed inset-x-0 bottom-0 z-30 border-t border-slate-200 bg-white/95 pb-[env(safe-area-inset-bottom)] shadow-[0_-4px_18px_rgba(15,23,42,0.06)] backdrop-blur md:hidden">
        <div className="mx-auto grid max-w-xl grid-cols-3 px-2 pt-1.5">
          {tabs.map(({ to, label, icon: Icon, key }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                `flex min-h-[60px] flex-col items-center justify-center gap-1 rounded-xl px-1 text-[11px] font-semibold ${
                  isActive ? "text-blue-700" : "text-slate-500"
                }`
              }
            >
              <span className="relative">
                <Icon className="h-5 w-5" />
                {countFor(key) > 0 && (
                  <span className="absolute -right-2 -top-1 grid min-h-4 min-w-4 place-items-center rounded-full bg-blue-600 px-1 text-[9px] font-bold text-white">
                    {countFor(key) > 9 ? "9+" : countFor(key)}
                  </span>
                )}
              </span>
              {label}
            </NavLink>
          ))}
        </div>
      </nav>
    </div>
  );
}
