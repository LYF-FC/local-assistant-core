# Spec 010 — delivery/backlog and M2 POC reconciliation

Documentation/POC-helper increment after merged #30. No domain, model, permission, migration or production activation.

R1: close only completed development foundations (#2 identity, #3 audit/approvals) using green main evidence; retain #4/#5/#6/#7/#9/#24/#25 with precise remaining work. Deferred main protection stays accepted; full spec 001/production acceptance is not implied by two issue closures.
R2: reconcile README/roadmap/readiness/spec status and first-run docs with merged #26–30 and migrations through 0005. Distinguish delivered code, hosted evidence, actual M2 and production acceptance.
R3: give a concrete isolated synthetic M2 procedure with separate Compose project/public-CA export, trusted local provisioning and Memory/Discovery checks. No real data, model install, credentials in evidence, host trust-store change or destructive reset by automation.
R4: first-run must use the same optional BUTLER_LOCAL_CA_FILE override as healthcheck, retain current default behavior and quote paths. Its banner describes delivered UI; foundation setup must not probe/encourage installation of an unrelated native model service.
R5: meaningful mocked helper acceptance checks that a custom public-CA path with spaces is exported and verified, synthetic .env contents remain unchanged and no model endpoint is contacted. Existing CI remains required; actual M2 result is still owner-run.
