"""Suite-wide pytest configuration.

Skips any test that needs tiktoken's encoding data when that data cannot be
loaded.  tiktoken downloads its encoding file on first use and caches it; on a
developer machine that has happened long ago, but a sandbox with no route to
openaipublic.blob.core.windows.net (e.g. a cloud agent session) cannot fetch it.
The skip happens at the point of use, so no list of affected tests has to be
kept in sync by hand -- anything that reaches tiktoken.get_encoding (in practice,
every schema conversion via clients.lib.count_schema_tokens) is covered.

There is deliberately no stand-in tokenizer: production needs the real one, and
a test that passed against an estimate would prove nothing about it.
"""

from typing import Any, Callable, Dict, Iterator

import pytest
import requests


@pytest.fixture(autouse=True, scope="session")
def _skip_when_tiktoken_data_unavailable() -> Iterator[None]:
    """Turn a failed tiktoken encoding download into a skip of that test."""
    try:
        import tiktoken
    except ImportError:
        yield
        return

    real_get_encoding: Callable[[str], Any] = tiktoken.get_encoding
    unavailable: Dict[str, str] = {}

    def get_encoding(encoding_name: str) -> Any:
        if encoding_name in unavailable:
            pytest.skip(unavailable[encoding_name])
        try:
            return real_get_encoding(encoding_name)
        except requests.exceptions.RequestException as exc:
            # Remember the failure: a blocked host fails the same way every
            # time, and retrying costs a connection attempt per test.
            unavailable[encoding_name] = (
                f"tiktoken encoding {encoding_name!r} not cached and cannot be "
                f"downloaded here ({type(exc).__name__})"
            )
            pytest.skip(unavailable[encoding_name])

    mp = pytest.MonkeyPatch()
    mp.setattr(tiktoken, "get_encoding", get_encoding)
    yield
    mp.undo()
