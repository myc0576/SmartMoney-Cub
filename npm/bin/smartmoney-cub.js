#!/usr/bin/env node
'use strict';

// Launcher for the SmartMoney-Cub review workbench.
//
// It resolves a local Python runtime, installs the harness into a private
// virtual environment on first run, and then starts the local web interface.
// Nothing is uploaded, and no browser opens until the server is listening.

const { spawnSync, spawn } = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const PACKAGE_NAME = 'smartmoney-cub-harness';
const MIN_PYTHON = [3, 10];
const ENV_PREFIX = process.env.SMCUB_HOME || path.join(os.homedir(), '.smartmoney-cub');

function log(message) {
  process.stderr.write(message + '\n');
}

function findPython() {
  const candidates = process.platform === 'win32'
    ? ['python', 'py', 'python3']
    : ['python3', 'python'];
  for (const candidate of candidates) {
    const probe = spawnSync(candidate, ['-c', 'import sys; print("%d.%d" % sys.version_info[:2])'], {
      encoding: 'utf8',
    });
    if (probe.status !== 0) continue;
    const parts = String(probe.stdout).trim().split('.').map(Number);
    if (parts[0] > MIN_PYTHON[0] || (parts[0] === MIN_PYTHON[0] && parts[1] >= MIN_PYTHON[1])) {
      return candidate;
    }
  }
  return null;
}

function venvPaths() {
  const dir = path.join(ENV_PREFIX, 'venv');
  const isWindows = process.platform === 'win32';
  return {
    dir: dir,
    python: isWindows ? path.join(dir, 'Scripts', 'python.exe') : path.join(dir, 'bin', 'python'),
    smcub: isWindows ? path.join(dir, 'Scripts', 'smcub.exe') : path.join(dir, 'bin', 'smcub'),
  };
}

function repositoryRoot() {
  return path.resolve(__dirname, '..', '..');
}

function install(extras) {
  const python = findPython();
  if (!python) {
    log('SmartMoney-Cub needs Python 3.10 or newer on PATH.');
    log('macOS: brew install python3    Windows: winget install Python.Python.3.12');
    process.exit(1);
  }
  const venv = venvPaths();
  if (!fs.existsSync(venv.python)) {
    log('Setting up a private environment in ' + venv.dir + ' (first run only)');
    const created = spawnSync(python, ['-m', 'venv', venv.dir], { stdio: 'inherit' });
    if (created.status !== 0) {
      log('Could not create the private environment. Install python3-venv and retry.');
      process.exit(created.status || 1);
    }
  }
  // Inside a source checkout the local package is installed, so contributors do
  // not have to reinstall on every edit.
  const local = repositoryRoot();
  const isCheckout = fs.existsSync(path.join(local, 'pyproject.toml'));
  const suffix = extras ? '[' + extras + ']' : '';
  const source = isCheckout ? local + suffix : PACKAGE_NAME + suffix;
  log('Installing ' + source);
  const installed = spawnSync(venv.python, ['-m', 'pip', 'install', '--upgrade', '--quiet', source], {
    stdio: 'inherit',
  });
  if (installed.status !== 0) {
    log('Installation failed. If the network is offline, install from a local wheel or checkout.');
    process.exit(installed.status || 1);
  }
  return venv;
}

function resolve() {
  const venv = venvPaths();
  if (fs.existsSync(venv.smcub)) return venv;
  return install('');
}

function run(args) {
  const venv = resolve();
  const child = spawn(venv.python, ['-m', 'smartmoney_cub_harness.cli'].concat(args), {
    stdio: 'inherit',
    env: process.env,
  });
  child.on('exit', function (code) { process.exit(code === null ? 0 : code); });
}

function main() {
  const args = process.argv.slice(2);
  if (args[0] === 'install') {
    install(args.indexOf('--with-ocr') >= 0 ? 'ocr' : '');
    return;
  }
  if (args[0] === 'doctor' || args[0] === '--doctor') {
    run(['doctor']);
    return;
  }
  run(args.length ? args : ['workbench']);
}

main();
