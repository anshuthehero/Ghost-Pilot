"""
Security & Token Helpers for Ghost Copilot.
"""

import hmac
import hashlib
import base64
import json
import secrets
import time
from typing import Optional, Dict, Any
from datetime import datetime, timedelta, timezone
from server.config.settings import settings

# Optional passlib for bcrypt, with standard hashlib fallback
try:
    from passlib.context import CryptContext
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
except ImportError:
    pwd_context = None


def verify_password(plain_password: str, hashed_password: str) -> bool:
    if pwd_context:
        return pwd_context.verify(plain_password, hashed_password)
    # Secure fallback using PBKDF2
    salt, hash_val = hashed_password.split("$") if "$" in hashed_password else ("", "")
    calculated = hashlib.pbkdf2_hmac("sha256", plain_password.encode(), salt.encode(), 100000).hex()
    return hmac.compare_digest(calculated, hash_val)


def get_password_hash(password: str) -> str:
    if pwd_context:
        return pwd_context.hash(password)
    # L-3 fix: use cryptographically random salt instead of time.time()
    salt = base64.b64encode(secrets.token_bytes(16)).decode()[:16]
    hash_val = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100000).hex()
    return f"{salt}${hash_val}"


def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """Creates a JWT or HMAC-signed access token."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": int(expire.timestamp())})
    
    # Robust standard HMAC-SHA256 JWT representation
    header = base64.urlsafe_b64encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode()).decode().rstrip("=")
    payload = base64.urlsafe_b64encode(json.dumps(to_encode).encode()).decode().rstrip("=")
    signature = base64.urlsafe_b64encode(
        hmac.new(settings.JWT_SECRET_KEY.encode(), f"{header}.{payload}".encode(), hashlib.sha256).digest()
    ).decode().rstrip("=")
    
    return f"{header}.{payload}.{signature}"


def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    """Validates signature and expiration of access token."""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        header, payload, sig = parts
        expected_sig = base64.urlsafe_b64encode(
            hmac.new(settings.JWT_SECRET_KEY.encode(), f"{header}.{payload}".encode(), hashlib.sha256).digest()
        ).decode().rstrip("=")
        
        if not hmac.compare_digest(sig, expected_sig):
            return None
            
        padded_payload = payload + "=" * (-len(payload) % 4)
        data = json.loads(base64.urlsafe_b64decode(padded_payload.encode()).decode())
        
        # Check expiration
        if "exp" in data and time.time() > data["exp"]:
            return None
        return data
    except Exception:
        return None
