# Spec 077 review checklist

Unchecked; a reviewer aid, not acceptance.

- [ ] No migration, new filing state, spec 069/Spec 074/075 change, grant, trigger, rate-limit or clock change.
- [ ] `outage on` uses only existing controls; `off` removes exactly those; restarts keep the model stopped while the flag is set; reset removes the flag.
- [ ] Reason text never calls an unconfirmed or waiting filing failed/lost/filed; the three-attempt end is stated as final.
- [ ] The filing panel's added read is read-only and the form is withheld until the listing is known; accepted invoice-review load behaviour unchanged.
- [ ] Peer checks are negative and include a positive control; password replacement used only on a disposable verify stack.
- [ ] F2 checksum is published and verified before it is copied; fixture is synthetic.
- [ ] Limits stated: simulated outage, S4 write-only outage, no non-owner-editor live check, no host reboot.
