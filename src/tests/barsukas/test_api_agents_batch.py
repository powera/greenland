from __future__ import annotations

import json

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from storage.models.schema import BarsukasTask, Lemma


def test_add_missing_translations_batch_aggregates_three_requests(client, app) -> None:
    engine = create_engine(f"sqlite:///{app.config['DB_PATH']}")
    session_factory = sessionmaker(bind=engine)
    with session_factory() as session:
        lemma3 = Lemma(
            lemma_text="run",
            definition_text="to move quickly",
            pos_type="verb",
            guid="V01_003",
            verified=True,
        )
        session.add(lemma3)
        session.commit()

    payload = {"model": "gpt-5.4-mini", "language": "fr", "batch": True, "batch_window_minutes": 10}
    response1 = client.post("/api/v1/agents/lemma/V01_001/add-missing-translations", json=payload)
    response2 = client.post("/api/v1/agents/lemma/N01_001/add-missing-translations", json=payload)
    response3 = client.post("/api/v1/agents/lemma/V01_003/add-missing-translations", json=payload)

    assert response1.status_code == 200
    assert response2.status_code == 200
    assert response3.status_code == 200

    with session_factory() as session:
        tasks = (
            session.query(BarsukasTask)
            .filter(
                BarsukasTask.target_type == "batch", BarsukasTask.task_type == "words.translations"
            )
            .all()
        )
        assert len(tasks) == 1
        batch_payload = json.loads(tasks[0].payload or "{}")
        lemma_ids = sorted(batch_payload.get("lemma_ids", []))
        assert len(lemma_ids) == 3
