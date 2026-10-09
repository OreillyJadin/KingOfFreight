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
import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { NavLink, useLocation, useNavigate } from "react-router-dom";
import { api } from "../api";
import type { Alert, StatusUpdate } from "../types";
import { formatClock } from "../utils";
import { Badge, Button, Card } from "./ui";
import { Wordmark } from "./Brand";
import ThemeToggle from "./ThemeToggle";

const tabs = [
  { to: "/inbox", label: "Inbox", icon: Mail, key: "inbox" },
  { to: "/truckstop", label: "TruckStop", icon: Truck, key: "truckstop" },
  { to: "/status", label: "Delivery Status", icon: Boxes, key: "delivery" },
];

function AlertsPanel({
  alerts,
  pending,
  onClose,
  placement,
}: {
  alerts: Alert[];
  pending: StatusUpdate[];
  onClose: () => void;
  placement: "header" | "sidebar";
}) {
  return (
    <Card
      className={`absolute z-40 overflow-hidden shadow-xl ${
        placement === "sidebar"
          ? "bottom-0 left-full ml-2 w-96"
          : "right-0 top-14 w-[min(92vw,390px)]"
      }`}
    >
      <div className="flex items-center justify-between border-b border-line/60 px-4 py-3">
        <div>
          <p className="font-bold text-fg">Needs attention</p>
          <p className="text-xs text-muted tabular-nums">
            {alerts.length + pending.length} open item{alerts.length + pending.length === 1 ? "" : "s"}
          </p>
        </div>
        <button
          onClick={onClose}
          className="grid h-10 w-10 place-items-center rounded-lg text-muted hover:bg-surface-3"
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
              className="block rounded-xl px-3 py-3 hover:bg-surface-2"
            >
              <p className="text-sm font-semibold text-fg tabular-nums">
                {alert.state === "no_reply"
                  ? `No reply to ${alert.kind} check-in sent ${formatClock(alert.checkin_sent_at)}`
                  : `${alert.parsed_status ?? "Unclear"} reply · ${alert.load.reference}`}
              </p>
              <p className="mt-1 line-clamp-2 text-xs text-muted">
                {alert.reply_raw_text || alert.parsed_summary || `${alert.load.reference} · ${alert.kind} check-in`}
              </p>
            </NavLink>
        ))}
        {pending.map((item) => (
          <NavLink
            to={`/status?load=${item.load_id}`}
            onClick={onClose}
            key={`draft-${item.id}`}
            className="block rounded-xl px-3 py-3 hover:bg-surface-2"
          >
            <p className="text-sm font-semibold text-fg">
              Review {item.status.replace("_", " ")} update
            </p>
            <p className="mt-1 text-xs text-muted tabular-nums">
              {item.source === "checkin" ? "Driver reply" : "Status draft"} · Load #{item.load_id}
            </p>
          </NavLink>
        ))}
        {alerts.length + pending.length === 0 && (
          <p className="px-3 py-6 text-center text-sm text-muted">
            You’re all caught up.
          </p>
        )}
      </div>
    </Card>
  );
}

