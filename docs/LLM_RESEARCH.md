# Task-specific model and dense/MoE research

Owner-requested investigation, 8 November 2026. RND-04/05 extend per-service lifecycle research and product innovation; they do not activate a model, change a running agent, download weights, grant a tool or authorize external inference. Both remain planned research. See [register](FEATURE_REGISTER.md), [dependencies](FEATURE_DEPENDENCIES.md), [installation controls](CONFIGURABLE_INSTALLATIONS.md) and [constitution](../.specify/memory/constitution.md).

## Specify

Determine whether one general local model or a small set of task-specific local models best meets actual household/professional requirements on each installation's supported hardware. Compare dense and sparse mixture-of-experts (MoE) candidates using reproducible task, privacy, reliability and resource evidence. Preserve a single-model baseline; specialization is a hypothesis, not a mandatory multi-model platform.

Separate models may suit conversational latency, repository coding, cited answers, structured extraction or long-context synthesis differently. Investigate those differences instead of assuming that a chatbot and coding worker need identical weights or that a specialist label implies better measured outcomes. Deterministic parsers, validation and structured state remain preferable where adequate. Embedding/reranking, vision and speech are separate capability evaluations, not assumed to share a generative LLM.

## Two independent routing questions

Application-level selection chooses an approved model/runtime for a task, feature and authorized workspace. An MoE model instead has learned internal routing among expert components; those components must not be assumed to be named household/coding specialists or independent tools. A selected application model can itself be dense or MoE. Compare each question independently and then their combined operating cost.

In ordinary dense models the same dense parameter structure participates across tokens; sparse MoE selects a subset of expert components while retaining shared model components. Active parameter counts alone do not establish model storage, resident memory or latency. Measure total weight footprint, runtime expert residency/offload, KV cache, quantization, context and memory-bandwidth effects on the actual machine. Do not advertise a sparse model as fitting the memory budget solely because its active count is small.

