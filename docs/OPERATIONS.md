# Production operations

## Deployment baseline

Run Nomaya behind TLS and an authenticated reverse proxy. Set a non-empty API
token, a narrow model allow-list, explicit CORS origins, a persistent encrypted
database volume, and a retention period. Never expose the development defaults to
the public internet.

## Operational limits

Configure evaluation concurrency, timeout, retry count, and a per-run cost cap.
The API should be monitored for failed jobs, timeouts, cancellation volume,
provider errors, spending, queue depth, and judge-inconclusive rates. Alert on
failed production jobs and on regression thresholds chosen by the compliance owner.

## Data handling

Use synthetic fixtures whenever possible. Transcripts are redacted before storage;
access to retained runs must be limited to authorised reviewers. Set a retention
period and run the purge operation on a schedule. Backups must use the same access
and encryption controls as the primary store.

## Incident response

If a run contains unredacted sensitive data, stop exports, restrict access, rotate
credentials if needed, purge affected artifacts according to incident policy, and
record the incident in the audit system. Re-run the affected evaluation only after
the root cause and remediation have been reviewed.
