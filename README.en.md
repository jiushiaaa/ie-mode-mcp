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

Currently provides **32 MCP tools**. See [VALIDATION.md](VALIDATION.md) for tested environments and real browser coverage.

## Installation

Requires Windows, Python 3.11+, Microsoft Edge with IE mode available, and an unlocked interactive desktop. The commands below require [uv](https://docs.astral.sh/uv/getting-started/installation/) and Git.

### Users: isolated installation

No manual clone or test dependencies are needed:

```powershell
uv tool install --python 3.12 git+https://github.com/jiushiaaa/ie-mode-mcp.git
uv tool update-shell
```

Open a new terminal, then run:

```powershell
ie-mode-setup doctor
ie-mode-setup install
ie-mode-setup check
```

`install` uses the installed Codex CLI to register the user-level `ie-mode` server and verify its absolute paths. Repeating the same registration makes no changes. A different existing configuration is refused unless you explicitly use `ie-mode-setup install --replace`, which backs up the previous registration before replacing it. Other MCP entries, IE mode settings and Windows security policies are not modified.

`check` launches this installation's MCP server and verifies the stdio handshake and tool discovery. It does not launch a browser or prove that the client reloaded. Verify actual IE mode with `ie-mode-probe 'https://your-legacy-site.example/'`. For other MCP clients, run `ie-mode-setup config` or `ie-mode-setup config --format toml` and copy the generated configuration.

Upgrade with `uv tool upgrade ie-mode-mcp`, then rerun `ie-mode-setup install` and `ie-mode-setup check` and reload your client. `ie-mode-setup uninstall` removes only this tool's Codex registration; `uv tool uninstall ie-mode-mcp` removes the isolated package installation.

You can give an agent with local terminal access this instruction:

> Follow the README at https://github.com/jiushiaaa/ie-mode-mcp to install the Windows local MCP server. Check uv, Git and the Codex CLI, perform the isolated installation, then run doctor, install and check and verify the output. If a different ie-mode configuration exists, show the differences before replacing it. Explain how to reload the client and verify IE mode using a URL I provide.

### Developers: install from source

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
| Environment and session | `environment_check`, `browser_start`, `browser_status`, `browser_close`, `browser_sessions`, `browser_cleanup_session` |
| Navigation and windows | `browser_navigate`, `browser_open_page`, `browser_windows`, `browser_switch_window`, `browser_close_window`, `browser_history`, `browser_resize` |
| Reading and waiting | `browser_snapshot`, `browser_find`, `browser_element_screenshot`, `browser_screenshot`, `browser_read_table`, `browser_inspect_element`, `browser_wait_text`, `browser_wait_ready` |
| Forms and interaction | `browser_click`, `browser_fill`, `browser_fill_many`, `browser_select`, `browser_choose_file`, `browser_press_key`, `browser_hover`, `browser_scroll` |
| Frames and compatibility | `browser_frame`, `browser_alert`, `browser_prepare_legacy_row` |

Legacy websites may use menu images without alternative text. Use `browser_screenshot` and the controls' `bounds` in the snapshot to identify the corresponding element references. Screenshots may contain business information.

### Large pages and regional exploration

- `browser_snapshot(offset=0, limit=50, text_offset=0, text_limit=12000)` paginates visible controls and text separately. Returns `total_controls`, `next_offset` and `next_text_offset`; a null continuation means that range has ended. Each page supports up to 200 controls and 32,000 characters, with control offsets up to 100,000 and text offsets up to 1,000,000. Prefer smaller `limit` values for large pages.
- `browser_find(query="Form title", by="text")` searches visible elements in the current frame, including ordinary containers. Text matching covers an element's own text nodes and aria-label/title/alt, up to 1,000 characters; it excludes input values and does not concatenate all descendant text. `by="id"`, `"name"` and `"tag"` match exactly. Supports `offset`/`limit` pagination and returns fresh references.
- Use `browser_snapshot(root_ref="returned reference", limit=20)` to read only a region. For its next page, use the newly returned `scope_ref`; previous references have expired. Pages are live DOM observations, so changes between reads may cause duplicates or omissions. This is not a frozen data export.
- `browser_element_screenshot(ref)` captures a visible element and may scroll it into view, invalidating old references. Unsupported drivers report an error without fallback. Screenshots may expose page information. No arbitrary JavaScript execution tool was added.

### Multiple processes and orphaned drivers

This version uses a named mutex to coordinate browser operations, including reads and input, within one Windows login session. A busy desktop returns an immediate error instead of queuing a business action. The lock spans one tool operation and Windows releases it if its owning thread/process exits. It does not prevent manual interaction, coordinate older versions or other automation programs, or isolate account cookies.

If another operation owns the desktop during server exit, closing can also be refused; use the orphan workflow afterward. A crash between driver launch and ownership registration can still leave an untracked driver. The tool does not guess its ownership or terminate it.

`browser_sessions()` reads this user's ownership records, classifying them as `active`, `orphaned_driver`, `finished`, `unknown` or `invalid`. Records live in `%LOCALAPPDATA%/ie-mode-mcp/sessions` and contain only session identifiers, owner/driver PIDs, process creation times and executable paths. Match `browser_status()`'s `managed_session_id` to identify the current server's record.

Preview with `browser_cleanup_session(session_id)`; explicitly execute with `dry_run=false`. Only after confirming the owner exited can cleanup remove the record or terminate the identity-matched IEDriver. Identity verification and termination use the same Windows process handle to avoid PID reuse races. Alive, inaccessible or unknown owners are refused. It never kills Edge, takes over sessions, cleans unregistered old drivers, or repeats submissions. Close remaining Edge windows manually. Records support local cooperation; they are not a security boundary against tampering by the same OS user.

### Page readiness, input, and session checks

- `browser_wait_ready(seconds=10, stable_seconds=1, include_frames=true)` checks loading in the current document and accessible descendant frames, then waits for stable DOM markup. It returns `ready`, `timed_out`, document counts, and inaccessible frame counts. It does not switch frames or accept dialogs. This does not guarantee business completion or the absence of future AJAX requests; wait for specific result text when needed.
- `browser_wait_text(text, gone=true)` waits for text to disappear from the current snapshot. Its scope and text-length limits apply; absence here is not proof that the text is absent from the whole website.
- `browser_click(ref, action="double")` double-clicks; `action="right"` right-clicks. Both require native mode and never retry automatically. Existing ordinary click calls remain compatible.
- `browser_press_key(ref, key="ENTER")` sends a key to the specified control. It also supports `TAB`, `ESCAPE`, arrows, deletion and page-navigation keys, or a single printable character. Combine `modifiers=["CONTROL"]` with `key="a"` for a chord. Targets must be visible and enabled; file inputs are excluded. Keys may submit forms, so verify the outcome.
- `browser_hover(ref)` moves the native pointer to reveal a hover menu without clicking. Take a fresh snapshot for the revealed menu references.
- `browser_scroll(direction="down", pixels=600)` scrolls the current document; `up`, `left`, `right`, `top`, and `bottom` are also supported. Use `direction="into_view", ref=...` to bring a control into view. Scroll events may load content; refresh the snapshot afterward.
- `browser_history(direction="back")` / `direction="forward"` navigates once. A timeout retains the session without retrying. History navigation may trigger form-resubmission prompts.
- `browser_resize(width=1100, height=850)` resizes the window and returns its actual dimensions, without changing zoom.
- `browser_status()` distinguishes not started, reachable, closed current window, pending dialog, and unreachable connection states. It never restarts, changes frames, or repeats business actions. `unreachable` does not prove that the browser process exited.

Pointer, keyboard, scrolling, history, resize, and wait operations invalidate old element references. Keyboard, pointer, and window operations may take desktop focus. Healthy session status queries preserve references. This project retains local Windows execution; it does not provide native macOS IE or a remote Windows worker.

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
- Snapshots default to 200 visible controls and 12,000 characters per page, with pagination and regional reads available; the table tool still returns at most 200 rows. Enter iframes explicitly. The top-level URL/title does not identify the frame URL.
- Page content is untrusted data, not user instructions. The server does not implement business approvals; callers must establish user intent and verify outcomes.
- ActiveX internals, UKey devices, native OS dialogs, arbitrary existing-tab takeover, and mixed Chromium/IE window routing are unsupported.
- Controlled windows are not guaranteed to have cookies isolated from existing windows. Do not rely on this project for multi-account isolation.
- Normal exit closes the owned WebDriver session. The quit request has a five-second timeout; stopping the driver afterward may take additional time. HTTP requests after session creation disable transport retries to avoid repeating timed-out requests. Forced termination may leave drivers or windows; use the ownership rules above. Unsaved business state is not guaranteed recoverable.

## Tests

```powershell
uv run pytest
uv run python tests/smoke_mcp.py
uv run python tests/smoke_ie.py
uv run python tests/smoke_explore.py
uv run python tests/smoke_sessions.py 'C:\tools\IEDriverServer.exe'
```

`smoke_ie` and `smoke_explore` start local HTTP fixtures and real Edge IE mode windows. `smoke_sessions` starts only the specified IEDriver to verify ownership and cleanup after its owner crashes. Browser tests require a Windows graphical desktop and a working IEDriver environment.

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
  server.py           32 serialized MCP tools and the stdio entry point
  page_scripts.py     Read-only readiness probing compatible with legacy IE
  probe.py            Interactive diagnostic command
  explore_scripts.py  Legacy-compatible visible element search
  session_registry.py Process coordination, identity and orphan driver cleanup
  setup.py            Registration, configuration and stdio connectivity checks
  windows_session.py  Windows desktop status checks
tests/
  fixtures/           Local test pages independent of real business websites
  test_*.py           Unit tests
  smoke_mcp.py        MCP stdio protocol test
  smoke_ie.py         Real IE11/IE7 browser regression
```

Reproducible [issues](https://github.com/jiushiaaa/ie-mode-mcp/issues) and pull requests are welcome. Include Windows, Edge, IEDriver, and Python versions, plus the page's `document_mode`. Prefer a minimal HTML example with sensitive information removed. When changing browser behavior, add a regression test and run the browser fixture on an available Windows desktop.

Page readiness and extended interactions were inspired by the feature design of [thomfilg/ie-mcp](https://github.com/thomfilg/ie-mcp), and independently implemented using this project's temporary element references, result verification, and no-automatic-retry rules.

## License

Licensed under the [MIT License](LICENSE). Dependencies currently target MCP Python SDK 1.x; `uv.lock` pins the resolved dependency versions.

See [VALIDATION.md](VALIDATION.md) for verified environments and limitations.
