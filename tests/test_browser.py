from contextlib import nullcontext
from unittest.mock import Mock, PropertyMock

import pytest
from selenium.common.exceptions import TimeoutException

from ie_mode_mcp.browser import Browser, validate_url, edge_path


def test_start_on_locked_desktop_never_launches_driver(monkeypatch):
    monkeypatch.setattr('ie_mode_mcp.browser.platform.system', lambda: 'Windows')
    monkeypatch.setattr('ie_mode_mcp.browser.desktop_status', lambda: {'state': 'locked'})
    launch = Mock()
    monkeypatch.setattr('ie_mode_mcp.browser.webdriver.Ie', launch)
    browser = Browser()
    with pytest.raises(RuntimeError, match='Unlock this session'):
        browser.start('https://example.com/')
    launch.assert_not_called()
    assert browser.driver is None


@pytest.mark.parametrize('state', ['unlocked', 'unknown'])
def test_start_does_not_misclassify_unknown_desktop_as_locked(monkeypatch, state):
    monkeypatch.setattr('ie_mode_mcp.browser.platform.system', lambda: 'Windows')
    monkeypatch.setattr('ie_mode_mcp.browser.desktop_status', lambda: {'state': state})
    monkeypatch.setattr('ie_mode_mcp.browser.edge_path', lambda: 'C:/Edge/msedge.exe')
    launch = Mock(return_value=Mock())
    monkeypatch.setattr('ie_mode_mcp.browser.webdriver.Ie', launch)
    browser = Browser()
    browser.navigate = Mock(return_value={'text': 'Ready'})
    assert browser.start('https://example.com/') == {'text': 'Ready'}
    launch.assert_called_once()


@pytest.mark.parametrize("url", ["file:///C:/secret", "javascript:alert(1)", "about:blank", "https://u:p@example.com", "relative"])
def test_reject_unsupported_navigation(url):
    with pytest.raises(ValueError):
        validate_url(url)


def test_action_invalidates_all_refs_and_does_not_echo_value():
    browser = Browser()
    element = text_field("secret")
    browser.document = Mock()
    browser.elements = {"r1e1": element, "r1e2": Mock()}
    result = browser.act("fill", "r1e1", "secret")
    element.clear.assert_called_once()
    element.send_keys.assert_called_once_with("secret")
    assert "secret" not in str(result)
    with pytest.raises(ValueError):
        browser.resolve("r1e2")


def test_manual_reload_rejects_old_document():
    browser = Browser()
    browser.document = Mock()
    browser.document.is_enabled.side_effect = RuntimeError("stale document")
    browser.elements["r1e1"] = Mock()
    with pytest.raises(RuntimeError, match="stale document"):
        browser.act("click", "r1e1")
    browser.elements["r1e1"].click.assert_not_called()


def test_close_clears_state_even_if_quit_fails():
    browser = Browser()
    browser.driver = Mock()
    browser.driver.quit.side_effect = RuntimeError("disconnected")
    with pytest.raises(RuntimeError):
        browser.close()
    assert browser.driver is None
    assert browser.close() == {"closed": True}


def test_no_session_is_actionable():
    with pytest.raises(RuntimeError, match="browser_start"):
        Browser().snapshot()


def test_snapshot_invalidates_refs_when_a_closing_page_returns_no_document():
    browser = Browser()
    browser.driver = Mock()
    browser.driver.execute_script.return_value = None
    browser.elements = {'old': Mock()}
    with pytest.raises(RuntimeError, match='page may be closing or navigating'):
        browser.snapshot()
    assert not browser.elements


def test_wait_text_uses_legacy_snapshot_and_returns_matching_refs():
    browser = Browser()
    browser.driver = Mock()
    matching = {"text": "Ready", "controls": [{"ref": "r2e1"}]}
    browser.snapshot = Mock(side_effect=[{"text": "Loading"}, matching])
    assert browser.wait_text("Ready", seconds=2) is matching
    assert browser.snapshot.call_count == 2
    browser.driver.find_element.assert_not_called()


