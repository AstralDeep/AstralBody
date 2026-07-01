# Verification Bundle — 044 Cross-Client Native Parity

Regeneration procedure: [../quickstart.md §6](../quickstart.md). Layout per
[../data-model.md §5](../data-model.md).

- `results.md` — per-acceptance-scenario outcomes (US1–US6), dated, per client.
- `web/`, `windows/`, `android/` — legible captures named `<scenario>-<client>.png`.
- Every capture must have readable text; the Windows harness **fails** (font sanity gate)
  rather than emit tofu. Android captures via `adb exec-out screencap -p`; web via browser.
- Matrix cells in [../parity-matrix.md](../parity-matrix.md) link here; the bundle is
  regenerable from a clean checkout (SC-007).
