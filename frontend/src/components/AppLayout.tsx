import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Bell,
  Boxes,
  Briefcase,
  Building2,
  LayoutDashboard,
  LogOut,
  Mail,
  Package,
  Radar,
  RefreshCw,
  Route,
  Settings,
  Truck,
  Warehouse,
  X,
} from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";
import type { ReactNode } from "react";
import { NavLink, useLocation, useNavigate } from "react-router-dom";
import { api } from "../api";
import { kof } from "../kof/api";
import type { Alert, StatusUpdate } from "../types";
import { formatClock } from "../utils";
import { Badge, Button, Card } from "./ui";
import { Wordmark } from "./Brand";
import ThemeToggle from "./ThemeToggle";
import AssistantWidget from "./AssistantWidget";

const tabs = [
  { to: "/customer-updates", label: "Customer updates", icon: Mail, key: "customer-updates" },
  { to: "/inbox", label: "Inbox", icon: Mail, key: "inbox" },
  { to: "/truckstop", label: "TruckStop", icon: Truck, key: "truckstop" },
  { to: "/status", label: "Delivery Status", icon: Boxes, key: "delivery" },
];

const kofTabs = [
  { to: "/dashboard", label: "Dashboard", short: "Dashboard", icon: LayoutDashboard },
  { to: "/tracking", label: "Tracking", short: "Tracking", icon: Radar },
  { to: "/loads", label: "Loads", short: "Loads", icon: Package },
  { to: "/customers", label: "Customers", short: "Customers", icon: Building2 },
  { to: "/branches", label: "Branches", short: "Branches", icon: Warehouse },
  { to: "/carriers", label: "Carriers & lanes", short: "Carriers", icon: Route },
  { to: "/sales", label: "Sales", short: "Sales", icon: Briefcase },
];

const mobileTabs = [
  { to: "/dashboard", label: "Dashboard", icon: LayoutDashboard, key: "" },
  { to: "/customer-updates", label: "Updates", icon: Mail, key: "customer-updates" },
  { to: "/tracking", label: "Tracking", icon: Radar, key: "" },
  { to: "/loads", label: "Loads", icon: Package, key: "" },
  { to: "/status", label: "Status", icon: Boxes, key: "delivery" },
  { to: "/inbox", label: "Inbox", icon: Mail, key: "inbox" },
  { to: "/truckstop", label: "TruckStop", icon: Truck, key: "truckstop" },
  { to: "/customers", label: "Customers", icon: Building2, key: "" },
  { to: "/branches", label: "Branches", icon: Warehouse, key: "" },
  { to: "/carriers", label: "Carriers", icon: Route, key: "" },
  { to: "/sales", label: "Sales", icon: Briefcase, key: "" },
];

