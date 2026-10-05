"""Tests for workqueue.llm_batch: staged LLM jobs, inline and batched.

A fake two-stage job stands in for a real agent.  Stage one writes a value per
item into a shared store; stage two's prompt lists every value stage one wrote,
which is how these tests see the barrier: a stage-two prompt built too early
would be missing some.
"""

import json
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional
from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session

from clients.batch_queue import (
    BatchQueue,
    BatchQueueManager,
    BatchRequestStatus,
    create_batch_database_session,
    request_extra,
)
from clients.lib import LLMCallsDisabledError
from clients.types import LLMCall, Response, Schema, SchemaProperty
from workqueue.llm_batch import (
    Done,
    Job,
    Next,
    Ready,
    Stage,
    StageContext,
    advance_run,
    complete_rows,
    fail_batch,
    run_inline,
    start_batch_run,
)

_MODEL = "gpt-6-luna"
_SCHEMA = Schema("Answer", "An answer", {"value": SchemaProperty("string", "The value")})


@pytest.fixture(autouse=True)
def _no_schema_size_check(monkeypatch: pytest.MonkeyPatch) -> None:
    """Request shape only; counting schema tokens needs tiktoken's downloaded data."""
    monkeypatch.setattr("clients.lib.count_schema_tokens", lambda schema_dict: 0)


class FakeJob:
    """A two-stage job over items ``{"lemma_id": n}``.

    Stage one asks for a word and stores it.  Stage two's prompt names every
    stored word, then stores the final answer.  Item 99 is answered without a
    model in stage one (``Ready``); item 0 is rejected by stage one's prepare.
    """

    def __init__(self) -> None:
        self.stage_one: Dict[int, str] = {}
        self.stage_two: Dict[int, str] = {}
        self.stage_two_prompts: List[str] = []
        self.job = Job(
            name="fake",
            stages=(
                Stage("fake.one", self.prepare_one, self.apply_one),
                Stage("fake.two", self.prepare_two, self.apply_two),
            ),
            item_key=lambda state: str(state["lemma_id"]),
        )

    def prepare_one(self, session: Any, state: Dict[str, Any], ctx: StageContext) -> Any:
        if state["lemma_id"] == 0:
            return Done("skipped", "nothing to do")
        if state["lemma_id"] == 99:
            return Ready({"value": "copied"})
        return LLMCall(prompt=f"one:{state['lemma_id']}", schema=_SCHEMA)

    def apply_one(
        self, session: Any, state: Dict[str, Any], data: Dict[str, Any], ctx: StageContext
    ) -> Any:
        if data.get("value") == "bad":
            raise ValueError("bad answer")
        self.stage_one[state["lemma_id"]] = data["value"]
        return Next({**state, "word": data["value"]})

    def prepare_two(self, session: Any, state: Dict[str, Any], ctx: StageContext) -> Any:
        prompt = "two:" + ",".join(sorted(self.stage_one.values()))
        self.stage_two_prompts.append(prompt)
        return LLMCall(prompt=prompt, schema=_SCHEMA)

    def apply_two(
        self, session: Any, state: Dict[str, Any], data: Dict[str, Any], ctx: StageContext
    ) -> Any:
        self.stage_two[state["lemma_id"]] = data["value"]
        return Done("written")


class FakeChatClient:
    def __init__(self, answer: Callable[[str], str]) -> None:
        self.answer = answer
        self.prompts: List[str] = []

    def generate_chat(self, prompt: str, model: Optional[str] = None, **_: Any) -> Response:
        self.prompts.append(prompt)
        return Response(
            response_text="", structured_data={"value": self.answer(prompt)}, usage=None
        )


