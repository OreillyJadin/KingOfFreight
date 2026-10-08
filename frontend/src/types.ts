export type LoadStatus =
  | "new"
  | "posted"
  | "booked"
  | "picked_up"
  | "in_transit"
  | "delayed"
  | "delivered";

export type Load = {
  id: number;
  reference: string;
  status: LoadStatus;
  pickup_location: string | null;
  pickup_city: string | null;
  pickup_state: string | null;
  pickup_datetime: string | null;
  delivery_location: string | null;
  delivery_city: string | null;
  delivery_state: string | null;
  delivery_datetime: string | null;
  weight_lbs: number | string | null;
  equipment_type: string | null;
  commodity: string | null;
  special_requirements: string | null;
  notes: string | null;
  customer_name: string | null;
  customer_contact_name: string | null;
  customer_email: string | null;
  customer_phone: string | null;
  customer_rate: number | string | null;
  carrier_rate: number | string | null;
  margin: number | string | null;
  margin_pct: number | string | null;
  carrier_id: number | null;
  driver_name: string | null;
  driver_phone: string | null;
  driver_email: string | null;
  dispatcher_name: string | null;
  dispatcher_phone: string | null;
  dispatcher_email: string | null;
  tracking_token: string;
  created_at: string;
  booked_at: string | null;
  delivered_at: string | null;
};

export type Carrier = {
  id: number;
  mc_number: string;
  dot_number: string | null;
  legal_name: string | null;
  dba_name: string | null;
  phone: string | null;
  email: string | null;
  allowed_to_operate: string | null;
  authority_status: string | null;
  safety_rating: string | null;
  insurance_on_file: boolean | null;
  bipd_on_file_amount: number | string | null;
  bipd_required_amount: number | string | null;
  out_of_service_date: string | null;
  flag: "green" | "yellow" | "red";
  flag_reasons: string[];
  raw: Record<string, unknown> | null;
  verified_at: string | null;
};

export type Communication = {
  id: number;
  load_id: number | null;
  carrier_id: number | null;
  channel: "email" | "sms" | "call";
  direction: "inbound" | "outbound";
  from_addr: string | null;
  to_addr: string | null;
  subject: string | null;
  content: string;
  tag: string;
  attachment_path: string | null;
  extracted: Record<string, unknown> | null;
  external_id: string | null;
  archived: boolean;
  created_at: string;
};

export type StatusUpdate = {
  id: number;
  load_id: number;
  status: LoadStatus;
  source: "manual" | "checkin" | "gps";
  note: string | null;
  eta: string | null;
  applied: boolean;
  customer_channel: "email" | "sms" | null;
  customer_message_subject: string | null;
  customer_message_preview: string | null;
  approved_by_broker: boolean;
  sent_to_customer: boolean;
  sent_at: string | null;
  state: "pending_approval" | "sent" | "skipped";
  checkin_id: number | null;
  created_at: string;
};

export type CheckIn = {
  id: number;
  load_id: number;
  kind: "pickup" | "dropoff";
  scheduled_time: string;
  send_at: string;
  checkin_sent_at: string | null;
  checkin_channel: "sms" | "email";
  driver_contact: string;
  message_text: string | null;
  reply_received: boolean;
  reply_raw_text: string | null;
  reply_received_at: string | null;
  parsed_status: LoadStatus | "unclear" | null;
  parsed_eta: string | null;
  parsed_summary: string | null;
  parse_confidence: number | string | null;
  needs_broker_attention: boolean;
  state: "scheduled" | "sent" | "replied" | "skipped" | "no_reply";
  alert_raised_at: string | null;
  alert_dismissed_at: string | null;
};

export type LocationPing = {
  id: number;
  load_id: number;
  lat: number | string;
  lng: number | string;
  accuracy_m: number | string | null;
  captured_at: string;
  user_agent: string | null;
};

export type LoadDetail = Load & {
  carrier: Carrier | null;
  status_updates: StatusUpdate[];
  checkins: CheckIn[];
  latest_location_ping: LocationPing | null;
  communications: Communication[];
};

export type Alert = {
  id: number;
  kind: "pickup" | "dropoff";
  state: "no_reply" | "replied";
  checkin_sent_at: string | null;
  scheduled_time: string;
  reply_raw_text: string | null;
  parsed_status: string | null;
  parsed_summary: string | null;
  needs_broker_attention: boolean;
  alert_raised_at: string | null;
  alert_dismissed_at: string | null;
  load: {
    id: number;
    reference: string;
    status: LoadStatus;
    pickup_city: string | null;
    delivery_city: string | null;
  };
};

export type BolExtraction = {
  reference?: string | null;
  pickup_location?: string | null;
  pickup_city?: string | null;
  pickup_state?: string | null;
  pickup_datetime?: string | null;
  pickup_time_known?: boolean | null;
  delivery_location?: string | null;
  delivery_city?: string | null;
  delivery_state?: string | null;
  delivery_datetime?: string | null;
  delivery_time_known?: boolean | null;
  weight_lbs?: number | null;
  equipment_type?: string | null;
  commodity?: string | null;
  pieces?: number | null;
  pallets?: number | null;
  reference_numbers?: Record<string, string> | null;
  customer_name?: string | null;
  customer_contact_name?: string | null;
  customer_email?: string | null;
  customer_phone?: string | null;
  special_requirements?: string | null;
  confidence?: number;
  notes?: string | null;
};

export type NewLoad = Partial<Load> & Pick<Load, "reference">;

export type BookPayload = {
  carrier_mc: string;
  carrier_rate: number;
  customer_rate: number;
  driver_name?: string;
  driver_phone?: string;
  driver_email?: string;
  dispatcher_name?: string;
  dispatcher_phone?: string;
  dispatcher_email?: string;
  checkin_offset_minutes?: number;
  checkin_channel?: "sms" | "email";
  override_red_flag?: boolean;
};

export type TrackingSummary = {
  reference: string;
  pickup_city: string | null;
  pickup_state: string | null;
  delivery_city: string | null;
  delivery_state: string | null;
  broker_company: string;
};
