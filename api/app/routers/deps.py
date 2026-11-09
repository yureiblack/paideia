"""Dependencies shared by several routers.

Purpose
-------
The language model is needed both by the documents router, which asks for a
summary once a document is read, and by the summaries router. Defining the
dependency here, rather than in either of them, keeps the two routers from
importing each other. Tests replace it with a stand-in model.
"""

from typing import Annotated

from fastapi import Depends

from app.llm import LLMProvider, default_provider


def get_llm() -> LLMProvider:
    """The language model summaries are written with. Tests swap it."""
    return default_provider()


LLMDep = Annotated[LLMProvider, Depends(get_llm)]
