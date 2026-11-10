import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, type TeamMember } from "../api";
import { Button, Card, Input } from "./ui";

function MemberRow({ member, disabled, onSave }: { member: TeamMember; disabled: boolean; onSave: (id: number, body: { name?: string; is_active?: boolean }) => void }) {
  const [name, setName] = useState(member.name);
  return <li className="space-y-3 py-4"><label className="block text-xs font-semibold text-muted">{member.is_active ? "Active" : "Inactive"}<Input className="mt-2" aria-label={`Name for ${member.name}`} maxLength={120} value={name} onChange={event => setName(event.target.value)} /></label><div className="flex flex-wrap gap-2"><Button size="sm" disabled={disabled || !name.trim() || name.trim() === member.name} onClick={() => onSave(member.id, { name: name.trim() })}>Save name</Button><Button size="sm" disabled={disabled} onClick={() => onSave(member.id, { is_active: !member.is_active })}>{member.is_active ? "Deactivate" : "Reactivate"}</Button></div></li>;
}

export default function TeamMembersCard() {
  const client = useQueryClient();
  const [name, setName] = useState("");
  const team = useQuery({ queryKey: ["team-members"], queryFn: api.teamMembers });
  const refresh = async () => { await Promise.all([client.invalidateQueries({ queryKey: ["team-members"] }), client.invalidateQueries({ queryKey: ["auth"] })]); };
  const add = useMutation({ mutationFn: api.addTeamMember, onSuccess: async () => { setName(""); await refresh(); } });
  const edit = useMutation({ mutationFn: ({ id, body }: { id: number; body: { name?: string; is_active?: boolean } }) => api.updateTeamMember(id, body), onSuccess: refresh });
  const busy = add.isPending || edit.isPending;
  return <Card as="section" className="p-5 sm:p-6"><h2 className="text-lg font-bold">Team members</h2><p className="mt-2 text-sm leading-relaxed text-muted">Names for the “Who’s using this?” picker, not separate logins. Anyone signed in can manage this list. Deactivation keeps past usage history.</p>
    {team.isPending ? <p className="mt-4 text-sm text-muted">Loading team…</p> : team.isError ? <div className="mt-4"><p role="alert" className="text-sm text-danger-ink">Couldn’t load the team.</p><Button className="mt-2" onClick={() => void team.refetch()}>Retry</Button></div> : <ul className="mt-3 divide-y divide-line">{team.data.map(member => <MemberRow key={`${member.id}:${member.name}`} member={member} disabled={busy} onSave={(id, body) => edit.mutate({ id, body })} />)}</ul>}
    <form className="mt-4 space-y-3 border-t border-line pt-5" onSubmit={event => { event.preventDefault(); if (name.trim()) add.mutate(name.trim()); }}><label className="block text-sm font-semibold">New team member<Input className="mt-2" maxLength={120} value={name} onChange={event => setName(event.target.value)} placeholder="Name" /></label><Button type="submit" disabled={busy || !name.trim()}>Add member</Button></form>
    {(add.error || edit.error) && <p role="alert" className="mt-3 text-sm text-danger-ink">{(add.error || edit.error)?.message}</p>}
  </Card>;
}
