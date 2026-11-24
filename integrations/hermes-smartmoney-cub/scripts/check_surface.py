# Validate the plugin surface the way Hermes does: import it, call register()
# with a recording stub context, and compare declared vs registered tools.
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import yaml

PLUGIN_DIR = Path(__file__).resolve().parents[1]


class RecordingContext:
    def __init__(self):
        self.tools: dict[str, dict] = {}
        self.hooks: list[str] = []
        self.skills: list[str] = []
        self.commands: list[str] = []
        self._config = {}

    def register_tool(self, name, toolset=None, schema=None, handler=None, **kw):
        assert schema and schema.get('name') == name, f'schema name mismatch for {name}'
        assert callable(handler), f'handler for {name} is not callable'
        self.tools[name] = {'toolset': toolset, 'schema': schema, 'handler': handler}

    def register_hook(self, name, callback):
        self.hooks.append(name)

    def register_skill(self, name, path):
        assert Path(path).exists(), f'skill file missing for {name}'
        self.skills.append(name)

    def register_command(self, name, handler, description='', args_hint=''):
        self.commands.append(name)

    def register_cli_command(self, *a, **k):
        raise AssertionError('unexpected register_cli_command')

    def get_config(self, key, default=None):
        return self._config.get(key, default)

    def set_config(self, key, value):
        self._config[key] = value


def main() -> int:
    manifest = yaml.safe_load((PLUGIN_DIR / 'plugin.yaml').read_text(encoding='utf-8'))

    spec = importlib.util.spec_from_file_location(
        'smcub_plugin', PLUGIN_DIR / '__init__.py',
        submodule_search_locations=[str(PLUGIN_DIR)],
    )
    pkg = importlib.util.module_from_spec(spec)
    sys.modules['smcub_plugin'] = pkg
    spec.loader.exec_module(pkg)

    ctx = RecordingContext()
    pkg.register(ctx)

    problems = []
    declared = set(manifest.get('provides_tools') or [])
    registered = set(ctx.tools)
    if declared != registered:
        problems.append(f'declared={sorted(declared)} registered={sorted(registered)}')

    declared_hooks = set(manifest.get('provides_hooks') or [])
    if declared_hooks != set(ctx.hooks):
        problems.append(f'hooks declared={sorted(declared_hooks)} registered={sorted(ctx.hooks)}')

    for name, entry in ctx.tools.items():
        out = entry['handler']({})
        assert isinstance(out, str), f'{name} did not return a string'
        json.loads(out)

    result = {
        'plugin': manifest['name'],
        'version': manifest['version'],
        'tools_registered': sorted(registered),
        'skills_registered': ctx.skills,
        'problems': problems,
    }
    print(json.dumps(result, indent=2))
    return 1 if problems else 0


if __name__ == '__main__':
    raise SystemExit(main())
