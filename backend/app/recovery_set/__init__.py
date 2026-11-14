"""Offline recovery-set manifest tool (spec 074): ``generate`` and ``verify``.

Synthetic-only implementation of the frozen specification. The package opens no database or
network connection, never writes inside a verified set, and verifies only the integrity and
authenticity of a defined backup set. It establishes no recoverability, restoration, key
custody, freshness authority or recovery-readiness claim.
"""