class FakeBatchClient:
    """Records submissions and serves results the test decides on."""

    def __init__(self) -> None:
        self.batches: Dict[str, List[Dict[str, Any]]] = {}
        self.status: Dict[str, str] = {}
        self.fail_next_submit = False
        self._uploads: Dict[str, List[Dict[str, Any]]] = {}

    def upload_batch_file(self, requests_data: List[Dict[str, Any]]) -> str:
        file_id = f"file-{len(self._uploads)}"
        self._uploads[file_id] = requests_data
        return file_id

    def create_batch(
        self, input_file_id: str, endpoint: str = "", metadata: Any = None, **_: Any
    ) -> Dict[str, Any]:
        if self.fail_next_submit:
            self.fail_next_submit = False
            raise RuntimeError("upload refused")
        batch_id = f"batch-{len(self.batches)}"
        self.batches[batch_id] = self._uploads[input_file_id]
        self.status[batch_id] = "in_progress"
        return {"id": batch_id}

    def get_batch_status(self, batch_id: str) -> Dict[str, Any]:
        return {"id": batch_id, "status": self.status[batch_id], "output_file_id": batch_id}

    def download_batch_results(self, output_file_id: str) -> List[Dict[str, Any]]:
        return self._results[output_file_id]

    def finish(self, batch_id: str, answer: Callable[[str], str]) -> None:
        self.status[batch_id] = "completed"
        if not hasattr(self, "_results"):
            self._results: Dict[str, List[Dict[str, Any]]] = {}
        self._results[batch_id] = [
            {
                "custom_id": line["custom_id"],
                "response": {
                    "status_code": 200,
                    "body": {
                        "status": "completed",
                        "output": [
                            {
                                "type": "message",
                                "content": [
                                    {
                                        "type": "output_text",
                                        "text": json.dumps(
                                            {"value": answer(line["body"]["input"])}
                                        ),
                                    }
                                ],
                            }
                        ],
                    },
                },
            }
            for line in self.batches[batch_id]
        ]

    def prompts(self, batch_id: str) -> List[str]:
        return [line["body"]["input"] for line in self.batches[batch_id]]


@pytest.fixture
def batch_session(tmp_path: Path) -> Iterator[Session]:
    session = create_batch_database_session(str(tmp_path / "batch_tracking.sqlite"))
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def batch_client() -> FakeBatchClient:
    return FakeBatchClient()


@pytest.fixture
def manager(batch_session: Session, batch_client: FakeBatchClient) -> BatchQueueManager:
    return BatchQueueManager(batch_session, batch_client=batch_client)  # type: ignore[arg-type]


def _word(prompt: str) -> str:
    return "w" + prompt.split(":")[1] if prompt.startswith("one:") else "final"


def _complete(
    fake: FakeJob,
    manager: BatchQueueManager,
    batch_client: FakeBatchClient,
    batch_id: str,
    answer: Callable[[str], str] = _word,
) -> Dict[str, int]:
    batch_client.finish(batch_id, answer)
    manager.retrieve_batch_results(batch_id)
    rows = manager.get_completed_requests(batch_id=batch_id)
    return complete_rows(fake.job, rows, MagicMock(), batch_id, manager)


# --- Job construction -------------------------------------------------------


def test_job_rejects_more_than_three_stages() -> None:
    stage = Stage("s", lambda *a: Done("skipped"), lambda *a: Done("written"))
    stages = tuple(Stage(f"s{i}", stage.prepare, stage.apply) for i in range(4))
    with pytest.raises(ValueError, match="1-3 stages"):
        Job(name="too_long", stages=stages, item_key=str)


def test_job_rejects_colon_in_name() -> None:
    stage = Stage("s", lambda *a: Done("skipped"), lambda *a: Done("written"))
    with pytest.raises(ValueError, match="':'"):
        Job(name="a:b", stages=(stage,), item_key=str)


# --- Inline -----------------------------------------------------------------


def test_inline_runs_all_of_stage_one_before_stage_two() -> None:
    fake = FakeJob()
    client = FakeChatClient(_word)
    results = run_inline(
        MagicMock(), fake.job, [{"lemma_id": 1}, {"lemma_id": 2}, {"lemma_id": 3}], client, _MODEL  # type: ignore[arg-type]
    )
    assert results == [Done("written")] * 3
    assert client.prompts[:3] == ["one:1", "one:2", "one:3"]
    # Every stage-two prompt saw every stage-one answer.
    assert fake.stage_two_prompts == ["two:w1,w2,w3"] * 3


def test_inline_ready_and_done_need_no_call() -> None:
    fake = FakeJob()
    client = FakeChatClient(_word)
    results = run_inline(MagicMock(), fake.job, [{"lemma_id": 0}, {"lemma_id": 99}], client, _MODEL)  # type: ignore[arg-type]
    assert results == [Done("skipped", "nothing to do"), Done("written")]
    assert fake.stage_one == {99: "copied"}
    assert client.prompts == ["two:copied"]


