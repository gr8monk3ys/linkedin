"""AI client for generating text using Claude API."""


def generate_with_ai(prompt: str, max_tokens: int = 500) -> str:
    """Generate text using Claude API."""
    try:
        import anthropic

        client = anthropic.Anthropic()  # Uses ANTHROPIC_API_KEY env var

        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text
    except Exception as e:
        return f"[AI generation failed: {e}. Make sure ANTHROPIC_API_KEY is set.]"
