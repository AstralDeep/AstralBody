"""
ECIES Credential Encryption — End-to-end encrypted credential delivery.

Provides ECDH (P-256) + HKDF-SHA256 + AES-256-GCM encryption so that
credentials stored by the orchestrator can only be decrypted by the
target agent's private key.

Ciphertext format (base64url-encoded, prefixed with "e2e:"):
    e2e:<base64url(eph_pub_65B | salt_16B | nonce_12B | ciphertext | tag_16B)>

Also contains shared JWK utilities used by both delegation.py and base_agent.py.
"""
import os
import base64
import hashlib
import json
import logging
from typing import Tuple, Dict, Optional

from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.backends import default_backend

logger = logging.getLogger("Crypto")

E2E_PREFIX = "e2e:"
HKDF_INFO = b"astral-credential-v1"
EC_CURVE = ec.SECP256R1()


# ---------------------------------------------------------------------------
# EC Key Pair Generation
# ---------------------------------------------------------------------------

def generate_ec_keypair() -> Tuple[ec.EllipticCurvePrivateKey, ec.EllipticCurvePublicKey]:
    """Generate an EC P-256 key pair."""
    private_key = ec.generate_private_key(EC_CURVE, default_backend())
    return private_key, private_key.public_key()


# ---------------------------------------------------------------------------
# JWK Utilities (extracted from delegation.py for shared use)
# ---------------------------------------------------------------------------

def build_jwk(public_key: ec.EllipticCurvePublicKey) -> dict:
    """Build a JWK dict from an EC public key (P-256)."""
    numbers = public_key.public_numbers()
    x_bytes = numbers.x.to_bytes(32, byteorder="big")
    y_bytes = numbers.y.to_bytes(32, byteorder="big")
    return {
        "kty": "EC",
        "crv": "P-256",
        "x": base64.urlsafe_b64encode(x_bytes).rstrip(b"=").decode(),
        "y": base64.urlsafe_b64encode(y_bytes).rstrip(b"=").decode(),
    }


def compute_jwk_thumbprint(jwk: dict) -> str:
    """Compute the JWK Thumbprint (RFC 7638) — base64url(SHA-256(canonical JWK))."""
    canonical = json.dumps(
        {"crv": jwk["crv"], "kty": jwk["kty"], "x": jwk["x"], "y": jwk["y"]},
        separators=(",", ":"),
        sort_keys=True,
    )
    digest = hashlib.sha256(canonical.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def ec_public_key_from_jwk(jwk: dict) -> ec.EllipticCurvePublicKey:
    """Reconstruct an EC P-256 public key from a JWK dict."""
    def _pad_b64(s: str) -> str:
        return s + "=" * (-len(s) % 4)

    x_bytes = base64.urlsafe_b64decode(_pad_b64(jwk["x"]))
    y_bytes = base64.urlsafe_b64decode(_pad_b64(jwk["y"]))
    x_int = int.from_bytes(x_bytes, byteorder="big")
    y_int = int.from_bytes(y_bytes, byteorder="big")
    public_numbers = ec.EllipticCurvePublicNumbers(x_int, y_int, EC_CURVE)
    return public_numbers.public_key(default_backend())


# ---------------------------------------------------------------------------
# PEM Key Persistence
# ---------------------------------------------------------------------------

def save_private_key(key: ec.EllipticCurvePrivateKey, path: str) -> None:
    """Serialize an EC private key to PEM and write to disk."""
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(pem)
    logger.info(f"Saved agent private key to {path}")


def load_private_key(path: str) -> ec.EllipticCurvePrivateKey:
    """Load an EC private key from a PEM file."""
    with open(path, "rb") as f:
        return serialization.load_pem_private_key(f.read(), password=None, backend=default_backend())


# ---------------------------------------------------------------------------
# ECIES Encryption (Orchestrator side)
# ---------------------------------------------------------------------------

def encrypt_for_agent(plaintext: str, agent_public_key: ec.EllipticCurvePublicKey) -> str:
    """Encrypt a credential value using ECIES so only the target agent can decrypt.

    Construction: ephemeral ECDH + HKDF-SHA256 + AES-256-GCM.

    Returns:
        String in format "e2e:<base64url(eph_pub | salt | nonce | ciphertext | tag)>"
    """
    # 1. Generate ephemeral EC key pair
    eph_private = ec.generate_private_key(EC_CURVE, default_backend())
    eph_public = eph_private.public_key()

    # 2. ECDH shared secret
    shared_secret = eph_private.exchange(ec.ECDH(), agent_public_key)

    # 3. Derive symmetric key via HKDF
    salt = os.urandom(16)
    derived_key = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        info=HKDF_INFO,
        backend=default_backend(),
    ).derive(shared_secret)

    # 4. AES-256-GCM encrypt
    nonce = os.urandom(12)
    aesgcm = AESGCM(derived_key)
    ciphertext_and_tag = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)

    # 5. Serialize: eph_pub_uncompressed (65 bytes) | salt (16) | nonce (12) | ciphertext+tag
    eph_pub_bytes = eph_public.public_bytes(
        serialization.Encoding.X962,
        serialization.PublicFormat.UncompressedPoint,
    )
    payload = eph_pub_bytes + salt + nonce + ciphertext_and_tag
    encoded = base64.urlsafe_b64encode(payload).rstrip(b"=").decode()

    return E2E_PREFIX + encoded


# ---------------------------------------------------------------------------
# ECIES Decryption (Agent side)
# ---------------------------------------------------------------------------

def decrypt_from_orchestrator(ciphertext: str, agent_private_key: ec.EllipticCurvePrivateKey) -> str:
    """Decrypt a credential value encrypted with encrypt_for_agent().

    Args:
        ciphertext: String in format "e2e:<base64url(...)>"
        agent_private_key: The agent's EC P-256 private key.

    Returns:
        Decrypted plaintext string.
    """
    if not ciphertext.startswith(E2E_PREFIX):
        raise ValueError("Ciphertext does not have e2e: prefix — not ECIES-encrypted")

    encoded = ciphertext[len(E2E_PREFIX):]
    # Pad base64url
    padded = encoded + "=" * (-len(encoded) % 4)
    raw = base64.urlsafe_b64decode(padded)

    # Parse: eph_pub (65 bytes) | salt (16) | nonce (12) | ciphertext+tag (remainder)
    if len(raw) < 65 + 16 + 12 + 16:  # minimum: header + salt + nonce + GCM tag
        raise ValueError("Ciphertext too short")

    eph_pub_bytes = raw[:65]
    salt = raw[65:81]
    nonce = raw[81:93]
    ciphertext_and_tag = raw[93:]

    # Reconstruct ephemeral public key
    eph_public = ec.EllipticCurvePublicKey.from_encoded_point(EC_CURVE, eph_pub_bytes)

    # ECDH shared secret
    shared_secret = agent_private_key.exchange(ec.ECDH(), eph_public)

    # Derive symmetric key
    derived_key = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        info=HKDF_INFO,
        backend=default_backend(),
    ).derive(shared_secret)

    # AES-256-GCM decrypt
    aesgcm = AESGCM(derived_key)
    plaintext_bytes = aesgcm.decrypt(nonce, ciphertext_and_tag, None)
    return plaintext_bytes.decode("utf-8")


def is_e2e_encrypted(value: str) -> bool:
    """Check if a stored credential value is ECIES-encrypted (vs legacy Fernet)."""
    return value.startswith(E2E_PREFIX)
