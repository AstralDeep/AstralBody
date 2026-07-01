# Verification Results — 044 (per acceptance scenario, per client)

**Status**: SCAFFOLD — rows filled during T022/T033/T042/T048/T051 interim checkpoints and the
full T053 run. Result vocabulary: ✅ pass · ❌ fail (→ Defect Register id) · ➖ n/a (sanctioned
web-only / not applicable to client).

## US1 — Dependable chat loop

| Scenario | Web | Windows | Android | Evidence |
|---|---|---|---|---|
| 1.1 server error visible, not silent/thinking | | | | |
| 1.2 socket drop → visible state → auto-reconnect ≤30 s + resume | ➖ (browser) | | | |
| 1.3 expired token → silent refresh; no-credential → explicit sign-in | | | | |
| 1.4 sign-out revokes server session (SC-004: old refresh token rejected) | | | | |
| 1.5 progress signals reflected; turn always terminal | | | | |
| 1.6 unsupported push type → logged deliberate ignore, no crash | | | | |

## US2 — Rendering fidelity

| Scenario | Web | Windows | Android | Evidence |
|---|---|---|---|---|
| 2.1 gallery: every advertised type legible, zero placeholder leaks | | | | |
| 2.2 unadvertised type server-substituted before delivery | | | | |
| 2.3 interactive round-trips (button/input/form multi-action/upload/download) | | | | |
| 2.4 large table fully accessible (pagination) | | | | |
| 2.5 canvas convergence (keyed upserts + full renders + streams) | | | | |
| 2.6 markdown construct set equivalent | | | | |

## US3 — Settings surfaces

| Scenario | Web | Windows | Android | Evidence |
|---|---|---|---|---|
| 3.1 menu + topbar match server model (grouping/order/roles/signout) | | | | |
| 3.2 surface loads bounded; timeout → retry affordance | ➖ | | | |
| 3.3 Load/Test/Save round-trips: success AND forced failure visible | | | | |
| 3.4 web-only capabilities absent or signposted on native | ➖ | | | |

## US4 — Attachments (Windows parity)

| Scenario | Web | Windows | Android | Evidence |
|---|---|---|---|---|
| 4.1 chips + parser status + remove + sent payload | | | | |
| 4.2 no-parser escalation story visible | | | | |
| 4.3 reload shows turn attachments consistently | | | | |

## US5 — Theme

| Scenario | Web | Windows | Android | Evidence |
|---|---|---|---|---|
| 5.1 preset applies immediately + persists across restart | | | | |
| 5.2 non-restylable elements disclosed | ➖ | | ➖ | |

## US6 — Evidence & guards

| Scenario | Web | Windows | Android | Evidence |
|---|---|---|---|---|
| 6.1 parity matrix complete (zero unknown cells) | — | — | — | |
| 6.2 all captures legible (0 tofu) | | | | |
| 6.3 drift guards fail on unclassified additions (mutation check) | — | — | — | |
| 6.4 docs match shipped reality | — | — | — | |
