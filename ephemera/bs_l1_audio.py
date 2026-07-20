"""Generate Bosnian audio for all level-1 lemmas, both m1 and f1 voices."""

from __future__ import annotations

import json
import sys

from api import generate_audio, list_by_difficulty


def fetch_level1_guids() -> list[str]:
    guids: list[str] = []
    offset = 0
    while True:
        page = list_by_difficulty("1", limit=200, offset=offset)
        rows = page["data"]
        if not rows:
            break
        guids.extend(row["guid"] for row in rows)
        offset += len(rows)
    return guids


def main(voice: str) -> int:
    guids = fetch_level1_guids()
    print(f"[{voice}] {len(guids)} level-1 GUIDs", flush=True)
    resp = generate_audio(
        agent="vieversys",
        guids=guids,
        language="bs",
        voice=voice,
        include_forms=False,
        force=False,
        upload_s3=True,
        auto_approve=False,
        timeout=1800,
    )
    data = resp["data"]
    print(
        f"[{voice}] generated={data['generated']} "
        f"skipped_existing={data['skipped_existing']} failed={data['failed']} "
        f"cost_usd={data['tts_cost_usd']:.4f}",
        flush=True,
    )
    if data["failed"]:
        for guid, result in data["by_guid"].items():
            if result.get("status") != "ok":
                print(f"[{voice}] FAIL {guid}: {result}", flush=True)
    return 0 if data["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
