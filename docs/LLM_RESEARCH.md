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

## Dated desk investigation — 24 November 2026: hardware-specific shortlist

### Scope and evidence status

The owner requested further LLM investigation while the MVP-01 journey implementation continues. This section extends the existing research contract; it is not a new tracker, runtime decision or completed RND-04/05 evaluation. Official sources below were read on 24 November 2026. No model weights were downloaded, inference run, provider activated or dependencies changed. Human verification and owner acceptance remain pending; this research changes no journey priority or acceptance state.

The repository baseline for this documentation update is `22420be8f9d7799e82aa8d38e88a1314dbc303d9`. Current scope and sequencing remain in [PROJECT_MASTER.md](../PROJECT_MASTER.md). Vendor capabilities and memory estimates below are inputs to testing, not Butler measurements. Exact candidate weight, quantizer, template and runtime revisions remain unselected.

### Hardware assumptions supplied by the owner

| Research profile | Owner-supplied target | Consequence for the comparison |
|---|---|---|
| POC | MacBook Pro, M2, 16 GB unified memory | Start with one quantized 4–9B-class model. Preserve memory for macOS, browser, PostgreSQL/API and PDF/OCR work; a model that loads in isolation may still be unusable during the journey. |
| MVP / Butler | Planned Mac mini, M5 Pro, 64 GB unified memory, 2 TB SSD | Compare a 27–31B-class general model with a sparse MoE challenger and a smaller interactive option. Storage allows several candidates on disk, not necessarily simultaneous residency. |

These are owner-reported research inputs, not a hardware availability, procurement, performance or installation certification. OS version, exact processor configuration, free memory under the running journey, concurrency and acceptable latency remain unknown. The 16 GB machine can establish POC behavior, but cannot establish the planned machine's performance. Quantization reduces weight memory; runtime buffers, image processing and context/KV state still need separate measurement. An advertised 128K/256K context is not an approved operating context.

### Current candidate comparison

The test order below is a research recommendation, not an adoption ranking. Start with a general model; add a specialist only if it improves a declared task enough to justify loading, swapping and maintenance costs.

