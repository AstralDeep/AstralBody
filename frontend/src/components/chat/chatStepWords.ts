/**
 * Approved cosmic-themed words used by the in-chat progress indicator.
 *
 * Single source of truth for FR-002 of feature 014-progress-notifications.
 * The list is enumerated verbatim in the spec — every word added/removed here
 * MUST also be reflected in [specs/014-progress-notifications/spec.md].
 *
 * The backend never reads this file; the indicator is purely client-driven
 * (see specs/014-progress-notifications/contracts/chat_status_extension.md).
 */
export const COSMIC_WORDS: readonly string[] = [
    "Accelerating",
    "Aligning",
    "Ascending",
    "Astralizing",
    "Attuning",
    "Beamforming",
    "Bending",
    "Binary-pairing",
    "Cascading",
    "Coalescing",
    "Collapsing",
    "Colliding",
    "Condensing",
    "Conjoining",
    "Converging",
    "Crystallizing",
    "Decelerating",
    "Decoupling",
    "Detaching",
    "Dilating",
    "Discerning",
    "Displacing",
    "Drifting",
    "Emanating",
    "Entangling",
    "Expanding",
    "Fluctuating",
    "Fluxing",
    "Gravitating",
    "Illuminating",
    "Inflating",
    "Ionizing",
    "Iterating",
    "Launching",
    "Levitating",
    "Manifesting",
    "Materializing",
    "Merging",
    "Navigating",
    "Orbiting",
    "Oscillating",
    "Phasing",
    "Polarizing",
    "Projecting",
    "Pulsating",
    "Quantizing",
    "Radiating",
    "Refracting",
    "Resonating",
    "Rotating",
    "Shimmering",
    "Superposing",
    "Syncing",
    "Transmogrifying",
    "Transmuting",
    "Traversing",
] as const;

/**
 * Pick a cosmic word, optionally avoiding a previous word so consecutive
 * picks never repeat (R7 anti-stutter rule).
 *
 * @param previous The word currently displayed; the next pick will not equal it.
 * @returns A word from {@link COSMIC_WORDS} that is not equal to `previous`.
 */
export function pickCosmicWord(previous?: string): string {
    if (COSMIC_WORDS.length === 0) {
        // Defensive — the constant is non-empty by construction. Returning a
        // placeholder is preferable to throwing during a UI render.
        return "";
    }
    if (COSMIC_WORDS.length === 1) {
        return COSMIC_WORDS[0];
    }
    let next = COSMIC_WORDS[Math.floor(Math.random() * COSMIC_WORDS.length)];
    if (previous !== undefined && next === previous) {
        // Skip exactly one slot to break the stutter without reintroducing
        // strong correlation with `previous`.
        const idx = COSMIC_WORDS.indexOf(next);
        next = COSMIC_WORDS[(idx + 1) % COSMIC_WORDS.length];
    }
    return next;
}
