"""Bare-minimum Gemini connectivity test. No app code, no retries, no chain.
Run this directly: python raw_gemini_test.py
"""
import os
import sys
import time
import socket

print("=== Step 1: DNS resolution ===")
try:
    ip = socket.gethostbyname("generativelanguage.googleapis.com")
    print(f"OK - resolved to {ip}")
except Exception as e:
    print(f"FAILED: {e}")
    sys.exit(1)

print("\n=== Step 2: Raw TCP+TLS connection on port 443 ===")
try:
    import ssl
    ctx = ssl.create_default_context()
    start = time.time()
    with socket.create_connection(("generativelanguage.googleapis.com", 443), timeout=10) as sock:
        with ctx.wrap_socket(sock, server_hostname="generativelanguage.googleapis.com") as ssock:
            elapsed = time.time() - start
            print(f"OK - TLS handshake completed in {elapsed:.2f}s")
            print(f"TLS version: {ssock.version()}")
except Exception as e:
    print(f"FAILED: {type(e).__name__}: {e}")
    sys.exit(1)

print("\n=== Step 3: Actual Gemini API call via google-genai SDK ===")
api_key = os.environ.get("GEMINI_API_KEY")
if not api_key:
    print("FAILED: GEMINI_API_KEY not set in this shell's environment.")
    print("(Note: this script does NOT load .env automatically - export the key first, or run with it inline)")
    sys.exit(1)

try:
    from google import genai
    start = time.time()
    client = genai.Client(api_key=api_key, http_options={"timeout": 15.0})
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents="Reply with exactly the word OK.",
    )
    elapsed = time.time() - start
    print(f"OK - API call succeeded in {elapsed:.2f}s")
    print(f"Response: {response.text!r}")
except Exception as e:
    print(f"FAILED: {type(e).__name__}: {e}")
    sys.exit(1)

print("\n=== ALL STEPS PASSED ===")