def test_wait_text_times_out_without_a_match():
    browser = Browser()
    browser.driver = Mock()
    browser.snapshot = Mock(return_value={"text": "Loading"})
    with pytest.raises(TimeoutException):
        browser.wait_text("Ready", seconds=1)


def test_dom_fill_uses_arguments_and_verifies_without_native_input():
    browser = Browser()
    browser.driver = Mock()
    browser.document = Mock()
    element = text_field('a";alert(1)')
    browser.elements = {'field': element}
    result = browser.fill_many([{'ref': 'field', 'value': 'a";alert(1)'}], mode='dom')
    assert result['verified']
    script, target, value = browser.driver.execute_script.call_args.args
    assert value not in script
    assert target is element
    element.click.assert_not_called()
    element.send_keys.assert_not_called()


def test_dom_fill_rejects_hidden_field_before_any_write():
    browser = Browser()
    browser.driver = Mock()
    browser.document = Mock()
    element = text_field('')
    browser.is_visible = Mock(return_value=False)
    browser.elements = {'field': element}
    with pytest.raises(ValueError, match='visible'):
        browser.act('fill', 'field', 'value', fill_mode='dom')
    browser.driver.execute_script.assert_not_called()


def test_textarea_accepts_ie_crlf_without_ignoring_other_whitespace():
    browser = Browser()
    element = text_field('line one\r\nline two\r\n')
    element.tag_name = 'textarea'
    browser.fill_text(element, 'line one\nline two\n', 'native')
    with pytest.raises(RuntimeError, match='verification failed'):
        browser.fill_text(element, 'line one\nline two', 'native')


def test_dom_select_passes_label_as_argument_and_never_native_clicks():
    browser = Browser()
    browser.driver = Mock()
    browser.document = Mock()
    browser.is_visible = Mock(return_value=True)
    element = Mock()
    element.tag_name = 'select'
    element.get_property.return_value = False
    browser.elements = {'choice': element}
    label = 'A "quoted" option'
    browser.act('select', 'choice', label, select_mode='dom')
    script, target, value = browser.driver.execute_script.call_args.args
    assert value == label and label not in script and target is element
    element.click.assert_not_called()
    assert not browser.elements


@pytest.mark.parametrize('tag,multiple,visible,enabled', [
    ('input', False, True, True), ('select', True, True, True),
    ('select', False, False, True), ('select', False, True, False)])
def test_dom_select_rejects_ineligible_controls_before_script(tag, multiple, visible, enabled):
    browser = Browser()
    browser.driver = Mock()
    browser.document = Mock()
    browser.is_visible = Mock(return_value=visible)
    element = Mock()
    element.tag_name = tag
    element.get_property.return_value = multiple
    element.is_enabled.return_value = enabled
    browser.elements = {'choice': element}
    with pytest.raises(ValueError):
        browser.act('select', 'choice', 'Option', select_mode='dom')
    browser.driver.execute_script.assert_not_called()


def test_dom_select_does_not_retry_a_reverted_selection():
    browser = Browser()
    browser.driver = Mock()
    browser.driver.execute_script.return_value = False
    browser.document = Mock()
    browser.is_visible = Mock(return_value=True)
    element = Mock()
    element.tag_name = 'select'
    element.get_property.return_value = False
    browser.elements = {'choice': element}
    with pytest.raises(RuntimeError, match='Selection verification failed'):
        browser.act('select', 'choice', 'Option', select_mode='dom')
    assert browser.driver.execute_script.call_count == 1
    element.click.assert_not_called()


def test_legacy_url_is_not_normalized():
    url = 'http://example.test/Tradelab//frame/?/1/../balance/export/default.aspx'
    assert validate_url(url) == url


