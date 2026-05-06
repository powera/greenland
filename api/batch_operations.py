"""Typed wrappers for Barsukas batch operation routes."""

from dataclasses import dataclass

from api._http import HttpResult, send_request


@dataclass(frozen=True)
class ListBatchesRequest:
    status: str = ""
    agent: str = ""


@dataclass(frozen=True)
class BatchOperationsResponse:
    result: HttpResult


def list_batches(request_data: ListBatchesRequest) -> BatchOperationsResponse:
    """Delegate to Barsukas `GET /batch-operations/` route."""
    return BatchOperationsResponse(
        result=send_request(
            "GET",
            "/batch-operations/",
            params={"status": request_data.status, "agent": request_data.agent},
        )
    )
