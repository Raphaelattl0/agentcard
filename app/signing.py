"""
Signs Agent Cards per the A2A v1.x spec:
  1. Canonicalize the card JSON using JCS (RFC 8785)
  2. Compute a JWS (RFC 7515) over the canonical bytes
  3. Attach as card.signatures[]

This is what lets a receiving agent verify the card was actually issued by
the domain owner, rather than trusting an arbitrary unsigned JSON file —
the spec's stated reason signed cards exist is to prevent forged Agent Cards
redirecting other agents to malicious endpoints.
"""
from __future__ import annotations
import json
import base64
import hashlib
from typing import Any
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.utils import Prehashed, decode_dss_signature, encode_dss_signature
from app.models import AgentCard, AgentCardSignature


def jcs_canonicalize(obj: Any) -> bytes:
    """
    Minimal JSON Canonicalization Scheme (RFC 8785) implementation:
    - object keys sorted lexicographically (recursively)
    - no insignificant whitespace
    - UTF-8 encoding
    Sufficient for our purposes (no exotic number formatting edge cases
    since all our values are strings/bools/lists/dicts).
    """
    def sort_recursive(o):
        if isinstance(o, dict):
            return {k: sort_recursive(o[k]) for k in sorted(o.keys())}
        if isinstance(o, list):
            return [sort_recursive(i) for i in o]
        return o

    canonical = sort_recursive(obj)
    return json.dumps(canonical, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def private_key_to_pem(private_key: ec.EllipticCurvePrivateKey) -> str:
    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return pem.decode("utf-8")


def private_key_from_pem(pem_str: str) -> ec.EllipticCurvePrivateKey:
    return serialization.load_pem_private_key(pem_str.encode("utf-8"), password=None)


def generate_signing_key() -> ec.EllipticCurvePrivateKey:
    """Each tenant agent gets its own ES256 keypair at provisioning time."""
    return ec.generate_private_key(ec.SECP256R1())


def public_key_jwk(private_key: ec.EllipticCurvePrivateKey) -> dict:
    pub = private_key.public_key()
    numbers = pub.public_numbers()
    size = (pub.curve.key_size + 7) // 8
    x = numbers.x.to_bytes(size, "big")
    y = numbers.y.to_bytes(size, "big")
    return {
        "kty": "EC",
        "crv": "P-256",
        "x": _b64url(x),
        "y": _b64url(y),
    }


def sign_agent_card(card: AgentCard, private_key: ec.EllipticCurvePrivateKey, key_id: str) -> AgentCard:
    """Returns a copy of the card with card.signatures populated."""
    # Sign the card WITHOUT the signatures field present (can't sign over itself)
    unsigned = card.model_copy(deep=True)
    unsigned.signatures = []
    payload_bytes = jcs_canonicalize(unsigned.model_dump(exclude_none=True))

    header = {"alg": "ES256", "kid": key_id, "b64": False, "crit": ["b64"]}
    header_b64 = _b64url(json.dumps(header, separators=(",", ":")).encode())

    # JWS with detached/unencoded payload per spec guidance: sign header.payload
    signing_input = header_b64.encode() + b"." + payload_bytes
    digest = hashlib.sha256(signing_input).digest()
    der_sig = private_key.sign(digest, ec.ECDSA(Prehashed(hashes.SHA256())))

    # Convert DER ECDSA signature to raw r||s for JWS compact form
    r, s = _der_to_rs(der_sig, private_key.curve.key_size)
    sig_b64 = _b64url(r + s)

    signed = card.model_copy(deep=True)
    signed.signatures = [AgentCardSignature(protected=header_b64, signature=sig_b64)]
    return signed


def _der_to_rs(der_sig: bytes, key_size_bits: int) -> tuple[bytes, bytes]:
    r, s = decode_dss_signature(der_sig)
    size = (key_size_bits + 7) // 8
    return r.to_bytes(size, "big"), s.to_bytes(size, "big")


def verify_agent_card(card: AgentCard, public_jwk: dict) -> bool:
    """Verification path a receiving client/agent would run."""
    if not card.signatures:
        return False
    sig_obj = card.signatures[0]
    unsigned = card.model_copy(deep=True)
    unsigned.signatures = []
    payload_bytes = jcs_canonicalize(unsigned.model_dump(exclude_none=True))
    signing_input = base64.urlsafe_b64decode(sig_obj.protected + "==") and (
        sig_obj.protected.encode() + b"." + payload_bytes
    )
    digest = hashlib.sha256(signing_input).digest()

    x = int.from_bytes(base64.urlsafe_b64decode(public_jwk["x"] + "=="), "big")
    y = int.from_bytes(base64.urlsafe_b64decode(public_jwk["y"] + "=="), "big")
    pub_numbers = ec.EllipticCurvePublicNumbers(x, y, ec.SECP256R1())
    pub_key = pub_numbers.public_key()

    raw_sig = base64.urlsafe_b64decode(sig_obj.signature + "==")
    half = len(raw_sig) // 2
    r, s = raw_sig[:half], raw_sig[half:]
    der_sig = encode_dss_signature(int.from_bytes(r, "big"), int.from_bytes(s, "big"))

    try:
        pub_key.verify(der_sig, digest, ec.ECDSA(Prehashed(hashes.SHA256())))
        return True
    except Exception:
        return False
