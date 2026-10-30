import hashlib
import hmac


def ip_hash(secret: str, ip: str) -> str:
    """Keyed hash so logs can group requests by client without storing the IP."""
    return hmac.new(secret.encode(), ip.encode(), hashlib.sha256).hexdigest()
