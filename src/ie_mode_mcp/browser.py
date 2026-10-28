import os
import platform
import re
import shutil
from pathlib import Path
from threading import RLock
from urllib.parse import urlsplit
from uuid import uuid4

from selenium import webdriver
from selenium.common.exceptions import NoSuchWindowException, TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.ie.service import Service
from selenium.webdriver.remote.file_detector import UselessFileDetector
from selenium.webdriver.support.ui import Select, WebDriverWait

from .windows_session import desktop_status


def edge_path():
    configured = os.environ.get("IE_MODE_EDGE_PATH")
    drive = os.environ.get("SystemDrive", "C:")
    roots = [os.environ.get("PROGRAMFILES(X86)", drive + "/Program Files (x86)"),
             os.environ.get("PROGRAMFILES", drive + "/Program Files"),
             os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData/Local"))]
    candidates = [configured] if configured else [
        str(Path(root) / "Microsoft/Edge/Application/msedge.exe") for root in roots
    ]
    return next((p for p in candidates if p and Path(p).is_file()), None)


def doctor():
    return {
        "platform": platform.system(),
        "edge_path": edge_path(),
        "driver_path": os.environ.get("IE_MODE_DRIVER_PATH") or shutil.which("IEDriverServer"),
        "driver_resolution": "Explicit path or PATH, otherwise Selenium Manager downloads the driver.",
        "desktop": desktop_status(),
        "requirements": [
            "Windows with Edge IE mode available",
            "Unlocked interactive Windows desktop for IEDriver startup and native input",
            "Browser zoom 100%; review Selenium IE driver configuration",
            "Protected Mode settings consistent across zones; no automatic setting changes",
        ],
    }


def validate_url(url):
    parsed = urlsplit(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError("Only absolute HTTP(S) URLs are supported.")
    if parsed.username or parsed.password:
        raise ValueError("Do not put credentials in URLs.")
    return url


class Browser:
    """One serialized WebDriver session. Element references expire after actions."""

    def __init__(self):
        self.driver = None
        self.lock = RLock()
        self.elements = {}
        self.revision = 0
        self.document = None

    def require_driver(self):
        if self.driver is None:
            raise RuntimeError("No session. Call browser_start first.")
        return self.driver

    def invalidate(self):
        self.elements.clear()
        self.document = None
        self.revision += 1

    def start(self, url):
        validate_url(url)
        if self.driver is not None:
            raise RuntimeError("A session already exists. Navigate or close it first.")
        if platform.system() != "Windows":
            raise RuntimeError("Edge IE mode requires Windows.")
        if desktop_status()["state"] == "locked":
            raise RuntimeError("Windows desktop is locked. Unlock this session before browser_start; IEDriver may hang while focusing its new window. No browser was started.")
        edge = edge_path()
        if not edge:
            raise RuntimeError("Edge not found. Set IE_MODE_EDGE_PATH.")
        options = webdriver.IeOptions()
        options.attach_to_edge_chrome = True
        options.edge_executable_path = edge
        # Start in the target site's security zone instead of the driver's localhost page.
        options.initial_browser_url = url
        options.browser_attach_timeout = 30000
        options.page_load_strategy = "eager"
        # Leave business prompts for an explicit browser_alert decision.
        options.unhandled_prompt_behavior = "ignore"
        service = Service(executable_path=os.environ.get("IE_MODE_DRIVER_PATH"), log_output=os.devnull)
        self.driver = webdriver.Ie(options=options, service=service)
        self.driver.command_executor.client_config.timeout = 45
        self.driver.set_page_load_timeout(30)
        self.driver.set_script_timeout(15)
        return self.navigate(url)

    def navigate(self, url):
        validate_url(url)
        self.invalidate()
        try:
            self.require_driver().get(url)
        except TimeoutException:
            return {"navigation_timed_out": True, "requested_url": url,
                    "note": "Page load exceeded 30 seconds. Session retained; take a snapshot to inspect the actual state before retrying."}
        return self.snapshot()

    def snapshot(self, include_values=False):
        driver = self.require_driver()
        self.invalidate()
        # One IE-compatible script avoids hundreds of slow WebDriver round trips.
        data = driver.execute_script("""
            function visibleText(root, limit) {
                var output = '';
                function visit(node) {
                    if (output.length >= limit) return;
                    if (node.nodeType === 3) {
                        var text = node.nodeValue.replace(/\\s+/g, ' ').replace(/^\\s+|\\s+$/g, '');
                        if (text) output += text + ' ';
                        return;
                    }
                    if (node.nodeType !== 1) return;
                    var tag = node.tagName.toLowerCase(), child;
                    if (/^(script|style|noscript|head|input|textarea)$/.test(tag)) return;
                    if (tag === 'select') {
                        if (node.selectedIndex >= 0) output += node.options[node.selectedIndex].text + ' ';
                        return;
                    }
                    var css = window.getComputedStyle ? window.getComputedStyle(node) : node.currentStyle;
                    if (css && (css.display === 'none' || css.visibility === 'hidden')) return;
                    for (child = node.firstChild; child; child = child.nextSibling) visit(child);
                }
                if (root) visit(root);
                return output.replace(/\\s+/g, ' ').substring(0, limit);
            }
            // IE7 document mode has no querySelectorAll; preserve DOM order.
            var nodes = document.getElementsByTagName('*');
            var labels = document.getElementsByTagName('label');
            var items = [], i, j, el, label, style;
            for (i = 0; i < nodes.length && items.length < 200; i++) {
                el = nodes[i];
                if (!/^(A|BUTTON|INPUT|SELECT|TEXTAREA|IFRAME|FRAME|TABLE)$/.test(el.tagName) &&
                    !/^(button|tab|option)$/.test(el.getAttribute('role') || '') &&
                    // AjaxControlToolkit suggestions use event listeners, not onclick attributes.
                    !(el.tagName === 'DIV' && el.parentNode &&
                      /_completionListElem$/.test(el.parentNode.id || '')) &&
                    !(el.tagName === 'TD' && el.getAttribute('tabID')) &&
                    !el.getAttribute('onclick')) continue;
                style = window.getComputedStyle ? window.getComputedStyle(el) : el.currentStyle;
                if ((!el.offsetWidth && !el.offsetHeight) ||
                    (style && (style.visibility === 'hidden' || style.display === 'none'))) continue;
                label = el.getAttribute('aria-label') || el.getAttribute('title') || el.getAttribute('alt') || '';
                if (!label && el.id) {
                    for (j = 0; j < labels.length; j++) {
                        if (labels[j].htmlFor === el.id) { label = labels[j].innerText || ''; break; }
                    }
                }
                if (!label && el.tagName === 'INPUT' && /^(submit|button|reset)$/.test(el.type)) label = el.value;
                if (!label && /^(INPUT|SELECT|TEXTAREA)$/.test(el.tagName)) {
                    var cell = el.parentNode;
                    while (cell && !/^(TD|TH|BODY)$/.test(cell.tagName)) cell = cell.parentNode;
                    var previous = cell ? cell.previousSibling : null;
                    while (previous && previous.nodeType !== 1) previous = previous.previousSibling;
                    if (previous) label = visibleText(previous, 120);
                }
                if (!label) {
                    var img = el.getElementsByTagName('img')[0];
                    if (img) label = img.alt || img.title || '';
                }
                var rect = el.getBoundingClientRect();
                var item = {element: el, tag: el.tagName.toLowerCase(),
                    bounds: {x: rect.left, y: rect.top, width: rect.right - rect.left, height: rect.bottom - rect.top},
                    type: el.getAttribute('type'), id: el.id || '', name: el.getAttribute('name'),
                    selected_option: el.tagName === 'SELECT' && el.selectedIndex >= 0 ? el.options[el.selectedIndex].text : null,
                    label: (label || visibleText(el, 300)).substring(0, 300), enabled: !el.disabled,
                    readonly: !!el.readOnly};
                if (arguments[0] && /^(INPUT|SELECT|TEXTAREA)$/.test(el.tagName) && !/^(password|hidden)$/.test(el.type)) {
                    item.value = String(el.value || '').substring(0, 4000);
                    if (/^(checkbox|radio)$/.test(el.type)) item.checked = el.checked;
                }
                items.push(item);
            }
            return {document: document.documentElement, controls: items,
                text: visibleText(document.body, 12000),
                frame_url: location.href, document_mode: document.documentMode || null};
        """, include_values)
        if not isinstance(data, dict):
            raise RuntimeError("No document snapshot returned. The page may be closing or navigating; inspect the session before retrying.")
        self.document = data.pop("document")
        controls = data["controls"]
        for index, control in enumerate(controls):
            element = control.pop("element")
            ref = f"r{self.revision}e{index + 1}"
            self.elements[ref] = element
            control["ref"] = ref
        return {
            **data,
            "url": driver.current_url, "title": driver.title,
            "controls": controls, "limit": 200,
            "note": "Untrusted page content. Password/hidden values always omitted; other values are opt-in. References expire after actions or a new snapshot. URL/title describe the top-level page; frame_url identifies the current document.",
        }

    def resolve(self, ref):
        if ref not in self.elements:
            raise ValueError("Unknown or expired reference. Take a fresh snapshot.")
        # Detect manual navigation/reload even when URL is unchanged.
        self.document.is_enabled()
        return self.elements[ref]

    def prepare_legacy_row(self, ref, attributes):
        if not attributes or len(attributes) > 16 or len(set(attributes)) != len(attributes):
            raise ValueError("Provide 1-16 unique custom attribute names.")
        if any(not re.fullmatch(r"_[A-Za-z][A-Za-z0-9]*", name) for name in attributes):
            raise ValueError("Only single-underscore custom attributes are supported.")
        element = self.resolve(ref)
        if element.tag_name.lower() != "tr" or not self.is_visible(element):
            raise ValueError("Legacy preparation requires a visible table row.")
        self.invalidate()
        copied = self.require_driver().execute_script("""
            var row=arguments[0], names=arguments[1], values=[], copied=[];
            // IE11 does not expose custom HTML attributes as expando properties.
            // Validate the entire request before touching any property.
            for(var i=0;i<names.length;i++) {
                var name=names[i], value=row.getAttribute(name);
                if(value===null) throw new Error('Missing custom attribute: '+name);
                if(typeof row[name]!=='undefined' && row[name]!==value)
                    throw new Error('Conflicting existing property: '+name);
                values.push(value);
            }
            for(var i=0;i<names.length;i++) {
                if(typeof row[names[i]]==='undefined') {
                    row[names[i]]=values[i]; copied.push(names[i]);
                }
            }
            return copied;
        """, element, attributes)
        return {"copied": copied, "note": "Copied existing row attributes to missing legacy properties in this document only. No click or submit performed. Take a fresh snapshot before acting."}

    def act(self, action, ref, value="", click_mode="native", fill_mode="native", select_mode="native"):
        if click_mode not in ("native", "dom"):
            raise ValueError("Click mode must be native or dom.")
        if fill_mode not in ("native", "dom"):
            raise ValueError("Fill mode must be native or dom.")
        if select_mode not in ("native", "dom"):
            raise ValueError("Select mode must be native or dom.")
        element = self.resolve(ref)
        if action == "fill":
            self.validate_text_field(element)
            if fill_mode == "dom" and not self.is_visible(element):
                raise ValueError("Field must be visible.")
        self.invalidate()
        if action == "click":
            if click_mode == "dom":
                if not self.is_visible(element) or not element.is_enabled():
                    raise ValueError("DOM click requires a visible, enabled element.")
                self.require_driver().execute_script("arguments[0].click();", element)
            else:
                element.click()
        elif action == "fill":
            self.fill_text(element, value, fill_mode)
        elif action == "select":
            if select_mode == "dom":
                if element.tag_name.lower() != "select" or element.get_property("multiple"):
                    raise ValueError("DOM select requires a single-choice dropdown.")
                if not self.is_visible(element) or not element.is_enabled():
                    raise ValueError("DOM select requires a visible, enabled dropdown.")
                verified = self.require_driver().execute_script("""
                    var e=arguments[0], label=arguments[1], found=-1, count=0;
                    function normalized(s) { return s.replace(/\\s+/g,' ').replace(/^ | $/g,''); }
                    for(var i=0;i<e.options.length;i++) {
                        if(normalized(e.options[i].text)===normalized(label)) {found=i;count++;}
                    }
                    if(count!==1) throw new Error('Expected exactly one matching option');
                    var o=e.options[found], p=o.parentNode;
                    if(o.disabled || (p.tagName.toLowerCase()==='optgroup' && p.disabled))
                        throw new Error('Option is disabled');
                    e.selectedIndex=found;
                    var doc=e.ownerDocument;
                    if(doc.createEvent) {
                        var input=doc.createEvent('HTMLEvents');input.initEvent('input',true,false);e.dispatchEvent(input);
                        var change=doc.createEvent('HTMLEvents');change.initEvent('change',true,false);e.dispatchEvent(change);
                    } else if(e.fireEvent) {e.fireEvent('onchange');}
                    return e.selectedIndex===found;
                """, element, value)
                if not verified:
                    raise RuntimeError("Selection verification failed. Inspect before retrying.")
            else:
                Select(element).select_by_visible_text(value)
        else:
            raise ValueError("Unknown action.")
        return {"performed": action, "note": "Read a fresh snapshot to verify the outcome; this does not confirm business success."}

    def table(self, ref):
        element = self.resolve(ref)
        if element.tag_name.lower() != "table":
            raise ValueError("Reference must identify a table.")
        rows = element.find_elements(By.CSS_SELECTOR, "tr")
        return {"rows": [[cell.text for cell in row.find_elements(By.CSS_SELECTOR, "th,td")]
                         for row in rows[:200]], "truncated": len(rows) > 200}

    def frame(self, ref=None, parent=False):
        driver = self.require_driver()
        if ref and parent:
            raise ValueError("Choose a frame reference or parent, not both.")
        element = self.resolve(ref) if ref else None
        self.invalidate()
        if parent:
            driver.switch_to.parent_frame()
        elif element is None:
            driver.switch_to.default_content()
        else:
            driver.switch_to.frame(element)
        return self.snapshot()

    def inspect(self, ref):
        element = self.resolve(ref)
        return self.require_driver().execute_script("""
            var e = arguments[0], result = {tag:e.tagName.toLowerCase(), frame_url:location.href};
            var names = ['id','name','type','href','src','title','alt','onclick','onchange','target'];
            for(var i=0;i<names.length;i++) result[names[i]]=e.getAttribute(names[i]);
            return result;
        """, element)

    def choose_file(self, ref, path):
        candidate = Path(path)
        if '\n' in path or '\r' in path or not candidate.is_absolute() or not candidate.is_file():
            raise ValueError("Provide one absolute path to an existing file.")
        candidate = candidate.resolve()
        element = self.resolve(ref)
        if (element.tag_name.lower() != 'input' or
                (element.get_dom_attribute('type') or '').lower() != 'file'):
            raise ValueError("Reference must identify a file input.")
        if not self.is_visible(element) or not element.is_enabled():
            raise ValueError("File input must be visible, enabled.")
        driver = self.require_driver()
        if driver.execute_script('return document.documentMode;') != 11:
            raise ValueError("File selection currently requires IE11 document mode; legacy modes may hang IEDriver.")
        self.invalidate()
        # This server and IEDriver run on the same Windows host. Do not use
        # RemoteWebDriver's ZIP-upload endpoint or a native file-picker dialog.
        with driver.file_detector_context(UselessFileDetector):
            element.send_keys(str(candidate))
        selected = driver.execute_script('return arguments[0].value;', element)
        if not isinstance(selected, str) or selected.replace('\\', '/').split('/')[-1].casefold() != candidate.name.casefold():
            raise RuntimeError("File selection could not be verified. Inspect before retrying.")
        return {"selected": True, "filename": candidate.name,
                "note": "No submit button was clicked. Page change handlers may upload automatically; verify the page before submitting or retrying."}

    def open_page(self, url):
        validate_url(url)
        driver = self.require_driver()
        before = set(driver.window_handles)
        self.invalidate()
        # IEDriver new_window can start a separate IE cookie session. Opening
        # from the current page preserves the user's existing browser context.
        driver.execute_script("window.open(arguments[0], arguments[1]);", url, "ie_mode_mcp_" + uuid4().hex)
        opened = WebDriverWait(driver, 15).until(lambda d: set(d.window_handles) - before)
        if len(opened) != 1:
            raise RuntimeError("Multiple new windows appeared. Inspect browser_windows before selecting one; do not repeat the open action.")
        driver.switch_to.window(opened.pop())
        WebDriverWait(driver, 15).until(lambda d: d.current_url != "about:blank" and
                                       d.execute_script("return document.readyState") in ("interactive", "complete"))
        return self.snapshot()

    def close_window(self):
        driver = self.require_driver()
        handles = driver.window_handles
        if len(handles) == 1:
            return self.close()
        current = driver.current_window_handle
        self.invalidate()
        driver.close()
        driver.switch_to.window(next(h for h in handles if h != current))
        return self.windows()

    @staticmethod
    def validate_text_field(element):
        tag = element.tag_name.lower()
        field_type = (element.get_dom_attribute('type') or 'text').lower()
        if not (tag == 'textarea' or tag == 'input' and field_type in
                ('text', 'password', 'email', 'search', 'tel', 'url', 'number')):
            raise ValueError("Fill requires an editable text field, not a button or file input.")
        if not element.is_enabled() or element.get_property('readOnly'):
            raise ValueError("Field is disabled or read-only.")

    def is_visible(self, element):
        # Selenium's current is_displayed script fails in IE7 document mode.
        return self.require_driver().execute_script("""
            var e=arguments[0], n=e;
            if(!e.offsetWidth && !e.offsetHeight) return false;
            while(n && n.nodeType===1) {
                var s=window.getComputedStyle ? window.getComputedStyle(n) : n.currentStyle;
                if(s && (s.display==='none' || s.visibility==='hidden' || s.visibility==='collapse')) return false;
                n=n.parentNode;
            }
            return true;
        """, element)

    def fill_text(self, element, value, mode):
        if mode == "dom":
            self.require_driver().execute_script("""
                var e=arguments[0], value=arguments[1], doc=e.ownerDocument;
                e.value=value;
                if(doc.createEvent) {
                    var input=doc.createEvent('HTMLEvents');
                    input.initEvent('input',true,false);e.dispatchEvent(input);
                    var change=doc.createEvent('HTMLEvents');
                    change.initEvent('change',true,false);e.dispatchEvent(change);
                } else if(e.fireEvent) { e.fireEvent('onchange'); }
            """, element, value)
        else:
            element.click()
            element.clear()
            element.send_keys(value)
        actual = element.get_property("value")
        if element.tag_name.lower() == "textarea":
            # IE can return CRLF even when the supplied textarea value used LF.
            actual = actual.replace("\r\n", "\n").replace("\r", "\n")
            value = value.replace("\r\n", "\n").replace("\r", "\n")
        if actual != value:
            raise RuntimeError("Input verification failed. Inspect the page before retrying.")

    def fill_many(self, fields, mode="native"):
        if mode not in ("native", "dom"):
            raise ValueError("Fill mode must be native or dom.")
        if not fields or len(fields) > 50:
            raise ValueError("Provide between 1 and 50 fields.")
        refs = [field['ref'] for field in fields]
        if len(set(refs)) != len(refs):
            raise ValueError("Duplicate field references.")
        elements = [self.resolve(ref) for ref in refs]
        for element in elements:
            self.validate_text_field(element)
            if mode == "dom" and not self.is_visible(element):
                raise ValueError("Field must be visible.")
        completed = []
        self.invalidate()
        for field, element in zip(fields, elements):
            try:
                self.fill_text(element, field['value'], mode)
            except Exception as error:
                return {"completed_refs": completed, "failed_ref": field['ref'],
                        "error_type": type(error).__name__,
                        "note": "Stopped after an input failure. Inspect before retrying; page event handlers may have run."}
            completed.append(field['ref'])
        return {"completed_refs": completed, "verified": True, "submitted": False}

    def windows(self, include_details=False):
        driver = self.require_driver()
        handles = driver.window_handles
        try:
            current = driver.current_window_handle
        except NoSuchWindowException:
            self.invalidate()
            return {"current": None, "handles": handles,
                    "note": "The selected window closed itself. Select a returned handle with browser_switch_window, then request details again."}
        result = {"current": current, "handles": handles}
        if not include_details:
            return result
        self.invalidate()
        result["windows"] = []
        try:
            for handle in result["handles"]:
                try:
                    driver.switch_to.window(handle)
                    result["windows"].append({"handle": handle, "url": driver.current_url, "title": driver.title})
                except NoSuchWindowException:
                    result["windows"].append({"handle": handle, "closed": True})
        finally:
            driver.switch_to.window(result["current"])
        result["note"] = "Restored the original window at its top-level document. Frame context and references were reset."
        return result

    def window(self, handle):
        driver = self.require_driver()
        if handle not in driver.window_handles:
            raise ValueError("Unknown window handle.")
        self.invalidate()
        driver.switch_to.window(handle)
        return self.snapshot()

    def wait_text(self, text, seconds=10):
        if not text or not 1 <= seconds <= 30:
            raise ValueError("Provide nonempty text and a timeout between 1 and 30 seconds.")
        driver = self.require_driver()
        def matching_snapshot(_):
            page = self.snapshot()
            return page if text in page["text"] else False

        return WebDriverWait(driver, seconds).until(matching_snapshot)

    def alert(self, action="read"):
        if action not in ("read", "accept", "dismiss"):
            raise ValueError("Action must be read, accept, or dismiss.")
        alert = self.require_driver().switch_to.alert
        text = alert.text
        if action != "read":
            self.invalidate()
            getattr(alert, action)()
        return {"text": text, "action": action}

    def close(self):
        driver, self.driver = self.driver, None
        self.invalidate()
        if driver:
            driver.quit()
        return {"closed": True}
