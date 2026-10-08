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
  StatusUpdate,
  TrackingSummary,
} from "./types";

type RequestOptions = RequestInit & { redirectOn401?: boolean };

async function request<T>(
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
    throw new Error(message);
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

export const api = {
  login: (password: string) =>
    request<{ authenticated: boolean }>("/auth/login", {
      ...json("POST", { password }),
      redirectOn401: false,
    }),
  logout: () => request<{ authenticated: boolean }>("/auth/logout", json("POST")),
  me: () =>
    request<{ authenticated: boolean; broker_timezone: string }>("/auth/me"),
  settings: () => request<BrokerPrefs>("/settings"),
  updateSettings: (partial: BrokerPrefsUpdate) =>
    request<BrokerPrefs>("/settings", json("PUT", partial)),
  loads: (tab: "truckstop" | "delivery", includeDelivered = false) =>
    request<Load[]>(
      `/loads?tab=${tab}&include_delivered=${includeDelivered ? "true" : "false"}`,
    ),
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
