import json
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.config import Config
from app.db import Base
from app.models import (
    SearchConfiguration,
    SearchExecution,
    SearchStatus,
    TmAgent,
    TmJob,
    TmJobStatus,
    utcnow,
)
from app.services import tm_service


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    try:
        yield session
    finally:
        session.close()


def test_snap_radius_km():
    # 5 miles = ~8 km -> closest standard option is 10 or 5
    km, label = tm_service.snap_radius_km(3, is_miles=True)
    assert km == 5
    assert label == "5 kilometers"

    km, label = tm_service.snap_radius_km(1, is_miles=False)
    assert km == 1
    assert label == "1 kilometer"

    km, label = tm_service.snap_radius_km(50, is_miles=True)
    assert km == 80
    assert label == "80 kilometers"

    km, label = tm_service.snap_radius_km(0)
    assert km == 5
    assert label == "5 kilometers"


def test_enqueue_and_claim_job(db_session):
    search = SearchConfiguration(
        name="Narayanganj Test Search",
        search_terms="toyota corolla",
        location="Narayanganj",
        radius_miles=5,
        min_price=2000,
        max_price=8000,
        status=SearchStatus.ACTIVE,
        created_at=utcnow(),
        updated_at=utcnow(),
    )
    db_session.add(search)
    db_session.commit()

    # Enqueue job
    job = tm_service.enqueue_job(db_session, search.id, trigger="manual")
    assert job is not None
    assert job.status == TmJobStatus.PENDING
    assert search.is_running is True

    # Claim job
    agent_id = "test_agent_001"
    claim_data = tm_service.claim_next_job(db_session, agent_id)
    assert claim_data is not None
    assert claim_data["job_id"] == job.id
    assert claim_data["search_terms"] == "toyota corolla"
    assert claim_data["location"] == "Narayanganj"
    assert claim_data["radius_label"] == "10 kilometers" or "kilometers" in claim_data["radius_label"]

    # Verify agent updated
    agent = db_session.query(TmAgent).filter_by(agent_id=agent_id).first()
    assert agent is not None
    assert agent.status == "busy"
    assert agent.current_job_id == job.id


def test_ingest_job_results(db_session):
    cfg = Config()
    search = SearchConfiguration(
        name="Ingestion Test",
        search_terms="Civic",
        min_price=500,
        max_price=5000,
        status=SearchStatus.ACTIVE,
        created_at=utcnow(),
        updated_at=utcnow(),
    )
    db_session.add(search)
    db_session.commit()

    job = tm_service.enqueue_job(db_session, search.id)

    mock_scraped_data = {
        "url": "https://www.facebook.com/marketplace/search/?query=Civic",
        "listings": [
            {
                "fb_item_id": "1122334455",
                "url": "https://www.facebook.com/marketplace/item/1122334455/",
                "title": "2010 Honda Civic LX",
                "price_text": "$2,500",
                "location": "Narayanganj",
            },
            {
                "fb_item_id": "9988776655",
                "url": "https://www.facebook.com/marketplace/item/9988776655/",
                "title": "2020 Expensive Supercar",
                "price_text": "$85,000",
                "location": "Narayanganj",
            },
        ],
    }

    summary = tm_service.ingest_job_results(db_session, cfg, job.id, mock_scraped_data)

    assert summary["found_count"] == 2
    assert summary["matched_count"] == 1  # only $2,500 Civic matches $500-$5000 range
    assert summary["new_count"] == 1

    # Verify job completed
    assert job.status == TmJobStatus.DONE
    assert search.is_running is False


def test_heartbeat_and_pause(db_session):
    agent_id = "test_browser_agent"
    hb_data = {"fb_user": "John Doe", "current_url": "https://www.facebook.com/marketplace/"}

    res = tm_service.record_heartbeat(db_session, agent_id, hb_data)
    assert res["status"] == "ok"
    assert res["paused"] is False

    agent = db_session.query(TmAgent).filter_by(agent_id=agent_id).first()
    assert agent is not None
    assert agent.fb_user == "John Doe"
