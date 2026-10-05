"""A stand-in LLM client that hands back the call it was asked to make.

Some LLM calls sit deep inside existing code -- a form generator that tries a
mechanical paradigm and only then asks the model, say.  To batch such a call
without rewriting every caller, run the same code with a ``DeferringClient``:
if the code reaches the model, ``generate_chat`` raises ``DeferLLMCall``
carrying the exact ``LLMCall`` the live client would have been given; if it
never reaches the model, the code returns its answer as usual.

Code between the caller and ``generate_chat`` that catches broad exceptions
must re-raise ``DeferLLMCall`` (``except DeferLLMCall: raise`` ahead of
``except Exception``), or the deferral reads as a failed call.
"""

from typing import Any, Dict, List, Optional, Union

import clients.lib
from clients.types import LLMCall, Response, Schema


class DeferLLMCall(Exception):
    """Raised by ``DeferringClient.generate_chat`` with the call it was given."""

    def __init__(self, call: LLMCall) -> None:
        super().__init__("LLM call deferred")
        self.call = call


class DeferringClient:
    """Duck-types the parts of ``UnifiedLLMClient`` that structured callers use."""

    def __init__(self, default_model: str) -> None:
        self.default_model = default_model

    def warm_model(self, model: str, timeout: Optional[float] = None) -> bool:
        return True

    def generate_chat(
        self,
        prompt: str,
        model: Optional[str] = None,
        brief: bool = False,
        json_schema: Optional[Union[Dict[str, Any], Schema]] = None,
        context: Optional[str] = None,
        timeout: Optional[float] = None,
        messages: Optional[List[Any]] = None,
        max_tokens: Optional[int] = None,
    ) -> Response:
        """Raise ``DeferLLMCall``; only structured, single-prompt calls can be deferred."""
        if json_schema is None:
            raise ValueError("Only structured (json_schema) calls can be deferred")
        if messages:
            raise ValueError("Message-list calls cannot be deferred")
        schema = (
            json_schema
            if isinstance(json_schema, Schema)
            else clients.lib.schema_from_dict(json_schema)
        )
        raise DeferLLMCall(
            LLMCall(prompt=prompt, schema=schema, context=context, max_tokens=max_tokens)
        )
