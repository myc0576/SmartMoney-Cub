# Versioning and Upgrades

`smartmoney-cub-harness` uses Semantic Versioning for its CLI, Python package, and portable artifact contracts.

Current release channel: GitHub Releases. Each release provides a Git tag, wheel, and source distribution. PyPI publication is optional and deferred until a project owner configures Trusted Publishing.

## Version meanings

- Patch (`0.1.0` -> `0.1.1`): compatible fixes, packaging improvements, diagnostics, and documentation.
- Minor (`0.1.x` -> `0.2.0`): backward-compatible CLI commands, schemas, or review capabilities.
- Major (`0.x` -> `1.0.0`, then `1.x` -> `2.0.0`): incompatible CLI, artifact, schema, or safety-contract changes.

Release `1.0.0` is the current release. It converges the review workbench into a
local-first product: a three-region interface with an import pipeline that parses
broker files on the machine, a review assistant whose outbound payload is redacted
before it leaves, and the hosted trader journal served from the same process. It
keeps the read-only safety contract unchanged. A published version is immutable and
must never be reused.

## Existing users

An existing installation does not update automatically. Choose the command that matches the original installation method.

### Editable Git checkout

```bash
git pull --ff-only
python -m pip install -e ".[dev]"
smcub --version
```

An editable installation normally sees source changes immediately after `git pull`. Reinstall after packaging metadata, entry points, package data, or dependencies change. Release `0.2.0` adds plugin entry points and packaged example data, so reinstall it once.

### pip installation

After the package is published to PyPI:

```bash
python -m pip install --upgrade smartmoney-cub-harness
smcub --version
```

### pipx installation

pipx is the preferred end-user CLI installation because it isolates the command from unrelated Python environments. Install the current GitHub tag directly:

```bash
pipx install "git+https://github.com/myc0576/SmartMoney-Cub.git@v1.0.0"
smcub --version
smcub doctor
```

To move an existing pipx installation to a future GitHub tag, install that tag with `--force`. After a future PyPI publication, the shorter commands become available:

```bash
pipx install smartmoney-cub-harness
pipx upgrade smartmoney-cub-harness
smcub --version
smcub doctor
```

### Copied source or downloaded archive

A copied directory or downloaded source archive has no update channel. Download a newer GitHub Release or migrate to a Git checkout or pipx installation.

## PATH conflicts

Multiple Python installations can each provide an executable named `smcub`. The shell runs the first match on `PATH`, which may be an older installation.

Run both commands after installation or upgrade:

```bash
smcub --version
smcub doctor
```

`doctor` reports whether multiple launchers exist and whether the first one belongs to the current Python environment. It reports only counts and booleans; it does not expose local installation paths.

## Release lifecycle

Every public release follows the same order:

1. Update the single package version source.
2. Run the full test suite, wheel build, doctor, privacy audit, and offline toy loop.
3. Merge the reviewed change into `main`.
4. Create an annotated `vX.Y.Z` Git tag for the merged commit.
5. Create a GitHub Release from the same tag and describe user-visible changes and safety-contract impact.
6. Attach the matching wheel and source distribution to the GitHub Release.
7. Install the tag in a clean pipx environment and verify `smcub --version`, `smcub doctor`, and the toy loop.

The Git tag, GitHub Release, and Python package metadata must match exactly. If PyPI is enabled later, its version must match them too.

## PyPI publication boundary

PyPI is not required for the current GitHub Release channel. If it is enabled later, the repository must use PyPI Trusted Publishing rather than storing a long-lived PyPI token. Publication must not begin until the PyPI project and its GitHub repository/environment trust relationship are configured and verified.

This CLI does not perform background update checks and does not modify its own Python environment. It remains offline by default with no telemetry or upload. Users initiate upgrades explicitly with Git, pip, or pipx.

`READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE`
