from unittest.mock import Mock, PropertyMock

import pytest
from selenium.common.exceptions import (
    InvalidSessionIdException, NoSuchWindowException, TimeoutException,
    UnexpectedAlertPresentException,
)
from selenium.webdriver.common.keys import Keys

from ie_mode_mcp.browser import Browser


def controlled():
    browser = Browser()
    browser.driver = Mock()
    browser.document = Mock()
    element = Mock(tag_name='input')
    element.get_dom_attribute.return_value = 'text'
    browser.elements = {'target': element}
    browser.is_visible = Mock(return_value=True)
    return browser, element


@pytest.mark.parametrize('action,method', [('double', 'double_click'), ('right', 'context_click')])
def test_extended_click_dispatches_once_and_invalidates(monkeypatch, action, method):
    browser, element = controlled()
    chain = Mock()
    getattr(chain, method).return_value = chain
    factory = Mock(return_value=chain)
    monkeypatch.setattr('ie_mode_mcp.browser.ActionChains', factory)
    browser.act(action, 'target')
    getattr(chain, method).assert_called_once_with(element)
    chain.perform.assert_called_once()
    element.click.assert_not_called()
    assert not browser.elements


def test_double_click_failure_is_not_retried(monkeypatch):
    browser, element = controlled()
    chain = Mock()
    chain.double_click.return_value = chain
    chain.perform.side_effect = TimeoutException()
    monkeypatch.setattr('ie_mode_mcp.browser.ActionChains', Mock(return_value=chain))
    with pytest.raises(TimeoutException):
        browser.act('double', 'target')
    chain.perform.assert_called_once()
    element.click.assert_not_called()
    assert not browser.elements


@pytest.mark.parametrize('action', ['double', 'right'])
def test_extended_click_rejects_dom_mode_before_resolving(action):
    browser = Browser()
    browser.resolve = Mock()
    with pytest.raises(ValueError, match='native'):
        browser.act(action, 'target', click_mode='dom')
    browser.resolve.assert_not_called()


def test_key_chord_targets_element_and_releases_modifiers():
    browser, element = controlled()
    result = browser.press_key('target', 'a', ['CONTROL'])
    element.send_keys.assert_called_once_with(Keys.CONTROL, 'a', Keys.NULL)
    element.click.assert_not_called()
    assert result['performed'] == 'press_key' and not browser.elements


@pytest.mark.parametrize('key,modifiers', [('ENTER', ['META']), ('hello', []),
                                         ('a', ['CONTROL', 'CONTROL']), ('\n', [])])
def test_key_rejects_bad_input_before_resolving(key, modifiers):
    browser = Browser()
    browser.resolve = Mock()
    with pytest.raises(ValueError):
        browser.press_key('target', key, modifiers)
    browser.resolve.assert_not_called()


@pytest.mark.parametrize('operation', ['key', 'hover', 'double', 'right'])
@pytest.mark.parametrize('condition', ['hidden', 'disabled'])
def test_interactions_reject_ineligible_targets(operation, condition):
    browser, element = controlled()
    browser.is_visible.return_value = condition != 'hidden'
    element.is_enabled.return_value = condition != 'disabled'
    with pytest.raises(ValueError, match='visible, enabled'):
        if operation == 'key':
            browser.press_key('target', 'ENTER')
        elif operation == 'hover':
            browser.hover('target')
        else:
            browser.act(operation, 'target')
    element.send_keys.assert_not_called()


def test_key_cannot_open_file_picker():
    browser, element = controlled()
    element.get_dom_attribute.return_value = 'file'
    with pytest.raises(ValueError, match='file input'):
        browser.press_key('target', 'ENTER')
    element.send_keys.assert_not_called()


def test_hover_never_clicks(monkeypatch):
    browser, element = controlled()
    chain = Mock()
    chain.move_to_element.return_value = chain
    monkeypatch.setattr('ie_mode_mcp.browser.ActionChains', Mock(return_value=chain))
    browser.hover('target')
    chain.move_to_element.assert_called_once_with(element)
    chain.perform.assert_called_once()
    element.click.assert_not_called()
    assert not browser.elements


@pytest.mark.parametrize('direction,pixels,ref', [('sideways', 1, None), ('down', -1, None),
                                                ('into_view', 1, None), ('down', 1, 'target')])
