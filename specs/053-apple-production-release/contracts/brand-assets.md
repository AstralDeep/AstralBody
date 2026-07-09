# Contract: Brand Assets & Store Listing (feature 053)

**Feature**: 053-apple-production-release · **Phase**: 1 (Design & Contracts)
**Decisions**: D15 (app icons — REVISED), D16 (screenshots), D17 (brand-asset reuse mapping)
**Requirements**: FR-004, FR-004a, FR-030, FR-031, FR-032
**Bar**: **SC-005a** (every App Store icon slot present at its exact required size; iOS/watch 1024² opaque; macOS slots keep their gutter — verified mechanically) and **SC-005b** (every required screenshot class present at an exactly-accepted pixel size, from the real Apple app). Both feed **SC-001a** (submission with a complete listing) under **US8**.

This contract fixes the brand-asset surface of the App Store record: which supplied
asset legitimately transfers, exactly which icon files ship on each platform and why
the opacity rule inverts between iOS/watch and macOS, and how screenshots are produced
for each required device class. The icon work is **DONE and build-verified** (see §2);
the screenshot work is operator-assisted and **pending** (see §3). Every item is a
**MUST** and maps to a functional requirement; the acceptance bar is SC-005a + SC-005b.

Two facts, established by inspecting the working tree, drive everything below:

1. **Store topology is one record.** iOS and macOS share the bundle id
   `com.personalailabs.astraldeep`, so they form a **single Universal Purchase**
   App Store Connect record with two platform versions; the watch app ships **embedded**
   inside the iOS build (D19). Net: **one listing** — one icon per platform idiom and one
   screenshot set covering four device classes, not three separate listings.
2. **Only one supplied asset yields shippable Apple pixels.** The operator supplied
   `android-client/Android Raw Assets/` (10 PNGs). Exactly one — the 3000×3000
   `AppIcon.png` master — produces Apple pixels. No screenshot transfers (§3).

---

## 1. Source of truth — supplied brand assets (FR-032 · D17)

The transfer status of **every** supplied asset MUST be recorded explicitly — *usable*,
*reference-only*, or *not transferable* — so no asset is silently ignored and none is
wrongly shipped (Constitution XIII, honest accounting). Ground truth: the pixel
dimensions below were read from the files with `sips` on branch
`053-apple-production-release`; several filenames **misdescribe their pixels** (the two
`*x*.png` files are 3× supersampled).

### Operator master

`android-client/Android Raw Assets/AppIcon.png` — **3000×3000**, RGBA whose alpha channel
is **100% opaque** (min == max == 255). Full-bleed square art on navy `#171940`. This is
the single source for **every** Apple icon; alpha-stripping it is *lossless* because it is
already fully opaque (see §2). This closes the former "operator must supply a master icon"
prerequisite (spec Assumptions — SATISFIED).

### Full 10-asset inventory

| Supplied asset | Filename claims | **Actual pixels** | Alpha | Aspect | Status | Apple use |
|---|---|---|---|---|---|---|
| `AppIcon.png` | — | **3000×3000** | opaque | 1:1 | **Usable** | Master for **all** Apple icons (§2 / D15) |
| `feature-graphic.png` | — | **1024×500** | no | ~2.05:1 | **Not transferable** | Google-Play-only slot; the App Store has **no** feature-graphic slot |
| `1920X1080.png` | 1920×1080 | **5760×3240** | yes | 16:9 | Reference-only | Desktop/web dashboard render; Mac needs a **16:10** native capture |
| `2560x1440.png` | 2560×1440 | **7680×4320** | yes | 16:9 | Reference-only | As above (also 3× supersampled) |
| `phone-1-welcome.png` | — | **1080×1920** | no | 9:16 | Reference-only | Composition/shot-list for iPhone captures; wrong aspect for iPhone 6.9" |
| `phone-2-dashboard.png` | — | **1080×1920** | no | 9:16 | Reference-only | As above |
| `tablet7-1-welcome.png` | — | **1920×1080** | no | 16:9 | Reference-only | Shot-list for iPad captures; wrong aspect for iPad 13" (4:3) |
| `tablet7-2-dashboard.png` | — | **1920×1080** | no | 16:9 | Reference-only | As above |
| `tablet10-1-welcome.png` | — | **2560×1440** | no | 16:9 | Reference-only | As above |
| `tablet10-2-dashboard.png` | — | **2560×1440** | no | 16:9 | Reference-only | As above |