def test_navigation_timeout_preserves_session_for_inspection():
    browser = Browser()
    driver = browser.driver = Mock()
    driver.get.side_effect = TimeoutException("slow page")
    result = browser.navigate("http://example.test/")
    assert result["navigation_timed_out"] is True
    assert browser.driver is driver
    driver.quit.assert_not_called()


def test_edge_discovery_with_minimal_mcp_environment(monkeypatch):
    from pathlib import Path
    for key in ("IE_MODE_EDGE_PATH", "PROGRAMFILES(X86)", "PROGRAMFILES", "LOCALAPPDATA", "SystemDrive"):
        monkeypatch.delenv(key, raising=False)
    expected = Path('C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe')
    monkeypatch.setattr(Path, 'is_file', lambda path: path == expected)
    assert Path(edge_path()) == expected


def test_fill_detects_silent_input_failure_without_echo():
    browser = Browser()
    browser.document = Mock()
    element = text_field('wrong')
    browser.elements['r1e1'] = element
    with pytest.raises(RuntimeError, match='Input verification failed'):
        browser.act('fill', 'r1e1', 'private value')
    assert not browser.elements


def test_batch_stops_after_first_failed_field():
    browser = Browser()
    browser.document = Mock()
    elements = [text_field('first'), text_field(''), text_field('third')]
    browser.elements = dict(zip(['a', 'b', 'c'], elements))
    result = browser.fill_many([{'ref':'a','value':'first'}, {'ref':'b','value':'private'}, {'ref':'c','value':'third'}])
    assert result['completed_refs'] == ['a']
    assert result['failed_ref'] == 'b'
    assert 'private' not in str(result)
    elements[2].click.assert_not_called()


def test_open_rejects_local_urls_before_creating_window():
    browser = Browser()
    browser.driver = Mock()
    with pytest.raises(ValueError):
        browser.open_page('file:///C:/secret')
    browser.driver.switch_to.new_window.assert_not_called()


def text_field(value):
    element = Mock()
    element.tag_name = 'input'
    element.get_dom_attribute.return_value = 'text'
    element.get_property.side_effect = lambda name: value if name == 'value' else False
    return element


@pytest.mark.parametrize('kind', ['submit', 'button', 'image', 'file', 'checkbox'])
def test_batch_preflights_every_field_before_any_click(kind):
    browser = Browser()
    browser.document = Mock()
    first, invalid = text_field(''), text_field('')
    invalid.get_dom_attribute.return_value = kind
    browser.elements = {'a': first, 'b': invalid}
    with pytest.raises(ValueError, match='editable text field'):
        browser.fill_many([{'ref': 'a', 'value': 'first'}, {'ref': 'b', 'value': 'second'}])
    first.click.assert_not_called()
    invalid.click.assert_not_called()


def test_fill_rejects_readonly_before_click():
    browser = Browser()
    browser.document = Mock()
    element = text_field('')
    element.get_property.side_effect = lambda name: name == 'readOnly'
    browser.elements = {'a': element}
    with pytest.raises(ValueError, match='read-only'):
        browser.act('fill', 'a', 'change')
    element.click.assert_not_called()


def test_explicit_dom_click_does_not_also_native_click():
    browser = Browser()
    browser.driver = Mock()
    browser.document = Mock()
    browser.is_visible = Mock(return_value=True)
    element = Mock()
    browser.elements = {'a': element}
    browser.act('click', 'a', click_mode='dom')
    browser.driver.execute_script.assert_called_once_with('arguments[0].click();', element)
    element.click.assert_not_called()
    assert not browser.elements


@pytest.mark.parametrize('names', [[], ['_id','_id'], ['__proto__'], ['onclick'], ['_id;alert(1)']])
def test_legacy_row_rejects_invalid_property_names_without_script(names):
    browser = Browser()
    browser.driver = Mock()
    with pytest.raises(ValueError):
        browser.prepare_legacy_row('row', names)
    browser.driver.execute_script.assert_not_called()


