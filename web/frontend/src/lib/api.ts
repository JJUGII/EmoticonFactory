import { getApiBase, ngrokRequestHeaders } from "./apiBase";

function apiUrl(path: string): string {
  const base = getApiBase();
  const p = path.startsWith("/") ? path : `/${path}`;
  return base ? `${base}${p}` : p;
}

export type JobPhase =
  | "created"
  | "uploaded"
  | "candidates_running"
  | "candidates_ready"
  | "canonical_selected"
  | "emoticons_running"
  | "completed"
  | "failed";

export type CutStatus = "pending" | "running" | "done" | "failed";

export interface JobStatus {
  job_id: string;
  phase: JobPhase;
  progress: number;
  message: string;
  current_cut?: string | null;
  cuts: { id: string; text: string; status: CutStatus; url?: string | null }[];
  error?: string | null;
}

export interface CandidateItem {
  index: number;
  url: string;
}

export interface ResultPayload {
  job_id: string;
  package_dir: string;
  preview?: Record<string, unknown> | null;
  cuts: { id: string; text: string; status: CutStatus; url?: string | null }[];
  canonical_url?: string | null;
}

function assetUrl(path: string): string {
  if (path.startsWith("http")) return path;
  return apiUrl(path);
}

export { getApiBase, assetUrl };

async function parseJson<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = "";
    try {
      const err = (await res.json()) as { detail?: string | unknown };
      if (typeof err.detail === "string") detail = err.detail;
      else if (Array.isArray(err.detail)) detail = JSON.stringify(err.detail);
    } catch {
      detail = res.statusText || `HTTP ${res.status}`;
    }
    throw new Error(detail || "요청 실패");
  }
  return res.json() as Promise<T>;
}

export async function uploadPhoto(
  file: File,
  opts?: { series_name?: string; theme?: string; generator?: string }
): Promise<{ job_id: string; preview_url: string }> {
  const fd = new FormData();
  fd.append("file", file, file.name || "photo.jpg");
  fd.append("series_name", opts?.series_name || "MySticker");
  fd.append("theme", opts?.theme || "사랑");
  fd.append("generator", opts?.generator || "mock");

  let res: Response;
  try {
    res = await fetch(apiUrl("/api/upload"), {
      method: "POST",
      headers: ngrokRequestHeaders(),
      body: fd,
    });
  } catch (err) {
    console.error("[UPLOAD_ERROR]", err);
    throw new Error(
      "서버에 연결할 수 없습니다. Vercel 배포 시 API_URL(백엔드 주소) 환경 변수를 설정했는지 확인해 주세요."
    );
  }

  const data = await parseJson<{ job_id: string; preview_url: string }>(res);
  return { job_id: data.job_id, preview_url: assetUrl(data.preview_url) };
}

export async function generateCandidates(
  jobId: string,
  generator: string,
  speciesHint = "",
  artStyle: "illustration" | "realistic" = "illustration"
): Promise<JobStatus> {
  const res = await fetch(apiUrl("/api/generate-candidates"), {
    method: "POST",
    headers: ngrokRequestHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({
      job_id: jobId,
      generator,
      theme: "사랑",
      species_hint: speciesHint,
      art_style: artStyle,
    }),
  });
  return parseJson(res);
}

export async function fetchCandidates(jobId: string): Promise<CandidateItem[]> {
  const res = await fetch(apiUrl(`/api/candidates/${jobId}`), {
    headers: ngrokRequestHeaders(),
  });
  const data = await parseJson<{ candidates: CandidateItem[] }>(res);
  return data.candidates.map((c) => ({ ...c, url: assetUrl(c.url) }));
}

export async function selectCandidate(
  jobId: string,
  candidateIndex: number
): Promise<JobStatus> {
  const res = await fetch(apiUrl("/api/select-candidate"), {
    method: "POST",
    headers: ngrokRequestHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({ job_id: jobId, candidate_index: candidateIndex }),
  });
  const data = await parseJson<{ job: JobStatus }>(res);
  return data.job;
}

