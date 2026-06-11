import os
import sys
from typing import Dict, Any

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from astralprims import (
    Text, Card, MetricCard, Alert, Grid, List_,
    Divider, create_ui_response
)

REQUIRED_CREDENTIALS = []


def roll_dice(n: int = 1, **kwargs) -> Dict[str, Any]:
    """Rolls N dice and totals them."""
    try:
        import random

        if n < 1:
            n = 1
        if n > 100:
            n = 100

        rolls = [random.randint(1, 6) for _ in range(n)]
        total = sum(rolls)

        components = [
            Card(
                title=f"Dice Roll Results ({n} dice)",
                content=[
                    Grid(
                        columns=2,
                        children=[
                            MetricCard(
                                title="Total",
                                value=str(total),
                                variant="default"
                            ),
                            MetricCard(
                                title="Number of Dice",
                                value=str(n),
                                variant="default"
                            ),
                        ]
                    ),
                    Divider(variant="solid"),
                    Text(content="Individual Rolls:", variant="subheading"),
                    List_(
                        items=[f"Die {i+1}: {roll}" for i, roll in enumerate(rolls)],
                        ordered=False,
                        variant="default"
                    ),
                ]
            ),
        ]

        return {
            "_ui_components": [c.to_dict() for c in components],
            "_data": {
                "n": n,
                "rolls": rolls,
                "total": total,
            }
        }
    except Exception as e:
        return create_ui_response([
            Alert(message=f"Failed to roll dice: {str(e)}", variant="error")
        ])


TOOL_REGISTRY = {
    "roll_dice": {
        "function": roll_dice,
        "description": "Rolls N dice and totals them",
        "input_schema": {
            "type": "object",
            "properties": {
                "n": {
                    "type": "integer",
                    "description": "Number of six-sided dice to roll (1-100)",
                    "default": 1
                }
            },
            "required": []
        },
        "scope": "tools:read"
    }
}