@pytest.mark.parametrize('tag,visible', [('input', True), ('tr', False)])
def test_legacy_row_rejects_nonrow_or_hidden_target(tag, visible):
    browser = Browser()
    browser.driver = Mock()
    browser.document = Mock()
    element = Mock(tag_name=tag)
    browser.elements = {'row': element}
    browser.is_visible = Mock(return_value=visible)
    with pytest.raises(ValueError, match='visible table row'):
        browser.prepare_legacy_row('row', ['_id'])
    browser.driver.execute_script.assert_not_called()


def test_legacy_row_uses_existing_element_and_invalidates_refs_without_click():
    browser = Browser()
    browser.driver = Mock()
    browser.driver.execute_script.return_value = ['_id']
    browser.document = Mock()
    element = Mock(tag_name='tr')
    browser.elements = {'row': element}
    browser.is_visible = Mock(return_value=True)
    assert browser.prepare_legacy_row('row', ['_id'])['copied'] == ['_id']
    assert browser.driver.execute_script.call_args.args[1:] == (element, ['_id'])
    element.click.assert_not_called()
    assert not browser.elements


def test_window_handles_only_preserves_references_and_context():
    browser = Browser()
    driver = browser.driver = Mock()
    driver.current_window_handle = 'main'
    driver.window_handles = ['popup', 'main']
    browser.elements = {'field': Mock()}
    assert browser.windows() == {'current': 'main', 'handles': ['popup', 'main']}
    driver.switch_to.window.assert_not_called()
    assert 'field' in browser.elements


def test_open_page_uses_current_page_opener_and_passes_url_as_argument():
    browser = Browser()
    driver = browser.driver = Mock()
    type(driver).window_handles = PropertyMock(side_effect=[['main'], ['child', 'main']])
    driver.current_url = 'https://example.test/child'
    driver.execute_script.side_effect = [None, 'complete']
    browser.snapshot = Mock(return_value={'text': 'Child ready'})
    url = 'https://example.test/child?name="quoted"'
    assert browser.open_page(url) == {'text': 'Child ready'}
    script, target, name = driver.execute_script.call_args_list[0].args
    assert target == url and url not in script
    # IE7's window.open rejects names containing hyphens or spaces.
    assert name.isascii() and name.isidentifier()
    driver.switch_to.new_window.assert_not_called()
    driver.switch_to.window.assert_called_once_with('child')
    driver.get.assert_not_called()


def test_open_page_does_not_choose_arbitrarily_if_two_windows_appear():
    browser = Browser()
    driver = browser.driver = Mock()
    type(driver).window_handles = PropertyMock(side_effect=[['main'], ['child', 'other', 'main']])
    with pytest.raises(RuntimeError, match='Multiple new windows'):
        browser.open_page('https://example.test/child')
    driver.switch_to.window.assert_not_called()
    assert driver.execute_script.call_count == 1


@pytest.mark.parametrize('include_details', [False, True])
def test_window_listing_recovers_handles_after_page_closes_itself(include_details):
    from selenium.common.exceptions import NoSuchWindowException
    browser = Browser()
    driver = browser.driver = Mock()
    driver.window_handles = ['main']
    type(driver).current_window_handle = PropertyMock(side_effect=NoSuchWindowException('Window is closed'))
    browser.elements = {'stale': Mock()}
    result = browser.windows(include_details=include_details)
    assert result['current'] is None
    assert result['handles'] == ['main']
    driver.switch_to.window.assert_not_called()
    assert not browser.elements


def test_window_details_identifies_unordered_handles_and_restores_original():
    browser = Browser()
    driver = browser.driver = Mock()
    driver.current_window_handle = 'main'
    driver.window_handles = ['popup', 'main']
    def switch(handle):
        driver.current_url = 'https://example.test/' + handle
        driver.title = handle + ' title'
    driver.switch_to.window.side_effect = switch
    browser.elements = {'old': Mock()}
    result = browser.windows(include_details=True)
    assert result['windows'] == [
        {'handle': 'popup', 'url': 'https://example.test/popup', 'title': 'popup title'},
        {'handle': 'main', 'url': 'https://example.test/main', 'title': 'main title'}]
    assert driver.switch_to.window.call_args.args == ('main',)
    assert not browser.elements