export async function fetchDefaultEmotions(): Promise<string[]> {
  const res = await fetch(apiUrl("/api/emotions/defaults"), {
    headers: ngrokRequestHeaders(),
  });
  const data = await parseJson<{ emotions: string[] }>(res);
  return data.emotions;
}

export async function generateEmoticons(
  jobId: string,
  emotions: string[],
  generator: string,
  gridMode = false,
  artStyle: "illustration" | "realistic" = "illustration"
): Promise<JobStatus> {
  const res = await fetch(apiUrl("/api/generate-emoticons"), {
    method: "POST",
    headers: ngrokRequestHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({
      job_id: jobId,
      emotions,
      generator,
      theme: "사랑",
      grid_mode: gridMode,
      art_style: artStyle,
    }),
  });
  return parseJson(res);
}

export async function fetchJob(jobId: string): Promise<JobStatus> {
  const res = await fetch(apiUrl(`/api/job/${jobId}`), {
    cache: "no-store",
    headers: ngrokRequestHeaders(),
  });
  return parseJson(res);
}

export async function fetchResult(jobId: string): Promise<ResultPayload> {
  const res = await fetch(apiUrl(`/api/result/${jobId}`), {
    cache: "no-store",
    headers: ngrokRequestHeaders(),
  });
  const data = await parseJson<ResultPayload>(res);
  return {
    ...data,
    cuts: data.cuts.map((c) => ({
      ...c,
      url: c.url ? assetUrl(c.url) : null,
    })),
    canonical_url: data.canonical_url ? assetUrl(data.canonical_url) : null,
  };
}

export function downloadZipUrl(jobId: string): string {
  return apiUrl(`/api/download/${jobId}`);
}

export function portfolioUrl(jobId: string): string {
  return apiUrl(`/api/portfolio/${jobId}`);
}

// ── 플랫폼 내보내기 ────────────────────────────────────────────────────────

export async function exportToTelegram(jobId: string): Promise<{ link: string; cached: boolean }> {
  const res = await fetch(apiUrl(`/api/export/telegram/${jobId}`), {
    method: "POST",
    ...ngrokRequestHeaders(),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Telegram 내보내기 실패");
  }
  return res.json();
}

export async function getDiscordInviteUrl(jobId: string): Promise<{ oauth2_url: string }> {
  const res = await fetch(apiUrl(`/api/export/discord/invite/${jobId}`), {
    ...ngrokRequestHeaders(),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Discord 초대 URL 생성 실패");
  }
  return res.json();
}

export async function getDiscordBotInviteUrl(): Promise<{ bot_invite_url: string }> {
  const res = await fetch(apiUrl("/api/export/discord/bot-invite"), {
    ...ngrokRequestHeaders(),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Discord 봇 초대 URL 생성 실패");
  }
  return res.json();
}

export async function uploadToDiscord(
  jobId: string,
  guildId: string
): Promise<{ uploaded_count: number; stickers: { id: string; name: string }[] }> {
  const res = await fetch(
    apiUrl(`/api/export/discord/upload/${jobId}?guild_id=${encodeURIComponent(guildId)}`),
    {
      method: "POST",
      headers: ngrokRequestHeaders(),
    }
  );
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Discord 업로드 실패");
  }
  return res.json();
}

export function downloadSlackZipUrl(jobId: string): string {
  return apiUrl(`/api/export/slack/download/${jobId}`);
}

export function pollJob(
  jobId: string,
  onUpdate: (s: JobStatus) => void,
  intervalMs = 2000,
  until?: JobPhase[]
): () => void {
  const stopPhases = until ?? [
    "candidates_ready",
    "completed",
    "failed",
    "canonical_selected",
  ];
  let active = true;
  const tick = async () => {
    if (!active) return;
    try {
      const s = await fetchJob(jobId);
      onUpdate(s);
      if (stopPhases.includes(s.phase)) {
        return;
      }
    } catch {
      /* ignore transient */
    }
    if (active) setTimeout(tick, intervalMs);
  };
  tick();
  return () => {
    active = false;
  };
}
