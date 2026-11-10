# Restricted manual financial capture — implementation contract

This contract specifies the remaining basic FIN-06 MVP slice: manually recorded goals, dated assumptions, recorded existing plans and source references in restricted finance space. It is design work, not an implemented register, accepted MVP journey, financial recommendation or provider authorization. The [complete register](FEATURE_REGISTER.md) and later financial scope remain unchanged.

## Outcomes and meaning

A member explicitly granted `finance_private` can create, inspect, correct, export and forget their own records. Another member with the same scope cannot see those records, IDs, counts, search matches, history or exports. A technical administrator has no implicit finance access. Shared household access and family/professional relationships confer none. Broader jointly managed financial records require a later explicit grant/ownership contract; do not silently treat the current scope name as household sharing.

Record categories are goal, assumption, plan and source. Topics cover lifestyle, target horizon, spending baseline, property ambition, accepted constraint and general context. Every record carries a required calendar `as_of` date and source reference. A goal is an intended outcome, not an expected return. A source is an attributed reference, not verified truth. Sources remain untrusted text or opaque IDs; never fetch a URL, read a document or initiate an account connection merely because a reference is recorded.

Each record explicitly labels its basis as **confirmed input**, **assumption**, **forecast** or **unknown**. Confirmation means the member confirms the recorded input, not independent verification, guaranteed results or professional endorsement. Unknown values remain null/unknown rather than zero, false, an empty confirmed amount or an inferred date. Corrections preserve prior versions and attribution; later records never silently replace an approved baseline or prior decision.

An existing plan can be recorded as proposed or accepted by the record owner. Accepted status requires explicit acknowledgement that the entry is a record of the owner's choice, not permission to execute it. Store who recorded that acknowledgement and when. Generic application approvals, record confirmation and future exact-action authority remain distinct. There is no transfer, trading, subscription, financing application, lender contact, automatic notification or external send in this slice.

## Bounded data contract for implementation

| Field | Bound / semantics |
|---|---|
| Identity | Server-generated UUID, immutable owner/scope/creation time; scope fixed to finance_private. No caller-supplied owner or scope move. |
| Kind/topic/basis | Closed enumerations above; unsupported values/versions/extra keys reject before mutation. Kind is immutable; correction cannot repurpose a record into a different semantic category. |
| Title / statement | Nonblank printable title at most160 Unicode characters; statement at most4000. Source text is rendered inertly. |
| Dates | Required valid ISO calendar as_of; optional target date. Supported years1900–2200. Calendar dates are not silently converted into UTC instants. Historical target dates remain valid and visibly historical; no guessed horizon. |
| Source | Required nonblank printable reference at most512 characters, plus optional source calendar date. No automatically resolved document/account authority. |
| Amount | Optional non-negative fixed decimal string, at most12 integer and2 fractional digits, canonical two-decimal representation; paired currency from EUR/USD/GBP/CHF/CAD/JPY. Null amount has null currency. No binary floating-point storage/arithmetic, totals, conversion, return or tax calculation. Precision is a capture format, not a claim about currency settlement rules. Unsupported currencies reject explicitly rather than substituting one. |
| Plan review | Null outside plan records; proposed/accepted inside. Accepted requires explicit record-only acknowledgement; all other kinds reject an acknowledgement masquerading as action authority. |
| Versions / quotas | Schema1, revision1 onward; expected revision on correction/forget. At most100 records per owner including tombstones,100 revisions per record,25 rows per list/export page and25 history rows per page. Enforce creation quota under owner lock. At revision limit correction pauses while reads/export/forget remain available; terminal forgetting can append one final scrubbed revision. |

Limits are an implementation contract, not current runtime behavior. Detailed schemas must preserve these bounds and define every no-op/history-limit outcome before code ships. The first implementation must not add the amount field if canonical validation/storage, ambiguity handling and the listed tests are incomplete; omitting it requires an explicit documented narrower slice rather than silently accepting untyped numbers.

## Storage and authority decision

Use dedicated financial capture records/revisions with server-validated closed schemas. Reuse existing session, scope, audit, transport and migration patterns; do not create a second identity or approval system. Generic Memory remains appropriate for explicit memory, but a client-only JSON convention cannot enforce this finance schema or its distinct unknown/forecast/plan semantics. Do not label arbitrary Memory profiles as a delivered financial register or inherit generic context eligibility for financial payloads. No automatic finance-to-memory, search, briefing, document-answer, professional or model-context projection is introduced.