function syncLabel(lastSuccess: string | null | undefined, running: boolean) {
  if (running) return "Syncing with KOF…";
  if (!lastSuccess) return "Not synced yet";
  const minutes = Math.max(0, Math.round((Date.now() - new Date(lastSuccess).getTime()) / 60000));
  if (minutes < 1) return "Synced just now";
  if (minutes < 60) return `Synced ${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 48) return `Synced ${hours}h ago`;
  return `Synced ${Math.round(hours / 24)}d ago`;
}

const sideLink = ({ isActive }: { isActive: boolean }) =>
  `flex min-h-11 md:min-h-10 items-center gap-3 rounded-r-xl border-l-2 px-3 text-sm font-semibold transition-colors duration-150 ${
    isActive ? "border-accent bg-surface-3 text-fg" : "border-transparent text-fg-2 hover:bg-surface-2"
  }`;

function AlertsPanel({
  id,
  alerts,
  pending,
  onClose,
  placement,
}: {
  id: string;
  alerts: Alert[];
  pending: StatusUpdate[];
  onClose: () => void;
  placement: "header" | "sidebar";
}) {
  return (
    <Card
      id={id}
      className={`absolute z-40 overflow-hidden shadow-xl motion-safe:animate-[fw-in_160ms_ease-out] ${
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
              <p className="mt-1 line-clamp-2 text-xs text-fg-2">
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
            <p className="mt-1 text-xs text-fg-2 tabular-nums">
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
  const sidebarAlertsId = useId();
  const headerAlertsId = useId();
  const alertsTrigger = useRef<HTMLButtonElement | null>(null);
  const sidebarAlertsButton = useRef<HTMLButtonElement>(null);
  const headerAlertsButton = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    const titles: Record<string, string> = {
      "/inbox": "Inbox · Fifth Wheel",
      "/truckstop": "TruckStop · Fifth Wheel",
      "/status": "Delivery Status · Fifth Wheel",
      "/settings": "Settings · Fifth Wheel",
      "/dashboard": "Dashboard · Fifth Wheel",
      "/tracking": "Tracking · Fifth Wheel",
      "/loads": "Loads · Fifth Wheel",
      "/customers": "Customers · Fifth Wheel",
      "/branches": "Branches · Fifth Wheel",
      "/carriers": "Carriers & lanes · Fifth Wheel",
      "/sales": "Sales · Fifth Wheel",
    };
    document.title = titles[location.pathname] ?? "Fifth Wheel";
  }, [location.pathname]);
  useEffect(() => {
    if (!alertsOpen) return;
    function closeOnEscape(event: KeyboardEvent) {
      if (event.key !== "Escape") return;
      event.preventDefault();
      setAlertsOpen(false);
      alertsTrigger.current?.focus();
    }
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [alertsOpen]);
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
  const sync = useQuery({
    queryKey: ["kof", "sync"],
    queryFn: kof.syncStatus,
    refetchInterval: 60_000,
    retry: false,
  });
  const alertItems = alerts.data ?? [];
  const pendingItems = pending.data ?? [];
  const totalAttention = alertItems.length + pendingItems.length;
  const countFor = (key: string) => {
    if (key === "customer-updates") return customerUpdates.data?.count ?? 0;
    if (key === "inbox") return inbox.data?.length ?? 0;
    if (key === "truckstop") return truckstop.data?.length ?? 0;
    return delivery.data?.length ?? 0;
  };
  const customerUpdates = useQuery({ queryKey: ["customer-updates"], queryFn: api.customerUpdates, refetchInterval: 30000 });
  async function logout() {
    await api.logout();
    await queryClient.clear();
    navigate("/login");
  }
  function toggleAlerts(trigger: HTMLButtonElement | null) {
    if (alertsOpen) {
      setAlertsOpen(false);
      return;
    }
    alertsTrigger.current = trigger;
    setAlertsOpen(true);
  }
  return (
    <div className="min-h-screen bg-bg pb-24 text-fg md:pb-0">
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:left-3 focus:top-3 focus:z-[200] rounded-lg bg-surface px-4 py-2 text-sm font-semibold text-fg shadow-card">Skip to content</a>
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-60 flex-col border-r border-line bg-surface md:flex">
        <NavLink to="/dashboard" className="flex h-[68px] shrink-0 items-center gap-2.5 px-5">
          <Wordmark className="min-w-0 truncate" markClassName="h-8 w-8 text-accent" />
        </NavLink>
        <div className="flex-1 overflow-y-auto">
        <p className="px-5 pt-3 text-[11px] font-bold uppercase tracking-[0.16em] text-muted">Insights</p>
        <nav aria-label="Insights" className="space-y-0.5 px-3 pt-1.5">
          {kofTabs.map(({ to, label, icon: Icon }) => (
            <NavLink key={to} to={to} className={sideLink}>
              <Icon className="h-4 w-4 shrink-0" />
              <span className="min-w-0 flex-1 truncate">{label}</span>
            </NavLink>
          ))}
        </nav>
        <p className="px-5 pt-5 text-[11px] font-bold uppercase tracking-[0.16em] text-muted">Operate</p>
        <nav aria-label="Main" className="space-y-0.5 px-3 pt-1.5">
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
                    className="min-h-5 min-w-5 rounded-full px-2 py-0.5 text-[11px]"
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
        </div>
        <div className="border-t border-line p-3">
          <NavLink
            to="/settings#sync"
            className="mb-1 flex min-h-10 items-center gap-2.5 rounded-xl px-3 text-xs font-semibold text-muted hover:bg-surface-2 hover:text-fg"
          >
            <RefreshCw
              className={`h-3.5 w-3.5 shrink-0 ${sync.data?.running ? "motion-safe:animate-spin" : ""} ${
                sync.data?.last_run?.status === "error" ? "text-danger-ink" : ""
              }`}
            />
            <span className="truncate">
              {sync.isError || !sync.data?.configured
                ? "KOF sync not set up"
                : sync.data.last_run?.status === "error"
                  ? "Last sync failed"
                  : syncLabel(sync.data.last_success_at, sync.data.running)}
            </span>
          </NavLink>
          <div className="relative mb-1">
            <button
              ref={sidebarAlertsButton}
              onClick={() => toggleAlerts(sidebarAlertsButton.current)}
              className="flex min-h-11 w-full items-center gap-3 rounded-xl px-3 text-left text-sm font-semibold text-fg-2 transition-colors duration-150 hover:bg-surface-2"
              aria-expanded={alertsOpen}
              aria-controls={sidebarAlertsId}
            >
              <span className="relative grid h-8 w-8 shrink-0 place-items-center">
                <Bell className="h-5 w-5" />
                {totalAttention > 0 && (
                  <span className="absolute -right-1 -top-1 grid min-h-5 min-w-5 place-items-center rounded-full bg-danger px-1 text-[11px] font-bold text-on-danger ring-2 ring-surface">
                    <span className="tabular-nums">{totalAttention > 9 ? "9+" : totalAttention}</span>
                  </span>
                )}
              </span>
              Alerts
            </button>
            {alertsOpen && (
              <AlertsPanel
                id={sidebarAlertsId}
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
          <NavLink to="/dashboard" className="flex min-w-0 items-center gap-2.5">
            <Wordmark className="min-w-0 truncate" markClassName="h-8 w-8 text-accent" />
          </NavLink>
          <div className="flex items-center gap-1.5">
            <div className="relative">
              <button
                ref={headerAlertsButton}
                onClick={() => toggleAlerts(headerAlertsButton.current)}
                className="relative grid h-11 w-11 place-items-center rounded-xl text-muted hover:bg-surface-2 hover:text-fg"
                aria-expanded={alertsOpen}
                aria-controls={headerAlertsId}
              >
                <Bell className="h-5 w-5" />
                <span className="sr-only">Alerts</span>
                {totalAttention > 0 && (
                  <span className="absolute right-1 top-1 grid min-h-5 min-w-5 place-items-center rounded-full bg-danger px-1 text-[11px] font-bold text-on-danger ring-2 ring-surface">
                    <span className="tabular-nums">{totalAttention > 9 ? "9+" : totalAttention}</span>
                  </span>
                )}
              </button>
              {alertsOpen && (
                <AlertsPanel
                  id={headerAlertsId}
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
      <main id="main" tabIndex={-1} className="mx-auto max-w-[1400px] px-4 pb-24 pt-6 sm:px-6 md:pb-10 md:pl-60 focus:outline-none">
        {children}
      </main>
      <nav aria-label="Main" className="fixed inset-x-0 bottom-0 z-30 border-t border-line bg-surface/95 pb-[env(safe-area-inset-bottom)] backdrop-blur md:hidden">
        <div className="flex snap-x gap-0.5 overflow-x-auto px-2 pt-1.5 [scrollbar-width:none]">
          {mobileTabs.map(({ to, label, icon: Icon, key }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                `flex min-h-[60px] min-w-[72px] flex-1 snap-start flex-col items-center justify-center gap-1 rounded-xl px-1 text-[11px] font-semibold ${
                  isActive ? "text-accent-ink" : "text-muted"
                }`
              }
            >
              <span className="relative">
                <Icon className="h-5 w-5" />
                {key && countFor(key) > 0 && (
                  <span className="absolute -right-2 -top-1 grid min-h-5 min-w-5 place-items-center rounded-full bg-accent px-1 text-[11px] font-bold text-on-accent">
                    <span className="tabular-nums">{countFor(key) > 9 ? "9+" : countFor(key)}</span>
                  </span>
                )}
              </span>
              {label}
            </NavLink>
          ))}
        </div>
      </nav>
      <AssistantWidget />
    </div>
  );
}
