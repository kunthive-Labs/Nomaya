# Evaluation governance

Nomaya is an evaluation and regression-testing tool. A successful run is evidence
about the scenario set and configuration used; it is not a legal certification of
an AI system or a statement that the system meets every applicable obligation.

## Required ownership

Every production suite must have a named product owner, compliance owner, and
technical owner. The compliance owner approves each regulation mapping, severity,
and release threshold. The technical owner approves execution settings and model
allow-lists. Changes to either must be recorded in the run metadata and audit log.

## Scenario lifecycle

1. Author scenarios in a branch with a stable ID, tags, regulation references,
   expected outcome, and a rationale.
2. Add deterministic compliant and non-compliant fixtures plus unit coverage.
3. Obtain compliance review before moving a scenario from `draft` to `approved`.
4. Version the suite and preserve old versions for reproducibility.
5. Run approved suites in CI; run holdout/adversarial suites before material model
   or prompt releases.

## Validity controls

- Maintain development, regression, and holdout suites separately. Do not tune an
  agent against a holdout suite.
- Include benign controls, adversarial phrasing, multi-turn context, tool use,
  identity verification, conflicting instructions, and escalation/handoff cases.
- Human-label a representative sample. Track LLM-judge agreement, inconclusive
  verdicts, false positives, and missed failures against those labels.
- Treat coverage as “covered by a check”, not proof that a regulation is fully
  satisfied.

## Release evidence

A release record should include the agent and judge model identifiers, prompt and
tool versions, suite version, run configuration, score thresholds, scenario
outcomes, approved exceptions, and reviewer sign-off. Keep this record according
to the organisation's retention policy, with sensitive transcript data redacted.
