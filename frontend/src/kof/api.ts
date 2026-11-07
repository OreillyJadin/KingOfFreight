import { request } from "../api";

export type KofStage =
  | "pending"
  | "booked"
  | "confirmation"
  | "awaiting_pickup"
  | "in_transit"
  | "awaiting_delivery"
  | "delivered"
  | "billed"
  | "paid";

export type KofLoadRow = {
  order_no: number;
  date_of_sale: string | null;
  customer: string | null;
  branch: string | null;
  carrier: string | null;
  mc: string | null;
  origin_city: string | null;
  origin_state: string | null;
  dest_city: string | null;
  dest_state: string | null;
  pick_at: string | null;
  pick_tz: string | null;
  delivery_at: string | null;
  drop_tz: string | null;
  equipment: string | null;
  weight: number | null;
  price: number | null;
  cost: number | null;
  profit: number | null;
  stage: KofStage;
  billed_status: string | null;
  paid_status: string | null;
  late: boolean;
};

export type KofParty = {
  company: string | null;
  address: string | null;
  city: string | null;
  state: string | null;
  zip: string | null;
  phone: string | null;
  email: string | null;
};

export type KofLoadDetail = KofLoadRow & {
  shipper: KofParty;
  consignee: KofParty;
  po: string | null;
  pu: string | null;
  invoice_no: string | null;
  product_description: string | null;
  carrier_contact: {
    name: string | null;
    phone: string | null;
    email: string | null;
    dispatch_contact: string | null;
    dispatch_phone: string | null;
  };
  notes: { at: string | null; author: string | null; text: string }[];
  log: { at: string | null; text: string }[];
  raw: Record<string, string>;
};

export type KofSyncStatus = {
  configured: boolean;
  enabled: boolean;
  running: boolean;
  load_count: number;
  last_run: {
    id: number;
    kind: "full" | "incremental";
    status: "running" | "ok" | "error";
    started_at: string;
    finished_at: string | null;
    loads_upserted: number;
    error: string | null;
  } | null;
  last_success_at: string | null;
};

export type KofTotals = {
  loads: number;
  revenue: number;
  cost: number;
  profit: number;
  margin_pct: number | null;
  avg_price: number | null;
  avg_cost: number | null;
  avg_profit: number | null;
  on_time_pct: number | null;
};

export type KofSummary = {
  totals: KofTotals;
  undated_loads: number;
  series: { period: string; loads: number; revenue: number; cost: number; profit: number; margin_pct: number | null }[];
  by_equipment: { equipment: string | null; loads: number; avg_price: number | null; avg_cost: number | null; margin_pct: number | null }[];
};

export type KofLane = {
  origin: string;
  destination: string;
  loads: number;
  avg_price: number | null;
  avg_cost: number | null;
  avg_profit: number | null;
  margin_pct: number | null;
  min_cost: number | null;
  max_cost: number | null;
  last_cost: number | null;
  last_date: string | null;
};

export type KofCustomer = {
  customer: string;
  loads: number;
  revenue: number;
  cost: number;
  profit: number;
  margin_pct: number | null;
  avg_price: number | null;
  last_load_date: string | null;
};

export type KofCarrier = {
  carrier: string;
  mc: string | null;
  loads: number;
  total_cost: number;
  avg_cost: number | null;
  on_time_pct: number | null;
  last_load_date: string | null;
  top_lanes: string[];
};

export type KofTrackingLoad = KofLoadRow & {
  last_note: { at: string | null; text: string } | null;
  hours_since_update: number | null;
};

export type KofTracking = {
  stages: { key: KofStage; label: string; loads: KofTrackingLoad[] }[];
};

export type KofSalesList = {
  key: string;
  label: string;
  count: number;
  columns: string[];
  rows: string[][];
};

export type KofBranch = {
  branch: string;
  customer: string | null;
  city: string | null;
  state: string | null;
  loads: number;
  revenue: number;
  cost: number;
  profit: number;
  margin_pct: number | null;
  avg_price: number | null;
  avg_cost: number | null;
  last_load_date: string | null;
  top_lanes: string[];
  working_status: string | null;
};

export type KofPickupSite = {
  company: string | null;
  city: string | null;
  state: string | null;
  loads: number;
  avg_price: number | null;
  avg_cost: number | null;
  margin_pct: number | null;
  last_date: string | null;
};

export type KofBranchDetail = {
  branch: string;
  customer: string | null;
  city: string | null;
  state: string | null;
  contact: { name: string | null; phone: string | null; email: string | null; address: string | null } | null;
  working_status: string | null;
  totals: Omit<KofTotals, "on_time_pct">;
  lanes: KofLane[];
  pickup_sites: KofPickupSite[];
  recent_loads: KofLoadRow[];
};

export type DateRange = { start?: string; end?: string };

function qs(params: Record<string, string | number | undefined | null>) {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") search.set(key, String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}

export type LoadQuery = DateRange & {
  q?: string;
  stage?: string;
  customer?: string;
  carrier?: string;
  origin_state?: string;
  dest_state?: string;
  sort?: string;
  page?: number;
  page_size?: number;
};

export const kof = {
  syncStatus: () => request<KofSyncStatus>("/kof/sync"),
  startSync: (kind: "incremental" | "full") =>
    request<{ started: boolean }>(`/kof/sync${qs({ kind })}`, { method: "POST" }),
  summary: (range: DateRange, interval: "week" | "month") =>
    request<KofSummary>(`/kof/summary${qs({ ...range, interval })}`),
  lanes: (
    range: DateRange,
    level: "state" | "city",
    minLoads = 1,
    limit = 100,
    filters: { branch?: string; customer?: string; origin_city?: string } = {},
  ) =>
    request<KofLane[]>(
      `/kof/lanes${qs({ ...range, ...filters, level, min_loads: minLoads, limit })}`,
    ),
  branches: (range: DateRange, customer: string) =>
    request<KofBranch[]>(`/kof/branches${qs({ ...range, customer })}`),
  branch: (branch: string, range: DateRange) =>
    request<KofBranchDetail>(`/kof/branches/detail${qs({ ...range, branch })}`),
  customers: (range: DateRange) => request<KofCustomer[]>(`/kof/customers${qs(range)}`),
  carriers: (range: DateRange) => request<KofCarrier[]>(`/kof/carriers${qs(range)}`),
  loads: (query: LoadQuery) =>
    request<{ total: number; items: KofLoadRow[] }>(`/kof/loads${qs(query)}`),
  load: (orderNo: number) => request<KofLoadDetail>(`/kof/loads/${orderNo}`),
  tracking: () => request<KofTracking>("/kof/tracking"),
  sales: () => request<{ lists: KofSalesList[] }>("/kof/sales"),
};
