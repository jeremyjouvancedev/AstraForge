from __future__ import annotations

import os
from typing import Any, Literal, Type, TypeVar

from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


def get_google_model(
    model: str = "gemini-3-pro-preview",
    temperature: float = 0.3,
    **kwargs: Any,
) -> ChatGoogleGenerativeAI:
    """Return a configured ChatGoogleGenerativeAI model."""
    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    return ChatGoogleGenerativeAI(
        model=model,
        temperature=temperature,
        google_api_key=api_key,
        **kwargs,
    )


def get_structured_google(
    output_schema: Any,
    model: str = "gemini-3-pro-preview",
    temperature: float = 0.3,
    **kwargs: Any,
) -> Any:
    """Return a Google model configured for structured output."""
    llm = get_google_model(model=model, temperature=temperature, **kwargs)
    return llm.with_structured_output(output_schema)


# Example usage from user:
#
# class Feedback(BaseModel):
#     sentiment: Literal["positive", "neutral", "negative"]
#     summary: str
#
# structured_model = get_structured_gemini(Feedback)
# response = structured_model.invoke("The new UI is great!")
# print(response.sentiment)
