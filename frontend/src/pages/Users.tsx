import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Navigate } from "react-router-dom";
import { api, type UserAccount } from "../api";
import { PageHeading } from "../components/common";
import { Badge, Button, Card, Input, Select } from "../components/ui";
import { useToast } from "../useToast";
import { formatDateTime } from "../utils";

function timestamp(value: string | null) {
  return formatDateTime(value, "Never");
}

function UserCard({ user }: { user: UserAccount }) {
  const cache = useQueryClient();
  const { showToast } = useToast();
  const [resetOpen, setResetOpen] = useState(false);
  const [password, setPassword] = useState("");
  const update = useMutation({
    mutationFn: (body: { role?: "admin" | "member"; is_active?: boolean }) => api.updateUser(user.id, body),
    onSuccess: async () => { await cache.invalidateQueries({ queryKey: ["users"] }); await cache.invalidateQueries({ queryKey: ["auth"] }); },
  });
  const reset = useMutation({
    mutationFn: () => api.resetUserPassword(user.id, password),
    onSuccess: async () => { setPassword(""); setResetOpen(false); await cache.invalidateQueries({ queryKey: ["users"] }); await cache.invalidateQueries({ queryKey: ["auth"] }); showToast("Temporary password saved. Share it securely with this user."); },
    onError: () => setPassword(""),
  });
  const busy = update.isPending || reset.isPending;
  return <Card className="p-5">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <h2 className="min-w-0 break-all text-lg font-bold">{user.username}</h2>
      <Badge tone={user.is_active ? "ok" : "neutral"}>{user.is_active ? "Active" : "Inactive"}</Badge>
    </div>
    <dl className="mt-3 space-y-1 text-xs text-muted">
      <div>Created: <span className="text-fg-2">{timestamp(user.created_at)}</span></div>
      <div>Last login: <span className="text-fg-2">{timestamp(user.last_login_at)}</span></div>
    </dl>
    {user.must_set_password && <p className="mt-2 text-xs text-warn-ink">Must set a new password at next sign-in.</p>}
    <label className="mt-4 block text-sm font-semibold">Role
      <Select className="mt-1 min-h-11" aria-label={`Role for ${user.username}`} value={user.role} disabled={busy} onChange={(event) => update.mutate({ role: event.target.value as "admin" | "member" })}>
        <option value="member">Member</option><option value="admin">Admin</option>
      </Select>
    </label>
    <div className="mt-3 flex flex-wrap gap-2">
      <Button disabled={busy} onClick={() => {
        if (!user.is_active || window.confirm(`Deactivate ${user.username}? Their sessions will be signed out.`)) update.mutate({ is_active: !user.is_active });
      }}>{user.is_active ? "Deactivate" : "Reactivate"}</Button>
      <Button disabled={busy} onClick={() => { setResetOpen(!resetOpen); setPassword(""); }}>Reset password</Button>
    </div>
    {resetOpen && <form className="mt-4 space-y-3 border-t border-line pt-4" onSubmit={(event) => { event.preventDefault(); reset.mutate(); }}>
      <label className="block text-sm font-semibold">New temporary password<Input className="mt-1 min-h-11" type="password" autoComplete="new-password" minLength={10} maxLength={256} required value={password} onChange={(event) => setPassword(event.target.value)} /></label>
      <Button type="submit" variant="primary" loading={reset.isPending} disabled={busy}>Save temporary password</Button>
    </form>}
    {(update.isError || reset.isError) && <p role="alert" className="mt-3 text-sm text-danger-ink">{update.error?.message || reset.error?.message}</p>}
  </Card>;
}

export default function Users() {
  const auth = useQuery({ queryKey: ["auth"], queryFn: api.me });
  const users = useQuery({ queryKey: ["users"], queryFn: api.users, enabled: auth.data?.role === "admin" });
  const cache = useQueryClient();
  const { showToast } = useToast();
  const [open, setOpen] = useState(false);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<"admin" | "member">("member");
  const create = useMutation({
    mutationFn: () => api.createUser({ username: username.trim(), password, role }),
    onSuccess: async () => { setUsername(""); setPassword(""); setRole("member"); setOpen(false); await cache.invalidateQueries({ queryKey: ["users"] }); showToast("User created. Share their temporary password securely."); },
    onError: () => setPassword(""),
  });
  if (auth.isPending) return <p className="text-muted">Loading…</p>;
  if (auth.data?.role !== "admin") return <Navigate to="/dashboard" replace />;
  return <div className="mx-auto max-w-3xl">
    <PageHeading eyebrow="Administration" title="Users" description="Give each broker their own sign-in. Only admins can manage users and integration credentials." />
    <Card className="mb-5 p-5">
      <Button variant="primary" onClick={() => setOpen(!open)}>{open ? "Cancel new user" : "Create user"}</Button>
      {open && <form className="mt-4 space-y-4" onSubmit={(event) => { event.preventDefault(); create.mutate(); }}>
        <label className="block text-sm font-semibold">Username<Input className="mt-1 min-h-11" autoComplete="off" maxLength={120} required value={username} onChange={(event) => setUsername(event.target.value)} /></label>
        <label className="block text-sm font-semibold">Temporary password<Input className="mt-1 min-h-11" type="password" autoComplete="new-password" minLength={10} maxLength={256} required value={password} onChange={(event) => setPassword(event.target.value)} /></label>
        <label className="block text-sm font-semibold">Role<Select className="mt-1 min-h-11" value={role} onChange={(event) => setRole(event.target.value as "admin" | "member")}><option value="member">Member</option><option value="admin">Admin</option></Select></label>
        <p className="text-xs text-muted">The user must choose a new password at their first sign-in.</p>
        <Button type="submit" loading={create.isPending}>Add user</Button>
      </form>}
      {create.isError && <p role="alert" className="mt-3 text-sm text-danger-ink">{create.error.message}</p>}
    </Card>
    {users.isPending ? <p className="text-muted">Loading users…</p> : users.isError ? <p role="alert" className="text-danger-ink">{users.error.message}</p> : <div className="space-y-4">{users.data.length ? users.data.map((user) => <UserCard key={user.id} user={user} />) : <p className="text-muted">No users found.</p>}</div>}
  </div>;
}
