# Validation

This document describes the tested scope of version 0.3.0. It is not a guarantee that every legacy website or business workflow will work.

## Verified environment

The full native browser regression passed on October 28, 2026 with:

- Windows with an unlocked interactive desktop and Microsoft Edge IE mode.
- Python 3.12.7, Selenium 4.51.0 and MCP Python SDK 1.30.0.
- Selenium Manager-resolved IEDriver win32 4.14.0.
- Local test pages in IE11 and IE7 document modes.

## Checks

| Check | Result | Scope |
| --- | --- | --- |
| Unit tests | 139 passed | Existing browser behavior plus ownership, PID reuse, cross-process mutex, pagination arguments, installation protection and transport retry prevention |
| MCP stdio smoke test | Passed; 32 tools discovered | Initialization, status, ownership registry, diagnostics, schemas and error responses |
| Real browser fixture | Passed on October 28, 2026 | Separate local IE11/IE7 session, without accessing production data |
| Focused page exploration | Passed in IE11 and IE7 | More than 200 controls, long text, regional pagination, search references and element screenshots |
| Real orphan driver cleanup | Passed | Live owner refused; owner exited abnormally; dry run preserved driver; execution stopped the verified driver and removed its record |
| Isolated Codex registration | Passed | Install, repeat install without changes, verified uninstall in a separate configuration directory |
| Isolated wheel installation | Passed | Three console entry points, doctor and MCP stdio check through uv tool installation |
| Source distribution and wheel | Built successfully | Python package and console entry points |

The native fixture covers Chinese text input, batch filling, dropdowns, query results, table extraction, nested frame navigation, prompt preservation, new windows, opener cookie continuity, legacy tabs, autocomplete options and custom row attributes. File selection succeeds in IE11; other document modes are rejected before native selection because an IE7 attempt timed out.

The October 28 extension also verified native double-click, right-click, hover, Enter key events, asynchronous DOM readiness, text disappearance, and scrolling in both IE11 and IE7. Window resizing, history back/forward and same-origin descendant-frame readiness passed in IE11. The fixture completed successfully; its 60-second diagnostic timer emitted a stack dump during the longer full run, not a failing test assertion.

The unit suite covers stability reset on DOM changes, timeout results, preservation of prompts, ineligible targets, modifier validation, stale references after interactions, no automatic click retry, and distinction between a closed current window and an unreachable session. It verifies reporting of skipped frames through mocked probes; the native fixture did not exercise a cross-origin frame.

Version 0.3.0 additionally tested a real Windows subprocess holding the desktop mutex: another process was refused, and acquisition succeeded after the holder was killed. Process cleanup tests cover PID reuse, unknown/live owners, dry runs and unconfirmed termination. The native cleanup fixture starts an IEDriver without Edge, exits its owner with `os._exit`, then verifies the driver's identity and termination using the registry tools. No real user windows are selected for cleanup.

An initial native run timed out during file selection. Its teardown exposed urllib3 retries on the quit request. Established sessions now disable those transport retries and use a five-second quit request timeout; a local HTTP server test verifies a disconnected DELETE is sent only once. An early large-page read also exceeded the former 15-second script limit; the script limit is now 30 seconds, within the 45-second transport timeout. A fresh full IE11/IE7 run passed afterward, including file selection, followed by a focused exploration regression for whitespace pagination and hidden select text. These are observed successful runs, not a claim that native file dialogs or arbitrary large sites never time out.

The isolated installer test uses a separate Codex configuration directory and does not overwrite the user's active MCP settings. The wheel installation test uses separate uv tool directories. `ie-mode-setup check` verifies this installation's stdio endpoint without launching a browser; it cannot prove that a running desktop client has reloaded its configuration.

## Compatibility findings

- IE `innerText` can expose hidden or script content. Snapshots instead traverse visible text nodes and omit password and hidden input values. This is not comprehensive redaction: visible page text can still contain private information.
- IE7 does not support all selectors or JavaScript used by modern WebDriver helpers. DOM traversal and legacy-compatible visibility checks are used where needed.
- Some old handlers expect attributes such as `row._id` to behave as JavaScript properties. `browser_prepare_legacy_row` explicitly bridges existing attributes on visible table rows without changing their values or submitting anything.
- Native clicks can miss at nonstandard browser zoom. Explicit `mode="dom"` is available for diagnosed failures, but is not equivalent to a full native event sequence and is never used as an automatic retry.
- Some autocomplete widgets require native selection. Filling their text alone does not establish the associated business identifier.
- `window.open` preserved the originating session in tested legacy pages where WebDriver's new-window command did not. This does not guarantee cookie isolation between separate browser sessions.
- Popup names use ASCII identifiers with underscores to avoid IE7's invalid-name error.
- Native HTML modal dialogs may not appear in WebDriver's window list. Opening an inspected URL in an ordinary window works only for independently loadable pages; dialog arguments, return values and parent callbacks are not emulated.
- A page may close its own window after saving. Window enumeration then returns the remaining handles and `current: null`, allowing explicit recovery without repeating the save.
- URL spelling can affect old applications, including doubled slashes and path case. Navigation preserves the supplied address rather than normalizing it.
- Windows desktop lock detection prevents startup when the session is confirmed locked. An unknown desktop state is reported as unknown, not treated as proof of readiness.
- Readiness checks are bounded observations of document loading and DOM markup stability, not proof that a workflow finished. Inaccessible frames are reported rather than assumed ready. Text disappearance is limited to the snapshot's current frame and text bounds.
- Session status does not recreate a disconnected browser, accept a prompt, or retry a submission. Version 0.3.0 adds cooperative desktop locking and explicit identity-checked orphan driver cleanup. No Edge process-tree cleanup, session takeover or account isolation is implemented.

## Known limits

- Windows only for browser operation. The browser must have a usable interactive desktop.
- No takeover of existing tabs, ActiveX internals, UKey control, native OS dialogs or general Chromium/IE mixed routing.
- No arbitrary script execution tool or general filesystem-reading tool is exposed through MCP.
- A successful click, alert or preview is not proof of a persisted record or completed workflow. Read a fresh page or query the saved record to verify business outcomes.
- Real-site server errors, missing records and broken page scripts are not fixed by these tools. Hidden text extracted by separate diagnostics is not proof that the normal UI can display it.
- External-site observations informed the compatibility work, but accounts, session captures, business records and site-specific helper scripts are excluded from this repository.

## Reproduce

```powershell
uv sync --locked --extra dev
uv run pytest
uv run python tests/smoke_mcp.py
uv run python tests/smoke_ie.py
uv run python tests/smoke_explore.py
uv run python tests/smoke_sessions.py 'C:\tools\IEDriverServer.exe'
uv build
```

The native fixture opens and closes its own browser session. Run it on an unlocked Windows desktop configured for IEDriver. Tests must not be pointed at a real business site to reproduce the local fixture results.