def test_inline_failure_costs_only_its_item() -> None:
    fake = FakeJob()
    client = FakeChatClient(lambda p: "bad" if p == "one:2" else _word(p))
    session = MagicMock()
    results = run_inline(session, fake.job, [{"lemma_id": 1}, {"lemma_id": 2}], client, _MODEL)  # type: ignore[arg-type]
    assert results[0] == Done("written")
    assert results[1].status == "failed" and "bad answer" in results[1].detail
    session.rollback.assert_called()


def test_inline_kill_switch_stops_the_run() -> None:
    fake = FakeJob()

    def refuse(prompt: str) -> str:
        raise LLMCallsDisabledError("blocked")

    with pytest.raises(LLMCallsDisabledError):
        run_inline(MagicMock(), fake.job, [{"lemma_id": 1}], FakeChatClient(refuse), _MODEL)  # type: ignore[arg-type]


# --- Batch ------------------------------------------------------------------


def test_stage_two_waits_for_every_stage_one_batch(
    manager: BatchQueueManager, batch_client: FakeBatchClient
) -> None:
    fake = FakeJob()
    report = start_batch_run(
        MagicMock(),
        manager,
        fake.job,
        [{"lemma_id": 1}, {"lemma_id": 2}, {"lemma_id": 3}],
        _MODEL,
        items_per_batch=2,
    )
    assert report.calls == 3
    assert report.batch_ids == ["batch-0", "batch-1"]

    first = _complete(fake, manager, batch_client, "batch-0")
    assert first["carried"] == 2
    assert first["next_stage_calls"] == 0
    assert len(batch_client.batches) == 2  # nothing new while batch-1 is out

    second = _complete(fake, manager, batch_client, "batch-1")
    assert second["next_stage_calls"] == 3
    # Stage two keeps the run's items_per_batch, so it goes out as two batches.
    stage_two_prompts = batch_client.prompts("batch-2") + batch_client.prompts("batch-3")
    assert stage_two_prompts == ["two:w1,w2,w3"] * 3

    final = _complete(fake, manager, batch_client, "batch-2")
    final_rest = _complete(fake, manager, batch_client, "batch-3")
    assert final["updated"] + final_rest["updated"] == 3
    assert fake.stage_two == {1: "final", 2: "final", 3: "final"}
    assert len(batch_client.batches) == 4


def test_failed_batch_opens_the_barrier(
    manager: BatchQueueManager, batch_client: FakeBatchClient
) -> None:
    fake = FakeJob()
    start_batch_run(
        MagicMock(),
        manager,
        fake.job,
        [{"lemma_id": 1}, {"lemma_id": 2}],
        _MODEL,
        items_per_batch=1,
    )
    _complete(fake, manager, batch_client, "batch-0")
    assert len(batch_client.batches) == 2

    batch_client.status["batch-1"] = "expired"
    manager.check_batch_status("batch-1")
    assert fail_batch(fake.job, "batch-1", manager, MagicMock()) == 1
    assert batch_client.prompts("batch-2") == ["two:w1"]


def test_advance_is_idempotent(manager: BatchQueueManager, batch_client: FakeBatchClient) -> None:
    fake = FakeJob()
    report = start_batch_run(MagicMock(), manager, fake.job, [{"lemma_id": 1}], _MODEL)
    _complete(fake, manager, batch_client, "batch-0")
    assert len(batch_client.batches) == 2
    assert advance_run(fake.job, report.run_id, manager, MagicMock()) == 0
    assert len(batch_client.batches) == 2


def test_completing_twice_applies_once(
    manager: BatchQueueManager, batch_client: FakeBatchClient
) -> None:
    fake = FakeJob()
    start_batch_run(MagicMock(), manager, fake.job, [{"lemma_id": 1}], _MODEL)
    _complete(fake, manager, batch_client, "batch-0")
    rows = manager.get_completed_requests(batch_id="batch-0")
    again = complete_rows(fake.job, rows, MagicMock(), "batch-0", manager)
    assert again["processed"] == 0


def test_open_items_are_skipped_by_a_new_run(
    manager: BatchQueueManager, batch_client: FakeBatchClient
) -> None:
    fake = FakeJob()
    start_batch_run(MagicMock(), manager, fake.job, [{"lemma_id": 1}], _MODEL)
    report = start_batch_run(
        MagicMock(), manager, fake.job, [{"lemma_id": 1}, {"lemma_id": 2}, {"lemma_id": 2}], _MODEL
    )
    assert report.skipped_in_flight == 2
    assert report.calls == 1

    # Waiting for stage two still counts as open.
    _complete(fake, manager, batch_client, "batch-0")
    report = start_batch_run(MagicMock(), manager, fake.job, [{"lemma_id": 1}], _MODEL)
    assert report.skipped_in_flight == 1


