import { useQuery } from "@tanstack/react-query";
import { api } from "./api";

export function useCapabilities() {
  return useQuery({ queryKey: ["integrations", "status"], queryFn: api.integrationsStatus, refetchInterval: 30000 });
}
