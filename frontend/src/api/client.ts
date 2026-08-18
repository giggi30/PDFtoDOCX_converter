export type JobStatus =
  | "QUEUED"
  | "PROCESSING"
  | "COMPLETED"
  | "FAILED"
  | "CANCELLED"
  | "EXPIRED";

export interface ConversionCreated {
  job_id: string;
  access_token: string;
  status: JobStatus;
  expires_at: string;
}

export interface ConversionStatus {
  job_id: string;
  status: JobStatus;
  phase: string | null;
  progress: number;
  warnings: string[];
  error: string | null;
  expires_at: string;
}

export interface QualityMetrics {
  visual_similarity: number;
  text_accuracy: number;
  layout_similarity: number;
  page_count_match: number;
}

export interface ConversionResult {
  job_id: string;
  overall_score: number | null;
  rating: "excellent" | "good" | "fair" | "poor" | null;
  metrics: QualityMetrics | null;
  differences: string[];
  source_preview_urls: string[];
  result_preview_urls: string[];
  download_available: boolean;
}

const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");

function endpoint(path: string): string {
  return API_BASE ? `${API_BASE}${path}` : path;
}

async function responseError(response: Response): Promise<Error> {
  const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
  return new Error(payload?.detail ?? "Il servizio non ha completato la richiesta.");
}

export async function createConversion(
  file: File,
): Promise<ConversionCreated> {
  const form = new FormData();
  form.append("file", file);
  const response = await fetch(endpoint("/api/v1/conversions"), { method: "POST", body: form });
  if (!response.ok) throw await responseError(response);
  return response.json() as Promise<ConversionCreated>;
}

function authorization(token: string): HeadersInit {
  return { Authorization: `Bearer ${token}` };
}

export async function getConversion(jobId: string, token: string): Promise<ConversionStatus> {
  const response = await fetch(endpoint(`/api/v1/conversions/${jobId}`), {
    headers: authorization(token),
  });
  if (!response.ok) throw await responseError(response);
  return response.json() as Promise<ConversionStatus>;
}

export async function getResult(jobId: string, token: string): Promise<ConversionResult> {
  const response = await fetch(endpoint(`/api/v1/conversions/${jobId}/result`), {
    headers: authorization(token),
  });
  if (!response.ok) throw await responseError(response);
  return response.json() as Promise<ConversionResult>;
}

export async function fetchArtifact(url: string, token: string): Promise<string> {
  const target = url.startsWith("http://") || url.startsWith("https://") ? url : endpoint(url);
  const response = await fetch(target, { headers: authorization(token) });
  if (!response.ok) throw await responseError(response);
  return URL.createObjectURL(await response.blob());
}

export async function downloadResult(jobId: string, token: string): Promise<void> {
  const response = await fetch(endpoint(`/api/v1/conversions/${jobId}/download`), {
    headers: authorization(token),
  });
  if (!response.ok) throw await responseError(response);
  const url = URL.createObjectURL(await response.blob());
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `${jobId}.docx`;
  anchor.click();
  URL.revokeObjectURL(url);
}
