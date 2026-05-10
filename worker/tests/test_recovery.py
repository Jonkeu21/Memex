from worker.db import insert_queue_row
from worker.recovery import reset_stuck_processing


def test_reset_processing_rows(tmp_db):
    rid = insert_queue_row(tmp_db, source_type="text", source_payload='{"text":"x"}', submitter="api:t")
    tmp_db.execute("UPDATE queue SET status='processing' WHERE id=?", (rid,))
    n = reset_stuck_processing(tmp_db)
    assert n == 1
    row = tmp_db.execute("SELECT status FROM queue WHERE id=?", (rid,)).fetchone()
    assert row["status"] == "queued"


def test_reset_no_processing_rows(tmp_db):
    n = reset_stuck_processing(tmp_db)
    assert n == 0
