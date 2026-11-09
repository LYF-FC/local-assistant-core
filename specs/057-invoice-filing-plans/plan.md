# Plan / analyze

Extend the existing source-bound invoice aggregate with an optional versioned filing plan, preserving sealed history, original export/forget and audit transactions. Add deterministic pure grammar/template helpers, three explicit plan lifecycle routes, strict optional plan parsing, and a document-detail child UI. No schema migration/dependency/service or executor; existing JSON payload/table bounds apply. Approval is non-executable review state and cannot become a generic approval ticket for future workers.

DOC-03 proposal work extends DOC-02/spec 056; it does not replace restricted mail/DOC-01 email lineage, DOC-03 apply/rollback or full MVP-03 crash/retry acceptance. Preserved detailed intake contract requires authorized folders, uncertainty review and original/email references; only synthetic logical destinations are modeled here. DOC-04 bulk cleanup remains distinct; INSTALL/RND and all 149IDs preserved.

PR11 merged at df88edfa398db275d1da4bdecfff5e8b9cebb843; exact feature head run 42607612132 passed all six jobs. Main run 42609440945 was in progress at initial inspection; do not claim exact-main certification or poll. Focused tests during implementation, then one final makecheck/security, full disposable PG/recovery and affected HTTPS phase. One coherent commit/push/draftPR; stop after publishing.