export default function AppLayout({ children }: { children: ReactNode }) {
  const navigate = useNavigate();
  const location = useLocation();
  const queryClient = useQueryClient();
  const [alertsOpen, setAlertsOpen] = useState(false);
  useEffect(() => {
    const titles: Record<string, string> = {
      "/inbox": "Inbox · Fifth Wheel",
      "/truckstop": "TruckStop · Fifth Wheel",
      "/status": "Delivery Status · Fifth Wheel",
      "/settings": "Settings · Fifth Wheel",
    };
    document.title = titles[location.pathname] ?? "Fifth Wheel";
  }, [location.pathname]);
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
    <div className="min-h-screen bg-bg pb-24 text-fg md:pb-0">
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-60 flex-col border-r border-line bg-surface md:flex">
        <NavLink to="/inbox" className="flex h-[68px] shrink-0 items-center gap-2.5 px-5">
          <Wordmark className="min-w-0 truncate" markClassName="h-8 w-8 text-accent" />
        </NavLink>
        <nav aria-label="Main" className="space-y-1 px-3 pt-3">
          {tabs.map(({ to, label, icon: Icon, key }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                `flex min-h-11 items-center gap-3 rounded-r-xl border-l-2 px-3 text-sm font-semibold transition-colors duration-150 ${
                  isActive
                    ? "border-accent bg-surface-3 text-fg"
                    : "border-transparent text-fg-2 hover:bg-surface-2"
                }`
              }
            >
              {({ isActive }) => (
                <>
                  <Icon className="h-4 w-4 shrink-0" />
                  <span className="min-w-0 flex-1 truncate">{label}</span>
                  <Badge
                    tone={isActive ? "accent" : "neutral"}
                    className="rounded-full px-2 py-0.5 text-[11px]"
                  >
                    <span className="tabular-nums">{countFor(key)}</span>
                  </Badge>
                </>
              )}
            </NavLink>
          ))}
        </nav>
        <div className="mx-4 my-4 border-t border-line" />
        <NavLink
          to="/settings"
          className={({ isActive }) =>
            `mx-3 flex min-h-11 items-center gap-3 rounded-r-xl border-l-2 px-3 text-sm font-semibold transition-colors duration-150 ${
              isActive
                ? "border-accent bg-surface-3 text-fg"
                : "border-transparent text-fg-2 hover:bg-surface-2"
            }`
          }
        >
          <Settings className="h-4 w-4 shrink-0" />
          Settings
        </NavLink>
        <div className="mt-auto border-t border-line p-3">
          <div className="relative mb-1">
            <button
              onClick={() => setAlertsOpen((open) => !open)}
              className="flex min-h-11 w-full items-center gap-3 rounded-xl px-3 text-left text-sm font-semibold text-fg-2 transition-colors duration-150 hover:bg-surface-2"
              aria-label={`Alerts, ${totalAttention} open`}
            >
              <span className="relative grid h-8 w-8 shrink-0 place-items-center">
                <Bell className="h-5 w-5" />
                {totalAttention > 0 && (
                  <span className="absolute -right-1 -top-1 grid min-h-5 min-w-5 place-items-center rounded-full bg-danger px-1 text-[10px] font-bold text-on-danger ring-2 ring-surface">
                    <span className="tabular-nums">{totalAttention > 9 ? "9+" : totalAttention}</span>
                  </span>
                )}
              </span>
              Alerts
            </button>
            {alertsOpen && (
              <AlertsPanel
                alerts={alertItems}
                pending={pendingItems}
                onClose={() => setAlertsOpen(false)}
                placement="sidebar"
              />
            )}
          </div>
          <div className="flex items-center gap-1">
            <ThemeToggle className="flex-1 justify-start" />
            <Button
              onClick={() => void logout()}
              variant="ghost"
              size="sm"
              icon={LogOut}
              className="min-h-11 px-3 text-muted hover:bg-surface-2 hover:text-fg"
              aria-label="Log out"
              title="Log out"
            >
              <span>Log out</span>
            </Button>
          </div>
        </div>
      </aside>
      <header className="sticky top-0 z-30 border-b border-line bg-surface/90 backdrop-blur md:hidden">
        <div className="mx-auto flex h-[68px] max-w-6xl items-center justify-between px-4 sm:px-6">
          <NavLink to="/inbox" className="flex min-w-0 items-center gap-2.5">
            <Wordmark className="min-w-0 truncate" markClassName="h-8 w-8 text-accent" />
          </NavLink>
          <div className="flex items-center gap-1.5">
            <div className="relative">
              <button
                onClick={() => setAlertsOpen((open) => !open)}
                className="relative grid h-11 w-11 place-items-center rounded-xl text-muted hover:bg-surface-2 hover:text-fg"
                aria-label={`Alerts, ${totalAttention} open`}
              >
                <Bell className="h-5 w-5" />
                {totalAttention > 0 && (
                  <span className="absolute right-1 top-1 grid min-h-5 min-w-5 place-items-center rounded-full bg-danger px-1 text-[10px] font-bold text-on-danger ring-2 ring-surface">
                    <span className="tabular-nums">{totalAttention > 9 ? "9+" : totalAttention}</span>
                  </span>
                )}
              </button>
              {alertsOpen && (
                <AlertsPanel
                  alerts={alertItems}
                  pending={pendingItems}
                  onClose={() => setAlertsOpen(false)}
                  placement="header"
                />
              )}
            </div>
            <ThemeToggle />
            <NavLink
              to="/settings"
              className={({ isActive }) =>
                `grid h-11 w-11 place-items-center rounded-xl ${
                  isActive
                    ? "bg-accent/12 text-fg ring-1 ring-inset ring-accent/30"
                    : "text-muted hover:bg-surface-2 hover:text-fg"
                }`
              }
              aria-label="Settings"
              title="Settings"
            >
              <Settings className="h-5 w-5" />
            </NavLink>
            <Button
              onClick={() => void logout()}
              variant="ghost"
              size="sm"
              icon={LogOut}
              className="h-11 px-3 text-muted hover:bg-surface-2 hover:text-fg"
              aria-label="Log out"
              title="Log out"
            >
              <span className="hidden sm:inline">Log out</span>
            </Button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-[1400px] px-4 pb-24 pt-6 sm:px-6 md:pb-10 md:pl-60">
        {children}
      </main>
      <nav className="fixed inset-x-0 bottom-0 z-30 border-t border-line bg-surface/95 pb-[env(safe-area-inset-bottom)] backdrop-blur md:hidden">
        <div className="mx-auto grid max-w-xl grid-cols-3 px-2 pt-1.5">
          {tabs.map(({ to, label, icon: Icon, key }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                `flex min-h-[60px] flex-col items-center justify-center gap-1 rounded-xl px-1 text-[11px] font-semibold ${
                  isActive ? "text-accent-ink" : "text-muted"
                }`
              }
            >
              <span className="relative">
                <Icon className="h-5 w-5" />
                {countFor(key) > 0 && (
                  <span className="absolute -right-2 -top-1 grid min-h-4 min-w-4 place-items-center rounded-full bg-accent px-1 text-[9px] font-bold text-on-accent">
                    <span className="tabular-nums">{countFor(key) > 9 ? "9+" : countFor(key)}</span>
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
