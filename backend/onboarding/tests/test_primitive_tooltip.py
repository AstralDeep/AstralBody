"""Verify the additive `tooltip` field on the base Component primitive."""
from __future__ import annotations

import pytest

from shared.primitives import (
    Alert,
    Button,
    Card,
    Component,
    Container,
    Image,
    Input,
    MetricCard,
    ProgressBar,
    Table,
    Text,
)


def test_base_component_defaults_tooltip_to_none():
    c = Component(type="text")
    assert c.tooltip is None


@pytest.mark.parametrize(
    "ctor,extras",
    [
        (Container, {}),
        (Text, {}),
        (Button, {"label": "x"}),
        (Card, {}),
        (Table, {"headers": [], "rows": []}),
        (Alert, {"message": "x"}),
        (ProgressBar, {"value": 1.0}),
        (MetricCard, {"title": "x", "value": "1"}),
        (Image, {"url": "data:"}),
        (Input, {}),
    ],
)
def test_subclasses_serialize_with_tooltip(ctor, extras):
    """Each subclass round-trips through to_json/from_json with the new field."""
    inst = ctor(tooltip="hello", **extras)
    payload = inst.to_json()
    assert payload.get("tooltip") == "hello"
    rebuilt = Component.from_json(payload)
    assert rebuilt.tooltip == "hello"


def test_tooltip_absent_when_unset():
    """Existing payloads without `tooltip` deserialize cleanly."""
    rebuilt = Component.from_json({"type": "text", "value": "hi"})
    assert rebuilt.tooltip is None


def test_tooltip_persists_through_roundtrip():
    btn = Button(label="hi", tooltip="click me")
    payload = btn.to_json()
    assert payload["tooltip"] == "click me"
    again = Button(**{k: v for k, v in payload.items() if k in Button.__dataclass_fields__})
    assert again.tooltip == "click me"
