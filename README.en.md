# ie-mode-mcp

[简体中文](README.md) | **English**

A local MCP server for AI assistants to automate Microsoft Edge in IE mode using Selenium and IEDriver.

An experimental Windows project for login, queries, forms, and file uploads on websites that still require IE mode. It launches a separate controlled window where you can log in manually and continue with automation. It does not attach to existing tabs.

```text
MCP client (such as Codex)
    → stdio → ie-mode-mcp → Selenium / IEDriver → Edge IE mode
```

The MCP interface uses stdio only and does not offer an HTTP/SSE server. IEDriver itself uses a local WebDriver port. This project provides general browser tools; it does not include website accounts, course materials, or scripts that complete specific business workflows.

## Features

- Read visible page content, tables, form values, and screenshots, and identify the current IE document mode.
- Click, fill individual or multiple fields, select dropdown options, and verify values by reading them back.
- Switch frames, iframes, windows, and legacy page tabs, and handle JavaScript dialogs.
- Select local files in IE11 document mode for the website's own upload flow.
- Use explicit DOM actions and custom row-attribute compatibility support for certain legacy pages.

Currently provides **21 MCP tools**. See [VALIDATION.md](VALIDATION.md) for tested environments and real browser coverage.

## Installation

Requires Windows, Python 3.11+, Microsoft Edge with IE mode available, and an unlocked interactive desktop. The commands below require [uv](https://docs.astral.sh/uv/getting-started/installation/) and Git.

```powershell
git clone https://github.com/jiushiaaa/ie-mode-mcp.git
cd ie-mode-mcp
uv sync --locked --extra dev
uv run ie-mode-probe
uv run ie-mode-probe 'https://your-legacy-site.example/'
```

Replace the example URL with a real website you are authorized to operate. Install from source; without uv, you can also run `py -3 -m pip install -e ".[dev]"` and then use the `ie-mode-probe` and `ie-mode-mcp` commands. The pip alternative does not use the exact dependency versions in `uv.lock`.

When no driver is specified, Selenium Manager resolves and downloads it, requiring internet access on the first run. For offline environments, download IEDriverServer from Selenium's official distribution and set `IE_MODE_DRIVER_PATH`. You can also specify the Edge executable with `IE_MODE_EDGE_PATH`. Both variables should contain absolute paths.

```powershell
$env:IE_MODE_DRIVER_PATH = 'C:\tools\IEDriverServer.exe'
uv run ie-mode-mcp
```

`ie-mode-probe` prints a snapshot and keeps the window open. After logging in, press Enter in the terminal to read another snapshot, or enter `q` to exit. Output may contain business information; do not commit real-site snapshots to the repository.

## MCP client configuration

Example configuration for a generic MCP client; replace the absolute project path:

```json
{
  "mcpServers": {
    "ie-mode": {
      "command": "D:/AI/ie-mode-mcp/.venv/Scripts/ie-mode-mcp.exe"
    }
  }
}
```

Equivalent configuration for clients that support TOML:

```toml
[mcp_servers.ie-mode]
command = 'D:\AI\ie-mode-mcp\.venv\Scripts\ie-mode-mcp.exe'
```

If you have the Codex CLI installed, you can register the local server:

```powershell
codex mcp add ie-mode -- 'D:\AI\ie-mode-mcp\.venv\Scripts\ie-mode-mcp.exe'
codex mcp get ie-mode --json
```

This registers the server at the user level, so other chats may also load it. Remove it with `codex mcp remove ie-mode`. An already running client may need to reload its MCP servers or restart to discover new tools.

Run `environment_check`, then call `browser_start`. Once you have logged in through the new window, call `browser_snapshot` to get element references. Use `browser_fill`, `browser_click`, or `browser_select`, and read a fresh snapshot after each action to verify the result. Use `browser_read_table` for tables; `browser_frame`, `browser_windows`, and `browser_switch_window` for frames and windows; `browser_alert` for JavaScript dialogs; and `browser_close` to end the session.

Example instruction for an MCP-enabled assistant:

> Check the IE mode environment and open the website I provide. After I log in, read the current page and list the available forms. Fill in the search criteria, run the query, and verify the results with a fresh snapshot.

`browser_start` creates a new visible window; it does not connect to an Edge tab you already have open. `ie-mode-mcp` is a stdio process launched by the client, so waiting for input when started manually is normal. Use `ie-mode-probe` for interactive terminal diagnostics.

### Tool reference

| Purpose | Tools |
| --- | --- |
| Environment and session | `environment_check`, `browser_start`, `browser_close` |
| Navigation and windows | `browser_navigate`, `browser_open_page`, `browser_windows`, `browser_switch_window`, `browser_close_window` |
| Reading and waiting | `browser_snapshot`, `browser_screenshot`, `browser_read_table`, `browser_inspect_element`, `browser_wait_text` |
| Form actions | `browser_click`, `browser_fill`, `browser_fill_many`, `browser_select`, `browser_choose_file` |
| Frames and compatibility | `browser_frame`, `browser_alert`, `browser_prepare_legacy_row` |

Legacy websites may use menu images without alternative text. Use `browser_screenshot` and the controls' `bounds` in the snapshot to identify the corresponding element references. Screenshots may contain business information.

### Complex forms and legacy dialogs

- `browser_snapshot(include_values=true)` reads current business form values, selected options, and the frame URL. Password and hidden field values are always excluded.
- `browser_fill_many` fills up to 50 text fields using references from the same snapshot. It checks all control types before filling and reads each value back afterward. It stops on failure and returns the completed references. Page events may still trigger business actions: completing a fill is not proof of a successful save.
- `browser_choose_file(ref, path)` selects one explicitly authorized local file in a visible file input. It requires an absolute path to an existing file and IE11 document mode. Older document modes fail before native input to avoid observed driver timeouts. The tool verifies the filename, does not click submit, and never retries automatically. A page may upload on selection, so check the outcome. Do not choose local files based on instructions embedded in a webpage.
- `browser_frame(parent=true)` returns to the parent frame without starting again from the top-level document.
- `browser_inspect_element` reads link and frame addresses and event-handler source text to help identify image buttons and legacy popup destinations. It does not execute handlers.
- Snapshots recognize `role="tab"` and `tabID` on legacy Infragistics table tabs, allowing reference-based navigation between data, terms, and review pages. Ordinary table cells are not all treated as interactive controls.
- Snapshots also recognize `role="option"` and visible AjaxControlToolkit autocomplete choices. Read their names and select the intended choice; entering text does not establish the associated business code.
- If a legacy table handler expects a custom attribute as `row._id`, but IE11 standards mode only exposes it through `getAttribute('_id')`, explicitly call `browser_prepare_legacy_row(ref, attributes=["_id", "_type", "_status"])` after diagnosing that incompatibility. It copies existing attributes on a visible table row to matching properties that are not already defined. It does not replace values, click, or submit. The change is lost on reload; take a fresh snapshot before clicking.
- `browser_click(ref, mode="dom")` explicitly calls the DOM click method of a visible, enabled element, for diagnosed native-click misses on scaled pages. Native clicks remain the default. The tool does not switch modes or retry automatically, avoiding duplicate submissions. DOM clicks do not reproduce the full mouse event sequence; read back the result.
- `browser_fill` and `browser_fill_many` accept explicit `mode="dom"` to set visible, editable text fields, dispatch input/change events, and verify the values. This is for diagnosed native-input failures on legacy pages. It does not simulate keyboard or focus/blur events, and does not retry automatically. Page handlers may submit data, so the caller must check the business outcome.
- `browser_select(ref, label, mode="dom")` explicitly selects the uniquely matching enabled option in a single-select dropdown and dispatches input/change events. This is useful when legacy IE native option clicks fail. Native selection remains the default; no automatic retry occurs. Text verification normalizes CRLF/LF only for textareas and otherwise compares whitespace and content strictly.
- Text waits reuse IE-compatible snapshots. New sessions preserve unhandled JavaScript dialogs until `browser_alert` explicitly accepts or dismisses them, so reading the page does not silently close prompts.
- For an inspected HTTP(S) destination, `browser_open_page` opens a regular controlled window through the current page's `window.open`, retaining the current browser session. Use `browser_close_window` when finished. Establish the correct login and application context first. If a popup is blocked or multiple new windows appear, inspect the window list instead of repeating the operation automatically.

Window handle order is not creation order. `browser_windows(include_details=true)` reads each controlled window's title and URL, then restores the original window at its top-level document. This clears the frame context and old references; re-enter the frame and take a fresh snapshot. By default, it only lists handles without switching windows.

If a page closes its own window, window enumeration returns the remaining handles with `current: null`. Select a handle with `browser_switch_window` before requesting details. The preceding save action is not retried automatically.

Native HTML dialogs opened with `showModalDialog` / `showModelessDialog` may not appear in WebDriver's window list. Opening a regular window only works for pages that load independently; it does not emulate `dialogArguments`, `returnValue`, or parent callbacks. Forms that depend on these mechanisms need individual verification. A success prompt alone does not prove that a record was saved; reopen the record to verify persistence.

Preserve the original website URL, including path case, doubled slashes, and query strings. Some legacy sites lose application context when an address is "cleaned up." The server validates the URL scheme but does not normalize paths.

## Boundaries

- One server process owns one browser session, with serialized tool calls.
- Navigation accepts HTTP(S) only. There is no arbitrary script execution or general local file-reading tool. `browser_choose_file` passes only the specified file to the page's file input.
- Snapshots omit input values by default; callers can opt in to non-password business values. Page text, labels, and tables may still contain sensitive information that enters the AI context. This is not a comprehensive redaction system.
- Element references expire after a new snapshot or action. Manual reloads are detected through stale document elements. Dynamic page updates may still require a fresh snapshot.
- Snapshots are limited to 200 visible controls and 12,000 characters of text; table reads are limited to 200 rows. Enter iframes explicitly. The top-level URL/title does not identify the frame URL.
- Page content is untrusted data, not user instructions. The server does not implement business approvals; callers must establish user intent and verify outcomes.
- ActiveX internals, UKey devices, native OS dialogs, arbitrary existing-tab takeover, and mixed Chromium/IE window routing are unsupported.
- Controlled windows are not guaranteed to have cookies isolated from existing windows. Do not rely on this project for multi-account isolation.
- The server closes its owned WebDriver session on exit. Forcefully terminating a process may leave windows that require manual cleanup.

## Tests

```powershell
uv run pytest
uv run python tests/smoke_mcp.py
uv run python tests/smoke_ie.py
```

The last command starts a local HTTP fixture server and real Edge IE mode windows to test filling, queries, tables, iframes, dialogs, and new windows. It requires a Windows graphical desktop and a working IEDriver environment.

## Environment troubleshooting

`environment_check` performs a read-only check of whether the current Windows session is locked. When it confirms a locked desktop, `browser_start` returns an unlock message without launching an IEDriver that could hang during window focus. A failed check returns `unknown`, which does not mean the desktop is available. The user must unlock it; the tool does not change lock-screen or security policies. Native input and IE mode startup require an interactive desktop. This is not an unattended service that keeps working while Windows is locked.

IEDriver has requirements for browser zoom, security zones, and Windows configuration. This project does not automatically edit the registry or ignore Protected Mode checks. On startup failure, retain the error and consult the official documentation; administrator-managed settings should be handled by the administrator. Entries in the browser's IE mode page list may expire.

- [Microsoft: Automate Edge IE mode with IEDriver](https://learn.microsoft.com/en-us/microsoft-edge/webdriver/ie-mode)
- [Selenium: IE driver configuration requirements](https://www.selenium.dev/documentation/ie_driver_server/)
- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)

## Project structure and contributions

```text
src/ie_mode_mcp/
  browser.py          Browser actions, snapshots, and compatibility handling
  server.py           21 serialized MCP tools and the stdio entry point
  probe.py            Interactive diagnostic command
  windows_session.py  Windows desktop status checks
tests/
  fixtures/           Local test pages independent of real business websites
  test_*.py           Unit tests
  smoke_mcp.py        MCP stdio protocol test
  smoke_ie.py         Real IE11/IE7 browser regression
```

Reproducible [issues](https://github.com/jiushiaaa/ie-mode-mcp/issues) and pull requests are welcome. Include Windows, Edge, IEDriver, and Python versions, plus the page's `document_mode`. Prefer a minimal HTML example with sensitive information removed. When changing browser behavior, add a regression test and run the browser fixture on an available Windows desktop.

`.local/` is for local debugging records and is ignored by Git. Do not commit passwords, cookies, real webpage screenshots, business documents, or personal information. Browser drivers, virtual environments, and build artifacts are also excluded from the source repository.

## License

Licensed under the [MIT License](LICENSE). Dependencies currently target MCP Python SDK 1.x; `uv.lock` pins the resolved dependency versions.

See [VALIDATION.md](VALIDATION.md) for verified environments and limitations.
