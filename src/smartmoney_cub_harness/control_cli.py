"""Command/JSON front door to the same operations used by the workbench."""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import getpass
import json
import os
import sys
import time
from pathlib import Path

from smartmoney_cub_harness.control_operations import OPERATIONS, capabilities
from smartmoney_cub_harness.control_runtime import ControlError, ControlRuntime
from smartmoney_cub_harness.schemas import SAFETY_DECLARATION
from smartmoney_cub_harness.safety import redact


FIELDS = ('provider', 'provider_id', 'plugin_id', 'symbol', 'interval', 'start', 'end',
          'account_id', 'portfolio_id', 'round_trip_id', 'session_id', 'run_id', 'rule_id',
          'strategy_id', 'promotion_id', 'profile_id', 'agent_id', 'preset_id', 'filename',
          'dimension', 'text', 'note', 'source', 'action')
NUMBERS = ('limit', 'offset', 'year', 'month', 'index', 'after_seq')


def _common(parser):
    parser.add_argument('--input', help='JSON object file, or - for stdin; never put secrets in argv')
    parser.add_argument('--set', action='append', default=[], metavar='KEY=VALUE', help='Set a non-secret input field; VALUE may be JSON')
    parser.add_argument('--json', action='store_true', help='Machine-readable result (JSONL for streams)')
    parser.add_argument('--state-dir')
    parser.add_argument('--server', help='Explicit HTTP(S) service URL; never falls back to local')
    parser.add_argument('--principal', default='human', help='Caller identity; integrations require grants')
    parser.add_argument('--run-root', help='Human-configured artifact boundary for integrations')
    parser.add_argument('--confirm', action='store_true', help='Explicit human confirmation of this exact invocation')
    parser.add_argument('--allow-network', action='store_true', help='Allow this invocation to reach its configured provider')
    parser.add_argument('--approval-id', help='Consume a human-approved request for this exact operation')
    parser.add_argument('--timeout', type=float, default=30)
    parser.add_argument('--output', help='Explicit output file; existing files require --overwrite')
    parser.add_argument('--overwrite', action='store_true')
    parser.add_argument('--format', choices=('json','html','csv'), default='json')
    parser.add_argument('--locale', help='Human-readable output locale (structured keys remain stable)')
    parser.add_argument('--configure', action='store_true', help='Run a human-only setup wizard with hidden secret input')
    parser.add_argument('--budget-usd', type=str, help='Explicit per-invocation model spending cap')
    parser.add_argument('--pricing-file', help='User-verified model input/output prices in USD per million tokens')
    parser.add_argument('--max-provider-calls', type=int, default=1)
    for field in FIELDS:
        parser.add_argument('--' + field.replace('_','-'))
    for field in NUMBERS:
        parser.add_argument('--' + field.replace('_','-'), type=int)


def register_control_commands(sub):
    direct = sub.add_parser('operation', help='Invoke a registered WebUI business operation')
    direct.add_argument('operation_name', choices=tuple(OPERATIONS))
    _common(direct)
    direct.set_defaults(control_operation=True)
    caps = sub.add_parser('capabilities', help='Describe CLI protocol and business operation contracts')
    caps.add_argument('--json', action='store_true')
    caps.set_defaults(control_operation=True, operation_name='capabilities')
    permissions = sub.add_parser('permissions', help='Inspect/revoke capabilities and confirm exact human requests')
    actions = permissions.add_subparsers(dest='permission_action', required=True)
    for action in ('list','grant','revoke','request','approve'):
        p = actions.add_parser(action)
        _common(p)
        p.set_defaults(control_operation=True, operation_name='permissions.' + action)
    for name, op in OPERATIONS.items():
        group, verb = name.split('.', 1)
        if group == 'permissions':
            continue
        if group not in sub.choices:
            parent = sub.add_parser(group, help=group + ' business operations')
            children = parent.add_subparsers(dest=group + '_action', required=True)
        else:
            parent = sub.choices[group]
            children = next((a for a in parent._actions if isinstance(a, argparse._SubParsersAction)), None)
            if children is None:
                continue
        if verb in children.choices:
            continue  # old public command contracts remain untouched
        p = children.add_parser(verb, help=op.method + ' ' + (op.path or 'local operation'))
        _common(p)
        p.set_defaults(control_operation=True, operation_name=name)


