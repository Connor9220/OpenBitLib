from typing import Union, Dict
import hmac
import hashlib
from typing import Dict
from urllib.parse import urlencode, urlparse
from settings import SECRET_KEY


def generate_hmac(url: str, secret_key: str = SECRET_KEY) -> str:
    """
    Generate an HMAC signature for the complete URL.

    Args:
        url (str): The full URL including query parameters.
        secret_key (str): The shared secret key.

    Returns:
        str: The generated HMAC signature.
    """
    # Use the full URL (path + query string) as the message
    parsed_url = urlparse(url)
    path = parsed_url.path
    query = parsed_url.query

    # Combine path and query without adding extra `?`
    if query:
        message = f"{path}?{query}"
    else:
        message = path  # No query parameters

    # Generate the HMAC signature
    signature = hmac.new(secret_key.encode(), message.encode(), hashlib.sha256).hexdigest()

    return signature


def verify_hmac(url: str, provided_signature: str, secret_key: str = SECRET_KEY) -> bool:
    """
    Verify an HMAC signature for the complete URL.

    Args:
        url (str): The full URL including query parameters.
        provided_signature (str): The HMAC signature to verify.
        secret_key (str): The shared secret key.

    Returns:
        bool: True if the signature is valid, False otherwise.
    """
    # Use the full URL (path + query string) as the message
    parsed_url = urlparse(url)
    message = f"{parsed_url.path}?{parsed_url.query}"

    # Generate the expected HMAC signature
    expected_signature = hmac.new(secret_key.encode(), message.encode(), hashlib.sha256).hexdigest()

    return hmac.compare_digest(expected_signature, provided_signature)
