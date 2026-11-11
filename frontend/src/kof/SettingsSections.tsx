import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { RefreshCw } from "lucide-react";
import { api } from "../api";
import { Badge, Button, Card, Input } from "../components/ui";
import { useToast } from "../useToast";
import { kof } from "./api";
import { count } from "./format";

function when(value?: string | null) {
  if (!value) return "never";
  return new Date(value).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

export function KofSyncCard({ isAdmin = false }: { isAdmin?: boolean }) {
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const connection = useQuery({
    queryKey: ["kof", "connection"],
    queryFn: kof.connection,
    retry: false,
  });
  const status = useQuery({
    queryKey: ["kof", "sync"],
    queryFn: kof.syncStatus,
    refetchInterval: (query) => (query.state.data?.running ? 5000 : 60000),
    retry: false,
  });
  const start = useMutation({
    mutationFn: (kind: "incremental" | "full") => kof.startSync(kind),
    onSuccess: async () => {
      showToast("Sync started.");
      await queryClient.invalidateQueries({ queryKey: ["kof", "sync"] });
    },
    onError: (issue: Error) => showToast(issue.message),
  });
  const connect = useMutation({
    mutationFn: () => kof.connect({ username, password }),
    onSuccess: async () => {
      setUsername("");
      setPassword("");
      showToast("Connected — first full sync takes about 20 minutes");
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["kof", "connection"] }),
        queryClient.invalidateQueries({ queryKey: ["kof", "sync"] }),
      ]);
    },
  });
  const disconnect = useMutation({
    mutationFn: kof.disconnect,
    onSuccess: async () => {
      showToast("Disconnected from King of Freight.");
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["kof", "connection"] }),
        queryClient.invalidateQueries({ queryKey: ["kof", "sync"] }),
      ]);
    },
    onError: (issue: Error) => showToast(issue.message),
  });
  const data = status.data;
  const run = data?.last_run;

  return (
    <Card as="section" id="sync" className="scroll-mt-6 p-5 sm:p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-bold text-fg">King of Freight sync</h2>
          <p className="mt-1 text-sm text-muted">
            Copies your loads, customers and sales lists from kingsoffreight.com. Read-only: nothing is ever changed there.
          </p>
        </div>
        {data && (
          <Badge tone={!data.configured ? "neutral" : run?.status === "error" ? "danger" : data.running ? "info" : "ok"}>
            {!data.configured ? "Not set up" : data.running ? "Syncing" : run?.status === "error" ? "Error" : "Connected"}
          </Badge>
        )}
      </div>
      {status.isError ? (
        <p className="mt-4 text-sm text-danger-ink">{(status.error as Error).message}</p>
      ) : !data || connection.isPending ? null : connection.isError ? (
        <p role="alert" className="mt-4 text-sm text-danger-ink">
          {(connection.error as Error).message}
        </p>
      ) : !connection.data?.configured && !isAdmin ? (
        <p className="mt-4 text-sm text-muted">Ask your admin to connect King of Freight. Sync status and Sync now will appear here once connected.</p>
      ) : !connection.data?.configured ? (
        <div className="mt-4">
          <h3 className="font-semibold text-fg">Connect King of Freight</h3>
          <p className="mt-1 text-sm text-muted">
            Enter your King of Freight login to start syncing your loads.
          </p>
          <form
            className="mt-4 grid gap-3 sm:grid-cols-2"
            autoComplete="off"
            onSubmit={(event) => {
              event.preventDefault();
              connect.mutate();
            }}
          >
            <label className="block">
              <span className="mb-1.5 block text-sm font-semibold text-fg-2">Username</span>
              <Input
                autoComplete="off"
                required
                value={username}
                onChange={(event) => setUsername(event.target.value)}
              />
            </label>
            <label className="block">
              <span className="mb-1.5 block text-sm font-semibold text-fg-2">Password</span>
              <Input
                type="password"
                autoComplete="new-password"
                required
                value={password}
                onChange={(event) => setPassword(event.target.value)}
              />
            </label>
            {connect.isError && (
              <p role="alert" className="text-sm text-danger-ink sm:col-span-2">
                {(connect.error as Error).message}
              </p>
            )}
            <div className="sm:col-span-2">
              <Button type="submit" variant="primary" loading={connect.isPending} full>
                Connect
              </Button>
            </div>
          </form>
        </div>
      ) : (
        <>
          {connection.data?.source === "app" && (
            <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-xl bg-surface-2 px-4 py-3">
              <p className="min-w-0 truncate text-sm text-fg-2">
                Connected as <span className="font-semibold text-fg">{connection.data.username}</span>
              </p>
              {isAdmin && <Button
                variant="secondary"
                loading={disconnect.isPending}
                onClick={() => {
                  if (window.confirm("Disconnect your King of Freight account?")) {
                    disconnect.mutate();
                  }
                }}
              >
                Disconnect
              </Button>}
            </div>
          )}
          {connection.data?.source === "env" && (
            <p className="mt-4 rounded-xl bg-surface-2 px-4 py-3 text-sm text-fg-2">
              Configured on the server
            </p>
          )}
          <dl className="mt-4 grid gap-3 sm:grid-cols-3">
            <div className="rounded-xl bg-surface-2 px-3 py-2">
              <dt className="text-[11px] font-bold uppercase tracking-[0.12em] text-muted">Loads synced</dt>
              <dd className="mt-0.5 font-bold tabular-nums text-fg">{count(data.load_count)}</dd>
            </div>
            <div className="rounded-xl bg-surface-2 px-3 py-2">
              <dt className="text-[11px] font-bold uppercase tracking-[0.12em] text-muted">Last success</dt>
              <dd className="mt-0.5 font-bold text-fg">{when(data.last_success_at)}</dd>
            </div>
            <div className="rounded-xl bg-surface-2 px-3 py-2">
              <dt className="text-[11px] font-bold uppercase tracking-[0.12em] text-muted">Automatic</dt>
              <dd className="mt-0.5 font-bold text-fg">{data.enabled ? "Every 15 min" : "Off"}</dd>
            </div>
          </dl>
          {run?.status === "error" && run.error && (
            <p role="alert" className="mt-3 rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger-ink">
              Last {run.kind} sync failed at {when(run.finished_at ?? run.started_at)}: {run.error}
            </p>
          )}
          <div className="mt-4 flex flex-wrap gap-2">
            <Button
              variant="primary"
              icon={RefreshCw}
              disabled={data.running || start.isPending}
              onClick={() => start.mutate("incremental")}
            >
              Sync now
            </Button>
            <Button disabled={data.running || start.isPending} onClick={() => start.mutate("full")}>
              Full refresh
            </Button>
          </div>
        </>
      )}
    </Card>
  );
}

