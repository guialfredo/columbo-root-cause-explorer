The app expects a new schema/config format, but a named volume still contains an old version (or corrupted data). Rebuilding the image does nothing. Only fixing/clearing/migrating the volume resolves it.

What the agent needs to conclude :
- Root cause : persistent named volume contains incompatible data
- Fix : docker compose down -v (or remove specific volume), or implement a migration path
- Proof : container uses the expected config/code, but volume-mounted data is old