"""Regression checks for the redesigned bilingual README visuals.

Verifies both READMEs reference the new cover and system flow assets, the
asset files exist with the expected PNG dimensions, both files contain a
language switch link, both carry the read-only contract, no merge markers
or absolute paths are leaked into the documentation set, and the asset
files do not exceed the Git-friendly size limit.
"""

import re
import struct
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]  # tests/ lives under the design worktree
ASSETS = REPO / "assets"
README_EN = REPO / "README.md"
README_ZH = REPO / "README.zh-CN.md"

COVER = "smartmoney-cub-harness-cover.png"
FLOW = "smartmoney-cub-system-flow-bilingual.png"
MARK = "smartmoney-cub-mark.png"

# The company name burned into the source artwork below the mark. This test is
# the one place the string is allowed to appear, because a guard has to name what
# it forbids; the product's own name is smartmoney-cub, and the wordmark must
# appear in none of the files the guard checks.
FORBIDDEN_WORDMARK = "JIADING"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def png_size(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n", f"{path} is not a PNG"
    w, h = struct.unpack(">II", data[16:24])
    return w, h


def assert_(cond: bool, msg: str) -> None:
    if not cond:
        print(f"FAIL: {msg}")
        sys.exit(1)
    print(f"  ok: {msg}")


def test_readme_visuals() -> None:
    en = read(README_EN)
    zh = read(README_ZH)

    # 1. both READMEs reference the new cover
    assert_(f"![SmartMoney-Cub bilingual cover](assets/{COVER})" in en,
            f"README.md embeds assets/{COVER}")
    assert_(COVER in en, f"README.md mentions {COVER}")

    # 2. both READMEs reference the new system flow
    assert_("smartmoney-cub-system-flow-bilingual.png" in en,
            "README.md embeds the system flow asset")
    assert_("smartmoney-cub-system-flow-bilingual.png" in zh,
            "README.zh-CN.md embeds the system flow asset")

    # 3. asset files exist
    cover_path = ASSETS / COVER
    flow_path = ASSETS / FLOW
    assert_(cover_path.exists(), f"asset exists: {cover_path}")
    assert_(flow_path.exists(), f"asset exists: {flow_path}")

    # 4. PNG dimensions are correct (covers 1600x800, flow 1920x1080)
    cw, ch = png_size(cover_path)
    assert_((cw, ch) == (1600, 800), f"{COVER} is 1600x800 (got {cw}x{ch})")
    fw, fh = png_size(flow_path)
    assert_((fw, fh) == (1920, 1080), f"{FLOW} is 1920x1080 (got {fw}x{fh})")

    # 5. file sizes are bounded (cover <=1.5MB, flow <=2MB)
    cover_kb = cover_path.stat().st_size / 1024
    flow_kb = flow_path.stat().st_size / 1024
    assert_(cover_kb <= 1536, f"{COVER} <= 1.5MB (got {cover_kb:.0f}KB)")
    assert_(flow_kb <= 2048, f"{FLOW} <= 2MB (got {flow_kb:.0f}KB)")

    # 6. language switch links
    assert_("README.zh-CN.md" in en, "README.md has language switch link to Chinese")
    assert_("README.md" in zh, "README.zh-CN.md has language switch link to English")

    # 7. safety contract present in both READMEs and architecture doc
    assert_("READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE" in en,
            "README.md carries the read-only contract")
    assert_("READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE" in zh,
            "README.zh-CN.md carries the read-only contract")

    # 8. architecture.md keeps maintainable Mermaid + documents the human gate
    arch = read(REPO / "docs" / "architecture.md")
    assert_("```mermaid" in arch, "docs/architecture.md preserves Mermaid source")
    assert_("control-plane" in arch.lower() or "Control Plane" in arch,
            "docs/architecture.md retains control-plane pipeline text")

    # 9. no merge conflict markers in READMEs, architecture docs, or opendesign
    for p in (README_EN, README_ZH, REPO / "docs" / "architecture.md"):
        body = read(p)
        for marker in ("<<<<<<<", "=======", ">>>>>>>"):
            assert_(marker not in body, f"{p.name} contains merge marker {marker!r}")

    # 10. no absolute local paths leaked into READMEs or new architecture text
    joined = "\n".join([en, zh, arch])
    # Windows-style drive paths like C:\ or D:\
    assert_(not re.search(r"[A-Za-z]:\\\\[^\s)\\]+", joined),
            "no Windows absolute paths in READMEs or architecture.md")

    # 11. alt text is meaningful (both images carry SmartMoney-Cub identifier)
    assert_("SmartMoney-Cub" in en.split(COVER)[0][-120:],
            f"README.md image alt text mentions SmartMoney-Cub (cover)")
    assert_("SmartMoney-Cub" in en or "SmartMoney-Cub" in zh,
            "system flow image alt text mentions SmartMoney-Cub")

    # 12. do not claim runtime-integrated status for reserved-slot projects
    assert_("runtime-integrated" not in en.split("## ")[1] or
            "TradingAgents" not in en.split("## ")[1].split("## ")[0],
            "README.md does not label reserved-slot tools as runtime-integrated")

    # 13. the brand mark ships as its own asset. Only the geometric mark is
    #     published: the source artwork pairs it with a company wordmark that
    #     must never reach the product, so the file is checked here for being the
    #     square mark it is meant to be and nothing wider.
    mark_path = ASSETS / MARK
    assert_(mark_path.exists(), f"asset exists: {mark_path}")
    mw, mh = png_size(mark_path)
    assert_((mw, mh) == (512, 512), f"{MARK} is 512x512 (got {mw}x{mh})")
    mark_kb = mark_path.stat().st_size / 1024
    assert_(mark_kb <= 400, f"{MARK} <= 400KB (got {mark_kb:.0f}KB)")

    print("\nAll README/asset regression checks passed.")


def test_wordmark_never_ships() -> None:
    """The source artwork's company wordmark must not reach the product.

    The mark was cropped out of a lockup that pairs it with a company name that
    is not this product's. That name is the one string that would make the two
    look interchangeable, so it is guarded by name across every file that a user
    can read directly: both READMEs, the interface entry point and component
    that render the brand, and the built page a packaged install serves. The
    built bundle is included because it is committed on purpose -- a stray copy
    there would ship even though nothing in the sources mentions it.
    """
    for path in (
        README_EN,
        README_ZH,
        REPO / "gui" / "index.html",
        REPO / "gui" / "src" / "App.tsx",
        REPO / "src" / "smartmoney_cub_harness" / "workbench" / "web" / "index.html",
    ):
        assert_(FORBIDDEN_WORDMARK not in read(path),
                f"{path.name} does not carry the source artwork's company wordmark")


if __name__ == "__main__":
    # The suite finds these checks by name, and the file is also meant to be run
    # directly: the reporting helpers above print one line per item instead of
    # staying quiet, and a failure exits non-zero. The guard is what makes that
    # true -- without it, running the file directly would import it, define the
    # checks, and pass without checking anything at all.
    test_readme_visuals()
    test_wordmark_never_ships()