export function ChangePasswordCard() {
  const auth = useQuery({ queryKey: ["auth"], queryFn: api.me });
  const { showToast } = useToast();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [error, setError] = useState("");
  const change = useMutation({
    mutationFn: () => api.changePassword(current, next),
    onSuccess: () => {
      setCurrent("");
      setNext("");
      showToast("Password changed.");
    },
    onError: (issue: Error) => setError(issue.message),
  });
  if (!auth.data?.username) return null;

  return (
    <Card as="section" className="p-5 sm:p-6">
      <h2 className="text-lg font-bold text-fg">Password</h2>
      <p className="mt-1 text-sm text-muted">Signed in as {auth.data.username}. Changing it signs out your other devices.</p>
      <form
        className="mt-4 grid gap-3 sm:grid-cols-[1fr_1fr_auto] sm:items-end"
        onSubmit={(event) => {
          event.preventDefault();
          setError("");
          if (next.length < 10) {
            setError("Use at least 10 characters.");
            return;
          }
          change.mutate();
        }}
      >
        <label className="block">
          <span className="mb-1.5 block text-sm font-semibold text-fg-2">Current password</span>
          <Input type="password" autoComplete="current-password" required value={current} onChange={(event) => setCurrent(event.target.value)} />
        </label>
        <label className="block">
          <span className="mb-1.5 block text-sm font-semibold text-fg-2">New password</span>
          <Input type="password" autoComplete="new-password" required value={next} onChange={(event) => setNext(event.target.value)} />
        </label>
        <Button type="submit" loading={change.isPending}>
          Change password
        </Button>
      </form>
      {error && (
        <p role="alert" className="mt-3 text-sm text-danger-ink">
          {error}
        </p>
      )}
    </Card>
  );
}
