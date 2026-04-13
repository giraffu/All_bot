import asyncio
from src.utils import load_prompts

def test_load_prompts():
    config = load_prompts()
    print("undress:", config.get("undress", "not found")[:50])
    print("negative_prompt:", config.get("negative_prompt", "not found")[:50])

test_load_prompts()
