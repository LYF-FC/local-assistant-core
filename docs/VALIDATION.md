# Validation status

Local verification of the generalized snapshot on 8 November 2026 passed:

- 847 backend unit tests, 357 client tests, production client build and 14 CI selection policy tests.
- All 693 PostgreSQL integration tests, including database namespace refusal and permission checks.
- Logical backup, restore and recovery verification against an isolated synthetic database.
- 71 distinct portable browser scenarios across general features and Work meeting/review flows, including an explicit private-default regression.
- Repository policy, formatting, workflow lint, dependency/security scans and publication privacy/link checks.

The complete 81-scenario hosted browser suite remains pending; 10 scenarios require the hosted harness. No local result is a hosted CI pass. Run the complete required workflow on the new public source head before release. Staging, production and actual-owner acceptance are not certified.

Generic IDs are for fresh installations. They are not a conversion path for an existing private database. Both online migrations and runtime role setup reject a mismatched database before mutation.
