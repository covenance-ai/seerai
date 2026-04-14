"""API token pricing per model.

Prices are per-token (not per 1K or 1M). We use output token pricing
since event metadata tracks tokens on AI responses. This gives a
conservative (lower-bound) estimate of API cost — real API usage also
incurs input token costs.

Update these when providers change pricing.
"""

# model name → cost per output token in USD
API_PRICE_PER_TOKEN: dict[str, float] = {
    # Anthropic
    "claude-sonnet-4": 15.0 / 1_000_000,
    "claude-sonnet-4-20250514": 15.0 / 1_000_000,
    "claude-haiku-4-5": 5.0 / 1_000_000,
    "claude-opus-4": 75.0 / 1_000_000,
    # OpenAI
    "gpt-4o": 10.0 / 1_000_000,
    "gpt-4o-mini": 0.60 / 1_000_000,
    "gpt-4.1": 8.0 / 1_000_000,
    "o3": 40.0 / 1_000_000,
    # Google
    "gemini-2.0-flash": 0.40 / 1_000_000,
    "gemini-2.5-pro": 10.0 / 1_000_000,
    # Mistral
    "mistral-large": 9.0 / 1_000_000,
}

# Fallback for unknown models — use a mid-range estimate
DEFAULT_PRICE_PER_TOKEN = 10.0 / 1_000_000


def token_cost(model: str, token_count: int) -> float:
    """Compute the API-equivalent cost for a given model and token count."""
    price = API_PRICE_PER_TOKEN.get(model, DEFAULT_PRICE_PER_TOKEN)
    return price * token_count
