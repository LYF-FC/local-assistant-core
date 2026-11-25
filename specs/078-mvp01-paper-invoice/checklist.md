# Checklist — spec 078 (requirements quality)

- [x] Every requirement names its owner decision (D1–D9) or states that it is an engineering choice (A-1..A-3).
- [x] Backend, migrations, `pdf_worker`, security controls: none changed (verify with the changed-paths list).
- [x] Real vs simulated labelled everywhere: engines real on synthetic bytes; destination, model, calendar simulated.
- [x] No accuracy claim for OCR; "not verified confinement" for seccomp; "metadata only" for filing; restart = SIGKILL/container only.
- [x] Fixtures synthetic, deterministic, checksummed, ≤128 KiB, distinct invoice numbers and Message-IDs.
- [x] Unknown is not zero stated on the review form, plan, filing view and guide.
- [x] Waiting/unavailable/empty never rendered as failed.
- [x] Owner steps are browser-only apart from the printed `scripts/mvp01-owner.sh` commands; ≤3 sign-ins.
- [ ] Owner acceptance (owner only).
