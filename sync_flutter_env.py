#!/usr/bin/env python3
"""
Sync environment variables from root .env to Flutter .env files.

This script merges environment variables from the root .env file with
Flutter-specific defaults, creating appropriate .env files for the Flutter app.
"""

import os
import re
from pathlib import Path
from typing import Dict, List

# Paths
ROOT_DIR = Path(__file__).parent
ROOT_ENV = ROOT_DIR / ".env"
FLUTTER_DIR = ROOT_DIR / "flutter"
FLUTTER_ENV = FLUTTER_DIR / ".env"
FLUTTER_ASSETS_ENV = FLUTTER_DIR / "assets" / ".env"

# Flutter-specific defaults that should always be present
FLUTTER_DEFAULTS = {
    "VITE_BFF_URL": "http://localhost:8001",
    "VITE_WS_URL": "ws://localhost:8001/ws",
    "VITE_KEYCLOAK_REDIRECT_URI": "astralbody://callback",
    "VITE_KEYCLOAK_SCOPES": "openid profile email",
}


def parse_env_file(filepath: Path) -> Dict[str, str]:
    """Parse a .env file into a dictionary."""
    env_vars = {}
    if not filepath.exists():
        return env_vars
    
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            # Skip empty lines and comments
            if not line or line.startswith('#'):
                continue
            # Parse KEY=VALUE
            if '=' in line:
                key, value = line.split('=', 1)
                env_vars[key.strip()] = value.strip()
    
    return env_vars


def write_env_file(filepath: Path, env_vars: Dict[str, str], comment: str = None):
    """Write environment variables to a .env file."""
    # Ensure directory exists
    filepath.parent.mkdir(parents=True, exist_ok=True)
    
    lines = []
    if comment:
        lines.append(f"# {comment}")
        lines.append("")
    
    # Write variables in a consistent order
    # First, Flutter-specific variables
    flutter_keys = [k for k in env_vars.keys() if k.startswith('VITE_') or k in ['DEBUG']]
    other_keys = [k for k in env_vars.keys() if k not in flutter_keys]
    
    if flutter_keys:
        lines.append("# Flutter Configuration")
        for key in sorted(flutter_keys):
            lines.append(f"{key}={env_vars[key]}")
        lines.append("")
    
    if other_keys:
        lines.append("# Other Configuration")
        for key in sorted(other_keys):
            lines.append(f"{key}={env_vars[key]}")
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    
    print(f"Written {len(env_vars)} variables to {filepath}")


def main():
    print("Syncing environment variables from root .env to Flutter...")
    
    # Parse root .env
    root_env = parse_env_file(ROOT_ENV)
    print(f"Found {len(root_env)} variables in root .env")
    
    # Parse existing Flutter .env (if any) to preserve any custom values
    flutter_env = parse_env_file(FLUTTER_ENV)
    
    # Start with Flutter defaults
    merged = FLUTTER_DEFAULTS.copy()
    
    # Merge with existing Flutter .env (preserving any custom values)
    merged.update(flutter_env)
    
    # Merge with root .env (root overrides everything)
    merged.update(root_env)
    
    # Ensure DEBUG is set from root if present, otherwise default to true
    if 'DEBUG' in root_env:
        merged['DEBUG'] = root_env['DEBUG']
    elif 'DEBUG' not in merged:
        merged['DEBUG'] = 'true'
    
    # Ensure VITE_USE_MOCK_AUTH is set from root if present
    if 'VITE_USE_MOCK_AUTH' in root_env:
        merged['VITE_USE_MOCK_AUTH'] = root_env['VITE_USE_MOCK_AUTH']
    
    # Write to flutter/.env
    write_env_file(
        FLUTTER_ENV, 
        merged,
        comment="Flutter Environment Configuration - Auto-generated from root .env"
    )
    
    # Write to flutter/assets/.env (for web)
    write_env_file(
        FLUTTER_ASSETS_ENV,
        merged,
        comment="Flutter Web Environment Configuration - Auto-generated from root .env"
    )
    
    # Print summary of key variables
    print("\nKey variables synced:")
    for key in ['VITE_BFF_URL', 'VITE_WS_URL', 'VITE_KEYCLOAK_AUTHORITY', 
                'VITE_KEYCLOAK_CLIENT_ID', 'VITE_USE_MOCK_AUTH', 'DEBUG']:
        if key in merged:
            print(f"  {key}={merged[key]}")
    
    print("\nSync complete!")


if __name__ == "__main__":
    main()
