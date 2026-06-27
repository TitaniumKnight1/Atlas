import pytest
import httpx
from unittest.mock import MagicMock
from backend.adapters.monitoring.collectors.fivem import FivemPlayerCountCollector
from backend.domain.monitoring import CollectorContext
from datetime import datetime, timezone

from backend.domain.shared_kernel import ProjectId
from pathlib import Path

def test_fivem_collector_graceful_failures():
    context = CollectorContext(
        sampled_at=datetime.now(timezone.utc), 
        process_run_id="run_123",
        project_id=ProjectId("test"),
        project_root=Path("test")
    )
    
    # Test 1: Unreachable / Timeout
    mock_client = MagicMock()
    mock_client.get.side_effect = httpx.RequestError("Timeout")
    collector = FivemPlayerCountCollector(port=30120, http_client=mock_client)
    samples = collector.collect(context)
    
    assert len(samples) == 1
    assert samples[0].metric_name == "player_count"
    assert samples[0].quality == "missing"
    assert samples[0].value_real == 0.0
    
    # Test 2: HTTP Error (e.g., 500 or 404)
    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError("500", request=MagicMock(), response=mock_response)
    mock_client.get.side_effect = None
    mock_client.get.return_value = mock_response
    
    collector = FivemPlayerCountCollector(port=30120, http_client=mock_client)
    samples = collector.collect(context)
    assert samples[0].quality == "missing"
    
    # Test 3: Malformed JSON
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.side_effect = ValueError("Invalid JSON")
    mock_client.get.return_value = mock_response
    
    collector = FivemPlayerCountCollector(port=30120, http_client=mock_client)
    samples = collector.collect(context)
    assert samples[0].quality == "missing"
