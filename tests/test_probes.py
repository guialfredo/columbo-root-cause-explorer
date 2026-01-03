"""Tests for probe specifications and registration.

These tests verify that:
- Probes are correctly registered with the @probe decorator
- ProbeSpec models maintain proper metadata
- Probe registry provides expected interfaces
"""

import pytest
from columbo.probes.spec import ProbeSpec, probe, PROBES
from columbo.probes.registry import probe_registry, PROBE_SCHEMAS
from columbo.schemas import ProbeResult


class TestProbeSpec:
    """Test the ProbeSpec data model."""
    
    def test_probe_spec_creation(self):
        """Test creating a ProbeSpec manually."""
        def dummy_probe():
            return {"result": "success"}
        
        spec = ProbeSpec(
            name="test_probe",
            description="A test probe",
            fn=dummy_probe,
            scope="container",
            tags={"test", "diagnostic"},
            args={"container": "Container name"},
            required_args={"container"},
            example='{"container": "test-container"}'
        )
        
        assert spec.name == "test_probe"
        assert spec.scope == "container"
        assert "test" in spec.tags
        assert "container" in spec.required_args
        assert callable(spec.fn)
    
    def test_probe_spec_immutable(self):
        """Test that ProbeSpec is frozen (immutable)."""
        def dummy_probe():
            pass
        
        spec = ProbeSpec(
            name="test_probe",
            description="Test",
            fn=dummy_probe,
            scope="container"
        )
        
        with pytest.raises(Exception):  # Pydantic frozen model raises on modification
            spec.name = "modified"


class TestProbeDecorator:
    """Test the @probe decorator for registration."""
    
    def test_probe_decorator_registers_function(self):
        """Test that @probe decorator registers probes in PROBES dict."""
        # Reset PROBES for this test (if needed in actual implementation)
        initial_count = len(PROBES)
        
        @probe(
            name="test_decorator_probe",
            description="Test probe created via decorator",
            scope="container",
            tags={"test"},
            args={"container": "Container name"},
            required_args={"container"},
            example='{"container": "test"}'
        )
        def test_probe_function(container, probe_name="test_decorator_probe"):
            return ProbeResult(
                probe_name=probe_name,
                success=True,
                data={"container": container}
            )
        
        # Verify probe is registered
        assert "test_decorator_probe" in PROBES
        spec = PROBES["test_decorator_probe"]
        assert spec.name == "test_decorator_probe"
        assert spec.scope == "container"
        assert callable(spec.fn)
        
        # Clean up by removing test probe
        if "test_decorator_probe" in PROBES:
            del PROBES["test_decorator_probe"]
    
    def test_probe_decorator_preserves_function(self):
        """Test that decorated function is still callable."""
        @probe(
            name="test_callable_probe",
            description="Test",
            scope="container"
        )
        def my_probe():
            return ProbeResult(
                probe_name="test_callable_probe",
                success=True,
                data={"test": "value"}
            )
        
        # Function should still be callable
        result = my_probe()
        assert isinstance(result, ProbeResult)
        assert result.success is True
        
        # Clean up
        if "test_callable_probe" in PROBES:
            del PROBES["test_callable_probe"]


class TestProbeRegistry:
    """Test the backward-compatible probe registry."""
    
    def test_probe_registry_exists(self):
        """Test that probe_registry is populated."""
        assert isinstance(probe_registry, dict)
        assert len(probe_registry) > 0
    
    def test_probe_registry_contains_functions(self):
        """Test that probe_registry maps names to callables."""
        # Should have at least the built-in probes
        for name, func in probe_registry.items():
            assert callable(func)
            assert isinstance(name, str)
    
    def test_probe_schemas_structure(self):
        """Test PROBE_SCHEMAS backward compatibility."""
        assert isinstance(PROBE_SCHEMAS, dict)
        
        # Each schema should have expected keys
        for name, schema in PROBE_SCHEMAS.items():
            assert "description" in schema
            assert "args" in schema
            assert "required_args" in schema
            assert "example" in schema
            assert isinstance(schema["description"], str)
            assert isinstance(schema["args"], dict)
            assert isinstance(schema["required_args"], set)
    
    def test_registry_consistency(self):
        """Test that registry and PROBES are consistent."""
        # All probes in probe_registry should exist in PROBES
        for name in probe_registry:
            assert name in PROBES
        
        # All probes in PROBES should exist in probe_registry
        for name in PROBES:
            assert name in probe_registry


class TestBuiltInProbes:
    """Test that expected built-in probes are registered."""
    
    def test_container_probes_registered(self):
        """Test that container probes are registered."""
        expected_probes = [
            "containers_state",
            "container_logs",
            "container_inspect",
        ]
        
        for probe_name in expected_probes:
            assert probe_name in PROBES, f"Expected probe {probe_name} not found"
            assert probe_name in probe_registry
    
    def test_probe_has_required_metadata(self):
        """Test that registered probes have proper metadata."""
        # Pick a known probe to test
        if "containers_state" in PROBES:
            spec = PROBES["containers_state"]
            assert spec.name == "containers_state"
            assert spec.description  # Should have a description
            assert spec.scope in ["container", "volume", "network", "config", "host"]
            assert isinstance(spec.tags, set)
