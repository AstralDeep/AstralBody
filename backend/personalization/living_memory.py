"""Living memory & personalization — 033 Wave-2′ (C-M6 / C-M7 / C-M8 / C-M9).

Four deterministic, dependency-free cores extending the existing memory
subsystem (C-M1 reconcile, C-M2 links, C-M3 PageRank, C-S9 signing):

* **C-M6 temporal validity + abstention** — memories carry ``valid_from`` /
  ``valid_to`` / ``ingested_at``; :func:`as_of` answers point-in-time queries,
  :func:`detect_contradiction` finds conflicting live facts in a category, and
  :func:`should_abstain` says "clarify, don't guess" when the live set conflicts
  or is low-confidence.
* **C-M7 principled forgetting** — an Ebbinghaus retention curve
  (:func:`retention_strength`) whose stability grows each time a memory is
  recalled (:func:`reinforce`); :func:`should_forget` is the decay floor, and
  :func:`safety_forget` is the immediate PHI/safety-triggered drop (doubles as
  data-minimization).
* **C-M8 evolving persona** — :func:`evolve_persona` proposes a refined persona
  from recent turns + feedback and keeps it only if it scores better
  (:func:`persona_score` — a textual "keep-best", no LLM required); a thumbs
  signal folds in via :func:`apply_feedback`.
* **C-M9 provenance / unlearning** — :func:`provenance_of` summarizes where a
  memory came from; :func:`unlearn_kind` classifies a "forget this" request as a
  genuine hard delete vs an auditable supersede.

All pure (stdlib ``math`` only). **No new dependency.** Each surface that wires
these into the live recall/write path is flag-gated and additive; with the flags
off, recall behaves exactly as today.
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

# ───────────────────────── flags ─────────────────────────────────────────────

def temporal_enabled() -> bool:
    """FF_MEMORY_TEMPORAL (default OFF; C-M6) — as-of filtering + abstention."""
    return os.getenv("FF_MEMORY_TEMPORAL", "false").strip().lower() in ("1", "true", "yes", "on")


def forgetting_enabled() -> bool:
    """FF_MEMORY_FORGETTING (default OFF; C-M7) — decay-based forgetting."""
    return os.getenv("FF_MEMORY_FORGETTING", "false").strip().lower() in ("1", "true", "yes", "on")


def persona_enabled() -> bool:
    """FF_MEMORY_PERSONA (default OFF; C-M8) — evolving persona steering."""
    return os.getenv("FF_MEMORY_PERSONA", "false").strip().lower() in ("1", "true", "yes", "on")


# ───────────────────────── C-M6 temporal validity ────────────────────────────

_FAR_FUTURE = 1 << 62  # a valid_to of None means "still valid" → treat as +inf


def is_valid_at(memory: Dict[str, Any], ts: int) -> bool:
    """Whether a memory is in force at epoch-ms ``ts``: ``valid_from <= ts <
    valid_to`` (an absent bound is open). A row with no temporal columns is
    always valid (today's behavior)."""
    vf = memory.get("valid_from")
    vt = memory.get("valid_to")
    lo = int(vf) if vf is not None else 0
    hi = int(vt) if vt is not None else _FAR_FUTURE
    return lo <= int(ts) < hi


def as_of(memories: List[Dict[str, Any]], ts: int) -> List[Dict[str, Any]]:
    """The memories in force at ``ts`` (point-in-time / as-of query)."""
    return [m for m in (memories or []) if is_valid_at(m, ts)]


def detect_contradiction(memories: List[Dict[str, Any]],
                         ts: Optional[int] = None) -> List[Tuple[str, List[Dict[str, Any]]]]:
    """Categories with >1 distinct live value at ``ts`` (now if None) — a
    contradiction the system should resolve or abstain on. Returns
    ``[(category, [conflicting memories]), …]``."""
    live = as_of(memories, ts) if ts is not None else list(memories or [])
    by_cat: Dict[str, List[Dict[str, Any]]] = {}
    for m in live:
        by_cat.setdefault(str(m.get("category", "")), []).append(m)
    out: List[Tuple[str, List[Dict[str, Any]]]] = []
    for cat, items in by_cat.items():
        values = {str(i.get("value", "")).strip().lower() for i in items}
        if len(values) > 1:
            out.append((cat, items))
    return out


def should_abstain(candidates: List[Dict[str, Any]], *,
                   min_salience: float = 0.0) -> bool:
    """True when the system should CLARIFY instead of answering from memory: the
    live candidates contradict each other, or none clears ``min_salience``."""
    if not candidates:
        return False
    if detect_contradiction(candidates):
        return True
    return max((float(c.get("salience", 0.0) or 0.0) for c in candidates),
               default=0.0) < min_salience


# ───────────────────────── C-M7 principled forgetting ────────────────────────

#: Default Ebbinghaus stability (ms) for a brand-new, never-recalled memory.
_BASE_STABILITY_MS = 7 * 24 * 3600 * 1000  # ~1 week e-folding time


def retention_strength(memory: Dict[str, Any], now: int) -> float:
    """Ebbinghaus retention R = exp(-Δt / S) in [0, 1], where Δt is the age since
    last recall (or creation) and stability S grows with recall count. A salient
    memory decays slower. Missing fields fall back to creation/age-0."""
    last = memory.get("last_recalled_at")
    if last is None:
        last = memory.get("created_at")
    if last is None:
        last = now
    dt = max(0, int(now) - int(last))
    recalls = int(memory.get("recall_count", 0) or 0)
    salience = float(memory.get("salience", 0.0) or 0.0)
    # each recall multiplies stability; salience adds a floor multiplier
    stability = _BASE_STABILITY_MS * (1 + recalls) * (1.0 + max(0.0, salience))
    return math.exp(-dt / stability) if stability > 0 else 0.0


def reinforce(memory: Dict[str, Any], now: int) -> Dict[str, Any]:
    """Return the recall-time deltas (recall_count+1, last_recalled_at=now) —
    the spaced-repetition reinforcement that resets the decay clock."""
    return {"recall_count": int(memory.get("recall_count", 0) or 0) + 1,
            "last_recalled_at": int(now)}


def should_forget(memory: Dict[str, Any], now: int, *, floor: float = 0.05) -> bool:
    """A decayed memory drops below the retention ``floor`` — a forgetting
    candidate (pinned/explicit memories are exempt)."""
    if memory.get("source") == "explicit" or memory.get("pinned"):
        return False
    return retention_strength(memory, now) < floor


def safety_forget(memory: Dict[str, Any], *, phi_check=None) -> bool:
    """Immediate, non-decay forget: a memory whose value trips the PHI/safety
    check must be dropped regardless of strength (data-minimization). Fails
    CLOSED — an erroring check forgets."""
    if phi_check is None:
        return False
    try:
        return bool(phi_check(str(memory.get("value", ""))))
    except Exception:
        return True


# ───────────────────────── C-M8 evolving persona ─────────────────────────────

@dataclass(frozen=True)
class PersonaCandidate:
    text: str
    score: float


def persona_score(persona: str, signals: List[str]) -> float:
    """A deterministic textual fit: fraction of preference signals reflected in
    the persona, minus a length penalty (keep it concise). Higher is better."""
    text = (persona or "").strip().lower()
    if not text:
        return 0.0
    sig = [s.strip().lower() for s in (signals or []) if s and s.strip()]
    if not sig:
        covered = 1.0
    else:
        covered = sum(1 for s in sig if s in text) / len(sig)
    length_penalty = min(0.3, len(text) / 4000.0)  # discourage runaway growth
    return round(covered - length_penalty, 6)


def evolve_persona(current: str, signals: List[str], *,
                   proposal: Optional[str] = None) -> PersonaCandidate:
    """Keep-best persona update: score the current persona and an optional
    proposal (e.g. an LLM-refined draft, or a deterministic append of uncovered
    signals) and return whichever scores higher. Never regresses."""
    cur = PersonaCandidate(current or "", persona_score(current or "", signals))
    cand_text = proposal if proposal is not None else _append_uncovered(current or "", signals)
    cand = PersonaCandidate(cand_text, persona_score(cand_text, signals))
    return cand if cand.score > cur.score else cur


def _append_uncovered(persona: str, signals: List[str]) -> str:
    text = persona or ""
    low = text.lower()
    add = [s.strip() for s in (signals or []) if s and s.strip() and s.strip().lower() not in low]
    if not add:
        return text
    prefix = (text + " ") if text and not text.endswith((" ", "\n")) else text
    return (prefix + "Prefers: " + "; ".join(add) + ".").strip()


def apply_feedback(persona: str, signal: str, sentiment: str) -> str:
    """Fold a feature-004 component-feedback signal into the persona steering:
    a thumbs-up reinforces the signal, a thumbs-down records an avoid. Pure."""
    s = (signal or "").strip()
    if not s:
        return persona or ""
    note = f"Likes: {s}." if str(sentiment).lower() in ("up", "positive", "1") else f"Avoid: {s}."
    base = (persona or "").strip()
    return (base + (" " if base else "") + note).strip()


# ───────────────────────── C-M9 provenance / unlearning ──────────────────────

def provenance_of(memory: Dict[str, Any]) -> Dict[str, Any]:
    """A user-facing provenance summary for a memory: where it came from, when it
    was learned/ingested, and whether it is integrity-signed (C-S9)."""
    return {
        "source": memory.get("source", "explicit"),
        "category": memory.get("category"),
        "learned_at": memory.get("created_at"),
        "ingested_at": memory.get("ingested_at") or memory.get("created_at"),
        "last_recalled_at": memory.get("last_recalled_at"),
        "signed": bool(memory.get("signature")),
    }


def unlearn_kind(request: str) -> str:
    """Classify a user "forget this" request: a privacy/erasure ask → ``hard``
    (genuine deletion, the external store makes this real); a correction ("that's
    wrong, it's X") → ``supersede`` (auditable replacement). Default ``supersede``
    so history stays auditable unless erasure is explicitly requested."""
    r = (request or "").strip().lower()
    erase_markers = ("forget", "delete", "erase", "remove", "wipe", "scrub",
                     "right to be forgotten", "gdpr")
    correct_markers = ("actually", "correction", "instead", "should be", "it's",
                       "no longer", "change it to", "update")
    if any(m in r for m in erase_markers) and not any(m in r for m in correct_markers):
        return "hard"
    return "supersede"
