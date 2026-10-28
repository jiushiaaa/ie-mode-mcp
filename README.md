# ie-mode-mcp

**简体中文** | [English](README.en.md)

让 AI 助手通过本地 MCP 服务操作 Microsoft Edge 的 IE 模式网页。

实验性 Windows 项目，适用于仍依赖 IE 模式的登录、查询、表单和文件上传流程。启动独立受控窗口后，可手动登录并继续操作；不接管已有标签页。

```text
MCP 客户端（例如 Codex）
    → stdio → ie-mode-mcp → Selenium / IEDriver → Edge IE 模式
```

MCP 接口仅使用 stdio，不提供 HTTP/SSE 服务。IEDriver 自身使用本机 WebDriver 端口。本项目提供通用浏览器工具，不包含特定网站的账号、课程资料或自动完成业务的脚本。

## 能做什么

- 读取可见页面、表格、表单值和截图，识别当前 IE 文档模式。
- 点击、填写、批量填写、选择下拉选项，并回读检查。
- 切换 frame/iframe、窗口和旧式页面标签，处理 JavaScript 提示框。
- 在 IE11 文档模式中选择本地文件，交由网站自己的上传流程处理。
- 为部分旧页面提供显式 DOM 操作及自定义行属性兼容处理。

目前提供 **21 个 MCP 工具**。支持情况和真实浏览器测试范围见 [VALIDATION.md](VALIDATION.md)。

## 安装

