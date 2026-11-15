"""Offline governance validators for the spec 074 recovery set (Phase C, non-operational).

This package validates *records* and computes *models*. It generates, stores, reads or rotates
no key, opens no network or database connection, never writes or deletes any file, never reads a
recovery set, and never parses key material. It does not import ``app.recovery_set`` and does not
change the closed output of that tool. Every owner decision that is still open (people, retention
periods, capacity ratios and margins, the dump ceiling) must be supplied explicitly or stays the
literal ``undecided``; no default is invented here. Nothing in this package is verification,
acceptance or an operational-readiness claim.
"""
