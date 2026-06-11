import os
import sys
import random
from typing import Dict, Any, List, Optional

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from astralprims import (
    Text, Card, Table, Container, MetricCard, ProgressBar,
    Alert, Grid, BarChart, LineChart, PieChart, PlotlyChart, List_,
    Collapsible, Divider, CodeBlock, Image, Tabs,
    FileDownload, FileUpload, Button, Input, ColorPicker,
    create_ui_response
)

REQUIRED_CREDENTIALS = []

def roll_dice(num_dice: int, sides: int, **kwargs) -> Dict[str, Any]:
    """
    Rolls a specified number of dice with a specified number of sides and returns the results.
    """
    try:
        if num_dice < 1 or sides < 2:
            return create_ui_response([
                Alert(message="Invalid input: Please provide at least 1 die and at least 2 sides.", variant="error")
            ])
        
        # Limit inputs to prevent resource exhaustion
        num_dice = min(num_dice, 100)
        sides = min(sides, 10000)

        rolls = [random.randint(1, sides) for _ in range(num_dice)]
        total = sum(rolls)
        average = total / num_dice

        # Create UI components
        components = [
            Card(
                title=f"Dice Roll Results ({num_dice}d{sides})",
                content=[
                    Grid(
                        columns=3,
                        children=[
                            MetricCard(title="Total Sum", value=str(total)),
                            MetricCard(title="Average", value=f"{average:.2f}"),
                            MetricCard(title="Dice Count", value=str(num_dice)),
                        ]
                    ),
                    Divider(variant="solid"),
                    Text(content="Individual Roll Results:", variant="body"),
                    List_(
                        items=[f"Die {i+1}: {val}" for i, val in enumerate(rolls)],
                        ordered=True
                    ) if num_dice <= 20 else 
                    CodeBlock(
                        code=f"Rolls: {rolls}", 
                        language="text"
                    ),
                    Divider(variant="solid"),
                    Text(content=f"Simulated {num_dice} rolls of a {sides}-sided die.", variant="caption")
                ]
            )
        ]

        return {
            "_ui_components": [c.to_dict() for c in components],
            "_data": {
                "num_dice": num_dice,
                "sides": sides,
                "rolls": rolls,
                "total": total,
                "average": average
            }
        }
    except Exception as e:
        return create_ui_response([
            Alert(message=f"An error occurred while rolling dice: {str(e)}", variant="error")
        ])

TOOL_REGISTRY = {
    "roll_dice": {
        "function": roll_dice,
        "description": "Rolls a specified number of dice with a specified number of sides and returns the results.",
        "input_schema": {
            "type": "object",
            "properties": {
                "num_dice": {
                    "type": "integer", 
                    "description": "The number of dice to roll (e.g., 3 for 3d6)."
                },
                "sides": {
                    "type": "integer", 
                    "description": "The number of sides on each die (e.g., 6 for a standard cube)."
                }
            },
            "required": ["num_dice", "sides"]
        },
        "scope": "tools:read"
    }
}