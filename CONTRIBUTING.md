# Contributing to Columbo

All contributions are welcome! We appreciate ideas for scenarios, probes, features, issues, and more.

## Getting Started

Before contributing, please:
- Review the design principles in the main [README](../README.md)
- Follow the [GitHub Copilot instructions](../.github/copilot-instructions.md) for architectural guidance

## Contributing Probes

When adding new probes:
- **Probes MUST be deterministic** – same input should always produce the same output
- **Probes MUST NEVER raise exceptions** – handle errors gracefully and include them in returned evidence
- Use the dedicated decorator for tagging and automatic registration

## Contributing Scenarios

When adding new scenarios:
- Refer to existing scenarios in `scenarios/` for structure
- Include at minimum:
  - `manifest.json` – scenario metadata and expected outcome
  - `README.md` – clear description and instructions
- Follow the established directory structure