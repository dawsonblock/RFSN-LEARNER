# Vendor components

This folder contains third-party or external codebases vendored for reference or optional integration.

Policy:
- `rfsn/` kernel and `upstream_learner/` never import from vendor by default.
- Anything under `vendor/` is non-authoritative and must not execute actions directly.
- If you wire vendor code into a controller, keep the gate as the only authority boundary.

Contents:
- `vendor/engram/` docs/artifacts (demo script removed)
- `vendor/conductor/` prompt/templates (execution commands removed; review minimized)
- `vendor/flashmla/` ML optimization library (optional; not in kernel path)
