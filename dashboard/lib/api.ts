export const API = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

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
  error?: string | null;
};

export type RunResult = {
  run_id: string;
  created_at: string;
  agent_model: string;
  judge_model: string;
  scenario_runs: ScenarioRun[];
  metrics: Metrics;
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

// Default per-request timeout; a hung API should surface an error, not freeze the UI.
const TIMEOUT_MS = 30_000;

async function j<T>(path: string, init?: RequestInit, timeoutMs = TIMEOUT_MS): Promise<T> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const res = await fetch(`${API}${path}`, { cache: "no-store", signal: ctrl.signal, ...init });
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
    return res.json();
  } catch (e: any) {
    if (e?.name === "AbortError") throw new Error(`Request timed out after ${timeoutMs / 1000}s`);
    throw e;
  } finally {
    clearTimeout(timer);
  }
}

export const getLatest = () => j<RunResult>("/api/runs/latest");
export const listRuns = () => j<RunSummary[]>("/api/runs");
export const getRun = (id: string) => j<RunResult>(`/api/runs/${id}`);
// A real evaluation against a slow model can take a while; give runs a longer budget.
export const triggerRun = (body: any) =>
  j<RunResult>(
    "/api/run",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
    120_000,
  );
