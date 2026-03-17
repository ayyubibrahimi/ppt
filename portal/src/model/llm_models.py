import json
import logging
import re
from typing import TypeVar, Type
from pydantic import BaseModel, ValidationError
from openai.lib.azure import AzureOpenAI
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    before_sleep_log,
    retry_if_not_exception_type,
)
from diskcache import Cache
import blake3
import os
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

T = TypeVar('T', bound=BaseModel)

# Azure configuration
AZURE_ENDPOINT = os.getenv('AZURE_ENDPOINT')
AZURE_API_KEY = os.getenv('AZURE_API_KEY')
API_VERSION = os.getenv('API_VERSION')

# Cache setup
CACHE_DIR = "llm-responses.cache"
llm_cache = Cache(CACHE_DIR)

# Available models
AVAILABLE_MODELS = [
    "gpt-4.1-mini",
    "gpt-4.1",
    "gpt-4.1-mini-2025-04-14"
]


class LLM:
    """
    Unified LLM client with built-in structured output support.
    Uses Azure OpenAI and provides structured Pydantic responses.
    """
    
    def __init__(self, model_name="gpt-4.1", base_url=None, max_model_len=8000):
        self.model_name = model_name
        self.client = AzureOpenAI(
            azure_endpoint=AZURE_ENDPOINT,
            api_key=AZURE_API_KEY,
            api_version=API_VERSION
        )
        logger.info(f"Initialized Azure OpenAI client with model {model_name}")
        
    def _run_raw_inference(self, prompt, model=None, max_tokens=4096, temperature=0.1):
        """
        Internal method: Run raw inference using Azure OpenAI.
        Use run_structured_inference() for structured output or run_inference() for text.
        """
        model_to_use = model if model else self.model_name
        
        if model_to_use not in AVAILABLE_MODELS:
            raise ValueError(f"Model {model_to_use} not available. Available: {AVAILABLE_MODELS}")
        
        messages = [{"role": "user", "content": prompt}]
        
        # Create cache key
        serialized = json.dumps(messages, sort_keys=True)
        hash_value = blake3.blake3(serialized.encode()).hexdigest()
        cache_key = f"llm_response-{model_to_use}:{hash_value}"
        
        # Check cache
        # cached_response = llm_cache.get(cache_key)
        # if cached_response:
        #     logger.debug(f"LLM Cache HIT for {cache_key}")
        #     return cached_response
        
        logger.debug(f"LLM Cache MISS for {cache_key}")
        
        @retry(
            stop=stop_after_attempt(5),
            wait=wait_exponential(multiplier=1, min=10, max=80),
            before_sleep=before_sleep_log(logger, logging.DEBUG),
        )
        def call_api():
            response = self.client.chat.completions.create(
                model=model_to_use,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=1,
                frequency_penalty=0,
                presence_penalty=0,
            )
            return response.choices[0].message.content
        
        try:
            content = call_api()
            llm_cache.set(cache_key, content)
            return content
        except Exception as e:
            logger.error(f"Azure OpenAI API error: {e}")
            raise RuntimeError(f"Failed to get response from Azure OpenAI: {e}")
    
    def run_inference(self, prompt, model=None, max_tokens=4096, temperature=0.1):
        """
        Run inference and return raw text response.
        
        Args:
            prompt: The prompt to send to the model
            model: Model name to use (optional, defaults to instance model)
            max_tokens: Maximum tokens to generate
            temperature: Temperature for generation
            
        Returns:
            Raw text response from the model
        """
        return self._run_raw_inference(prompt, model, max_tokens, temperature)
    
    def run_structured_inference(self, prompt: str, response_model: Type[T],
                               model=None, max_tokens=4096, temperature=0.1) -> T:
        """
        Run inference and return a structured Pydantic model.

        Includes retry logic for JSON parsing failures.

        Args:
            prompt: The prompt to send to the model
            response_model: Pydantic model class for the expected response
            model: Model name to use (optional, defaults to instance model)
            max_tokens: Maximum tokens to generate
            temperature: Temperature for generation

        Returns:
            Instance of the response_model with parsed data
        """
        schema = response_model.model_json_schema()

        structured_prompt = f"""{prompt}

IMPORTANT: Respond with valid JSON that matches this exact schema:
```json
{json.dumps(schema, indent=2)}
```

Your response must be valid JSON only, wrapped in ```json and ``` tags.
Do not include duplicate fields. Ensure proper comma placement.
"""

        # Retry up to 3 times on JSON parsing failures
        max_retries = 3
        last_error = None

        for attempt in range(max_retries):
            try:
                # Add variation to temperature on retries to get different responses
                retry_temperature = temperature + (attempt * 0.05)

                raw_response = self._run_raw_inference(
                    structured_prompt, model, max_tokens, retry_temperature
                )

                json_str = self._extract_json_from_response(raw_response)
                parsed_data = json.loads(json_str)

                # Clean JSON: Extract data from schema wrapper if present
                cleaned_data = self._clean_schema_response(parsed_data)

                return response_model.model_validate(cleaned_data)

            except (json.JSONDecodeError, ValidationError) as e:
                last_error = e
                logger.warning(
                    f"Attempt {attempt + 1}/{max_retries} failed to parse structured response: {e}"
                )

                if attempt < max_retries - 1:
                    logger.info(f"Retrying with adjusted temperature ({retry_temperature:.2f})...")
                else:
                    logger.error(f"All {max_retries} attempts failed")
                    logger.error(f"Raw response was: {raw_response}")

        # All retries exhausted
        raise ValueError(f"Model returned invalid JSON after {max_retries} attempts: {last_error}")

    def _clean_schema_response(self, parsed_data: dict) -> dict:
        """
        Clean LLM response that may be wrapped in JSON Schema format.

        Since we show the LLM a JSON Schema, it often returns data wrapped
        in the schema structure with actual values in the 'properties' field.

        Args:
            parsed_data: Parsed JSON dict from LLM

        Returns:
            Cleaned dict with actual data (extracted from 'properties' if needed)
        """
        # If response has 'properties' field, extract the actual data from there
        if "properties" in parsed_data:
            return parsed_data["properties"]

        # Otherwise return as-is
        return parsed_data

    def _extract_json_from_response(self, response: str) -> str:
        """
        Extract JSON content from markdown code blocks with robust error handling.

        Handles:
        - Markdown code fences (```json ... ```)
        - Plain JSON objects
        - Extra whitespace
        - Comments
        """
        # Strategy 1: Try to extract from ```json``` blocks
        json_pattern = r'```json\s*(.*?)\s*```'
        matches = re.findall(json_pattern, response, re.DOTALL)

        if matches:
            json_str = matches[0].strip()
            # Validate this is actually valid JSON before returning
            if self._is_valid_json(json_str):
                return json_str

        # Strategy 2: Try to extract from ``` ``` blocks (without json tag)
        generic_fence_pattern = r'```\s*(.*?)\s*```'
        matches = re.findall(generic_fence_pattern, response, re.DOTALL)

        if matches:
            for match in matches:
                json_str = match.strip()
                if json_str.startswith('{') and self._is_valid_json(json_str):
                    return json_str

        # Strategy 3: Find JSON object in the response (longest match)
        json_pattern = r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}'
        matches = re.findall(json_pattern, response, re.DOTALL)

        if matches:
            # Try each match from longest to shortest
            sorted_matches = sorted(matches, key=len, reverse=True)
            for match in sorted_matches:
                json_str = match.strip()
                if self._is_valid_json(json_str):
                    return json_str

        # Strategy 4: Try to find and fix common JSON errors
        if '{' in response and '}' in response:
            # Extract everything between first { and last }
            start_idx = response.find('{')
            end_idx = response.rfind('}')
            json_str = response[start_idx:end_idx+1].strip()

            if self._is_valid_json(json_str):
                return json_str

        raise ValueError("No valid JSON content found in response")

    def _is_valid_json(self, json_str: str) -> bool:
        """Check if a string is valid JSON."""
        try:
            json.loads(json_str)
            return True
        except (json.JSONDecodeError, ValueError):
            return False
    
    def test_connection(self):
        """Test the LLM connection with a simple structured response"""
        try:
            from pydantic import BaseModel, Field
            
            class TestResponse(BaseModel):
                message: str = Field(description="A simple test message")
                status: str = Field(description="Status of the test")
            
            response = self.run_structured_inference(
                "Respond with a test message saying you're working and status 'ok'",
                TestResponse
            )
            
            logger.info(f"LLM Test Response: {response.message} (Status: {response.status})")
            return True
            
        except Exception as e:
            logger.error(f"LLM Test Failed: {e}")
            return False


llm = LLM(model_name="gpt-4.1-mini-2025-04-14")


# Convenience functions for backward compatibility
def run_structured_inference(prompt: str, response_model: Type[T], **kwargs) -> T:
    """Convenience function for structured inference using the global LLM instance."""
    return llm.run_structured_inference(prompt, response_model, **kwargs)


def run_inference(prompt, model=None, max_tokens=4096, temperature=0.1):
    """
    Run inference and return raw text response.
    This is the main function for text generation.
    """
    return llm.run_inference(prompt, model, max_tokens, temperature)


def test_llm():
    """Test the LLM connection"""
    return llm.test_connection()


if __name__ == "__main__":
    print("Testing Azure OpenAI connection...")
    if test_llm():
        print("✓ Azure OpenAI is working correctly!")
    else:
        print("✗ Azure OpenAI test failed!")