def _value(text):
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def _payload(args):
    payload = {}
    if args.input:
        if args.input == '-':
            payload = json.load(sys.stdin)
        else:
            path = Path(args.input).expanduser()
            if args.principal != 'human':
                from smartmoney_cub_harness.control_permissions import _reject_symlink_components
                _reject_symlink_components(path)
                if not args.run_root or not path.resolve().is_relative_to(Path(args.run_root).resolve(strict=True)):
                    raise PermissionError('input file is outside configured run_root')
            payload = json.loads(path.read_text())
            if _has_secret(payload) and path.stat().st_mode & 0o077:
                raise PermissionError('credential input files must be accessible only to their owner (chmod 600)')
        if not isinstance(payload, dict):
            raise ValueError('input must be a JSON object')
    for assignment in args.set:
        key, separator, value = assignment.partition('=')
        if not separator or not key:
            raise ValueError('--set expects KEY=VALUE')
        if any(word in key.lower() for word in ('secret','password','credential','api_key','cookie','token')):
            raise PermissionError('secret fields cannot be supplied in command-line arguments')
        parsed = _value(value)
        if _has_secret({key: parsed}):
            raise PermissionError('secret fields cannot be supplied in command-line arguments')
        payload[key] = parsed
    for name in FIELDS + NUMBERS:
        value = getattr(args, name)
        if value is not None:
            payload[name] = value
    return payload


