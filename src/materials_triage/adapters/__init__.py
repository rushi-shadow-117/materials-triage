"""Source adapters.

Contract (every adapter): return normalized records that carry the source name,
the source record ID, the fetch timestamp, the SHA256 of the raw response body,
and explicit units. Raw responses are stored immutably by the provenance store
before any normalization. Missing fields stay missing.
"""
