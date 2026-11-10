import type {
  Alert,
  BookPayload,
  BrokerPrefs,
  BrokerPrefsUpdate,
  Carrier,
  Communication,
  Load,
  LoadDetail,
  NewLoad,
  StopTimezones,
  StatusUpdate,
  TrackingSummary,
} from "./types";

type RequestOptions = RequestInit & { redirectOn401?: boolean };

export type UserAccount = {
  id: number;
  username: string;
  role: "admin" | "member";
  is_active: boolean;
  must_set_password: boolean;
  created_at: string;
  last_login_at: string | null;
};

export class ApiError extends Error {
  constructor(message: string, public status: number) {
    super(message);
  }
}

export type AssistantConnection = { configured: boolean; source: "env" | "app" | null };
export type TwilioConnection = {
  configured: boolean;
  source: "env" | "app" | null;
  account_sid: string | null;
  from_number: string | null;
  sms: "twilio" | "mock";
};
export type TwilioInput = { account_sid: string; auth_token: string; from_number: string };
export type AssistantMessage = { role: "user" | "assistant"; content: string };
export type OutlookConnection = {
  configured: boolean; source: "app" | "env" | null; client_id: string | null;
  redirect_uri: string; status: "not_set_up" | "ready" | "connected" | "needs_reconnect";
  account: { email: string; name: string } | null;
};
export type AssistantReply = {
  reply: string;
  loads: { source: "kof" | "operational"; id: number; label: string }[];
  actions?: (KofTextAction | KofEmailAction)[];
};
export type KofTextAction = { type: "send_kof_text"; order_no: number; recipient: "carrier" | "dispatch"; to_label: string; body: string };
export type KofEmailAction = { type: "send_kof_email"; order_no: number; recipient: "carrier" | "dispatch"; to_label: string; subject: string; body: string };
export type KofEmail = { id: number; direction: string; from_addr: string | null; to_addr: string | null; subject: string; content: string; created_at: string };
export type KofMessage = {
  id: number; order_no: number | null; direction: "out" | "in";
  to_phone: string | null; from_phone: string | null; body: string;
  status: "sent" | "failed" | "received" | "ambiguous"; error: string | null;
  created_at: string; match_method: string | null; candidate_order_nos: number[];
  parsed_status: string | null; parsed_eta: string | null; parsed_summary: string | null;
  confirmed: false;
};

export async function request<T>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const { redirectOn401 = true, headers: initialHeaders, ...init } = options;
  const headers = new Headers(initialHeaders);
  if (init.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(`/api${path}`, {
    ...init,
    headers,
    credentials: "include",
  });
  if (
    response.status === 401 &&
    redirectOn401 &&
    window.location.pathname !== "/login" &&
    !window.location.pathname.startsWith("/t/")
  ) {
    window.location.assign("/login");
  }
  if (!response.ok) {
    const body = await response.text();
    let message = body || `Request failed (${response.status})`;
    try {
      const parsed = JSON.parse(body) as { detail?: string };
      message = parsed.detail ?? message;
    } catch {
      message = body || message;
    }
    throw new ApiError(message, response.status);
  }
  if (response.status === 204) return undefined as T;
  const contentType = response.headers.get("content-type") ?? "";
  if (contentType.includes("application/json")) {
    return (await response.json()) as T;
  }
  return (await response.text()) as T;
}

const json = (method: string, body?: unknown): RequestInit => ({
  method,
  ...(body === undefined ? {} : { body: JSON.stringify(body) }),
});

export type CustomerUpdateDraft = {
  id: number; order_no: number; customer: string | null;
  source_refs: { channel: string; id: number; excerpt: string; received_at: string }[];
  summary: string; status: string; eta: string | null; confidence: number;
  to_email: string; subject: string; body: string; state: "pending" | "sent" | "dismissed";
  version: number; updated_at: string; send_started_at: string | null; error: string | null;
};

