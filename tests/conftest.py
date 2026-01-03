"""Pytest configuration and shared fixtures."""

import pytest
from pathlib import Path
from datetime import datetime
from typing import List
from unittest.mock import Mock

from columbo.schemas import (
    DebugSession,
    ProbeResult,
    ProbeCall,
    Hypothesis,
    ConfidenceLevel,
)


@pytest.fixture
def sample_probe_result():
    """Create a sample ProbeResult for testing."""
    return ProbeResult(
        probe_name="test_probe",
        success=True,
        data={"status": "healthy", "container": "test-container"}
    )


@pytest.fixture
def sample_hypothesis():
    """Create a sample Hypothesis for testing."""
    return Hypothesis(
        id="hyp_001",
        statement="Container is failing due to environment misconfiguration",
        confidence=ConfidenceLevel.medium,
        rationale="Environment variables are not set correctly"
    )


@pytest.fixture
def sample_debug_session(sample_probe_result, sample_hypothesis):
    """Create a sample DebugSession for testing."""
    return DebugSession(
        session_id="test_session_001",
        initial_problem="Container fails to start",
        probe_history=[ProbeCall(step=1, probe_name="test_probe", result=sample_probe_result.model_dump())],
        active_hypotheses=[sample_hypothesis]
    )


@pytest.fixture
def mock_docker_container():
    """Create a mock Docker container for testing probes."""
    container = Mock()
    container.name = "test-container"
    container.id = "abc123def456"
    container.status = "running"
    container.logs = Mock(return_value=b"Sample log output\nLine 2\nLine 3")
    container.attrs = {
        "State": {"Status": "running", "Running": True},
        "Config": {"Env": ["KEY1=value1", "KEY2=value2"]},
        "NetworkSettings": {"Networks": {}}
    }
    return container


@pytest.fixture
def mock_docker_client(mock_docker_container):
    """Create a mock Docker client for testing."""
    client = Mock()
    client.containers.list = Mock(return_value=[mock_docker_container])
    client.containers.get = Mock(return_value=mock_docker_container)
    return client


@pytest.fixture
def temp_session_dir(tmp_path):
    """Create a temporary directory for session storage."""
    session_dir = tmp_path / "test_sessions"
    session_dir.mkdir()
    return session_dir
