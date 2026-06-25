"""Diagnostic script to verify the active LLM provider is reachable and working."""

import sys
import os
import logging
from dotenv import load_dotenv

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath("."))

# Load environment variables from .env with override=True
load_dotenv(override=True)

from llm.provider_factory import get_provider

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("check_provider")


def main() -> None:
    try:
        provider = get_provider()
        logger.info(f"Initialized provider: {provider.__class__.__name__}")
        if hasattr(provider, "provider_name"):
            logger.info(f"Configured provider name: {provider.provider_name}")
        if hasattr(provider, "default_model"):
            logger.info(f"Configured model: {provider.default_model}")
        if hasattr(provider, "api_key") and provider.api_key:
            k = provider.api_key
            logger.info(f"Active API Key in memory: {k[:12]}...{k[-4:]} (Length: {len(k)})")
        
        logger.info("Sending test prompt: 'Reply with exactly the word OK.'")
        result = provider.generate_text("You are a test.", "Reply with exactly the word OK.")
        print(f"\n[Raw Result] -> {result}\n")
        logger.info("SUCCESS: Provider is fully reachable and working!")
    except Exception as e:
        logger.error(f"FAILURE: Could not connect to provider. Error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
