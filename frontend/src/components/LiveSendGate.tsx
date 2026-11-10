import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { useCapabilities } from "../useCapabilities";

export default function LiveSendGate({ channel, children }: { channel: "sms" | "email"; children: ReactNode }) {
  const capabilities = useCapabilities();
  const live = channel === "sms" ? capabilities.data?.sms_live : capabilities.data?.email_live;
  return live ? <>{children}</> : <p className="text-xs text-muted">Connect {channel === "sms" ? "Texting" : "Outlook"} in <Link className="underline" to={channel === "sms" ? "/settings#twilio" : "/settings#outlook"}>Settings</Link>.</p>;
}
