import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api";
import { Button, Card } from "./ui";
import { Wordmark } from "./Brand";

export default function OperatorChooser({ onSelected, onCancel, onLogout, allowClear = false }: { onSelected: () => void; onCancel?: () => void; onLogout: () => void; allowClear?: boolean }) {
  const queryClient = useQueryClient();
  const team = useQuery({ queryKey: ["team-members"], queryFn: api.teamMembers });
  const select = useMutation({ mutationFn: api.selectOperator, onSuccess: async session => {
    queryClient.setQueryData(["auth"], session);
    await queryClient.invalidateQueries({ queryKey: ["usage"] });
    onSelected();
  } });
  const active = team.data?.filter(member => member.is_active) ?? [];
  return <main className="grid min-h-screen place-items-center bg-bg px-5 py-10 text-fg">
    <div className="w-full max-w-md space-y-7">
      <Wordmark markClassName="h-9 w-9 text-accent" />
      <div><p className="text-xs font-bold uppercase tracking-widest text-accent">Your workspace</p><h1 className="mt-2 text-3xl font-extrabold">Who’s using this?</h1><p className="mt-3 text-sm leading-relaxed text-muted">Choose your name so activity is credited to you. This doesn’t change your login or permissions.</p></div>
      {team.isPending ? <p className="text-muted">Loading team…</p> : team.isError ? <Card className="p-5"><p role="alert" className="text-sm text-danger-ink">Couldn’t load the team.</p><Button className="mt-3" onClick={() => void team.refetch()}>Retry</Button></Card> : <div className="space-y-3">{active.map(member => <Button autoFocus={member.id === active[0]?.id} key={member.id} className="min-h-20 w-full justify-between px-6 text-xl" disabled={select.isPending} onClick={() => select.mutate(member.id)}><span className="break-words text-left">{member.name}</span><span aria-hidden="true" className="ml-4 text-muted">→</span></Button>)}{!active.length && <p className="text-sm text-muted">No active team members. Manage the team in Settings.</p>}</div>}
      {select.isError && <p role="alert" className="text-sm text-danger-ink">{select.error.message}</p>}
      <div className="flex flex-wrap gap-3">{onCancel && <Button onClick={onCancel}>Back</Button>}{allowClear && <Button disabled={select.isPending} onClick={() => select.mutate(null)}>Use login identity</Button>}<Button variant="ghost" onClick={onLogout}>Log out</Button></div>
      <p className="text-xs text-muted">Separate accounts and permissions are still managed in Users.</p>
    </div>
  </main>;
}
