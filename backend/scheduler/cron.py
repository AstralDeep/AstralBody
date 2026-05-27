"""Pure-Python, timezone-aware next-run evaluator (feature 025, T043).

Supports the three schedule kinds from the spec (FR-020):
  * ``one_shot`` — ``schedule_expr`` is an ISO-8601 timestamp.
  * ``interval`` — ``schedule_expr`` is ``"<N><unit>"`` where unit ∈ {s,m,h,d}.
  * ``cron``     — a standard 5-field expression: ``min hour dom mon dow``.

No third-party dependency (Constitution V) — uses stdlib ``datetime`` +
``zoneinfo``. Cron evaluation steps minute-by-minute from the reference time
to the next matching minute (bounded), which is simple and correct for the
minute-resolution scheduler tick.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Set

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - py<3.9 only
    ZoneInfo = None  # type: ignore

_INTERVAL_RE = re.compile(r"^\s*(\d+)\s*([smhd])\s*$", re.IGNORECASE)
_UNIT_SECONDS = {"s": 1, "m": 60, "h": 3600, "d": 86400}

# Search bound for cron "next match" — covers any valid cron pattern.
_CRON_SEARCH_MINUTES = 366 * 24 * 60


class ScheduleError(ValueError):
    """Raised for an invalid schedule expression."""


def _tz(name: str):
    if not name or name.upper() == "UTC" or ZoneInfo is None:
        return timezone.utc
    try:
        return ZoneInfo(name)
    except Exception as exc:  # pragma: no cover - invalid tz name
        raise ScheduleError(f"invalid timezone: {name}") from exc


# ── Cron field parsing ────────────────────────────────────────────────────

def _parse_field(field: str, lo: int, hi: int) -> Set[int]:
    """Expand one cron field into the set of allowed integer values."""
    values: Set[int] = set()
    for part in field.split(","):
        part = part.strip()
        step = 1
        if "/" in part:
            base, step_s = part.split("/", 1)
            step = int(step_s)
            if step <= 0:
                raise ScheduleError(f"invalid step in '{field}'")
        else:
            base = part
        if base == "*":
            start, end = lo, hi
        elif "-" in base:
            a, b = base.split("-", 1)
            start, end = int(a), int(b)
        else:
            start = end = int(base)
        if start < lo or end > hi or start > end:
            raise ScheduleError(f"field value out of range in '{field}' ({lo}-{hi})")
        values.update(range(start, end + 1, step))
    return values


def parse_cron(expr: str):
    """Parse a 5-field cron expression into per-field allowed-value sets."""
    fields = expr.split()
    if len(fields) != 5:
        raise ScheduleError("cron expression must have exactly 5 fields: 'min hour dom mon dow'")
    minute = _parse_field(fields[0], 0, 59)
    hour = _parse_field(fields[1], 0, 23)
    dom = _parse_field(fields[2], 1, 31)
    month = _parse_field(fields[3], 1, 12)
    # Day-of-week: 0-6 (Sun-Sat); accept 7 as Sunday.
    dow_raw = _parse_field(fields[4], 0, 7)
    dow = {0 if d == 7 else d for d in dow_raw}
    dom_restricted = fields[2] != "*"
    dow_restricted = fields[4] != "*"
    return minute, hour, dom, month, dow, dom_restricted, dow_restricted


def _cron_matches(dt: datetime, parsed) -> bool:
    minute, hour, dom, month, dow, dom_restricted, dow_restricted = parsed
    if dt.minute not in minute or dt.hour not in hour or dt.month not in month:
        return False
    # cron weekday: Monday=0..Sunday=6 in Python; convert to 0=Sun..6=Sat.
    py_dow = dt.weekday()  # Mon=0
    cron_dow = (py_dow + 1) % 7  # Sun=0
    day_ok_dom = dt.day in dom
    day_ok_dow = cron_dow in dow
    # Standard cron semantics: if both DOM and DOW are restricted, match either.
    if dom_restricted and dow_restricted:
        return day_ok_dom or day_ok_dow
    if dom_restricted:
        return day_ok_dom
    if dow_restricted:
        return day_ok_dow
    return True


def _next_cron(expr: str, tzname: str, after: datetime) -> Optional[datetime]:
    parsed = parse_cron(expr)
    tz = _tz(tzname)
    local = after.astimezone(tz)
    # Start at the next whole minute.
    candidate = (local + timedelta(minutes=1)).replace(second=0, microsecond=0)
    for _ in range(_CRON_SEARCH_MINUTES):
        if _cron_matches(candidate, parsed):
            return candidate.astimezone(timezone.utc)
        candidate += timedelta(minutes=1)
    return None  # pragma: no cover - unreachable for valid crons


# ── Public API ──────────────────────────────────────────────────────────--

def compute_next_run_ms(
    schedule_kind: str,
    schedule_expr: str,
    timezone_name: str,
    after_ms: int,
) -> Optional[int]:
    """Return the next run time (epoch-ms, UTC) strictly after ``after_ms``.

    Returns ``None`` for a one-shot whose time has already passed (the job is
    then completed by the caller).
    """
    after = datetime.fromtimestamp(after_ms / 1000, tz=timezone.utc)

    if schedule_kind == "one_shot":
        raw = schedule_expr.strip().replace("Z", "+00:00")
        try:
            when = datetime.fromisoformat(raw)
        except ValueError as exc:
            raise ScheduleError(f"invalid one_shot timestamp: {schedule_expr}") from exc
        if when.tzinfo is None:
            when = when.replace(tzinfo=_tz(timezone_name))
        when = when.astimezone(timezone.utc)
        return int(when.timestamp() * 1000) if when > after else None

    if schedule_kind == "interval":
        m = _INTERVAL_RE.match(schedule_expr)
        if not m:
            raise ScheduleError(f"invalid interval: {schedule_expr} (use e.g. '15m', '2h', '1d')")
        n, unit = int(m.group(1)), m.group(2).lower()
        seconds = n * _UNIT_SECONDS[unit]
        if seconds <= 0:
            raise ScheduleError("interval must be positive")
        return after_ms + seconds * 1000

    if schedule_kind == "cron":
        nxt = _next_cron(schedule_expr, timezone_name, after)
        return int(nxt.timestamp() * 1000) if nxt else None

    raise ScheduleError(f"unknown schedule_kind: {schedule_kind}")


def interval_seconds(schedule_kind: str, schedule_expr: str) -> Optional[int]:
    """Return the interval length in seconds for an ``interval`` schedule.

    Used by governance to enforce the minimum-interval floor (FR-038).
    Returns ``None`` for non-interval kinds.
    """
    if schedule_kind != "interval":
        return None
    m = _INTERVAL_RE.match(schedule_expr)
    if not m:
        raise ScheduleError(f"invalid interval: {schedule_expr}")
    return int(m.group(1)) * _UNIT_SECONDS[m.group(2).lower()]
