"use client";

import { useEffect, useMemo, useState } from "react";
import {
  cancelJob, getHealth, getJob, getLatest, getRun, listRuns, listScenarios, submitJob,
  Health, Job, RunResult, RunSummary, ScenarioDefinition, ScenarioRun,
} from "../lib/api";

const pct = (n: number) => `${(n * 100).toFixed(n === 1 || n === 0 ? 0 : 1)}%`;

export default function Page() {
  const [run, setRun] = useState<RunResult | null>(null);
  const [history, setHistory] = useState<RunSummary[]>([]);
  const [health, setHealth] = useState<Health | null>(null);
  const [scenarios, setScenarios] = useState<ScenarioDefinition[]>([]);
  const [agent, setAgent] = useState("");
  const [judge, setJudge] = useState("");
  const [k, setK] = useState(1);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [selectedTags, setSelectedTags] = useState<string[]>([]);
  const [selectedScenario, setSelectedScenario] = useState<ScenarioRun | null>(null);
  const [loading, setLoading] = useState(true);
  const [job, setJob] = useState<Job | null>(null);

  async function refreshHistory() {
    try {
      setHistory(await listRuns());
    } catch {
      setHistory([]);
    }
  }

  useEffect(() => {
    async function initialise() {
      try {
        const [apiHealth, apiScenarios, latest] = await Promise.all([
          getHealth(),
          listScenarios().catch(() => []),
          getLatest().catch(() => null),
        ]);
        setHealth(apiHealth);
        setScenarios(apiScenarios);
        setRun(latest);
        setAgent(apiHealth.agent_model);
        setJudge(apiHealth.judge_model);
        await refreshHistory();
      } catch (e: unknown) {
        setErr(apiError("Could not load Nomaya", e));
      } finally {
        setLoading(false);
      }
    }
    initialise();
  }, []);

  async function loadRun(id: string) {
    try {
      setErr(null);
      setRun(await getRun(id));
      setSelectedScenario(null);
    } catch (e: unknown) {
      setErr(apiError("Could not load that run", e));
    }
  }

  async function doRun() {
    setBusy(true);
    setErr(null);
    try {
      let current = await submitJob({ agent, judge, k, tags: selectedTags.length ? selectedTags : undefined });
      setJob(current);
      while (current.status === "queued" || current.status === "running") {
        await delay(350);
        current = await getJob(current.job_id);
        setJob(current);
      }
      if (current.status === "completed" && current.result) {
        setRun(current.result);
        setSelectedScenario(null);
        await refreshHistory();
      } else {
        setErr(current.error || "The evaluation did not complete.");
      }
    } catch (e: unknown) {
      setErr(apiError("Could not start the evaluation", e));
    } finally {
      setBusy(false);
    }
  }

  async function cancelEvaluation() {
    if (!job || job.status === "completed" || job.status === "failed" || job.status === "cancelled") return;
    try {
      setJob(await cancelJob(job.job_id));
    } catch (e: unknown) {
      setErr(apiError("Could not cancel the evaluation", e));
    }
  }

  const m = run?.metrics;
  const models = health?.allowed_models.includes("*")
    ? uniqueModels([health.agent_model, health.judge_model, agent, judge])
    : health?.allowed_models ?? [];
  const tags = useMemo(() => [...new Set(scenarios.flatMap((scenario) => scenario.tags))].sort(), [scenarios]);
  const filteredRuns = run?.scenario_runs.filter((scenario) => (
    scenario.title.toLowerCase().includes(search.toLowerCase()) ||
    scenario.scenario_id.toLowerCase().includes(search.toLowerCase())
  )) ?? [];

  return (
    <div className="wrap">
      <div className="head">
        <div>
          <div className="brand">Nomaya</div>
          <h1>Finance Compliance Agent Evaluation</h1>
          <p className="subtitle">
            Run any lab&apos;s agent through regulation-mapped scenarios and verify behavior against
            named obligations — GLBA, UDAAP, Reg Z/E, FCRA, ECOA, SR&nbsp;11-7, NYDFS&nbsp;500, EU&nbsp;AI&nbsp;Act, DORA.
          </p>
        </div>
        <div className="toolbar" aria-label="Evaluation controls">
          <label className="field compact-field">
            <span>Agent model</span>
            <select value={agent} onChange={(e) => setAgent(e.target.value)} disabled={!health || busy}>
            {models.map((a) => (
              <option key={a} value={a}>{a}</option>
            ))}
            </select>
          </label>
          <label className="field compact-field">
            <span>Judge model</span>
            <select value={judge} onChange={(e) => setJudge(e.target.value)} disabled={!health || busy}>
              {models.map((model) => <option key={model} value={model}>{model}</option>)}
            </select>
          </label>
          <label className="field compact-field">
            <span>Attempts</span>
            <select value={k} onChange={(e) => setK(Number(e.target.value))} title="Attempts per scenario (pass@k)" disabled={!health || busy}>
            {[1, 3, 5].map((n) => <option key={n} value={n}>k={n}</option>)}
            </select>
          </label>
          <button className="primary" onClick={doRun} disabled={busy || !agent || !judge}>
            {busy ? "Running…" : "Run evaluation"}
          </button>
          {busy && job && <button type="button" className="secondary" onClick={cancelEvaluation}>Cancel evaluation</button>}
        </div>
      </div>

      {health && <p className="api-status" role="status">API connected · database {health.database} · {health.allowed_models.includes("*") ? "unrestricted model allow-list" : `${models.length} permitted models`}</p>}
      {job && <JobProgress job={job} />}

      {tags.length > 0 && (
        <fieldset className="tag-filter" disabled={busy}>
          <legend>Scenario focus <span>Optional — leave clear to run the full suite.</span></legend>
          <div className="tag-options">
            {tags.map((tag) => <label key={tag} className="tag-option">
              <input type="checkbox" checked={selectedTags.includes(tag)} onChange={() => setSelectedTags((current) => current.includes(tag) ? current.filter((item) => item !== tag) : [...current, tag])} />
              <span>{tag}</span>
            </label>)}
          </div>
        </fieldset>
      )}

      {err && <div className="err" role="alert"><p>{err}</p><button type="button" onClick={() => setErr(null)}>Dismiss</button></div>}

      {loading && <LoadingState />}
      {!loading && !run && !err && <div className="empty"><h2>No evaluation yet</h2><p>Select permitted models, then run the complete suite or focus on scenario tags above.</p></div>}

      {run && m && (
        <>
          <div className="meta">
            run {run.run_id} · agent <span className="tag">{run.agent_model}</span> · judge{" "}
            <span className="tag">{run.judge_model}</span> · {new Date(run.created_at).toLocaleString()}
          </div>

          <div className="cards">
            <Card label="Pass rate" value={pct(m.pass_rate)} tone={m.pass_rate >= 0.9 ? "ok" : m.pass_rate >= 0.6 ? "warn" : "bad"} bar={m.pass_rate} />
            <Card label="Detection rate" value={pct(m.violation_detection_rate)} note="recall on tempting cases" />
            <Card label="False positives" value={pct(m.false_positive_rate)} tone={m.false_positive_rate === 0 ? "ok" : "bad"} />
            <Card label="Weighted score" value={pct(m.weighted_score ?? 1)} tone={(m.weighted_score ?? 1) >= 0.9 ? "ok" : (m.weighted_score ?? 1) >= 0.6 ? "warn" : "bad"} note="severity-weighted" />
            <Card label="Coverage" value={pct(m.compliance_coverage)} note={`${m.regulations_covered.length}/${m.regulations_total} regulations`} bar={m.compliance_coverage} />
            <Card label="pass@k reliability" value={pct(m.pass_all_k)} note={`drop ${pct(m.reliability_drop)} · k=${m.k}`} />
            <Card label="Cost / run" value={`$${m.cost_usd_per_run.toFixed(4)}`} note={`${m.throughput_runs_per_sec} runs/s`} />
          </div>

          {Object.keys(m.violations_by_regulation).length > 0 && (
            <>
              <h2>Violations by regulation</h2>
              <div className="panel scroll">
                <table>
                  <thead><tr><th>Regulation</th><th>Violations</th></tr></thead>
                  <tbody>
                    {Object.entries(m.violations_by_regulation).map(([reg, n]) => (
                      <tr className="reg-row" key={reg}>
                        <td>{reg}</td>
                        <td><span className="count">{n}</span></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}

          <h2>Scenario results</h2>
          <label className="field search-field">
            <span>Find a scenario</span>
            <input type="search" placeholder="Search by title or ID" value={search} onChange={e => setSearch(e.target.value)} />
          </label>
          <div className="panel scroll">
            <table>
              <thead>
                <tr><th>Scenario</th><th>Label</th><th>Result</th><th>Checks</th></tr>
              </thead>
              <tbody>
                {filteredRuns.map((s, i) => (
                  <tr key={`${s.scenario_id}-${i}`}>
                    <td>
                      <div>{s.title}</div>
                      <div className="sid">{s.scenario_id}{m.k > 1 ? ` · attempt ${s.attempt + 1}` : ""}</div>
                    </td>
                    <td><span className="lbl">{s.label}</span></td>
                    <td><span className={`badge ${s.passed ? "pass" : "fail"}`}>{s.passed ? "PASS" : "FAIL"}</span></td>
                    <td>
                      {s.check_results.map((c) => (
                        <span key={c.check_id} className={`chip ${c.passed ? "pass" : "fail"}`}>
                          {c.passed ? "✓" : "✕"} {c.check_id}
                        </span>
                      ))}
                      <button className="text-button" type="button" onClick={() => setSelectedScenario(s)}>View evidence<span className="sr-only"> for {s.title}</span></button>
                    </td>
                  </tr>
                ))}
                {filteredRuns.length === 0 && <tr><td colSpan={4} className="table-empty">No scenario results match “{search}”.</td></tr>}
              </tbody>
            </table>
          </div>

          {selectedScenario && <ScenarioDetail scenario={selectedScenario} onClose={() => setSelectedScenario(null)} />}

          {history.length > 0 && (
            <>
              <h2>Run history</h2>
              <div className="panel scroll">
                <table>
                  <thead>
                    <tr><th>Run</th><th>When</th><th>Agent</th><th>Pass rate</th><th>Violations</th></tr>
                  </thead>
                  <tbody>
                    {history.map((r) => (
                      <tr key={r.run_id} className={r.run_id === run.run_id ? "row-active" : ""}>
                        <td><button className="run-link" type="button" onClick={() => loadRun(r.run_id)} aria-current={r.run_id === run.run_id ? "page" : undefined}><span className="sid">{r.run_id}</span></button></td>
                        <td className="lbl">{new Date(r.created_at).toLocaleString()}</td>
                        <td><span className="tag">{r.agent_model}</span></td>
                        <td>
                          {r.pass_rate !== null ? (
                            <span className={`badge ${r.pass_rate >= 0.9 ? "pass" : "fail"}`}>{pct(r.pass_rate)}</span>
                          ) : (
                            "—"
                          )}
                        </td>
                        <td><span className="count">{r.violations ?? "—"}</span></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}

          <p className="foot">
            Regulation mappings are paraphrased for orientation and are not legal advice — review with
            qualified compliance staff before relying on them.
          </p>
        </>
      )}
    </div>
  );
}

function LoadingState() {
  return <div className="loading" aria-live="polite" aria-label="Loading Nomaya data"><div /><div /><div /></div>;
}

function JobProgress({ job }: { job: Job }) {
  const total = Math.max(job.progress.total, 1);
  const complete = Math.min(job.progress.completed, total);
  const label = job.status === "queued" ? "Evaluation queued" : job.status === "running" ? "Evaluation running" : `Evaluation ${job.status}`;
  return <section className="job-progress" aria-live="polite">
    <div><strong>{label}</strong><span>{complete} / {job.progress.total} scenario attempts</span></div>
    <progress value={complete} max={total} />
  </section>;
}

function ScenarioDetail({ scenario, onClose }: { scenario: ScenarioRun; onClose: () => void }) {
  return <section className="detail panel" aria-labelledby="evidence-title">
    <div className="detail-head"><div><p className="eyebrow">Scenario evidence</p><h3 id="evidence-title">{scenario.title}</h3><p className="sid">{scenario.scenario_id}</p></div><button type="button" onClick={onClose}>Close</button></div>
    <div className="evidence-list">
      {scenario.check_results.map((check) => <article key={check.check_id} className={`evidence-item ${check.passed ? "pass" : "fail"}`}>
        <div><span className={`badge ${check.passed ? "pass" : "fail"}`}>{check.passed ? "PASS" : "FAIL"}</span> <strong>{check.check_id}</strong> <span className="lbl">{check.severity}</span></div>
        <p>{check.message || "No evaluator message was returned."}</p>
        {check.evidence && <pre>{check.evidence}</pre>}
      </article>)}
    </div>
    <h4>Transcript</h4>
    <div className="transcript">{scenario.transcript.turns.length ? scenario.transcript.turns.map((turn, index) => <article key={`${turn.role}-${index}`}><p className="turn-role">{turn.role}</p><p>{turn.content}</p></article>) : <p className="muted">No transcript was stored for this scenario.</p>}</div>
  </section>;
}

function uniqueModels(models: string[]) {
  return [...new Set(models.filter(Boolean))];
}

function apiError(prefix: string, error: unknown) {
  const message = error instanceof Error ? error.message : "Unknown error";
  return `${prefix}. Check that the Nomaya API is running and configured for this dashboard. (${message})`;
}

function delay(milliseconds: number) {
  return new Promise<void>((resolve) => setTimeout(resolve, milliseconds));
}

function Card({ label, value, note, tone, bar }: { label: string; value: string; note?: string; tone?: "ok" | "bad" | "warn"; bar?: number }) {
  return (
    <div className="card">
      <div className="k">{label}</div>
      <div className={`v ${tone || ""}`}>{value}</div>
      {note && <div className="note">{note}</div>}
      {bar !== undefined && <div className="track"><i style={{ width: `${Math.round(bar * 100)}%` }} /></div>}
    </div>
  );
}
