"use client";

import { useEffect, useState } from "react";
import { getLatest, getRun, listRuns, triggerRun, RunResult, RunSummary } from "../lib/api";

const AGENTS = [
  "mock/compliant-agent",
  "mock/naive-agent",
  "openai/gpt-4o-mini",
  "anthropic/claude-haiku-4-5",
  "gemini/gemini-2.0-flash",
  "mistral/mistral-large-latest",
  "ollama/llama3.1",
];

const pct = (n: number) => `${(n * 100).toFixed(n === 1 || n === 0 ? 0 : 1)}%`;

export default function Page() {
  const [run, setRun] = useState<RunResult | null>(null);
  const [history, setHistory] = useState<RunSummary[]>([]);
  const [agent, setAgent] = useState(AGENTS[0]);
  const [k, setK] = useState(1);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  function refreshHistory() {
    listRuns().then(setHistory).catch(() => setHistory([]));
  }

  useEffect(() => {
    getLatest().then(setRun).catch(() => setRun(null));
    refreshHistory();
  }, []);

  function loadRun(id: string) {
    getRun(id).then(setRun).catch(() => {});
  }

  async function doRun() {
    setBusy(true);
    setErr(null);
    try {
      const r = await triggerRun({ agent, judge: "mock/judge", k });
      setRun(r);
      refreshHistory();
    } catch (e: any) {
      setErr(`Could not reach the Nomaya API. Start it with \`nomaya serve\`. (${e.message})`);
    } finally {
      setBusy(false);
    }
  }

  const m = run?.metrics;

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
        <div className="toolbar">
          <select value={agent} onChange={(e) => setAgent(e.target.value)}>
            {AGENTS.map((a) => (
              <option key={a} value={a}>{a}</option>
            ))}
          </select>
          <select value={k} onChange={(e) => setK(Number(e.target.value))} title="Attempts per scenario (pass@k)">
            {[1, 3, 5].map((n) => <option key={n} value={n}>k={n}</option>)}
          </select>
          <button className="primary" onClick={doRun} disabled={busy}>
            {busy ? "Running…" : "Run evaluation"}
          </button>
        </div>
      </div>

      {err && <p className="err" style={{ marginTop: 24 }}>{err}</p>}

      {!run && !err && <div className="empty">No run yet. Pick an agent and hit <b>Run evaluation</b>.</div>}

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
          <div className="panel scroll">
            <table>
              <thead>
                <tr><th>Scenario</th><th>Label</th><th>Result</th><th>Checks</th></tr>
              </thead>
              <tbody>
                {run.scenario_runs.map((s, i) => (
                  <tr key={`${s.scenario_id}-${i}`}>
                    <td>
                      <div>{s.title}</div>
                      <div className="sid">{s.scenario_id}{m.k > 1 ? ` · attempt ${s.attempt + 1}` : ""}</div>
                    </td>
                    <td><span className="lbl">{s.label}</span></td>
                    <td><span className={`badge ${s.passed ? "pass" : "fail"}`}>{s.passed ? "PASS" : "FAIL"}</span></td>
                    <td>
                      {s.check_results.map((c) => (
                        <span key={c.check_id} className={`chip ${c.passed ? "pass" : "fail"}`} title={`${c.message} ${c.evidence}`.trim()}>
                          {c.passed ? "✓" : "✕"} {c.check_id}
                        </span>
                      ))}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

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
                      <tr
                        key={r.run_id}
                        className={`row-click ${r.run_id === run.run_id ? "row-active" : ""}`}
                        onClick={() => loadRun(r.run_id)}
                      >
                        <td><span className="sid">{r.run_id}</span></td>
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
