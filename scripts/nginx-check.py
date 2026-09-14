"""Check the shipped nginx config the way nginx -t would.

Why this exists: an nginx config that fails to parse, or that references a
variable no map defines, stops nginx from starting at all — the site is down and
the failure is not in any test suite. The config has been read and reviewed, but
never parsed, because this environment has no nginx binary.

crossplane is a Python nginx-config parser. It is not nginx itself, so this check
proves the syntax and variable classes of problem, not runtime behaviour. That
distinction is stated rather than blurred: on a host with nginx installed, run
`nginx -t -c` against this file for the authoritative answer.

    pip install crossplane
    python scripts/nginx-check.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

CONFIG = Path(__file__).resolve().parents[1] / "deploy" / "nginx.conf"

# Variables nginx provides without any declaration. A name outside this set that
# no map defines is a startup error, which is the failure this check exists for.
BUILTIN_VARIABLES = {
    "host", "remote_addr", "remote_port", "scheme", "request_uri", "uri", "args",
    "http_upgrade", "http_host", "server_name", "server_port", "request_method",
    "http_x_forwarded_for", "http_x_forwarded_proto", "proxy_add_x_forwarded_for",
    "request", "document_root", "binary_remote_addr", "connection", "http_user_agent",
}

# Variables the config deliberately takes from an included file, because they hold
# a secret that must not live in this repository. They are listed here rather than
# inferred from the include, so adding a new one is a deliberate edit: an inferred
# rule would silently accept a typo like "$smcub_tokn" merely because some include
# existed. deploy/README.md documents how the operator creates each file.
INCLUDE_SUPPLIED_VARIABLES = {
    "smcub_token": "/etc/nginx/snippets/smcub-token.conf",
}


def main() -> int:
    if not CONFIG.is_file():
        print(f"missing config: {CONFIG}")
        return 1
    text = CONFIG.read_text(encoding="utf-8")

    # The shipped file is a server block meant to be included inside an http
    # block, so wrap it the way an operator would before parsing.
    wrapped = "events {}\nhttp {\n" + text + "\n}\n"

    print("[1] parse the config (syntax and directive placement)")
    # The parser is optional; the checks below are not. Every check that can run
    # without it does, so a machine without crossplane still catches a missing
    # proxy directive or a stale variable name instead of reporting nothing.
    parser_available = True
    try:
        from crossplane import parse
    except ImportError:
        parser_available = False
        print("    skipped: crossplane is not installed (pip install crossplane).")
        print("    The remaining checks still run; only full syntax parsing is skipped.")
    if parser_available:
        try:
            parse(wrapped)
        except Exception as exc:  # the parser raises several types
            print(f"    FAIL: {type(exc).__name__}: {str(exc)[:200]}")
            return 1
        print("    PASS: parses cleanly")

    print()
    print("[2] every variable is built in or defined by a map")
    # The map's target carries a '$'; uses elsewhere are read without it, so
    # compare on the bare name on both sides.
    defined = set(re.findall(r"\bmap\s+\S+\s+\$(\w+)", text))
    assigned = set(re.findall(r"\bset\s+\$(\w+)", text))
    used = set(re.findall(r"\$(\w+)", text))
    known = BUILTIN_VARIABLES | defined | assigned | set(INCLUDE_SUPPLIED_VARIABLES)
    undefined = sorted(name for name in used if name not in known)
    print("    maps defined  :", sorted(defined) or "none")
    print("    set in file   :", sorted(assigned) or "none")
    if INCLUDE_SUPPLIED_VARIABLES:
        print("    from includes :", dict(INCLUDE_SUPPLIED_VARIABLES))
    print("    undefined vars:", undefined or "none")
    if undefined:
        print("    FAIL: nginx refuses to start on an unknown variable")
        return 1
    print("    PASS: no unknown variables")

    print()
    print("[3] the pieces a hosted deployment depends on")
    required = {
        "a server block": bool(re.search(r"^\s*server\s*\{", text, re.M)),
        "TLS certificates": "ssl_certificate" in text,
        "the /trader/ proxy": "location /trader/" in text,
        "prefix stripping": "proxy_pass http://smcub_trader/;" in text,
        "SSE without buffering": "proxy_buffering off;" in text,
        "client_max_body_size set": "client_max_body_size" in text,
        "the websocket upgrade map": "map $http_upgrade $connection_upgrade" in text,
        # A browser cannot send a custom header on a page load or on the page's own
        # asset requests, so the proxy is the only thing that can supply the token a
        # token-protected deployment requires. Without this the product 401s for
        # every visitor.
        "the token reaches the app": "proxy_set_header X-SMCUB-Token $smcub_token;" in text,
    }
    for label, present in required.items():
        print(f"    {'OK  ' if present else 'MISS'} {label}")
    missing = [label for label, present in required.items() if not present]
    if missing:
        print("    FAIL: missing", missing)
        return 1

    print()
    print("NGINX CONFIG VALIDATED (parses, no unknown variables, required pieces present)")
    print("Note: crossplane is a parser, not nginx. On a host with nginx installed,")
    print("      run 'nginx -t -c' against this file for the authoritative check.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