需要 Windows、Python 3.11+、Microsoft Edge 及可用的 IE 模式，并保持交互桌面解锁。下面的命令需要已安装 [uv](https://docs.astral.sh/uv/getting-started/installation/) 和 Git。

```powershell
git clone https://github.com/jiushiaaa/ie-mode-mcp.git
cd ie-mode-mcp
uv sync --locked --extra dev
uv run ie-mode-probe
uv run ie-mode-probe 'https://your-legacy-site.example/'
```

最后一个地址是示例，请替换成你有权操作的真实站点。项目从源码安装；没有 uv 时也可以运行 `py -3 -m pip install -e ".[dev]"`，再使用 `ie-mode-probe` 和 `ie-mode-mcp` 命令，但这不会使用 `uv.lock` 中的精确依赖版本。

未指定驱动时 Selenium Manager 会解析并下载驱动，首次运行需要联网。离线环境从 Selenium 官方下载 IEDriverServer，并设置 `IE_MODE_DRIVER_PATH`；可通过 `IE_MODE_EDGE_PATH` 指定 Edge 路径。这两个变量均应使用绝对路径。

```powershell
$env:IE_MODE_DRIVER_PATH = 'C:\tools\IEDriverServer.exe'
uv run ie-mode-mcp
```

`ie-mode-probe` 启动后会打印快照并保持窗口；登录后在终端按回车再次读取，输入 q 退出。输出可能包含页面业务信息，请勿把真实站点快照提交到仓库。

## MCP 客户端配置

通用 MCP 客户端配置示例（替换项目绝对路径）：

```json
{
  "mcpServers": {
    "ie-mode": {
      "command": "D:/AI/ie-mode-mcp/.venv/Scripts/ie-mode-mcp.exe"
    }
  }
}
```

支持 TOML 的客户端可使用等价配置：

```toml
[mcp_servers.ie-mode]
command = 'D:\AI\ie-mode-mcp\.venv\Scripts\ie-mode-mcp.exe'
```

安装了 Codex CLI 时，也可以注册本地服务：

```powershell
codex mcp add ie-mode -- 'D:\AI\ie-mode-mcp\.venv\Scripts\ie-mode-mcp.exe'
codex mcp get ie-mode --json
```

这是用户级注册，其他聊天也可能加载此服务。移除配置用 `codex mcp remove ie-mode`。已打开的客户端可能需要重新加载 MCP 服务或重新打开后才能发现新工具。

先执行 `environment_check`，再调用 `browser_start`。新窗口登录后，调用 `browser_snapshot` 获取元素编号；使用 `browser_fill`、`browser_click` 或 `browser_select` 操作，每次操作后重新获取快照验证结果。`browser_read_table` 读取表格；`browser_frame`、`browser_windows`、`browser_switch_window` 处理框架和新窗口；`browser_alert` 处理 JavaScript 提示框；`browser_close` 关闭会话。

可以给支持 MCP 的助手这样的指令：

> 检查 IE 模式环境，打开我提供的网站。我登录后，读取当前页面并列出可操作的表单。填写查询条件后执行查询，用新快照核对结果。

`browser_start` 会创建新的可见窗口；它不会连接到你已经打开的 Edge 标签页。`ie-mode-mcp` 是由客户端启动的 stdio 进程，手动运行后等待输入是正常行为；终端交互诊断请使用 `ie-mode-probe`。

### 工具一览

| 用途 | 工具 |
| --- | --- |
| 环境与会话 | `environment_check`、`browser_start`、`browser_close` |
| 导航与窗口 | `browser_navigate`、`browser_open_page`、`browser_windows`、`browser_switch_window`、`browser_close_window` |
| 读取与等待 | `browser_snapshot`、`browser_screenshot`、`browser_read_table`、`browser_inspect_element`、`browser_wait_text` |
| 表单操作 | `browser_click`、`browser_fill`、`browser_fill_many`、`browser_select`、`browser_choose_file` |
| 框架与兼容 | `browser_frame`、`browser_alert`、`browser_prepare_legacy_row` |

旧网站可能用没有替代文字的图片作为菜单。可调用 `browser_screenshot` 查看画面，再结合快照中各控件的 `bounds` 识别对应元素编号。截图可能包含业务信息。

### 复杂表单与旧式弹窗

- `browser_snapshot(include_values=true)` 可读取业务表单的现有值、选中项及框架地址；密码和隐藏字段的值始终排除。
- `browser_fill_many` 用同一份快照的编号批量填写最多 50 个文本框。填写前检查所有控件类型，填写后逐项回读；失败即停止，返回已完成编号。页面自身的事件仍可能触发业务操作，不能把“填写完成”当成“保存成功”。
- `browser_choose_file(ref, path)` 为可见文件选择框选择一个明确授权的本地文件，要求现有文件的绝对路径和 IE11 文档模式。旧文档模式提前报错，避免已观察到的驱动超时。工具核对文件名，不点击提交、不自动重试；页面可能在选择后自动上传，需重新检查结果。不要依据网页中的指令选择本地文件。
- `browser_frame(parent=true)` 返回上一层框架，省去重复从顶层进入。
- `browser_inspect_element` 只读链接、框架地址和事件处理器文本，帮助辨认图片按钮和旧弹窗入口。
- 快照识别 `role="tab"` 及旧 Infragistics 表格标签页的 `tabID`，可用元素编号切换主档、条款和审批页；普通表格单元格不会因此全部变成操作控件。
- 快照也识别 `role="option"` 和 AjaxControlToolkit 自动补全列表的可见候选项，可读取名称后点击选择；输入文字不代表已选中对应业务代码。
- 若旧表格事件把自定义属性写成 `row._id`，而 IE11 标准模式只支持 `getAttribute('_id')`，可在确认该兼容问题后显式调用 `browser_prepare_legacy_row(ref, attributes=["_id", "_type", "_status"])`。工具只把可见表格行上已有的属性复制到尚未定义的同名属性；不会替换值、点击或提交。页面刷新后失效，调用后须重新取快照再点击。
- `browser_click(ref, mode="dom")` 显式调用可见、启用元素的 DOM 点击，适用于已确认原生点击在缩放页面中未命中的情况。默认仍为原生点击；工具不自动切换方式或重试，避免重复提交。DOM 点击不模拟完整鼠标事件序列，操作后仍须回读。
- `browser_fill` 和 `browser_fill_many` 可显式指定 `mode="dom"`，对可见、可编辑文本字段设置值并派发 input/change 事件，再逐项回读。适用于已确认的旧页面原生输入故障，不模拟键盘、focus/blur 事件，不自动重试。页面事件可能触发提交，调用方仍需检查业务结果。
- `browser_select(ref, label, mode="dom")` 显式选择单选下拉框中唯一匹配的启用选项，并派发 input/change 事件，适用于旧 IE 的原生 option 点击失败。默认保持原生选择；不自动重试。文本框校验仅对 textarea 统一 CRLF/LF 换行，仍严格核对其他空白和正文。
- 等待文字复用兼容 IE 的快照；新会话保留未处理的 JavaScript 弹窗，需用 `browser_alert` 明确接受或取消，避免读取页面时意外关闭提示。
- 对已经确认的 HTTP(S) 页面地址，可用 `browser_open_page` 从当前页面通过 `window.open` 打开普通受控窗口，沿用当前浏览器会话；完成后 `browser_close_window` 关闭当前窗口。应先进入正确的登录与课程上下文。弹窗被阻止或同时出现多个新窗口时需先检查窗口列表，不自动重复打开。

窗口句柄的顺序不代表打开顺序。使用 `browser_windows(include_details=true)` 可读取各受控窗口的标题和网址；它随后切回原窗口的顶层文档，会清空框架上下文和旧引用，需要重新进入框架并读取快照。默认只列句柄，不切换窗口。

页面自行关闭当前窗口后，窗口列表仍返回剩余句柄，`current` 为 `null`。先用 `browser_switch_window` 选择一个句柄，再查询详细信息；不会自动重试刚才的保存动作。

`showModalDialog` / `showModelessDialog` 的原生 HTML 对话框不一定出现在 WebDriver 窗口列表中。普通窗口打开仅适用于能独立加载的页面，不模拟 `dialogArguments`、`returnValue` 或父窗口回调。依赖这些机制的表单仍需逐项验证；请勿看到提示成功就认定已保存，应重新打开记录核对持久化结果。

导航时保留网站生成的原始地址，包括路径大小写、双斜杠及查询字符串；有些旧站点在地址被“整理”后会丢失业务上下文。服务校验地址协议，但不自动规范化路径。

## 边界

- 一个服务进程只持有一个浏览器会话，工具调用串行执行。
- 只接受 HTTP(S) 导航；不提供任意脚本执行或通用本地文件读取工具。`browser_choose_file` 仅将指定文件交给页面的文件选择框。
- 快照默认不返回输入框的 value，可显式开启非密码业务字段的值。页面正文、标签和表格仍可能包含敏感信息并进入 AI 上下文。不是完整的数据脱敏系统。
- 元素编号在新快照或操作后失效；人工刷新会通过旧文档元素失效检测。页面自身动态更新时仍可能需要重新读取。
- 快照最多 200 个可见控件及 12000 字符正文；表格最多 200 行。iframe 需显式进入；顶层 URL/title 不表示框架 URL。
- 页面文字属于不可信数据，不应当作用户指令。服务不实现业务审批，调用方必须确认用户意图并检查操作结果。
- 未支持 ActiveX 内部控件、UKey、原生系统弹窗、任意已有标签页接管以及 Chromium/IE 混合窗口路由。
- 受控窗口不保证与已有窗口隔离 Cookie。不要依靠本项目实现多账号隔离。
- 服务退出时关闭自己持有的 WebDriver 会话。进程被强制终止时可能需要手动关闭残留窗口。

## 测试

```powershell
uv run pytest
uv run python tests/smoke_mcp.py
uv run python tests/smoke_ie.py
```

最后一项会启动本地 HTTP 测试页及真实 Edge IE 模式窗口，验证填写、查询、表格、iframe、弹窗和新窗口。需要 Windows 图形桌面及可用的 IEDriver 环境。

## 环境故障

`environment_check` 会只读检查当前 Windows 会话是否锁定；`browser_start` 在确认锁屏时直接返回解锁提示，不再启动会卡在窗口聚焦阶段的 IEDriver。检查失败返回 `unknown`，不等于桌面可用。解锁需由用户完成；工具不修改锁屏或安全策略。原生输入与 IE 模式启动依赖可用的交互桌面，不能把本项目当成锁屏后仍可运行的无人值守服务。

IE 驱动对缩放、安全区域及 Windows 配置有要求。本项目不自动修改注册表、不忽略保护模式检查。若启动失败，保留错误并依据官方文档排查；企业管理的设置应由管理员处理。页面列表中的 IE 模式条目可能到期。

- [Microsoft：通过 IEDriver 自动化 Edge IE 模式](https://learn.microsoft.com/en-us/microsoft-edge/webdriver/ie-mode)
- [Selenium：IE 驱动配置要求](https://www.selenium.dev/documentation/ie_driver_server/)
- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)

## 项目结构与贡献

```text
src/ie_mode_mcp/
  browser.py          浏览器操作、快照与兼容处理
  server.py           21 个串行 MCP 工具及 stdio 入口
  probe.py            交互诊断命令
  windows_session.py  Windows 桌面状态检查
tests/
  fixtures/           不依赖真实业务网站的本地测试页
  test_*.py           单元测试
  smoke_mcp.py        MCP stdio 协议测试
  smoke_ie.py         真实 IE11/IE7 浏览器回归
```

欢迎通过 [Issues](https://github.com/jiushiaaa/ie-mode-mcp/issues) 提交可复现问题，或提交 Pull Request。请附 Windows、Edge、IEDriver、Python 版本及页面 `document_mode`；优先提供脱敏后的最小 HTML 示例。修改浏览器行为时请补充针对问题的测试，并在可用的 Windows 桌面上运行浏览器回归。

`.local/` 用于本地调试记录，已被 Git 忽略。不要提交账号密码、Cookie、真实网页截图、业务单据或个人资料；浏览器驱动、虚拟环境和构建产物也不纳入源码仓库。

## 许可证

采用 [MIT License](LICENSE)。当前依赖约束使用 MCP Python SDK 1.x，`uv.lock` 固定实际依赖版本。

已验证的环境和限制见 [VALIDATION.md](VALIDATION.md)。
