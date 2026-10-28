"""Installation helpers. No browser or system-policy changes without a probe."""
import argparse
import asyncio
from importlib.metadata import version
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from uuid import uuid4

from .browser import doctor


def server_config():
    return {'command': str(Path(sys.executable).resolve()), 'args': ['-m', 'ie_mode_mcp.server']}


def codex_run(*args):
    executable = shutil.which('codex')
    if not executable:
        raise RuntimeError('Codex CLI was not found. Use ie-mode-setup config and add that configuration to your MCP client.')
    return subprocess.run([executable, 'mcp', *args], capture_output=True, text=True,
                          encoding='utf-8', errors='replace', timeout=30)


def existing_codex_config():
    result = codex_run('list', '--json')
    if result.returncode:
        raise RuntimeError('Cannot read Codex MCP configuration: ' + result.stderr.strip())
    entries = json.loads(result.stdout)
    return next((entry for entry in entries if entry['name'] == 'ie-mode'), None)


def transport(config):
    return config.get('transport', config)


def matches_current(config):
    saved, wanted = transport(config), server_config()
    return (config.get('enabled', True) is not False and saved.get('type', 'stdio') == 'stdio'
            and os.path.normcase(saved.get('command', '')) == os.path.normcase(wanted['command'])
            and saved.get('args', []) == wanted['args'])


def install_codex(replace=False):
    existing = existing_codex_config()
    if existing and matches_current(existing):
        return {'installed': True, 'changed': False, 'server': 'ie-mode'}
    backup = None
    if existing:
        if not replace:
            raise RuntimeError('ie-mode is already configured differently. Inspect it first; use install --replace to explicitly replace it.')
        directory = Path(os.environ.get('LOCALAPPDATA', str(Path.home() / 'AppData/Local'))) / 'ie-mode-mcp' / 'config-backups'
        directory.mkdir(parents=True, exist_ok=True)
        backup = directory / (str(uuid4()) + '.json')
        backup.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding='utf-8')
    config = server_config()
    result = codex_run('add', 'ie-mode', '--', config['command'], *config['args'])
    if result.returncode:
        raise RuntimeError('Codex registration failed: ' + result.stderr.strip())
    saved = existing_codex_config()
    if not saved or not matches_current(saved):
        raise RuntimeError('Codex registration readback did not match. Inspect codex mcp get ie-mode --json.')
    return {'installed': True, 'changed': True, 'server': 'ie-mode',
            'previous_config_backup': str(backup) if backup else None,
            'next': 'Run ie-mode-setup check; reload MCP in your client. Browser readiness still requires ie-mode-probe with your URL.'}


def uninstall_codex():
    existing = existing_codex_config()
    if not existing:
        return {'removed': False, 'reason': 'not_registered'}
    saved = transport(existing)
    command = Path(saved.get('command', '')).name.lower()
    ours = (saved.get('args') == ['-m', 'ie_mode_mcp.server'] or command in ('ie-mode-mcp', 'ie-mode-mcp.exe'))
    if not ours:
        raise RuntimeError('ie-mode points to another program; refusing to remove it.')
    result = codex_run('remove', 'ie-mode')
    if result.returncode or existing_codex_config() is not None:
        raise RuntimeError('Codex removal could not be verified.')
    return {'removed': True, 'note': 'Only the Codex registration was removed. Package and browser windows were not changed.'}


async def protocol_check():
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    config = server_config()
    async with asyncio.timeout(30):
        async with stdio_client(StdioServerParameters(**config)) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                status = await session.call_tool('browser_status', {})
                if status.isError or not {'browser_start', 'browser_find', 'browser_sessions'}.issubset({t.name for t in tools.tools}):
                    raise RuntimeError('MCP status or tool discovery failed.')
                return {'mcp_connected': True, 'tool_count': len(tools.tools),
                        'config': config, 'browser_started': False,
                        'note': 'Checks this installation over stdio, not client reload or IE browser readiness.'}


def main():
    parser = argparse.ArgumentParser(description='Install, configure and diagnose ie-mode-mcp without editing system policies.')
    commands = parser.add_subparsers(dest='action', required=True)
    commands.add_parser('doctor', help='Read prerequisites and installed version; does not launch IE')
    config = commands.add_parser('config', help='Print configuration with absolute paths')
    config.add_argument('--format', choices=['json', 'toml'], default='json')
    install = commands.add_parser('install', help='Register this installation as ie-mode in Codex using its CLI')
    install.add_argument('--replace', action='store_true', help='Back up and replace a different existing ie-mode registration')
    commands.add_parser('uninstall', help='Remove only this tool registration from Codex')
    commands.add_parser('check', help='Verify stdio initialization and tools; does not launch a browser')
    args = parser.parse_args()
    try:
        if args.action == 'doctor':
            result = {**doctor(), 'version': version('ie-mode-mcp'), 'python': sys.executable,
                      'codex_cli': shutil.which('codex')}
        elif args.action == 'config':
            config = server_config()
            if args.format == 'toml':
                print('[mcp_servers.ie-mode]\ncommand = ' + json.dumps(config['command'], ensure_ascii=False)
                      + '\nargs = ' + json.dumps(config['args']))
                return
            result = {'mcpServers': {'ie-mode': config}}
        elif args.action == 'install':
            result = install_codex(args.replace)
        elif args.action == 'uninstall':
            result = uninstall_codex()
        else:
            result = asyncio.run(protocol_check())
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (RuntimeError, OSError, ValueError, TimeoutError, subprocess.SubprocessError) as error:
        print(json.dumps({'error': str(error)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)


if __name__ == '__main__':
    main()
