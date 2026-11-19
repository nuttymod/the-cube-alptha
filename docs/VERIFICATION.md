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
The [Windows and Linux GitHub Actions run](https://github.com/nuttymod/the-cube-alptha/actions/runs/44435861984)
passed on November 19, 2026 UTC (November 18 in Toronto), covering:

- All package integrity and connection failure tests.
- Real game, Root, Root Mode, Client, Loader, title and optimizer checks.
- First-run Python environment creation and dependency installation.
- Node bridge and Go cache HTTP tests.
- The live Aspire host and a unique Node-to-Go cache round trip.
- Shutdown and release of all five service ports.

The run's artifacts contain the actual game screenshots and connection logs.

The first-run runtime downloader requires access to official distribution sites.
The automatic runtime download paths and macOS launch have not been exercised
locally. The test environment already had Node.js, Go, .NET and Python available.