| Candidate | Official evidence and license | Proposed place in Butler's comparison | Main unresolved question |
|---|---|---|---|
| Qwen3.5-9B | Official image/text model; Apache 2.0. [Model card](https://huggingface.co/Qwen/Qwen3.5-9B). | First POC general-model baseline at a pinned approximately 4-bit quantization; conversation, grounded answers and extraction proposals. | FR/ES/EN quality, abstention and responsiveness while the full journey runs on 16 GB; exact native runtime/quant support. |
| Ministral 3 8B Instruct 2512 | Vision-capable instruct model; Apache 2.0; vendor publishes a GGUF repository with quantization choices. [Official GGUF card](https://huggingface.co/mistralai/Ministral-3-8B-Instruct-2512-GGUF). | POC challenger to Qwen, particularly for concise instruction following and structured proposals. | Whether it improves accuracy or latency under identical task/context budgets; vision support in the exact runtime build. |
| Gemma 4 E4B / 12B | Multimodal family; Apache 2.0. Google lists approximate Q4_0 accelerator memory of 4.5 / 6.7 GB, explicitly environment-dependent. [Overview](https://gemma.ai/models/gemma-4/), [model card](https://gemma.ai/models/gemma-4/model-card/). | E4B as a compact POC challenger; 12B as a conditional POC candidate and smaller MVP option. | Whole-system memory and latency, including modality/context costs; Google's figures are not Mac measurements or guaranteed headroom. |
| Qwen3.8-27B | Dense 27B language model with vision encoder and configurable thinking; Apache 2.0. [Official model card](https://huggingface.co/Qwen/Qwen3.8-27B). | First stronger general-model baseline for the 64 GB target; compare thinking disabled/enabled with bounded output. | Native runtime compatibility, reliable citations/extraction and whether quality gains justify time and memory. Do not substitute the community merge observed above. |
| Gemma 4 26B A4B / 31B | Sparse MoE / dense alternatives; Apache 2.0. Google's approximate Q4_0 figures are 14.4 / 17.5 GB. [Overview](https://gemma.ai/models/gemma-4/), [model card](https://gemma.ai/models/gemma-4/model-card/). | Main MVP dense/MoE comparison against Qwen3.8-27B, using the same synthetic tasks and bounded context/output. | Quality versus latency under actual Apple hardware; the MoE's active count is not its resident weight budget. |
| gpt-oss-20b | Text-only MoE, about 21B total / 3.6B active; Apache 2.0, Harmony format. Vendor says MXFP4 deployment can run within 16 GB. [Official card](https://huggingface.co/openai/gpt-oss-20b). | Secondary text reasoning/tool-proposal comparator on 64 GB. Not the initial 16 GB whole-journey baseline. | Correct format/parser support, FR/ES/EN grounding and bounded reasoning latency. A vendor 16 GB claim does not leave established capacity for the rest of Butler. |
| Nemotron 3 Nano 30B A3B | Hybrid Mamba/attention MoE, 30B total / 3.5B active; vendor lists FR/ES/EN among supported languages. NVIDIA Nemotron Open Model License, not Apache 2.0. [Official card](https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16). | Reserve 64 GB reasoning challenger after the first comparison, subject to license and native runtime review. | Whether its hybrid architecture and exact quantization have suitable Apple support; no NVIDIA benchmark establishes Mac performance. |

The 27–31B entries are not first-pass 16 GB POC recommendations. Large flagship models with a small active expert count are not automatically laptop candidates. No generic winner follows from vendor coding or reasoning leaderboards: Butler needs multilingual grounding, correction, permission-aware tool proposals and predictable operation during document processing.

**Assessment of the earlier candidate.** Retain official Qwen3.8-27B as a plausible 64 GB comparison candidate, but defer the `lucloner/qwen38-27b-turbofcfusion` derivative: its listing reports an 18 GB artifact, multi-stage refusal removal and an import workaround, while derivative licensing and reproducible quality evidence remain unresolved. Its "M2" benchmark label refers to a test on dual TITAN RTX GPUs, not an Apple M2 measurement. Those results establish neither Mac fit nor Butler task quality. This assessment follows a fresh reading of the [packager's listing](https://ollama.com/lucloner/qwen38-27b-turbofcfusion) and the [official base card](https://huggingface.co/Qwen/Qwen3.8-27B); the 22 November observation above remains dated history. Switch Transformers and Mixtral above are architectural references, not previously selected deployment models. Model selection, benchmarking, human verification and owner acceptance all remain pending.

### Runtime and capability boundaries

Compare native Ollama as the existing architecture's serving candidate with llama.cpp where explicit GGUF/backend controls help reproducibility. MLX is a separate Apple-native comparison where the exact model architecture is supported; [MLX LM](https://github.com/ml-explore/mlx-lm) provides text generation and quantization on Apple silicon, which does not by itself establish vision support. [llama.cpp](https://github.com/ggml-org/llama.cpp) documents Apple Silicon/Metal support. Pin runtime versions and test model-specific templates, tool parsing and modality support rather than treating an OpenAI-compatible endpoint as semantic compatibility.

Set context and concurrency explicitly for every experiment. [Ollama's context documentation](https://docs.ollama.com/context-length) describes memory-dependent defaults and the cost of larger contexts; defaults are not a controlled comparison. Keep accelerated inference native, with ordinary Butler services in their existing containers. Do not tune macOS memory limits or rely on sustained swap merely to make a candidate load.

Retrieval needs its own baseline: [Qwen3-Embedding-0.6B](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B) is a small multilingual embedding candidate; the official family also includes a 0.6B reranker. Evaluate retrieval recall and evidence coverage separately from generated answer quality before adding a reranker. Any model/index change needs explicit versioning and reindex/migration planning. Neither embeddings nor a vision model replace authorization, provenance or the deterministic PDF/OCR/parser baseline. Speech remains a separate investigation.

Hosted ChatGPT/Claude development agents and Butler's local inference are different resource decisions. No paid API, subscription change, remote inference or private-data transfer follows from this shortlist. Any future external-model comparison must first satisfy the existing gateway's payload, permission, retention and budget rules.

### Proposed bounded evaluation, not yet authorized or run

Prepare a reproducible synthetic manifest before downloading weights. Proposed first pass: 60 held-out cases, 12 each for conversation, cited answers, extraction, summaries and synthetic repository coding, balanced across FR/ES/EN. Coding is a separate sandbox experiment, not a prerequisite for the invoice journey. Include known answers, missing/conflicting fields, forged document instructions, correction, revoked access and attempted cross-scope tool calls. Test application-enforced denials separately from model abstention. Keep a deterministic/no-model baseline for each applicable task.

Proposed resource bounds for review: one candidate loaded at a time, two initial candidates per hardware profile, at most four hours of active measurement per profile and 40 GB of downloaded artifacts for the POC / 120 GB for the MVP comparison. Start at 4K and 8K context on the POC and 8K and 16K on the MVP target, with a 512-token normal output cap; reasoning gets a separate explicit total-token/time cap. Record exact templates, quantization and seeds/settings; run three trials per case. Context expansion, extra candidates or repeat runs must fit an agreed revised budget, not silently extend it.

Before any run, the reviewer and owner must settle numerical acceptance thresholds: field accuracy and critical-field error tolerance, valid schema rate, citation entailment/coverage, appropriate abstention, task success, time to first token, complete-answer latency, timeout/retry rate and whole-system memory/pressure limits. No arbitrary threshold is represented here as an accepted requirement. Synthetic finance extraction must preserve unknown/null and source references; permission failures cannot be offset by a good average quality score.

Measure cold/warm load, peak inference memory and whole-machine pressure/swap, first-token/completion latency, model switching and concurrent chat plus PDF/OCR plus deterministic job responsiveness. Report all OOM/timeouts and variability. Three trials per case are exploratory; any percentile must state sample size and is not production-tail certification. Retain raw public/synthetic outputs with model/runtime/configuration provenance, and have a human review multilingual usefulness and evidence fidelity.

**Evidence-based next action:** finalize that manifest and its thresholds/resource envelope, then obtain the separately scoped authorization required above for downloads and benchmark execution. Begin the 16 GB comparison with Qwen3.5-9B versus Ministral 3 8B; keep Gemma E4B as the smaller alternative if memory or latency fails. For the 64 GB target, start with Qwen3.8-27B versus Gemma 4 26B A4B, adding the dense 31B comparator only within the approved budget. Actual fit, quality, latency, hardware availability and the value of specialization remain unverified. RND-04/05 remain open; no model, runtime, license or owner acceptance is selected by this document.
