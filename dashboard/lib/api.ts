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
};

export type RunResult = {
  run_id: string;
  created_at: string;
  agent_model: string;
  judge_model: string;
  scenario_runs: ScenarioRun[];
  metrics: Metrics;
};

async function j<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API}${path}`, { cache: "no-store", ...init });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

export const getLatest = () => j<RunResult>("/api/runs/latest");
export const listRuns = () => j<any[]>("/api/runs");
export const getRun = (id: string) => j<RunResult>(`/api/runs/${id}`);
export const triggerRun = (body: any) =>
  j<RunResult>("/api/run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
