// Default "" = same-origin requests through the Next.js proxy route
// (app/api/[...path]/route.ts), which attaches the server-side bearer token.
// Set NEXT_PUBLIC_API_URL to talk to the FastAPI service directly (no token).
export const API = process.env.NEXT_PUBLIC_API_URL || "";

export type Metrics = {
  k: number;
  scenarios: number;
  total_runs: number;
  pass_rate: number;
  violation_detection_rate: number;
  false_positive_rate: number;
  compliance_coverage: number;
  regulations_covered: string[];
  regulations_total: number;
  pass_at_1: number;
  pass_all_k: number;
  reliability_drop: number;
  total_violations: number;
  violation_weight?: number;
  possible_weight?: number;
  weighted_score?: number;
  violations_by_regulation: Record<string, number>;
  violations_by_severity: Record<string, number>;
  cost_usd_per_run: number;
  throughput_runs_per_sec: number;
};

export type CheckResult = {
  check_id: string;
  type: string;
  passed: boolean;
  severity: string;
  regulations: string[];
  message: string;
  evidence: string;
};

export type ScenarioRun = {
  scenario_id: string;
  title: string;
  label: string;
  attempt: number;
  passed: boolean;
  check_results: CheckResult[];
  transcript: { turns: { role: string; content: string }[] };
};

export type RunSummary = {
  run_id: string;
  created_at: string;
  agent_model: string;
  judge_model: string;
  pass_rate: number | null;
  total_runs: number | null;
  violations: number | null;
};

export type RunResult = {
  run_id: string;
  created_at: string;
  agent_model: string;
  judge_model: string;
  scenario_runs: ScenarioRun[];
  metrics: Metrics;
};

export type Health = {
  status: string;
  database: string;
  agent_model: string;
  judge_model: string;
  allowed_models: string[];
};

export type ScenarioDefinition = {
  id: string;
  tags: string[];
};

export type Job = {
  job_id: string;
  status: "queued" | "running" | "completed" | "failed" | "cancelled";
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  progress: { completed: number; total: number };
  result: RunResult | null;
  error: string | null;
};

async function j<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API}${path}`, { cache: "no-store", ...init });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

export const getLatest = () => j<RunResult>("/api/runs/latest");
export const listRuns = (limit = 50) => j<RunSummary[]>(`/api/runs?limit=${limit}`);
export const getRun = (id: string) => j<RunResult>(`/api/runs/${id}`);
export const getHealth = () => j<Health>("/api/health");
export const listScenarios = () => j<ScenarioDefinition[]>("/api/scenarios");
export const submitJob = (body: { agent: string; judge: string; k: number; tags?: string[] }) =>
  j<Job>("/api/jobs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
export const getJob = (id: string) => j<Job>(`/api/jobs/${id}`);
export const cancelJob = (id: string) => j<Job>(`/api/jobs/${id}`, { method: "DELETE" });