def test_window_details_restores_original_when_a_prompt_interrupts_listing():
    from selenium.common.exceptions import UnexpectedAlertPresentException
    browser = Browser()
    driver = browser.driver = Mock()
    driver.current_window_handle = 'main'
    driver.window_handles = ['popup', 'main']
    driver.switch_to.window.side_effect = [UnexpectedAlertPresentException(), None]
    with pytest.raises(UnexpectedAlertPresentException):
        browser.windows(include_details=True)
    assert driver.switch_to.window.call_args.args == ('main',)
    driver.switch_to.alert.accept.assert_not_called()
    driver.switch_to.alert.dismiss.assert_not_called()


@pytest.mark.parametrize('attribute', ['is_displayed', 'is_enabled'])
def test_dom_click_rejects_hidden_or_disabled(attribute):
    browser = Browser()
    browser.driver = Mock()
    browser.document = Mock()
    element = Mock()
    getattr(element, attribute).return_value = False
    browser.is_visible = Mock(return_value=attribute != 'is_displayed')
    browser.elements = {'a': element}
    with pytest.raises(ValueError, match='visible, enabled'):
        browser.act('click', 'a', click_mode='dom')
    browser.driver.execute_script.assert_not_called()
    element.click.assert_not_called()


@pytest.mark.parametrize('kind', ['relative', 'missing', 'directory', 'multiple'])
def test_choose_file_rejects_invalid_paths_before_touching_browser(tmp_path, kind):
    browser = Browser()
    browser.resolve = Mock()
    paths = {'relative': 'file.txt', 'missing': str(tmp_path / 'absent.txt'),
             'directory': str(tmp_path), 'multiple': str(tmp_path / 'a\nb')}
    with pytest.raises(ValueError, match='one absolute path'):
        browser.choose_file('ref', paths[kind])
    browser.resolve.assert_not_called()


@pytest.mark.parametrize('condition', ['text', 'hidden', 'disabled', 'legacy', 'success', 'mismatch', 'failure'])
def test_choose_file_validates_target_and_never_retries(tmp_path, condition):
    path = tmp_path / 'attachment.txt'
    path.write_text('PRIVATE FILE CONTENT', encoding='utf-8')
    browser = Browser()
    browser.driver = Mock()
    browser.driver.file_detector_context.return_value = nullcontext()
    browser.driver.execute_script.side_effect = [7 if condition == 'legacy' else 11,
        r'C:\fakepath\attachment.txt' if condition != 'mismatch' else '']
    browser.document = Mock()
    element = Mock()
    element.tag_name = 'input'
    element.get_dom_attribute.return_value = 'text' if condition == 'text' else 'file'
    element.is_enabled.return_value = condition != 'disabled'
    browser.is_visible = Mock(return_value=condition != 'hidden')
    browser.elements = {'ref': element}
    if condition in ('text', 'hidden', 'disabled', 'legacy'):
        with pytest.raises(ValueError):
            browser.choose_file('ref', str(path))
        element.send_keys.assert_not_called()
    else:
        if condition == 'failure':
            element.send_keys.side_effect = TimeoutException()
        if condition in ('failure', 'mismatch'):
            with pytest.raises((TimeoutException, RuntimeError)):
                browser.choose_file('ref', str(path))
        else:
            result = browser.choose_file('ref', str(path))
            assert result['selected'] is True
            assert result['filename'] == path.name
            assert str(tmp_path) not in str(result) and 'PRIVATE FILE CONTENT' not in str(result)
        element.send_keys.assert_called_once_with(str(path.resolve()))
        assert not browser.elements
    element.click.assert_not_called()
