# Known recovery checkpoint

Operators must reject a valid older authenticated manifest when it differs from an independently retained source export checkpoint. Export emits public checkpoint metadata. Offline verification and normal preview/apply require an explicit expected manifest hash before database access. The existing hash binds the complete canonical body, including export identity/time/workspace/items. No format change, migration, service, dependency, external data, key material output or production access.

Acceptance: same-key older authentic export A is rejected under trusted newer checkpoint B without writes; B reconciles a real older dump; missing/malformed/mismatched checkpoints fail before connection; review/receipt binds checkpoint context; export cannot accept a target checkpoint. Existing quarantine, review freshness, atomicity, key pin and file protections remain.

This proves identity relative to the retained checkpoint, never global latest completeness. A deliberately trusted older checkpoint can still match its own file. No automatic adoption from candidate files or database receipts. Trusted owner library calls remain explicitly labelled and do not establish independent trust. Recovery remains incomplete, disabled and without grants.
