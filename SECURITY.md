# Security

This source is a development/test foundation. It is not a supported production release. Production/staging API startup is refused; normal development networking stays loopback-only. Publishing source never publishes a running database or application.

Controls include Argon2id credentials, revocable server-side session digests, secure __Host cookies, CSRF, exact Host/Origin and trusted-proxy boundaries, persistent login limits, scoped/owner-filtered reads, optimistic revisions, transactional minimal audit, restricted database roles and negative permission/concurrency/restore tests. There is no administrator-proof archive or guarantee against an operator with host/superuser access.

Use generated per-environment secrets. Never commit records, `.env`, private keys, mailbox content, exports or real employer/household data. Synthetic fixtures are intentional examples, not reusable service credentials. Keep private copies outside this repository and its history.

No external AI fallback, mail/calendar connector, real work source or external dispatch is enabled by publishing the code. Optional Work paths remain explicitly synthetic and separately opted in. Text/Markdown is inert source data; review does not verify truth. Production key management, independent recovery, MFA/recovery policy, sandboxed parsers and domain-specific acceptance remain separate work.

Report vulnerabilities privately through the repository's private reporting channel when one is configured, or contact its maintainer out of band. Never post live credentials or personal records in public issues. Public reporting support is not assumed to be configured by this local preparation.
