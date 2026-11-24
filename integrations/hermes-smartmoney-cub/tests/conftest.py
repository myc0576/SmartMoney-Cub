"""Load the plugin directory as a package so its tests can import it.

The plugin root is a Python package (its ``__init__.py`` uses relative imports
such as ``from . import schemas, tools``), which is how Hermes loads an
installed plugin directory. Loading it by package name here keeps the tests
exercising the same import shape Hermes uses, instead of importing the flat
modules as top-level names (which raises
``ImportError: attempted relative import with no known parent package``).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parent.parent
PACKAGE = "hermes_smartmoney_cub_plugin"


def _load_plugin():
    spec = importlib.util.spec_from_file_location(
        PACKAGE,
        PLUGIN_DIR / "__init__.py",
        submodule_search_locations=[str(PLUGIN_DIR)],
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[PACKAGE] = module
    spec.loader.exec_module(module)
    return module


plugin = sys.modules.get(PACKAGE) or _load_plugin()

# The test module imports the helpers by their bare module names.
sys.modules.setdefault("tools", plugin.tools)
sys.modules.setdefault("schemas", plugin.schemas)
