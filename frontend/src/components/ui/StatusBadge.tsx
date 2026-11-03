import { Badge } from "./Badge";
import { statusTone } from "../../lib/format";

export function StatusBadge({
  status,
  label,
}: {
  status: string | null | undefined;
  label?: string;
}) {
  return <Badge tone={statusTone(status)}>{label ?? status ?? "unknown"}</Badge>;
}
