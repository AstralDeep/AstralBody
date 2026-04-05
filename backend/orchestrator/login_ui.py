"""
SDUI Login Page Builder.

Generates the login page as SDUI components that the backend sends
to unauthenticated clients over WebSocket.

Design matches the React LoginScreen.tsx:
  - Colors: bg #0F1221, surface #1A1E2E, primary #6366F1, secondary #8B5CF6
  - Glass card, gradient button, centered layout
"""
from typing import List, Dict, Any, Optional
from shared.primitives import (
    Container, Text, Button, Card, Alert, Input,
)


def build_login_page(error: Optional[str] = None) -> List[Dict[str, Any]]:
    """Generate SDUI login page components matching the React design."""
    card_content: List[Any] = [
        Text(
            content="Sign in to access the dashboard",
            variant="h3",
            id="login-heading",
            style={
                "textAlign": "center",
                "color": "#FFFFFF",
                "fontWeight": "600",
                "fontSize": "16px",
            },
        ),
    ]

    if error:
        card_content.append(
            Alert(
                message=error,
                variant="error",
                id="login-error",
            )
        )

    card_content.append(
        Button(
            label="Sign In with SSO  \u2192",
            action="sso_login",
            variant="primary",
            id="sso-button",
            style={
                "width": "100%",
                "padding": "10px 0",
                "background": "linear-gradient(to right, #6366F1, #8B5CF6)",
                "borderRadius": "8px",
                "fontSize": "14px",
                "fontWeight": "500",
                "color": "#FFFFFF",
            },
        )
    )

    children: List[Any] = [
        # Logo icon
        Container(
            children=[
                Text(
                    content="\u26A1",
                    variant="h1",
                    id="login-icon",
                    style={
                        "fontSize": "28px",
                        "textAlign": "center",
                        "color": "#FFFFFF",
                    },
                ),
            ],
            id="login-logo",
            style={
                "width": "64px",
                "height": "64px",
                "borderRadius": "16px",
                "background": "linear-gradient(135deg, #6366F1, #06B6D4)",
                "display": "flex",
                "alignItems": "center",
                "justifyContent": "center",
                "alignSelf": "center",
                "boxShadow": "0 10px 15px rgba(99, 102, 241, 0.2)",
            },
        ),
        # Title
        Text(
            content="AstralDeep",
            variant="h1",
            id="login-title",
            style={
                "textAlign": "center",
                "color": "#FFFFFF",
                "fontSize": "24px",
                "fontWeight": "700",
                "letterSpacing": "-0.025em",
            },
        ),
        # Subtitle
        Text(
            content="Multi-Agent Orchestration Platform",
            variant="caption",
            id="login-subtitle",
            style={
                "textAlign": "center",
                "color": "#9CA3AF",
                "fontSize": "14px",
                "marginTop": "4px",
                "marginBottom": "24px",
            },
        ),
        # Login card
        Card(
            title="",
            content=card_content,
            id="login-card",
            variant="glass",
            style={
                "maxWidth": "400px",
                "width": "100%",
                "padding": "24px",
                "background": "rgba(26, 30, 46, 0.4)",
                "backdropFilter": "blur(16px)",
                "border": "1px solid rgba(255, 255, 255, 0.05)",
                "borderRadius": "12px",
                "boxShadow": "0 20px 25px -5px rgba(0, 0, 0, 0.3)",
            },
        ),
        # Version footer
        Text(
            content="v1.0.0",
            variant="caption",
            id="login-version",
            style={
                "textAlign": "center",
                "color": "rgba(156, 163, 175, 0.5)",
                "fontSize": "10px",
                "marginTop": "24px",
            },
        ),
    ]

    page = Container(
        children=children,
        id="login-container",
        style={
            "display": "flex",
            "flexDirection": "column",
            "alignItems": "center",
            "justifyContent": "center",
            "minHeight": "100vh",
            "background": "linear-gradient(135deg, #0F1221, #1A1E2E, #0F1221)",
            "gap": "8px",
        },
    )

    return [page.to_json()]


def build_credential_login_page(error: Optional[str] = None) -> List[Dict[str, Any]]:
    """Generate SDUI credential login page matching the Keycloak form design."""
    card_content: List[Any] = [
        Text(
            content="Sign in to your account",
            variant="h2",
            id="cred-heading",
            style={
                "color": "#FFFFFF",
                "fontWeight": "600",
                "fontSize": "18px",
                "marginBottom": "16px",
            },
        ),
        Input(
            name="username",
            placeholder="Username or email",
            input_type="text",
            id="cred-username",
            style={
                "marginBottom": "12px",
            },
        ),
        Input(
            name="password",
            placeholder="Password",
            input_type="password",
            id="cred-password",
            style={
                "marginBottom": "16px",
            },
        ),
    ]

    if error:
        card_content.append(
            Alert(
                message=error,
                variant="error",
                id="cred-error",
            )
        )

    card_content.append(
        Button(
            label="Sign In",
            action="credential_login",
            variant="primary",
            payload={"collect_inputs": True},
            id="cred-submit",
            style={
                "width": "100%",
                "padding": "10px 0",
                "background": "#2563EB",
                "borderRadius": "8px",
                "fontSize": "14px",
                "fontWeight": "500",
                "color": "#FFFFFF",
            },
        )
    )

    card_content.append(
        Button(
            label="\u2190  Back",
            action="show_login",
            variant="secondary",
            id="cred-back",
            style={
                "width": "100%",
                "padding": "8px 0",
                "fontSize": "13px",
                "marginTop": "8px",
            },
        )
    )

    children: List[Any] = [
        # Title
        Text(
            content="ASTRAL",
            variant="h1",
            id="cred-title",
            style={
                "textAlign": "center",
                "color": "#FFFFFF",
                "fontSize": "24px",
                "fontWeight": "300",
                "letterSpacing": "0.3em",
                "marginBottom": "24px",
            },
        ),
        # Login card with blue accent top border
        Card(
            title="",
            content=card_content,
            id="cred-card",
            variant="glass",
            style={
                "maxWidth": "440px",
                "width": "100%",
                "padding": "32px",
                "background": "rgba(30, 41, 59, 0.85)",
                "borderTop": "3px solid #2563EB",
                "borderRadius": "8px",
            },
        ),
    ]

    page = Container(
        children=children,
        id="credential-container",
        style={
            "display": "flex",
            "flexDirection": "column",
            "alignItems": "center",
            "justifyContent": "center",
            "minHeight": "100vh",
            "background": "linear-gradient(135deg, #0F1221, #1A1E2E, #0F1221)",
            "gap": "8px",
        },
    )

    return [page.to_json()]
