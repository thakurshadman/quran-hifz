# Security and privacy

## Reporting

Do not put credentials, personal recordings, transcripts, or exploitable details
in a public issue. If GitHub private vulnerability reporting is enabled, use the
repository Security tab to report privately. Its availability has not been
verified. If unavailable, ask the owner through a non-sensitive issue to enable a
private reporting channel; share only the request for a channel publicly.
Do not assume a monitored security email or response SLA exists.

The project currently has no application releases. The human owner triages
reports and must establish supported versions, response ownership, and a private
reporting channel before a public application release (**SEC-001**).

## Audio and user data

- Request microphone access only after a deliberate user action. Clearly show
  capture state and provide a stop control; release the microphone on stop/exit.
- Disclose on-device versus transmitted processing before capture/transmission.
  Never switch to remote processing without the required informed choice.
- Default retention is no persistent audio or transcript storage. Document and
  bound any transient processing buffers; purge them on completion/cancellation.
- Remote candidates must document provider logging, retention, training use,
  subprocessors, region, and deletion behavior. Unknown provider retention is
  not evidence of zero retention and cannot satisfy the release gate.
- Collect research recordings only with consent and rights for the stated use.
  Keep them in approved restricted storage, outside this public repository.
  Define retention, withdrawal, deletion, and any age-related safeguards before
  recruiting participants. No production/user audio collection occurs in Phase 0.
- No raw audio, transcripts, tokens, or identifying telemetry in normal logs.
  Accounts and behavioral analytics are outside the initial prototype.

## Threat model and release gate

Before introducing a data flow, identify assets, trust boundaries, threats,
controls, and verification: microphone misuse, transport interception, malicious
metadata, compromised dependencies/models, credential exposure, unauthorized
storage, and Qur’an dataset tampering. Use TLS for remote transport and minimize
access to all retained research data.

Security/privacy violations block merge. Before release, verify consent UX,
capture shutdown, storage/log behavior, third-party terms, deletion, dependency
audit, and incident/rollback procedures. Qur’an integrity also requires the
elevated content review defined in [ENGINEERING.md](ENGINEERING.md).
