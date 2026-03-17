"""
LLM models for data classification.
"""

import logging
from typing import Type, TypeVar
from pydantic import BaseModel

from model.llm_models import llm as shared_llm_client

logger = logging.getLogger(__name__)

T = TypeVar('T', bound=BaseModel)

# Use the shared LLM client instance
llm = shared_llm_client

logger.info("✅ Data classification LLM client initialized (using shared Azure OpenAI client)")


def run_structured_inference(prompt: str, response_model: Type[T], **kwargs) -> T:
    """
    Run structured inference and return a Pydantic model.

    This is a convenience wrapper around the shared LLM client.

    Args:
        prompt: The prompt to send to the model
        response_model: Pydantic model class for the expected response
        **kwargs: Additional arguments (model, max_tokens, temperature)

    Returns:
        Instance of the response_model with parsed data

    Raises:
        ValueError: If model returns invalid JSON
        RuntimeError: If LLM API call fails
    """
    return llm.run_structured_inference(prompt, response_model, **kwargs)


def run_inference(prompt: str, **kwargs) -> str:
    """
    Run inference and return raw text response.

    Args:
        prompt: The prompt to send to the model
        **kwargs: Additional arguments (model, max_tokens, temperature)

    Returns:
        Raw text response from the model

    Raises:
        RuntimeError: If LLM API call fails
    """
    return llm.run_inference(prompt, **kwargs)
