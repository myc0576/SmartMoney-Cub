"""Real plugin installer channel for SmartMoney-Cub Harness.

Creates and manages an isolated virtual environment and source checkouts under
<root>/plugins, ensuring strict read-only boundary, catalog whitelist enforcement,
and deterministic health probes.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

from smartmoney_cub_harness.agent.providers import load_credentials, save_credentials
from smartmoney_cub_harness.plugins.catalog import catalog_index
from smartmoney_cub_harness.plugins.catalog_contract import (
    INSTALL_BUILTIN,
    INSTALL_GIT,
    INSTALL_PYPI,
)
from smartmoney_cub_harness.schemas import SAFETY_DECLARATION


class PluginInstaller:
    """Installs curated plugins into a dedicated venv and source repository."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        self.plugins_dir = (self.root / "plugins").resolve()
        self.venv_dir = (self.plugins_dir / "venv").resolve()
        self.sources_dir = (self.plugins_dir / "sources").resolve()
        self._lock = threading.RLock()

    def _ensure_within_root(self, path: Path) -> Path:
        resolved = path.resolve()
        try:
            resolved.relative_to(self.plugins_dir)
        except ValueError:
            raise PermissionError(f"Path outside plugin root: {resolved}")
        return resolved

    def _venv_python(self) -> Path:
        if sys.platform == "win32":
            return self.venv_dir / "Scripts" / "python.exe"
        return self.venv_dir / "bin" / "python"

    def _ensure_venv(self) -> Path:
        self._ensure_within_root(self.venv_dir)
        python_bin = self._venv_python()
        if python_bin.is_file():
            return python_bin

        self.venv_dir.parent.mkdir(parents=True, exist_ok=True)
        uv_path = shutil.which("uv")
        created = False
        if uv_path:
            cmd = [uv_path, "venv", str(self.venv_dir)]
            res = subprocess.run(cmd, capture_output=True, text=True, check=False)
            if res.returncode == 0 and python_bin.is_file():
                created = True

        if not created:
            cmd = [sys.executable, "-m", "venv", str(self.venv_dir)]
            res = subprocess.run(cmd, capture_output=True, text=True, check=False)
            if res.returncode != 0:
                raise RuntimeError(f"Failed to create venv: {res.stderr}")

        return python_bin

    def _save_plugin_credentials(self, plugin_id: str, credentials: dict[str, Any]) -> None:
        existing = load_credentials(self.root)
        plugins_cred = existing.get("plugins")
        if not isinstance(plugins_cred, dict):
            plugins_cred = {}
        plugins_cred[plugin_id] = credentials
        existing["plugins"] = plugins_cred
        save_credentials(self.root, existing)

    def probe(self, entry: dict[str, Any], *, timeout: int = 60) -> dict[str, Any]:
        """Check health of a plugin without installing or mutating disk."""
        spec = entry.get("install") if isinstance(entry.get("install"), dict) else {}
        kind = spec.get("kind")
        if kind == INSTALL_GIT and entry.get("level") == "companion":
            source = self._ensure_within_root(self.sources_dir / str(entry["plugin_id"]))
            healthy = source.is_dir() and (source / ".git").is_dir()
            return {
                "status": "ok" if healthy else "error", "healthy": healthy,
                "detail": "source checkout present; configure and run upstream separately" if healthy else "source checkout is missing",
                "runtime_integrated": False, "safety": SAFETY_DECLARATION,
            }
        if kind == INSTALL_BUILTIN:
            return {
                "status": "ok",
                "healthy": True,
                "detail": "builtin harness component verified",
                "safety": SAFETY_DECLARATION,
            }

        module = spec.get("module")
        if not module:
            return {
                "status": "error",
                "healthy": False,
                "detail": "no import module specified for health check",
                "safety": SAFETY_DECLARATION,
            }

        python_bin = self._venv_python()
        if not python_bin.is_file():
            return {
                "status": "error",
                "healthy": False,
                "detail": "virtual environment not yet created",
                "safety": SAFETY_DECLARATION,
            }

        cmd = [str(python_bin), "-c", f"import {module}"]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
            if res.returncode == 0:
                return {
                    "status": "ok",
                    "healthy": True,
                    "detail": f"module {module} imported successfully",
                    "safety": SAFETY_DECLARATION,
                }
            stderr_summary = (res.stderr or "").strip().splitlines()
            err_msg = stderr_summary[-1] if stderr_summary else f"import failed with code {res.returncode}"
            return {
                "status": "error",
                "healthy": False,
                "detail": f"import failed: {err_msg}",
                "safety": SAFETY_DECLARATION,
            }
        except subprocess.TimeoutExpired:
            return {
                "status": "error",
                "healthy": False,
                "detail": f"health check timed out after {timeout}s",
                "safety": SAFETY_DECLARATION,
            }
        except Exception as exc:
            return {
                "status": "error",
                "healthy": False,
                "detail": f"health check failed: {exc}",
                "safety": SAFETY_DECLARATION,
            }

    def install(
        self,
        entry: dict[str, Any],
        *,
        permissions_confirmed: bool,
        credentials: dict[str, Any] | None = None,
        config: dict[str, Any] | None = None,
        timeout: int = 300,
    ) -> dict[str, Any]:
        """Perform verified installation of a catalog entry."""
        steps: list[dict[str, Any]] = []

        # 1. Catalog whitelist check
        plugin_id = str(entry.get("plugin_id") or "")
        whitelist = catalog_index()
        if not plugin_id or plugin_id not in whitelist:
            return {
                "status": "error",
                "steps": [
                    {
                        "step": "permissions",
                        "status": "refused",
                        "detail": f"plugin {plugin_id!r} is not in curated catalog whitelist",
                    }
                ],
                "error": "not_in_whitelist",
                "safety": SAFETY_DECLARATION,
            }

        curated_entry = whitelist[plugin_id]
        if curated_entry.get("execution_risk") == "high":
            return {
                "status": "error",
                "steps": [
                    {
                        "step": "permissions",
                        "status": "refused",
                        "detail": "该项目自带下单能力，永不安装 (execution ban absolute)",
                    }
                ],
                "error": "execution_risk_high_refused",
                "safety": SAFETY_DECLARATION,
            }

        # 2. Permissions check
        if not permissions_confirmed:
            steps.append(
                {
                    "step": "permissions",
                    "status": "failed",
                    "detail": "必须先确认只读权限与安全边界 (READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE)",
                }
            )
            return {
                "status": "error",
                "steps": steps,
                "error": "permissions_not_confirmed",
                "safety": SAFETY_DECLARATION,
            }

        steps.append(
            {
                "step": "permissions",
                "status": "ok",
                "detail": "只读权限与安全边界已确认",
            }
        )

        mode = curated_entry.get("credential_mode", "none")
        supplied = credentials if isinstance(credentials, dict) else {}
        requirements = curated_entry.get("credential_requirements") or []
        allowed = {item["name"] for item in requirements}
        error = None
        if supplied and mode != "managed_local":
            error = "external_credentials_not_accepted" if mode == "external_only" else "credentials_not_accepted"
        elif set(supplied) - allowed:
            error = "unknown_credential_fields"
        elif any(item.get("required") and not str(supplied.get(item["name"]) or "").strip() for item in requirements):
            error = "credentials_required"
        if error:
            return {"status": "error", "steps": steps, "error": error, "safety": SAFETY_DECLARATION}

        with self._lock:
            spec = curated_entry.get("install") if isinstance(curated_entry.get("install"), dict) else {}
            kind = spec.get("kind")
            fetch_cleanup_needed = False
            git_target_dir: Path | None = None

            try:
                # 3. Fetch step
                if kind == INSTALL_BUILTIN:
                    steps.append(
                        {
                            "step": "fetch",
                            "status": "skipped",
                            "detail": "内置能力无需下载安装第三方包",
                        }
                    )
                elif kind == INSTALL_PYPI:
                    python_bin = self._ensure_venv()
                    package = spec.get("package")
                    version = spec.get("version")
                    pkg_req = f"{package}=={version}" if version else str(package)

                    uv_path = shutil.which("uv")
                    if uv_path:
                        cmd = [uv_path, "pip", "install", "--python", str(python_bin), pkg_req]
                    else:
                        cmd = [str(python_bin), "-m", "pip", "install", pkg_req]

                    res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
                    if res.returncode != 0:
                        stderr_summary = (res.stderr or "").strip().splitlines()
                        err_msg = stderr_summary[-1] if stderr_summary else f"exit code {res.returncode}"
                        steps.append(
                            {
                                "step": "fetch",
                                "status": "failed",
                                "detail": f"pip install failed: {err_msg}",
                            }
                        )
                        return {
                            "status": "error",
                            "steps": steps,
                            "error": "fetch_failed",
                            "safety": SAFETY_DECLARATION,
                        }
                    steps.append(
                        {
                            "step": "fetch",
                            "status": "ok",
                            "detail": f"package {pkg_req} installed into venv",
                        }
                    )
                elif kind == INSTALL_GIT:
                    repo = spec.get("repo")
                    tag = spec.get("tag")
                    target = self.sources_dir / plugin_id
                    self._ensure_within_root(target)
                    git_target_dir = target
                    if target.exists():
                        # The checkout may contain user changes or configuration.
                        # Reinstallation must not erase them, even on a failed probe.
                        health = self.probe(curated_entry, timeout=min(60, timeout))
                        steps.append({"step": "fetch", "status": "skipped", "detail": "existing source checkout preserved"})
                        steps.append({"step": "health", "status": "ok" if health["healthy"] else "failed", "detail": health["detail"]})
                        return {"status": "ok" if health["healthy"] else "error", "steps": steps,
                                "health": health, "safety": SAFETY_DECLARATION}
                    fetch_cleanup_needed = True
                    self.sources_dir.mkdir(parents=True, exist_ok=True)

                    cmd = ["git", "clone", "--depth", "1"]
                    if tag:
                        cmd.extend(["--branch", str(tag)])
                    cmd.extend([str(repo), str(target)])

                    res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
                    if res.returncode != 0:
                        if target.exists():
                            shutil.rmtree(target, ignore_errors=True)
                        stderr_summary = (res.stderr or "").strip().splitlines()
                        err_msg = stderr_summary[-1] if stderr_summary else f"git clone exit code {res.returncode}"
                        steps.append(
                            {
                                "step": "fetch",
                                "status": "failed",
                                "detail": f"git clone failed: {err_msg}",
                            }
                        )
                        return {
                            "status": "error",
                            "steps": steps,
                            "error": "fetch_failed",
                            "safety": SAFETY_DECLARATION,
                        }

                    # Source companions are not runtime integrations. Checking
                    # out code does not authorize importing or running it.
                    steps.append(
                        {
                            "step": "fetch",
                            "status": "ok",
                            "detail": f"source cloned from {repo} to sources/{plugin_id}",
                        }
                    )
                else:
                    steps.append(
                        {
                            "step": "fetch",
                            "status": "failed",
                            "detail": f"unknown install kind: {kind}",
                        }
                    )
                    return {
                        "status": "error",
                        "steps": steps,
                        "error": "unknown_install_kind",
                        "safety": SAFETY_DECLARATION,
                    }

                # 4. Health check step
                probe_res = self.probe(curated_entry, timeout=min(60, timeout))
                if not probe_res.get("healthy"):
                    # Health check failed! Clean up if necessary
                    if fetch_cleanup_needed and git_target_dir and git_target_dir.exists():
                        shutil.rmtree(git_target_dir, ignore_errors=True)
                    steps.append(
                        {
                            "step": "health",
                            "status": "failed",
                            "detail": probe_res.get("detail", "health probe failed"),
                        }
                    )
                    return {
                        "status": "error",
                        "steps": steps,
                        "health": probe_res,
                        "error": "health_check_failed",
                        "safety": SAFETY_DECLARATION,
                    }

                steps.append(
                    {
                        "step": "health",
                        "status": "ok",
                        "detail": probe_res.get("detail", "health probe ok"),
                    }
                )
                # Commit credentials only after installation and health verification.
                if supplied:
                    self._save_plugin_credentials(plugin_id, supplied)
                return {
                    "status": "ok",
                    "steps": steps,
                    "health": probe_res,
                    "safety": SAFETY_DECLARATION,
                }

            except subprocess.TimeoutExpired:
                if fetch_cleanup_needed and git_target_dir and git_target_dir.exists():
                    shutil.rmtree(git_target_dir, ignore_errors=True)
                steps.append(
                    {
                        "step": "fetch",
                        "status": "failed",
                        "detail": f"operation timed out after {timeout}s",
                    }
                )
                return {
                    "status": "error",
                    "steps": steps,
                    "error": "timeout",
                    "safety": SAFETY_DECLARATION,
                }
            except Exception as exc:
                if fetch_cleanup_needed and git_target_dir and git_target_dir.exists():
                    shutil.rmtree(git_target_dir, ignore_errors=True)
                steps.append(
                    {
                        "step": "fetch",
                        "status": "failed",
                        "detail": f"unexpected error: {exc}",
                    }
                )
                return {
                    "status": "error",
                    "steps": steps,
                    "error": str(exc),
                    "safety": SAFETY_DECLARATION,
                }

    def uninstall(self, plugin_id: str) -> dict[str, Any]:
        """Revoke state and clean up packages and git sources."""
        with self._lock:
            whitelist = catalog_index()
            entry = whitelist.get(plugin_id)
            source_dir = self.sources_dir / plugin_id
            if source_dir.exists():
                self._ensure_within_root(source_dir)
                shutil.rmtree(source_dir, ignore_errors=True)

            if entry and entry.get("install", {}).get("kind") == INSTALL_PYPI:
                package = entry["install"].get("package")
                python_bin = self._venv_python()
                if package and python_bin.is_file():
                    uv_path = shutil.which("uv")
                    if uv_path:
                        cmd = [uv_path, "pip", "uninstall", "--python", str(python_bin), package, "-y"]
                    else:
                        cmd = [str(python_bin), "-m", "pip", "uninstall", package, "-y"]
                    subprocess.run(cmd, capture_output=True, text=True, check=False)

            return {
                "status": "ok",
                "plugin_id": plugin_id,
                "safety": SAFETY_DECLARATION,
            }
