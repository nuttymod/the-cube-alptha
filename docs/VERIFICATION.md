# Verification

Local checks on November 18, 2026:

- Eight package/connection tests passed, including corruption rejection,
  modified-code rejection, path traversal rejection and settings preservation.
- The actual game ran 12 headless frames with the original official Root
  package set. Root Mode, NuttyMod Root, Client 1.0.2 and Loader 1.4.5 were active.
- The custom title and native CPE optimizer were verified. Physics configuration
  was restored when leaving the simulation.
- Screenshots and `game-verification.json` were produced by the real game.
- The Go cache compiled successfully. The Aspire AppHost compiled with zero
  warnings/errors using the cached .NET 8.0.33 reference packs in a temporary
  copy; the normal build restores the SDK's current reference packs online.

The local workspace denies network listeners, including loopback sockets.
Live Node/Go HTTP tests and the complete Aspire connection therefore require
the Windows/Linux GitHub Actions jobs. Consult the workflow status and artifacts
for their actual results; the local game smoke test does not prove connectivity.

The first-run runtime downloader requires access to official distribution sites.
The automatic runtime download paths and macOS launch have not been exercised
locally. The test environment already had Node.js, Go, .NET and Python available.
