"""Quick test to verify probe schemas and dependencies are working."""

from debugging_assistant.probes import PROBE_SCHEMAS, PROBE_DEPENDENCIES, probe_registry
from debugging_assistant.modules import PROBE_DOCUMENTATION


def test_schemas():
    """Verify all probes have schemas defined."""
    print("Testing probe schemas...\n")
    
    for probe_name in probe_registry.keys():
        if probe_name in PROBE_SCHEMAS:
            schema = PROBE_SCHEMAS[probe_name]
            print(f"✓ {probe_name}")
            print(f"  Description: {schema['description']}")
            print(f"  Example args: {schema['example']}")
        else:
            print(f"✗ {probe_name} - MISSING SCHEMA")
    
    print(f"\nTotal probes: {len(probe_registry)}")
    print(f"Probes with schemas: {len(PROBE_SCHEMAS)}")


def test_dependencies():
    """Verify dependency configuration."""
    print("\n" + "="*60)
    print("Testing probe dependencies...\n")
    
    for probe_name, dep_config in PROBE_DEPENDENCIES.items():
        print(f"✓ {probe_name}")
        print(f"  Requires: {dep_config['requires']}")
        print(f"  Description: {dep_config['description']}")


def test_documentation():
    """Print the full documentation that the LLM sees."""
    print("\n" + "="*60)
    print("LLM Probe Documentation:\n")
    print(PROBE_DOCUMENTATION)


if __name__ == "__main__":
    test_schemas()
    test_dependencies()
    test_documentation()
