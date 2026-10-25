import type { ApiResult } from "@/lib/api";

export type DataRequest = {
  id: string;
  kind: "export" | "erasure";
  status: "received" | "processing" | "completed" | "refused";
  created_at: string;
  completed_at: string | null;
  expires_at: string | null;
};

export type DataRequests = { data: DataRequest[]; erasure_grace_days: number };

export type StepUp = <T>(
  action: () => Promise<ApiResult<T>>,
  options?: { retry?: boolean },
) => Promise<ApiResult<T>>;
