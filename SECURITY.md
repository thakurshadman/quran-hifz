# Security and privacy

## Reporting

This is initially a personal pilot for the owner and a few known people. Raise
problems privately with the owner through existing communication. Do not put
credentials, recordings, transcripts or exploitable details in public issues.
GitHub private vulnerability reporting is optional for this pilot; no monitored
security email or response SLA is claimed. Before public release, establish an
appropriate private reporting route and support responsibilities.

The [SEC-001 pilot policy](docs/security/SEC-001.md) and
[short pilot note](docs/security/PILOT-NOTE.md) replace the earlier formal
research protocol for owner-and-friends use. No runtime safeguards exist yet.

## Audio and user data

- Start capture deliberately, show its state, and release it on stop/exit.
- Explain local or named remote processing before use; no silent remote fallback.
- Default to no persistent recordings/transcripts. Bound temporary buffers and
  clear them on completion/cancellation.
- Check remote provider retention/training behavior before transmission; unknown
  retention is not zero retention. Keep API secrets server-side where applicable.
- Save debugging samples only with explicit agreement on purpose, access and a
  deletion date. Honor deletion requests across copies; keep samples restricted.
- Keep audio, transcripts, tokens and identifying payloads out of logs/git.
  Accounts and analytics remain outside the initial prototype.
- Structured research or model training needs a separate decision and appropriate
  consent, rights, access, retention and withdrawal arrangements before collection.

## Threat model and release gate

Check the actual capture, storage/transmission and cancellation paths before use.
Use encrypted remote transport, restrict access, validate untrusted input and
review dependencies/models. Follow the practical checks in SEC-001; documentation
checks alone do not establish runtime safety.

Security/privacy defects still block merge. Qur’an integrity and uncertainty
handling retain the elevated review defined in [ENGINEERING.md](ENGINEERING.md).
Revisit privacy and reporting arrangements before unfamiliar users, a public
release, persistent research datasets or training. Code review, CI and repository
protections are unchanged.
