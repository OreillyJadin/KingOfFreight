import { useEffect, useRef } from "react";
import { api } from "../api";
import { startHeartbeat } from "../usage-heartbeat";

export default function UsageHeartbeat({ path, identity }: { path: string; identity: string }) {
  const currentPath = useRef(path);
  currentPath.current = path;
  useEffect(() => startHeartbeat(() => api.usageHeartbeat(currentPath.current)), [identity]);
  return null;
}