export const api = {
  customerUpdates: () => request<{ count: number; drafts: CustomerUpdateDraft[]; email_mode: "outlook" | "graph" | "mock" }>("/customer-updates"),
  editCustomerUpdate: (id: number, body: { version: number; to_email: string; subject: string; body: string }) => request<CustomerUpdateDraft>(`/customer-updates/${id}`, json("PATCH", body)),
  approveCustomerUpdate: (id: number, version: number) => request<CustomerUpdateDraft>(`/customer-updates/${id}/approve`, json("POST", { version })),
  dismissCustomerUpdate: (id: number, version: number) => request<CustomerUpdateDraft>(`/customer-updates/${id}/dismiss`, json("POST", { version })),
  integrationsStatus: () => request<{ llm: "anthropic" | "mock"; sms: "twilio" | "mock"; twilio_configured: boolean; email: "outlook" | "graph" | "mock"; email_live: boolean; sms_live: boolean; assistant_live: boolean }>("/integrations/status"),
  kofMessages: (orderNo: number) => request<KofMessage[]>(`/kof/loads/${orderNo}/messages`),
  sendKofText: (orderNo: number, recipient: KofTextAction["recipient"], body: string) => request<KofMessage>(`/kof/loads/${orderNo}/messages`, json("POST", { recipient, body })),
  kofEmails: (orderNo: number) => request<KofEmail[]>(`/kof/loads/${orderNo}/emails`),
  kofEmailDraft: (orderNo: number) => request<KofEmailAction>(`/kof/loads/${orderNo}/emails/draft`),
  sendKofEmail: (action: KofEmailAction) => request<KofEmail>(`/kof/loads/${action.order_no}/emails`, json("POST", { recipient: action.recipient, subject: action.subject, body: action.body })),
  outlookConnection: () => request<OutlookConnection>("/email/connection"),
  saveOutlookConnection: (body: { client_id: string; client_secret: string }) => request<OutlookConnection>("/email/connection", json("PUT", body)),
  removeOutlookConnection: () => request<void>("/email/connection", json("DELETE")),
  disconnectOutlook: () => request<void>("/email/account", json("DELETE")),
  twilioConnection: () => request<TwilioConnection>("/integrations/twilio/connection"),
  saveTwilioConnection: (body: TwilioInput) => request<TwilioConnection>("/integrations/twilio/connection", json("PUT", body)),
  removeTwilioConnection: () => request<void>("/integrations/twilio/connection", json("DELETE")),
  testTwilio: (to: string) => request<{ sent: boolean }>("/integrations/twilio/test", json("POST", { to })),
  assistantConnection: () => request<AssistantConnection>("/assistant/connection"),
  saveAssistantKey: (api_key: string) => request<AssistantConnection>("/assistant/connection", json("PUT", { api_key })),
  removeAssistantKey: () => request<void>("/assistant/connection", json("DELETE")),
  assistantChat: (messages: AssistantMessage[]) => request<AssistantReply>("/assistant/chat", json("POST", { messages })),
  login: ({ username, password }: { username?: string; password: string }) =>
    request<{ authenticated: boolean; username: string | null; must_set_password: boolean }>(
      "/auth/login",
      {
        ...json("POST", { username: username?.trim() || null, password }),
        redirectOn401: false,
      },
    ),
  setPassword: (new_password: string) =>
    request<{ ok: boolean }>("/auth/set-password", json("POST", { new_password })),
  changePassword: (current_password: string, new_password: string) =>
    request<{ ok: boolean }>(
      "/auth/change-password",
      json("POST", { current_password, new_password }),
    ),
  logout: () => request<{ authenticated: boolean }>("/auth/logout", json("POST")),
  claimAdmin: (username: string, password: string) => request<UserAccount>("/admin/claim", json("POST", { username, password })),
  users: () => request<UserAccount[]>("/admin/users"),
  createUser: (body: { username: string; password: string; role: "admin" | "member" }) => request<UserAccount>("/admin/users", json("POST", body)),
  updateUser: (id: number, body: { role?: "admin" | "member"; is_active?: boolean }) => request<UserAccount>(`/admin/users/${id}`, json("PATCH", body)),
  resetUserPassword: (id: number, password: string) => request<UserAccount>(`/admin/users/${id}/reset-password`, json("POST", { password })),
  me: () =>
    request<{
      authenticated: boolean;
      broker_timezone: string;
      username?: string | null;
      must_set_password?: boolean;
      role: "admin" | "member" | null;
      can_claim_admin: boolean;
    }>("/auth/me"),
  settings: () => request<BrokerPrefs>("/settings"),
  updateSettings: (partial: BrokerPrefsUpdate) =>
    request<BrokerPrefs>("/settings", json("PUT", partial)),
  loads: (tab: "truckstop" | "delivery", includeDelivered = false) =>
    request<Load[]>(
      `/loads?tab=${tab}&include_delivered=${includeDelivered ? "true" : "false"}`,
    ),
  stopTimezones: () => request<StopTimezones>("/meta/stop-timezones"),
  load: (id: number) => request<LoadDetail>(`/loads/${id}`),
  createLoad: (payload: NewLoad) =>
    request<Load>("/loads", json("POST", payload)),
  patchLoad: (id: number, payload: Partial<Load>) =>
    request<Load>(`/loads/${id}`, json("PATCH", payload)),
  postLoad: (id: number) =>
    request<Load>(`/loads/${id}/post`, json("POST")),
  postText: (id: number) => request<string>(`/loads/${id}/post-text`),
  bookLoad: (id: number, payload: BookPayload) =>
    request<Load>(`/loads/${id}/book`, json("POST", payload)),
  manualStatus: (
    id: number,
    payload: { status: string; note?: string; eta?: string },
  ) => request<StatusUpdate>(`/loads/${id}/status`, json("POST", payload)),
  pendingUpdates: () =>
    request<StatusUpdate[]>("/status-updates?state=pending_approval"),
  approve: (
    id: number,
    payload: { subject: string; body: string; channel: "email" | "sms" },
  ) => request<StatusUpdate>(`/status-updates/${id}/approve`, json("POST", payload)),
  skip: (id: number, apply: boolean) =>
    request<StatusUpdate>(
      `/status-updates/${id}/skip`,
      json("POST", { apply }),
    ),
  verifyCarrier: (mc_number: string) =>
    request<Carrier>("/carriers/verify", json("POST", { mc_number })),
  sendCheckin: (id: number) =>
    request<LoadDetail["checkins"][number]>(
      `/checkins/${id}/send-now`,
      json("POST"),
    ),
  dismissAlert: (id: number) =>
    request<LoadDetail["checkins"][number]>(
      `/checkins/${id}/dismiss-alert`,
      json("POST"),
    ),
  alerts: () => request<Alert[]>("/alerts"),
  inbox: () => request<Communication[]>("/inbox"),
  archive: (id: number) =>
    request<Communication>(`/inbox/${id}/archive`, json("POST")),
  uploadBol: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<Communication>("/bol/upload", { method: "POST", body: form });
  },
  createLoadFromInbox: (
    id: number,
    payload: Record<string, unknown>,
  ) => request<Load>(`/inbox/${id}/create-load`, json("POST", payload)),
  sendTrackingLink: (id: number) =>
    request<Communication>(`/loads/${id}/send-tracking-link`, json("POST")),
  simulateSms: (from: string, body: string) =>
    request<{ accepted: boolean }>(
      "/dev/simulate/sms-reply",
      json("POST", { from, body }),
    ),
  simulateEmail: (from: string, subject: string, body: string) =>
    request<{ accepted: boolean }>(
      "/dev/simulate/inbound-email",
      json("POST", { from, subject, body }),
    ),
  runTick: () =>
    request<{ completed: boolean }>("/dev/run-tick", json("POST")),
  trackingSummary: (token: string) =>
    request<TrackingSummary>(`/track/${encodeURIComponent(token)}`, {
      redirectOn401: false,
    }),
  trackingPing: (
    token: string,
    payload: { lat: number; lng: number; accuracy_m?: number },
  ) =>
    request<{ stored: boolean }>(
      `/track/${encodeURIComponent(token)}/ping`,
      json("POST", payload),
    ),
};
