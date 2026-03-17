import tiktoken 

def count_tokens(text: str) -> int:
    """Count tokens in text using tiktoken."""
    enc = tiktoken.encoding_for_model("gpt-4")
    return len(enc.encode(text))
