"""Print a new random broker-password key for MOHZ_BROKER_KEY.

    python -m mohz.keygen
"""
import base64
import os

if __name__ == "__main__":
    print(base64.urlsafe_b64encode(os.urandom(32)).decode().rstrip("="))