def test_ready_and_done_in_batch_start(
    manager: BatchQueueManager, batch_client: FakeBatchClient
) -> None:
    fake = FakeJob()
    report = start_batch_run(
        MagicMock(), manager, fake.job, [{"lemma_id": 0}, {"lemma_id": 99}], _MODEL
    )
    assert report.calls == 0
    assert report.resolved_without_llm == {"skipped": 1, "carried": 1}
    # The carried item had no batch to wait for, so stage two went out at once.
    assert batch_client.prompts("batch-0") == ["two:copied"]


def test_dry_run_writes_and_submits_nothing(
    manager: BatchQueueManager, batch_client: FakeBatchClient, batch_session: Session
) -> None:
    fake = FakeJob()
    report = start_batch_run(
        MagicMock(),
        manager,
        fake.job,
        [{"lemma_id": 1}, {"lemma_id": 99}],
        _MODEL,
        dry_run=True,
    )
    assert report.calls == 1
    assert report.resolved_without_llm == {"answered": 1}
    assert fake.stage_one == {}
    assert batch_client.batches == {}
    assert batch_session.query(BatchQueue).count() == 0


def test_dry_run_does_not_prepare_a_job_whose_prepare_writes(
    manager: BatchQueueManager, batch_client: FakeBatchClient
) -> None:
    fake = FakeJob()
    prepared: List[int] = []

    def prepare(session: Any, state: Dict[str, Any], ctx: StageContext) -> Any:
        prepared.append(state["lemma_id"])
        return LLMCall(prompt="x", schema=_SCHEMA)

    job = Job(
        name="writer",
        stages=(Stage("writer.one", prepare, fake.apply_one),),
        item_key=lambda state: str(state["lemma_id"]),
        prepare_writes=True,
    )
    report = start_batch_run(
        MagicMock(), manager, job, [{"lemma_id": 1}, {"lemma_id": 2}], _MODEL, dry_run=True
    )
    assert prepared == []
    assert report.unprepared == 2
    assert report.calls == 0

    report = start_batch_run(MagicMock(), manager, job, [{"lemma_id": 1}], _MODEL)
    assert prepared == [1]
    assert report.calls == 1


def test_submit_failure_cancels_the_chunk(
    manager: BatchQueueManager, batch_client: FakeBatchClient, batch_session: Session
) -> None:
    fake = FakeJob()
    batch_client.fail_next_submit = True
    with pytest.raises(RuntimeError, match="upload refused"):
        start_batch_run(MagicMock(), manager, fake.job, [{"lemma_id": 1}], _MODEL)
    rows = batch_session.query(BatchQueue).all()
    assert [row.status for row in rows] == [BatchRequestStatus.CANCELLED.value]
    # A cancelled item is not open: a rerun picks it up.
    report = start_batch_run(MagicMock(), manager, fake.job, [{"lemma_id": 1}], _MODEL)
    assert report.calls == 1


def test_bad_answer_fails_only_its_row(
    manager: BatchQueueManager, batch_client: FakeBatchClient
) -> None:
    fake = FakeJob()
    start_batch_run(MagicMock(), manager, fake.job, [{"lemma_id": 1}, {"lemma_id": 2}], _MODEL)
    result = _complete(
        fake, manager, batch_client, "batch-0", lambda p: "bad" if p == "one:2" else _word(p)
    )
    assert result["failed"] == 1
    assert result["carried"] == 1
    assert batch_client.prompts("batch-1") == ["two:w1"]
    failed = [
        request_extra(row)
        for row in manager.get_completed_requests(batch_id="batch-0")
        if request_extra(row).get("outcome") == "failed"
    ]
    assert len(failed) == 1 and "bad answer" in failed[0]["detail"]


def test_batch_request_body_matches_the_live_builder(
    manager: BatchQueueManager, batch_client: FakeBatchClient
) -> None:
    from clients.openai.client import build_responses_request

    fake = FakeJob()
    start_batch_run(MagicMock(), manager, fake.job, [{"lemma_id": 5}], _MODEL)
    sent = batch_client.batches["batch-0"][0]["body"]
    assert sent == build_responses_request(_MODEL, "one:5", json_schema=_SCHEMA)
