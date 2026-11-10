import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../api";
import { Button, Card, Input } from "./ui";

export default function AdminClaimBanner() {
  const cache = useQueryClient();
  const [open, setOpen] = useState(false);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const claim = useMutation({
    mutationFn: () => api.claimAdmin(username.trim(), password),
    onSuccess: async () => {
      setPassword("");
      await cache.invalidateQueries();
    },
    onError: () => setPassword(""),
  });
  return <Card className="mb-5 border-accent/40 p-4">
    <p className="font-semibold text-fg">You’re signed in with the shared workspace password.</p>
    <p className="mt-1 text-sm text-muted">The owner should create the admin account, then add a separate username for each broker.</p>
    {!open ? <Button className="mt-3" variant="primary" onClick={() => setOpen(true)}>Create the admin account</Button> :
      <form className="mt-4 space-y-3" onSubmit={(event) => { event.preventDefault(); claim.mutate(); }}>
        <label className="block text-sm font-semibold">Admin username<Input className="mt-1" autoComplete="username" required maxLength={120} value={username} onChange={(event) => setUsername(event.target.value)} /></label>
        <label className="block text-sm font-semibold">New password<Input className="mt-1" type="password" autoComplete="new-password" minLength={10} maxLength={256} required value={password} onChange={(event) => setPassword(event.target.value)} /></label>
        <div className="flex gap-2"><Button type="submit" variant="primary" loading={claim.isPending}>Create admin account</Button><Button disabled={claim.isPending} onClick={() => { setOpen(false); setPassword(""); }}>Cancel</Button></div>
      </form>}
    {claim.isError && <p role="alert" className="mt-3 text-sm text-danger-ink">{claim.error.message}</p>}
  </Card>;
}
