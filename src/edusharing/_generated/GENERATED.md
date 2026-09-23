# Provenance of this layer

Machine output. Do not edit by hand -- `scripts/generate_client.py`
rewrites it together with this note.

- Generator: `openapi-python-client` 0.29.1 (from `uv.lock`)
- Spec: edu-sharing Repository REST API 1.1
- Source: `openapi/edu-sharing-11.0.json`
- SHA-256 of the spec: `94eb2f09b1924616419a7a4ab0bef90b85562cd4d27eb94452b20f17920e37f5`

The hash is of the spec as it was read -- before the path parameter
defaults were removed and the response content types normalised.
After generating, the script inserts deterministic ValueError checks
for empty and pure dot path segments (`.`, `..`).