def test_scroll_rejects_ambiguous_or_invalid_arguments(direction, pixels, ref):
    browser, _ = controlled()
    with pytest.raises(ValueError):
        browser.scroll(direction, pixels, ref)
    browser.driver.execute_script.assert_not_called()


def test_scroll_into_view_passes_observed_element_as_argument():
    browser, element = controlled()
    browser.scroll('into_view', ref='target')
    assert browser.driver.execute_script.call_args.args[1:] == ('into_view', 600, element)
    assert not browser.elements


def test_history_timeout_keeps_session_and_does_not_retry():
    browser, _ = controlled()
    driver = browser.driver
    driver.back.side_effect = TimeoutException()
    assert browser.history('back')['navigation_timed_out']
    driver.back.assert_called_once()
    driver.quit.assert_not_called()
    assert browser.driver is driver and not browser.elements


def test_resize_validates_bounds_and_returns_actual_size():
    browser, _ = controlled()
    with pytest.raises(ValueError):
        browser.resize(1, 800)
    browser.driver.set_window_size.assert_not_called()
    browser.driver.get_window_rect.return_value = {'width': 1000, 'height': 700}
    assert browser.resize(1000, 700)['window']['width'] == 1000
    assert not browser.elements


def test_status_does_not_launch_a_session():
    assert Browser().status() == {'session_exists': False, 'state': 'not_started'}


def test_status_preserves_refs_and_frame_on_healthy_session():
    browser, _ = controlled()
    browser.driver.window_handles = ['one']
    browser.driver.current_window_handle = 'one'
    assert browser.status()['state'] == 'ready'
    assert browser.elements
    browser.driver.switch_to.default_content.assert_not_called()


def test_status_distinguishes_closed_window_from_dead_session():
    browser, _ = controlled()
    browser.driver.window_handles = ['other']
    type(browser.driver).current_window_handle = PropertyMock(side_effect=NoSuchWindowException())
    result = browser.status()
    assert result['state'] == 'window_closed' and result['handles'] == ['other']
    assert not browser.elements


@pytest.mark.parametrize('error,state', [(InvalidSessionIdException(), 'unreachable'),
                                      (UnexpectedAlertPresentException(), 'dialog_open')])
def test_status_does_not_restart_or_accept_prompts(error, state):
    browser, _ = controlled()
    type(browser.driver).window_handles = PropertyMock(side_effect=error)
    assert browser.status()['state'] == state
    browser.driver.quit.assert_not_called()
    browser.driver.switch_to.alert.accept.assert_not_called()


def test_wait_ready_resets_stability_after_dom_change(monkeypatch):
    browser, _ = controlled()
    root = object()
    def probe(signature, complete=True):
        return {'document': root, 'signature': signature, 'complete': complete,
                'documents': 2, 'skipped_frames': 1, 'elements': 30}
    browser.driver.execute_script.side_effect = [probe('a'), probe('b'), probe('b'), probe('b')]
    monkeypatch.setattr('ie_mode_mcp.browser.monotonic', Mock(side_effect=[0, 0, 0.5, 1.0, 1.5, 1.5]))
    result = browser.wait_ready(seconds=3, stable_seconds=1)
    assert result['ready'] and result['skipped_frames'] == 1
    assert browser.driver.execute_script.call_count == 4
    assert 'signature' not in result and 'document' not in result and not browser.elements
    browser.driver.switch_to.default_content.assert_not_called()


def test_wait_ready_timeout_never_claims_success():
    browser, _ = controlled()
    browser.driver.execute_script.return_value = {'document': object(), 'signature': 'a',
        'complete': False, 'documents': 1, 'skipped_frames': 0, 'elements': 5}
    result = browser.wait_ready(seconds=1, stable_seconds=0.25)
    assert not result['ready'] and result['timed_out']


def test_wait_ready_preserves_prompt_error():
    browser, _ = controlled()
    browser.driver.execute_script.side_effect = UnexpectedAlertPresentException()
    with pytest.raises(UnexpectedAlertPresentException):
        browser.wait_ready()
    browser.driver.switch_to.alert.accept.assert_not_called()


def test_wait_text_can_wait_for_disappearance():
    browser, _ = controlled()
    ready = {'text': 'Done', 'controls': []}
    browser.snapshot = Mock(side_effect=[{'text': 'Loading'}, ready])
    assert browser.wait_text('Loading', seconds=2, gone=True) is ready
