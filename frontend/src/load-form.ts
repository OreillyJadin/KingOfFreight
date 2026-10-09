import { getBrokerTimeZone, toZoneInputValue } from "./utils";

export type LoadDraft = Record<string, string>;

export const loadFieldGroups = [
  {
    title: "Load details",
    fields: [
      ["reference", "Reference", "text"],
      ["pickup_location", "Pickup location", "text"],
      ["pickup_city", "Pickup city", "text"],
      ["pickup_state", "Pickup state", "text"],
      ["pickup_datetime", "Pickup date & time", "datetime-local"],
      ["delivery_location", "Delivery location", "text"],
      ["delivery_city", "Delivery city", "text"],
      ["delivery_state", "Delivery state", "text"],
      ["delivery_datetime", "Delivery date & time", "datetime-local"],
      ["weight_lbs", "Weight (lb)", "number"],
      ["equipment_type", "Equipment", "text"],
      ["commodity", "Commodity", "text"],
      ["special_requirements", "Special requirements", "text"],
      ["notes", "Notes", "text"],
    ],
  },
  {
    title: "Customer",
    fields: [
      ["customer_name", "Customer", "text"],
      ["customer_contact_name", "Contact name", "text"],
      ["customer_email", "Customer email", "email"],
      ["customer_phone", "Customer phone", "tel"],
      ["customer_rate", "Customer rate ($)", "number"],
      ["carrier_rate", "Carrier rate ($)", "number"],
    ],
  },
  {
    title: "Driver & dispatcher",
    fields: [
      ["driver_name", "Driver name", "text"],
      ["driver_phone", "Driver phone", "tel"],
      ["driver_email", "Driver email", "email"],
      ["dispatcher_name", "Dispatcher name", "text"],
      ["dispatcher_phone", "Dispatcher phone", "tel"],
      ["dispatcher_email", "Dispatcher email", "email"],
    ],
  },
] as const;

export function draftFrom(source: Record<string, unknown> = {}): LoadDraft {
  const draft: LoadDraft = {};
  for (const group of loadFieldGroups) {
    for (const [key] of group.fields) {
      const value = source[key];
      draft[key] = value === null || value === undefined ? "" : String(value);
    }
  }
  for (const stop of ["pickup", "delivery"]) {
    const datetimeKey = `${stop}_datetime`;
    const timezoneKey = `${stop}_timezone`;
    const value = draft[datetimeKey];
    const sourceTimezone =
      typeof source[timezoneKey] === "string" ? String(source[timezoneKey]) : "";
    if (value && /[zZ]$|[+-]\d{2}:\d{2}$/.test(value)) {
      const zone = sourceTimezone || getBrokerTimeZone();
      draft[timezoneKey] = zone;
      draft[datetimeKey] = toZoneInputValue(value, zone);
    } else {
      draft[timezoneKey] = sourceTimezone;
      if (value) draft[datetimeKey] = value.slice(0, 16);
    }
  }
  return draft;
}

export function payloadFromDraft(draft: LoadDraft) {
  const payload: Record<string, unknown> = {};
  for (const group of loadFieldGroups) {
    for (const [key, , type] of group.fields) {
      const value = draft[key]?.trim() ?? "";
      payload[key] = value === "" ? null : type === "number" ? Number(value) : value;
    }
  }
  payload.reference = draft.reference.trim();
  for (const stop of ["pickup", "delivery"]) {
    const key = `${stop}_timezone`;
    payload[key] = draft[key]?.trim() || null;
  }
  return payload;
}
