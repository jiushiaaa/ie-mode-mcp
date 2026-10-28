import json
from unittest.mock import Mock

import pytest

from ie_mode_mcp.browser import Browser
from ie_mode_mcp import setup


def test_regional_snapshot_pagination_returns_new_scope_and_expires_old_refs():
    browser = Browser()
    browser.driver = Mock()
    browser.document = Mock()
    region = Mock()
    browser.elements = {'region': region}
    browser.is_visible = Mock(return_value=True)
    browser.driver.execute_script.return_value = {'document': Mock(), 'controls': [], 'text': 'page 2'}
    result = browser.snapshot(root_ref='region', offset=200, text_offset=12000)
    args = browser.driver.execute_script.call_args.args
    assert args[2:] == (region, 200, 200, 12000, 12000)
    assert 'region' not in browser.elements
    assert browser.elements[result['scope_ref']] == region


@pytest.mark.parametrize('kwargs', [{'offset': -1}, {'limit': 201}, {'text_limit': 32001}, {'text_offset': -1}])
def test_snapshot_rejects_bad_bounds_without_invalidating(kwargs):
    browser = Browser()
    browser.elements['keep'] = Mock()
    with pytest.raises(ValueError):
        browser.snapshot(**kwargs)
    assert 'keep' in browser.elements


def test_search_returns_actionable_refs_without_clicking():
    browser = Browser()
    browser.driver = Mock()
    element = Mock()
    browser.elements = {'old': Mock()}
    browser.driver.execute_script.return_value = {'document': Mock(), 'matches': [{'element': element}], 'total': 1}
    result = browser.find('form', by='tag')
    assert browser.resolve(result['matches'][0]['ref']) is element
    assert 'old' not in browser.elements
    element.click.assert_not_called()


@pytest.mark.parametrize('query,kwargs', [('', {}), ('x', {'by': 'js'}), ('x', {'limit': 0}), ('x', {'offset': -1})])
def test_search_validates_before_executing(query, kwargs):
    browser = Browser()
    browser.driver = Mock()
    with pytest.raises(ValueError):
        browser.find(query, **kwargs)
    browser.driver.execute_script.assert_not_called()


def test_element_screenshot_invalidates_references():
    browser = Browser()
    browser.driver = Mock()
    browser.document = Mock()
    element = Mock(screenshot_as_png=b'png')
    browser.elements['target'] = element
    browser.is_visible = Mock(return_value=True)
    assert browser.screenshot('target') == b'png'
    assert not browser.elements


def test_disabled_registration_is_not_claimed_installed(monkeypatch):
    monkeypatch.setattr(setup, 'existing_codex_config', lambda: {'enabled': False, 'transport': setup.server_config()})
    with pytest.raises(RuntimeError, match='--replace'):
        setup.install_codex()


def test_transport_failure_is_not_retried_after_start(monkeypatch):
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from threading import Thread
    from selenium.webdriver.remote.client_config import ClientConfig
    from selenium.webdriver.remote.remote_connection import RemoteConnection
    from urllib3.exceptions import HTTPError
    requests = []
    class Disconnect(BaseHTTPRequestHandler):
        def do_DELETE(self):
            requests.append(self.path)
            self.close_connection = True
    http = ThreadingHTTPServer(('127.0.0.1', 0), Disconnect)
    Thread(target=http.serve_forever, daemon=True).start()
    url = f'http://127.0.0.1:{http.server_port}'
    connection = RemoteConnection(client_config=ClientConfig(remote_server_addr=url, keep_alive=True))
    browser = Browser()
    driver = Mock(command_executor=connection)
    monkeypatch.setattr('ie_mode_mcp.browser.platform.system', lambda: 'Windows')
    monkeypatch.setattr('ie_mode_mcp.browser.desktop_status', lambda: {'state': 'unlocked'})
    monkeypatch.setattr('ie_mode_mcp.browser.edge_path', lambda: 'C:/Edge/msedge.exe')
    monkeypatch.setattr('ie_mode_mcp.browser.webdriver.Ie', lambda **kwargs: driver)
    browser.navigate = Mock(return_value={})
    try:
        browser.start('https://example.com')
        with pytest.raises(HTTPError):
            connection._request('DELETE', url + '/session/fixture')
        assert requests == ['/session/fixture']
        browser.close()
        assert connection.client_config.timeout == 5
    finally:
        connection.close()
        http.shutdown()
        http.server_close()


def test_install_refuses_existing_configuration_by_default(monkeypatch):
    monkeypatch.setattr(setup, 'existing_codex_config', lambda: {'name': 'ie-mode', 'transport': {'command': 'another-program'}})
    run = Mock()
    monkeypatch.setattr(setup, 'codex_run', run)
    with pytest.raises(RuntimeError, match='--replace'):
        setup.install_codex()
    run.assert_not_called()


def test_install_is_idempotent(monkeypatch):
    monkeypatch.setattr(setup, 'existing_codex_config', lambda: {'transport': setup.server_config()})
    run = Mock()
    monkeypatch.setattr(setup, 'codex_run', run)
    assert not setup.install_codex()['changed']
    run.assert_not_called()


def test_replace_backs_up_old_configuration_and_verifies_readback(tmp_path, monkeypatch):
    old = {'transport': {'command': 'old-command', 'args': []}}
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path))
    monkeypatch.setattr(setup, 'existing_codex_config', Mock(side_effect=[old, {'transport': setup.server_config()}]))
    run = Mock(return_value=Mock(returncode=0))
    monkeypatch.setattr(setup, 'codex_run', run)
    result = setup.install_codex(replace=True)
    from pathlib import Path
    assert json.loads(Path(result['previous_config_backup']).read_text(encoding='utf-8')) == old
    run.assert_called_once_with('add', 'ie-mode', '--', setup.server_config()['command'], '-m', 'ie_mode_mcp.server')


def test_install_does_not_claim_success_when_readback_differs(monkeypatch):
    monkeypatch.setattr(setup, 'existing_codex_config', Mock(side_effect=[None, {'command': 'wrong'}]))
    monkeypatch.setattr(setup, 'codex_run', Mock(return_value=Mock(returncode=0)))
    with pytest.raises(RuntimeError, match='readback'):
        setup.install_codex()


def test_uninstall_refuses_another_program(monkeypatch):
    monkeypatch.setattr(setup, 'existing_codex_config', lambda: {'command': 'other', 'args': []})
    run = Mock()
    monkeypatch.setattr(setup, 'codex_run', run)
    with pytest.raises(RuntimeError, match='another program'):
        setup.uninstall_codex()
    run.assert_not_called()


def test_uninstall_verifies_removal(monkeypatch):
    monkeypatch.setattr(setup, 'existing_codex_config', Mock(side_effect=[setup.server_config(), None]))
    run = Mock(return_value=Mock(returncode=0))
    monkeypatch.setattr(setup, 'codex_run', run)
    assert setup.uninstall_codex()['removed']
    run.assert_called_once_with('remove', 'ie-mode')
