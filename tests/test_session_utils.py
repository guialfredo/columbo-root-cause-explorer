"""Tests for session management utilities.

These tests verify that debug sessions can be:
- Saved to JSON files correctly
- Loaded from JSON files with proper deserialization
"""

import pytest
import json
from pathlib import Path
from columbo.session_utils import (
    save_session_to_file,
    load_session_from_file,
)
from columbo.schemas import (
    DebugSession,
)


class TestSessionSerialization:
    """Test saving and loading debug sessions."""
    
    def test_save_session_creates_file(self, sample_debug_session, temp_session_dir):
        """Test that save_session_to_file creates a JSON file."""
        output_path = save_session_to_file(
            sample_debug_session,
            output_dir=str(temp_session_dir)
        )
        
        assert output_path.exists()
        assert output_path.suffix == ".json"
        assert sample_debug_session.session_id in output_path.name
    
    def test_saved_session_is_valid_json(self, sample_debug_session, temp_session_dir):
        """Test that saved session contains valid JSON."""
        output_path = save_session_to_file(
            sample_debug_session,
            output_dir=str(temp_session_dir)
        )
        
        with open(output_path, 'r') as f:
            data = json.load(f)
        
        assert data["session_id"] == sample_debug_session.session_id
        assert data["initial_problem"] == sample_debug_session.initial_problem
        assert "probe_history" in data
        assert "active_hypotheses" in data
    
    def test_load_session_from_file(self, sample_debug_session, temp_session_dir):
        """Test that sessions can be loaded back from JSON."""
        output_path = save_session_to_file(
            sample_debug_session,
            output_dir=str(temp_session_dir)
        )
        
        loaded_session = load_session_from_file(str(output_path))
        
        assert isinstance(loaded_session, DebugSession)
        assert loaded_session.session_id == sample_debug_session.session_id
        assert loaded_session.initial_problem == sample_debug_session.initial_problem
        assert len(loaded_session.probe_history) == len(sample_debug_session.probe_history)
        assert len(loaded_session.active_hypotheses) == len(sample_debug_session.active_hypotheses)
    
    def test_roundtrip_preserves_data(self, temp_session_dir):
        """Test that save->load roundtrip preserves probe results."""
        from columbo.schemas import ProbeCall
        
        original_session = DebugSession(
            session_id="roundtrip_test",
            initial_problem="Container fails to start",
            probe_history=[
                ProbeCall(step=1, probe_name="container_logs", result={"logs": "test"}),
                ProbeCall(step=2, probe_name="container_env", result={"env": {}}),
            ]
        )
        
        # Save and load
        path = save_session_to_file(original_session, output_dir=str(temp_session_dir))
        loaded_session = load_session_from_file(str(path))
        
        # Verify data integrity
        assert loaded_session.session_id == original_session.session_id
        assert len(loaded_session.probe_history) == 2
        assert loaded_session.probe_history[0].probe_name == "container_logs"
        assert loaded_session.probe_history[1].probe_name == "container_env"


class TestSessionUtilsEdgeCases:
    """Test edge cases and error handling."""
    
    def test_load_nonexistent_file_raises_error(self):
        """Test that loading non-existent file raises appropriate error."""
        with pytest.raises(FileNotFoundError):
            load_session_from_file("/nonexistent/path/session.json")
    
    def test_save_to_nonexistent_directory_creates_it(self, tmp_path):
        """Test that saving to non-existent directory creates it."""
        nested_dir = tmp_path / "level1" / "level2"
        
        session = DebugSession(
            session_id="test_mkdir",
            initial_problem="Test"
        )
        
        # Should not raise error and should create directories
        output_path = save_session_to_file(session, output_dir=str(nested_dir))
        assert output_path.exists()
        assert nested_dir.exists()
    
    def test_session_with_no_probes_serializes(self, temp_session_dir):
        """Test that minimal session (no probes) can be saved/loaded."""
        minimal_session = DebugSession(
            session_id="minimal",
            initial_problem="Just starting investigation"
        )
        
        path = save_session_to_file(minimal_session, output_dir=str(temp_session_dir))
        loaded = load_session_from_file(str(path))
        
        assert loaded.session_id == "minimal"
        assert len(loaded.probe_history) == 0
        assert len(loaded.active_hypotheses) == 0