Every route must check current user/session and explicit finance grant, then owner/scope visibility before returning content or metadata. Origin/CSRF applies to mutations and protected POST read operations under the established transport. Lock current user/grant before the selected record, revalidate expiry/current authority after waits, use expected revision and atomically commit current row, matching history and metadata-only audit before releasing success. Use sealed database guards for identity, increasing revisions, valid active/forgotten shape, bounded payload and matched append-only history; runtime cannot delete/truncate or rewrite accepted history. Read paths and denied-ID responses must not reveal whether another owner has a record.

An accepted plan acknowledgement binds the exact payload/current revision, actor and decision timestamp. Any material correction resets acceptance to proposed and requires a fresh explicit acknowledgement. No inherited acknowledgement from a prior version or cross-record receipt. A stale/conflicting response preserves the user's draft but withdraws confirmation; never retry a mutation automatically. A no-op cannot create a new acceptance decision implicitly.

## Privacy, export and forgetting

The UI is explicit and in memory only. Clear sensitive views/drafts/confirmations on denial, logout, session/view changes and hidden tab; discard late responses and expire displayed finance snapshots after at most60seconds. No local storage, browser URL, telemetry, ordinary log, model request or general context contains finance payloads. Finance-only navigation appears only for currently granted users; the server remains the authority. Inaccessible/unsupported records are unavailable, not silently rewritten or treated as zero.

Explicit exports require a copy/privacy acknowledgement and preserve schema, stable IDs, dates, source, basis, correction lineage and recorded plan-review attribution. Supply human-readable Markdown and versioned JSON for the selected current record/history or bounded page; no implicit full-database export. Downloads are unmanaged copies and cannot be revoked. No outbound service receives data; the only egress is the owner's explicit local download.

Forgetting scrubs current values and all managed historical payloads atomically, retaining only documented minimal UUID/owner/scope/revision/state/timestamp tombstones and metadata audit. Repeated forgetting is safe and never resurrects data. No amount, title, statement, source, basis or plan decision survives in a forgotten history/export. This does not erase old dumps/WAL, screenshots or downloads. Record suppression/recovery requirements explicitly; a successful local scrub is not a whole-installation erasure certificate.

## Required implementation evidence

1. Strict schema, decimal/date/enum/basis/unknown and plan acknowledgement tests, including malformed/oversized/extra fields and material-correction acceptance reset. Never calculate forecasts or perform a financial action.
2. Two independent synthetic members with finance grants plus an administrator without one: bidirectional read/query/count/history/export/mutation denial, revoked membership/session after lock wait, Origin/CSRF negatives and no raw validation input in errors/audit.
3. Actual disposable PostgreSQL runtime role/idempotence, SQL identity/history/tombstone guards, concurrent quota/correction races, stale revisions, audit failure rollback and commit-before-release evidence.
4. Real migration upgrade/check/downgrade/upgrade and full protected logical restore: active confirmed/assumption/forecast/unknown records, dated sources and acceptance attribution preserved; forgotten values remain scrubbed. A downgrade that drops records needs reviewed backup/rollback and explicit loss disclosure. No private deployment upgrade is implied.
5. Trusted synthetic HTTPS desktop/mobile create/read/correct/history, explicit plan review/reset, unknown versus zero/forecast, JSON/Markdown export acknowledgement, forgetting, conflict draft retention, hidden/late-response clearing and actual grant/session denial. Fixtures use CI's default butler migration owner and prove runtime refusal before privileged seeding.
6. Required checks, privacy/source review and conservative full hosted CI for backend/schema/permission work. Keep branch evidence, merged engineering, host/provider acceptance and full FIN-06 scope separate. Do not promote the register from this design batch.

## Retained later scope

Full FIN-06 goal/progress modelling and FIN-01/02/07–17 remain open: reconciled imports, actual-versus-plan comparisons, reproducible trajectory/scenario engines, investment policy/portfolio, property/opportunity research, currency/tax/jurisdiction metadata and professional review. Manual source capture does not certify those dependencies. Deferred REV/refactoring work remains after the existing scope/later stages. Implementation uses synthetic examples only; personal financial plans and private history remain outside Git.
