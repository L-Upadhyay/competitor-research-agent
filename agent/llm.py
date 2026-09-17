# Shared language model (LLM) setup, so every agent uses the same model and settings.

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

# Load the secret keys (including OPENAI_API_KEY) from the .env file.
load_dotenv()

# The OpenAI model all agents use. Change it here to switch every agent at once.
# gpt-5.4-mini is an inexpensive, current model (verified working on 2026-09-16).
MODEL_NAME = "gpt-5.4-mini"


def get_llm():
    """Return a ready-to-use OpenAI chat model.

    temperature=0 makes answers as consistent as possible between runs.
    ChatOpenAI reads OPENAI_API_KEY from the environment automatically.
    """
    return ChatOpenAI(model=MODEL_NAME, temperature=0, timeout=60)