The [Switch Transformers paper](https://www.jmlr.org/papers/v23/21-0998.html) describes sparse conditional parameter selection and associated routing/communication trade-offs. The [Mixtral paper](https://arxiv.org/abs/2401.04088) gives a concrete sparse architecture where selected feedforward experts differ per token/layer and active parameters differ from total parameters. These primary references explain architecture, not which current model is best for Butler. Their historical benchmark results are not current candidate rankings, local inference measurements or guarantees of memory fit.

## Task evaluation matrix

| Task | Quality and safety evaluation | Operating constraints |
|---|---|---|
| Conversational assistant/coordinator | FR/ES/EN instruction following, correction/abstention, useful concise answers, grounded memory use and appropriate tool proposals | Interactive first-token/tail latency, session/context isolation and bounded context |
| Repository coding worker | Held-out synthetic repository tasks: issue reproduction, correct patches, executable tests, regression avoidance and honest completion reporting | Sandboxed tools, file/network budgets, full completion time/retry count; no live shell/deploy authority from generated code |
| Document answers | Source-faithful answers/citations, authorization, abstention with missing/conflicting evidence and malicious source instructions | Retrieval quality/context limits, citation validation and no unintended egress |
| Structured invoice/record extraction | Schema validity and field-level accuracy, exact provenance, uncertainty, null versus invented values and duplicate ambiguity | Deterministic parser/validator baseline, bounded retries and mandatory human review where required |
| Summaries/briefings/professional advice | Evidence preservation, decisions versus suggestions, unknown owners/dates, multilingual quality and long-context degradation | Correct workspace/context, retention, inference bounds and no cross-domain leakage |

## Experiment and comparison protocol

1. Inventory intended hardware and available RAM/unified memory/VRAM, OS/runtime/accelerator support, supported commercial licenses and acceptable storage/power/latency. Installation hardware is a variable, not one universal recommended purchase. Do not infer production sizing from a development machine.
2. Build a small dated shortlist from official model cards, weight/license documents, supported runtime documentation and primary results. Pin weights/tokenizer/template/runtime/backend revisions, architecture, total/active counts, quantization and license restrictions. Verify current availability/support before experiments; do not adopt a model from an old paper's leaderboard.
3. Define bounded public/synthetic datasets, held-out cases, expected results, numerical quality/refusal/citation/schema/latency/memory thresholds and run/time/storage budgets before testing. Do not benchmark on private family/employer records. A coding sandbox gets synthetic repositories and no production credentials. No new experiment/training/collector schedule is created here.
4. Compare a general-model baseline, plausible task specialists and dense/MoE candidates. Hold task, prompt, context and output budgets, tools and hardware constant where feasible. Report unavoidable differences and quality/resource trade-off curves; equal active parameters, equal quantization labels or equal advertised size alone do not make experiments equivalent.
5. Record cold/warm startup, loading/unloading and task switching, prefill/first-token and generation/completion time, throughput, p50/p95 where adequately sampled, success/retries, peak and steady memory, KV/cache growth, disk use, accelerator utilization and energy/thermal behavior where measured. Include concurrent chat/coding requests and background deterministic-job responsiveness. Mark unavailable metrics unknown rather than estimated measurements.
6. Separate prompt/template, retrieval/tooling and quantization effects from architecture. Repeat enough to report variability and include failures/OOM/timeouts. An LLM judge may assist but cannot substitute for executable coding tests, field/citation checks and human review. Small samples are exploratory, not confidence or statistical superiority claims.
7. Produce a dated task/model/runtime/configuration matrix and adopt/defer/reject recommendation. Explain whether gains justify multiple resident models, serialized swapping, one general model or no LLM for a task. Set a revisit trigger when requirements or verified releases change. A negative result is a valid research outcome.

Actual weight downloads and benchmarks require a separately scoped resource/rights-reviewed experiment. This document delivers the investigation contract, not completed comparisons or permission to consume unbounded hardware/network resources.

## Future configuration and authority boundary

If evidence supports specialization, propose an ADR and versioned per-task model configuration under INSTALL-02/03/10. Model selection should be explainable and auditable with policy/version/task/runtime provenance and a safe global disable. Handle missing/incompatible/unavailable models explicitly; a configured local fallback must be authorized, resource-bounded and reported. No silent remote fallback, quality downgrade or expanded permission follows an error or model-confidence score.

Feature enablement, model readiness and current user/workspace permission are separate checks. All selected models share the same application-enforced content/tool limits; a coding model receives no inherent shell/deployment rights. Keep household and Work prompts/history/caches/retrieval isolated even when inference hardware is shared. No cross-model unrestricted memory broadcast. Conversation and model failures must leave deterministic reminders, records and recovery available. Existing external-model gateway approval rules remain unchanged.

This research concerns Butler's application capabilities. It does not change the model, subscription, settings or behavior of the Codex application used to develop the repository.

## Plan, tasks and acceptance

Use the low-risk documentation flow for this scope extension: specify → plan → tasks → implement → converge. Retain all prior requirements; add RND-04/05 with dependencies; align canonical context/architecture/decisions/operations/setup and roadmap; verify ID parity, links, privacy and documentation policy before one completed batch push. Record exact-head hosted evidence in PR metadata, with no automatic merge.

Later investigation acceptance requires a sourced current shortlist, declared task/hardware/budget assumptions, reproducible bounded fixture/evaluation manifests, measured baseline/comparison results and failures, architecture-versus-routing analysis, quality/resource trade-offs and an explicit recommendation with limitations. Do not mark research complete from this specification alone. A routing/runtime implementation needs separate full feature planning, model/permission/egress refusal tests, provenance, concurrency/resource tests and controlled rollout/rollback evidence.

Prioritize feasibility and baseline work alongside scoped local answers/coordinator design. Multi-model execution or MoE adoption is not an unconditional MVP blocker. No existing requirement is removed; no provider, private-data processing, production change or model license is selected here. No data leaves the installation as a result of this documentation-only change.

Planning convergence: all 147 prior references remain; register and dependency tables each contain the same 149 unique IDs. Changed links/anchors, privacy review, repository invariants and all 14 CI policy tests pass locally. Source secret scanning reports no findings. No model comparison or runtime acceptance is claimed. Exact-head hosted policy evidence belongs in PR metadata, and owner review/merge is still required.

## Dated candidate observation — 22 November 2026: a community Qwen3.8-27B fine-tune

Owner-requested desk check of one community build, "Qwen3.8-27B TURBO Fable Cold-Fusion 735/882 Heretic Uncensored NEO CODER MAX MTP GGUF". This is an input to the shortlist step above, **not a shortlist entry, adoption, rejection of the base family, approval or recommendation to download or run anything**. Nothing was downloaded or run. It selects no model, runtime or license and changes no requirement, gate, status or priority; no model choice is recorded in this repository. Facts were read from the pages cited below on 22 November 2026 and may change; items marked *self-reported* are the packager's own, unverified claims.

**What the build is (per its Ollama listing).** A community multi-stage merge, refusal-removal ("Heretic" abliteration) and quantization of Qwen3.8-27B, published under the `lucloner` namespace with one `mtp-q4km` tag (about 18 GB, 256K context, text input, tools and thinking capabilities). The derivative's license is not stated on the page; only the base is said to be Apache 2.0. The name's "735/882" are the packager's own ARC-Challenge/ARC-Easy scores on an mxfp8 quant (*self-reported*); "Cold Fusion" and "NEO CODER MAX" are not defined by a cited method, paper or code. The packager reports that a stock Ollama import corrupts the file and that appending an extra tensor fixes it (*self-reported*, not verified).

**The base model (vendor and press reports).** Qwen3.8-27B was released on 14 August 2026 under Apache 2.0 as a dense 27B vision-language model with a 262,144-token native context (extendable by YaRN) and switchable thinking. The separate 2.4T-A95B "Max" model has a different license; that does not apply to the 27B. Published benchmarks are largely the vendor's own, partly on its own harness, and are not like-for-like comparisons. Third-party size figures for 4-bit weights are roughly 17–19 GB (community-reported).

**Assessment against the requirements above (an observation for the shortlist step, not a decision).**

| Concern | Observation |
|---|---|
| Refusal removal | The build's purpose is reducing refusals. Butler relies on application-enforced permissions, not on a model, but a private-records assistant also benefits from a model that abstains and resists hostile document content; this must be measured, not assumed. |
| Provenance and supply chain | A merge across several individuals without a reproducible recipe, and a packaging workaround, cannot be audited at reasonable cost. |
| License | The derivative's license is unstated; a derivative needs its own license review before any use. |
| Evidence | The benchmark table, speed and token-saving claims are *self-reported* or marketing, on different quantizations than the listed tag. |
| Task fit | The build's "coder" emphasis does not match Butler's runtime tasks; repository coding workers are a separate row in the task matrix. |

If the family is revisited, evaluate **official weights from the vendor and reputable quantizers** (pinned revisions, recorded license text) under the protocol above, alongside other dense and MoE candidates, on synthetic fixtures only, with refusal, abstention and hostile-document behavior in the evaluation set and the owner's actual hardware recorded first. The base's vision capability may be relevant to scanned-invoice and document tasks (compare against OCR and deterministic parsing). Any download, license acceptance or benchmark remains a separately scoped, owner-approved experiment.

Sources read on 22 November 2026: [Ollama listing](https://ollama.com/lucloner/qwen38-27b-turbofcfusion); [eWeek on the Qwen3.8-27B license](https://www.eweek.com/news/alibaba-qwen3-8-27b-license-apac-china/); [NYU Shanghai RITS on Qwen3.8-27B](https://rits.shanghai.nyu.edu/ai/qwen3-8-27b-one-gpu/). The official model card and the packager's Hugging Face page were linked from these pages but not read.