def _has_secret(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if not key.endswith('_env') and any(word in key.lower() for word in ('secret', 'password', 'api_key', 'cookie', 'access_token')):
                return True
            if _has_secret(item):
                return True
    elif isinstance(value, list):
        return any(_has_secret(item) for item in value)
    return False


def _confirmed(args, name):
    if args.principal != 'human':
        if args.confirm:
            raise PermissionError('integrations cannot self-confirm')
        return False
    if args.confirm:
        return True
    needs = args.configure or name in {'permissions.grant', 'permissions.revoke', 'permissions.approve'} or bool(OPERATIONS.get(name) and OPERATIONS[name].confirmation)
    if needs and sys.stdin.isatty() and not args.json:
        sys.stderr.write('Confirm ' + name + ' for the supplied inputs? Type yes: ')
        return input().strip().lower() == 'yes'
    return False


def _configure(args, runtime, name, payload, info):
    if args.principal != 'human' or args.server or not runtime.confirmed:
        raise PermissionError('configuration requires local human confirmation')
    from smartmoney_cub_harness.control_setup import configure
    values = dict(payload.get('values') or {})
    # Environment references avoid putting a credential in argv or a JSON file.
    for key in tuple(values):
        if key.endswith('_env'):
            variable = str(values.pop(key))
            if variable not in os.environ:
                raise ControlError('missing_configuration', 'Required credential environment variable is not set', 4)
            values[key[:-4]] = os.environ[variable]
    for link in info.get('official_links', []):
        print(link['label'] + ': ' + link['url'], file=sys.stderr)
    for field in info.get('required_fields', []):
        if field.get('reference'):
            continue
        key = field['name']
        if key in values:
            continue
        if not sys.stdin.isatty():
            if field.get('required'):
                raise ControlError('missing_configuration', 'Required field: ' + key + '; use protected JSON values or an environment reference', 4)
            continue
        prompt = key + (' (hidden)' if field.get('secret') else '') + ': '
        if field.get('secret'):
            value = getpass.getpass(prompt, stream=sys.stderr)
        else:
            print(prompt, end='', file=sys.stderr, flush=True)
            value = input()
        value = value or field.get('value', '')
        if not value and field.get('required'):
            raise ControlError('missing_configuration', key + ' is required', 4)
        if value:
            values[key] = value
        elif field.get('value'):
            values[key] = field['value']
    identifier = info['identifier']
    if name == 'connections.setup':
        return runtime.execute('connections.connect', {'provider_id': identifier, 'credentials': values, 'config': payload.get('config', {})})
    return configure(name.split('.')[0], identifier, runtime.root, values)


def _emit(value, args):
    if isinstance(value, bytes):
        if not args.output:
            raise ControlError('output_required', 'Binary artifacts require --output')
        data = value
    else:
        value = redact(value)
        if args.format != 'json':
            from smartmoney_cub_harness.control_exports import render_result
            rendered = render_result(value, args.format)
        else:
            rendered = json.dumps(value, ensure_ascii=False, indent=None if args.json else 2)
        data = (rendered + '\n').encode('utf-8')
    if args.output:
        path = Path(args.output).expanduser()
        if args.principal != 'human':
            from smartmoney_cub_harness.control_permissions import _reject_symlink_components
            _reject_symlink_components(path)
            if not args.run_root or not path.resolve().is_relative_to(Path(args.run_root).resolve(strict=True)):
                raise PermissionError('output is outside configured run_root')
        if path.is_symlink():
            raise PermissionError('output symlinks are refused')
        if not getattr(args, '_output_handle', None):
            args._output_handle = path.open('wb' if args.overwrite else 'xb')
            sys.stderr.write('Output written. ' + SAFETY_DECLARATION + '\n')
        args._output_handle.write(data)
        args._output_handle.flush()
    else:
        sys.stdout.write(data.decode('utf-8'))


def run_control(args):
    runtime = None
    contexts = ExitStack()
    try:
        name = args.operation_name
        if name == 'capabilities':
            print(json.dumps(capabilities(), ensure_ascii=False, indent=None if args.json else 2))
            return 0
        payload = _payload(args)
        if args.configure and not name.endswith('.setup'):
            raise ValueError('--configure is only valid with setup commands')
        confirmation = _confirmed(args, name)
        from smartmoney_cub_harness.control_budget import BudgetGuard, paid_budget
        if (args.budget_usd is None) != (args.pricing_file is None):
            raise ControlError('budget_configuration_required', '--budget-usd and --pricing-file must be supplied together', 4)
        pricing = json.loads(Path(args.pricing_file).read_text()) if args.pricing_file else {
            '__unpriced__': {'input_usd_per_million': 0, 'output_usd_per_million': 0}}
        budget_spec = {'cap_usd': args.budget_usd or '0', 'pricing': pricing, 'max_calls': args.max_provider_calls}
        contexts.enter_context(paid_budget(BudgetGuard(**budget_spec)))
        runtime = ControlRuntime(state_dir=args.state_dir, server=args.server, principal=args.principal,
                                 run_root=args.run_root, confirmed=confirmation, allow_network=args.allow_network,
                                 approval_id=args.approval_id, timeout=args.timeout, budget_spec=budget_spec)
        if name in {'permissions.list','permissions.grant','permissions.revoke','permissions.approve'}:
            if args.principal != 'human':
                raise PermissionError('only the human administration interface manages grants')
            if args.server:
                raise ControlError('local_admin_required', 'Manage grants on the service host')
            store = runtime.permissions
            if name == 'permissions.list':
                result = store.list(payload.get('principal'))
            else:
                if not confirmation:
                    raise PermissionError('explicit human --confirm is required')
                if name == 'permissions.grant':
                    capability = str(payload.get('capability') or '')
                    if capability not in OPERATIONS and not (capability.endswith('.*') and any(n.startswith(capability[:-1]) for n in OPERATIONS)):
                        raise ValueError('capability must name a registered operation or family')
                    result = store.grant(str(payload.get('principal') or 'hermes'), capability, dict(payload.get('scope') or {}))
                elif name == 'permissions.revoke':
                    result = store.revoke(str(payload.get('grant_id') or ''))
                else:
                    result = store.approve(str(payload.get('request_id') or ''), True, str(payload.get('note') or ''))
        elif name == 'connections.authorize':
            from smartmoney_cub_harness.control_oauth import authorize
            result = authorize(runtime, payload, lambda value: _emit(value, args))
        elif name == 'replay.play':
            delay = float(payload.pop('delay', 0.4))
            maximum = int(payload.pop('max_steps', 10000))
            if delay < 0.05 or not 0 < maximum <= 10000:
                raise ValueError('delay >= 0.05 and 1 <= max_steps <= 10000 required')
            runtime.execute('replay.play', payload)
            try:
                for _ in range(maximum):
                    result = runtime.execute('replay.action', {**payload, 'action': 'tick'})
                    _emit(result, args)
                    record = result.get('session', result)
                    if not record.get('playing') or record.get('cursor', 0) >= record.get('bar_count', 1) - 1:
                        break
                    time.sleep(delay)
            finally:
                runtime.execute('replay.pause', payload)
            return 0
        elif name == 'connections.watch':
            delay = float(payload.pop('delay', 30))
            if delay < 1:
                raise ValueError('watch interval must be at least one second')
            while True:
                result = runtime.execute('connections.sync', payload)
                _emit(result, args)
                time.sleep(delay)
        else:
            result = runtime.execute(name, payload)
            if args.configure:
                if not name.endswith('.setup'):
                    raise ValueError('--configure is only valid with setup commands')
                result = _configure(args, runtime, name, payload, result)
        if OPERATIONS.get(name) and OPERATIONS[name].stream:
            stream_failed = False
            try:
                for event in result:
                    _emit(event, args)
                    if isinstance(event, dict) and (event.get('kind') == 'error' or event.get('status') in {'error', 'failed', 'blocked'}):
                        stream_failed = True
            except KeyboardInterrupt:
                runtime.execute('assistant.cancel', {'session_id': payload['session_id']})
                raise
            if stream_failed:
                return 5
        else:
            if isinstance(result, tuple) and name == 'benchmark.image':
                result = result[0]
            _emit(result, args)
            if isinstance(result, dict) and (result.get('partial') or result.get('status') in {'partial','error','failed','blocked','not_found'}):
                return 7 if result.get('partial') else 5
        return 0
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        status = getattr(exc, 'exit_code', 3 if isinstance(exc, PermissionError) else 2)
        value = {'status': 'error', 'error': {'code': getattr(exc, 'code', 'permission_denied' if isinstance(exc, PermissionError) else 'invalid_request'),
                 'message': str(redact(str(exc)))}, 'safety': SAFETY_DECLARATION}
        print(json.dumps(value, ensure_ascii=False), file=sys.stdout if getattr(args, 'json', False) else sys.stderr)
        return status
    finally:
        if getattr(args, '_output_handle', None):
            args._output_handle.close()
        if runtime:
            runtime.close()
        contexts.close()