**Why nothing but the icon ships**: the App Store has no feature-graphic slot (Google Play
only), and every screenshot render mismatches Apple's required aspect ratios on every class
(phone 9:16 vs iPhone 6.9" ~0.46; tablet 16:9 vs iPad 13" 4:3; desktop 16:9 vs Mac 16:10),
*and* App Review Guideline 2.3.3 requires screenshots of the **real Apple app in use** — a
render of the Android/web UI is a 2.3.3 rejection risk. Screenshots are therefore captured
natively (§3), and the reference-only renders are kept only as a composition/shot-list guide.

---

## 2. Icon contract (FR-004, FR-004a, FR-030 · D15) — **DONE, build-verified**

Every Apple icon is derived from the master by the committed, dependency-free generator
`apple-clients/Scripts/generate_app_icons.py` (stdlib Python + the Apple `sips` tool —
**zero new dependencies**, Constitution V). The platforms genuinely differ, and the
**opacity rule inverts** between them; a blanket "strip all alpha" step would break macOS.

### 2.1 iOS + watchOS — one opaque, full-bleed 1024² square

Each of iOS and watchOS ships a **single 1024×1024, square, full-bleed, fully opaque** PNG.
The system masks the corners at render time (rounded-rect on iOS, circle on watchOS), so
rounding MUST NOT be baked into the artwork
([HIG — App icons](https://developer.apple.com/design/human-interface-guidelines/app-icons);
[Configuring your app icon](https://developer.apple.com/documentation/xcode/configuring-your-app-icon)).
An alpha channel here **fails upload validation as ITMS-90717** — "The App Store Icon …
can't be transparent nor contain an alpha channel"
([ITMS-90717 thread](https://developer.apple.com/forums/thread/96003)). Stripping the
master's alpha is lossless because the master is already fully opaque; the generator
**refuses to proceed** if it ever encounters real transparency (`strip_alpha` raises when
`min(alpha) != 255`).

Emitted files (all 1024×1024, **no alpha**):

| File (repo-relative) | Idiom | Notes |
|---|---|---|
| `apple-clients/AstralApp/AstralApp/Assets.xcassets/AppIcon.appiconset/AppIcon-1024.png` | iOS `universal` | default appearance |
| `…/AppIcon.appiconset/AppIcon-1024-dark.png` | iOS `universal` (dark) | `appearances: [{luminosity: dark}]` |
| `apple-clients/AstralWatch/Assets.xcassets/AppIcon.appiconset/AppIcon-1024.png` | watchOS `universal` | the watch target previously had **no asset catalog at all** — this catalog + its `Contents.json` are new |

### 2.2 macOS — rounded-rect body in a transparent gutter, ten slots

The classic `AppIcon.appiconset` workflow does **not** auto-mask, so each macOS slot must
itself supply the rounded-rect ("squircle") shape inside a **transparent gutter** — the
artwork carries the shape. Apple's macOS icon grid places an **824×824 body** on the
**1024** canvas (a **~100 px** gutter on each side) with a **~185.4 px** continuous-corner
radius. RGBA is **correct and required** here — transparency in the gutter is expected and
is **not** an ITMS-90717 violation (that rule governs only the iOS/watchOS App Store icon
slot). SC-005a requires the gutter be **retained**; a "strip all alpha" step would flatten
the macOS shape and break it.

Emitted files (all **RGBA**, gutter retained), the ten classic slots @1x/@2x:

`mac-16x16@1x.png` (16²) · `mac-16x16@2x.png` (32²) · `mac-32x32@1x.png` (32²) ·
`mac-32x32@2x.png` (64²) · `mac-128x128@1x.png` (128²) · `mac-128x128@2x.png` (256²) ·
`mac-256x256@1x.png` (256²) · `mac-256x256@2x.png` (512²) · `mac-512x512@1x.png` (512²) ·
`mac-512x512@2x.png` (1024²) — all under the iOS target's `AppIcon.appiconset`.

The generator also rewrites `AppIcon.appiconset/Contents.json` (2 iOS + 10 mac images) and
writes the new watch `Contents.json` (1 watchOS image).

### 2.3 The generator and its `--check` self-check (FR-030)

`generate_app_icons.py` re-encodes PNGs in pure stdlib (`zlib`/`struct`) and resamples via
`sips`; the macOS squircle mask is an antialiased superellipse (exponent `n=4.0`) computed
in-process. Its **`--check`** mode (run in CI / before archive) asserts the invariants and
exits non-zero on any violation, so an icon regression fails **loudly** rather than at
upload:

- **Sizes** — the three 1024² icons are exactly 1024×1024; each macOS slot is exactly its
  declared pixel size (16→1024).
- **iOS/watch opacity** — the three 1024² icons have **3 channels (no alpha)**; an alpha
  channel is reported as `ITMS-90717; must be opaque RGB`.
- **macOS gutter retention** — each macOS slot has **4 channels (RGBA)**; a 3-channel slot
  is reported as `must keep its transparent gutter`.

### 2.4 Status: DONE — build-verified evidence

- `sips` independently confirms **`hasAlpha: no`** on the three 1024² icons and
  **`hasAlpha: yes`** on all ten macOS slots (matches the `--check` contract).
- `xcodebuild -scheme AstralApp -destination 'generic/platform=iOS Simulator' -configuration Debug`
  → **BUILD SUCCEEDED**; `actool` emitted `AppIcon60x60@2x.png` and
  `AppIcon76x76@2x~ipad.png`; `Assets.car` carries phone **and** iPad renditions in both the
  default and dark appearances (so iPad — TARGETED_DEVICE_FAMILY `1,2` — is covered).

### 2.5 Remaining icon task (FR-004a) — **TODO**

The watch catalog exists and is wired in `Contents.json`, but the **AstralWatch target** does
not yet name it: `ASSETCATALOG_COMPILER_APPICON_NAME = AppIcon` is currently set **only on
the AstralApp (iOS/macOS) build configs** in
`apple-clients/AstralApp/AstralApp.xcodeproj/project.pbxproj` (its two Debug/Release configs),
and is absent from the AstralWatch configs. It MUST be added to the **AstralWatch** target's
build configs so the embedded watch app's archive carries its own app icon (US1 acceptance
scenario 3). This is the only open item in the icon contract.

---

## 3. Screenshot contract (FR-031 · D16) — operator-assisted, **pending**

Screenshots MUST be captured from the **real Apple apps** at **exactly one accepted pixel
size per required device class**, and MAY then carry AstralDeep brand/caption overlays.
Because this record covers iPhone, iPad (TARGETED_DEVICE_FAMILY `1,2`, and the build emits
`AppIcon76x76@2x~ipad.png`), Mac, and the embedded watch, **four** classes are required.

### 3.1 Required classes and accepted pixel sizes

Pick **one** accepted size per class; portrait shown, landscape swaps W/H. Use the **same
Apple Watch size across all localizations** (App Store Connect requires a single watch size
per record).

| Class | Accepted pixel sizes |
|---|---|
| **iPhone 6.9"** | 1260×2736 · 1290×2796 · 1320×2868 |
| **iPad 13"** | 2048×2732 · 2064×2752 |
| **Mac** (16:10) | 1280×800 · 1440×900 · 2560×1600 · 2880×1800 |
| **Apple Watch** | 422×514 · 416×496 · 410×502 · 396×484 · 368×448 · 312×390 |

**1–10 screenshots per class.** App Store Connect accepts **only** exact pixel dimensions —
an off-by-one or a wrong aspect ratio is rejected at upload
([Screenshot specifications](https://developer.apple.com/help/app-store-connect/reference/app-information/screenshot-specifications/)).

### 3.2 Guideline 2.3.3 — the app in use

Every screenshot's underlying pixels MUST depict the **real Apple app in use** — a live
chat/dashboard/SDUI screen — **not** a splash, welcome, login, or title card alone. Text
and image overlays are **explicitly permitted**
([App Review Guidelines §2.3.3](https://developer.apple.com/app-store/review/guidelines/)),
so an AstralDeep caption/brand frame may be composited **over** the native capture; the
capture beneath must still be the working app.

### 3.3 Native capture procedure (operator-assisted)

- **iPhone / iPad / Apple Watch** — capture at native resolution with
  `xcrun simctl io <device-udid> screenshot <out.png>` on the matching simulator device
  (choose the simulator whose native size equals an accepted size for the class).
- **macOS** — capture the running app **window** (window capture), not the full desktop, at
  one accepted 16:10 size.
- **Overlays** — composite the brand/caption frame after capture.

**Operator-assisted caveat**: the automation environment **cannot tap or type in a
simulator**, so the operator drives each app to the target screen (sign in, open a chat,
render a component) before capture — or the capture is scripted via deep links. This is why
US8 lists screenshots + listing copy as an **operator-provided, blocking prerequisite** to
submission (spec Assumptions).

### 3.4 Listing metadata (FR-015a, sourced from the operator)

The record's single listing also requires — from operator-provided copy — app name,
description, keywords, support + marketing + privacy-policy URLs, age rating, and the
export-compliance answer. Screenshots are one field of that listing; this contract owns the
screenshot field, `release-pipeline.md` owns the submission that consumes the completed
listing.

---

## 4. Invariants + FR mapping

- **I-1 (FR-004 / FR-030 / SC-005a)** — Every required icon slot is present at its exact
  size, derived from the operator master by the committed dependency-free generator; the
  generator's `--check` passes. *DONE, build-verified (§2.4).*
- **I-2 (FR-004 / SC-005a)** — The iOS and watchOS 1024² App Store icons carry **no alpha
  channel** (ITMS-90717), while the ten macOS slots **retain** their transparent gutter. The
  opacity rule inverts between the two idioms; `--check` enforces both directions. *DONE.*
- **I-3 (FR-004a)** — The watch target has its **own** asset catalog with its app icon wired
  via `ASSETCATALOG_COMPILER_APPICON_NAME = AppIcon`. Catalog + `Contents.json` exist; the
  build-setting on the **AstralWatch** target is the one open item (§2.5). *Catalog DONE;
  build-setting TODO.*
- **I-4 (FR-031 / SC-005b)** — Every required class (iPhone 6.9", iPad 13", Mac, Apple Watch)
  has ≥1 screenshot at an **exactly-accepted** pixel size, captured from the **real Apple
  app in use** (2.3.3), one watch size across all localizations, overlays permitted.
  *Pending, operator-assisted (§3).*
- **I-5 (FR-032)** — Every supplied asset has a recorded transfer status (§1); the Google
  Play feature graphic is **not transferable**, the desktop/phone/tablet renders are
  **reference-only**, only `AppIcon.png` is **usable** — none is silently dropped and none is
  wrongly shipped.
- **I-6 (FR-026 / SC-011)** — Zero new third-party dependencies: icon derivation is stdlib +
  `sips`; capture is `simctl`/`xcodebuild`. No package is added.

## Reviewer / implementer checklist

Run the icon items before every archive; the screenshot items before submission.

- [ ] `python3 apple-clients/Scripts/generate_app_icons.py --check` exits **0** (sizes;
      iOS/watch opaque; macOS gutter retained).
- [ ] `sips -g hasAlpha` reports **no** on the three 1024² icons and **yes** on all ten
      macOS slots.
- [ ] iOS `AppIcon.appiconset/Contents.json` lists the 2 iOS (default + dark) + 10 mac
      images; the watch `AppIcon.appiconset/Contents.json` lists the 1 watchOS image.
- [ ] `ASSETCATALOG_COMPILER_APPICON_NAME = AppIcon` is set on the **AstralWatch** target's
      build configs (FR-004a) — currently only on AstralApp.
- [ ] A Debug iOS-Simulator build succeeds and `actool` emits phone **and** `~ipad`
      renditions into `Assets.car` (default + dark).
- [ ] Screenshots exist for **all four** classes, each at an exactly-accepted pixel size,
      one Apple Watch size across all localizations, 1–10 per class.
- [ ] Every screenshot's underlying capture shows the **real Apple app in use** (not a
      splash/login/title card); any overlay sits over a compliant capture (2.3.3).
- [ ] The brand-asset inventory (§1) records a status for **all 10** supplied files; the
      feature graphic is marked **not transferable**, the renders **reference-only**.
- [ ] No new third-party dependency was introduced by icon or screenshot production
      (SC-011).

**Sources** (retrieved 2026-07-08):
[Screenshot specifications](https://developer.apple.com/help/app-store-connect/reference/app-information/screenshot-specifications/) ·
[App Review Guidelines §2.3.3](https://developer.apple.com/app-store/review/guidelines/) ·
[HIG — App icons](https://developer.apple.com/design/human-interface-guidelines/app-icons) ·
[Configuring your app icon](https://developer.apple.com/documentation/xcode/configuring-your-app-icon) ·
[ITMS-90717 thread](https://developer.apple.com/forums/thread/96003).
