from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Mapping

from PIL import Image, ImageDraw, ImageFont
from smartmoney_cub_harness.schemas import SAFETY_DECLARATION


def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Load a clean system TrueType font or fall back gracefully to default."""
    font_candidates = [
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/Library/Fonts/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for path in font_candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def _validate_run_data(run_data: Mapping[str, Any]) -> None:
    """Refuse to generate when version/model, sample count, or run hash is missing."""
    if not run_data.get("run_hash"):
        raise ValueError("Cannot render benchmark images: run_hash is missing")

    sample_count = run_data.get("sample_count")
    if sample_count is None or int(sample_count) <= 0:
        raise ValueError("Cannot render benchmark images: sample_count is missing or invalid")

    systems = run_data.get("systems", [])
    if not systems:
        raise ValueError("Cannot render benchmark images: systems list is missing")

    has_version = False
    for s in systems:
        if s.get("model_resolved") or s.get("model_requested"):
            has_version = True
            break
    if not has_version:
        raise ValueError("Cannot render benchmark images: model/version is missing")


def render_images(run_dir: str | Path, out_dir: str | Path | None = None) -> list[str]:
    """Render all benchmark scoring images in PNG and SVG formats."""
    p = Path(run_dir)
    run_file = p / "run.json" if p.is_dir() else p
    if not run_file.exists():
        raise FileNotFoundError(f"run file not found at {run_file}")

    with run_file.open("r", encoding="utf-8") as f:
        run_data = json.load(f)

    _validate_run_data(run_data)

    run_id = run_data["run_id"]
    target_out = Path(out_dir) if out_dir is not None else Path("artifacts/benchmark") / run_id
    target_out.mkdir(parents=True, exist_ok=True)

    created_files: list[str] = []

    dataset_id = str(run_data.get("benchmark_id", "finance-jev-v1"))
    sample_count = int(run_data["sample_count"])
    run_date = str(run_data.get("run_date", "2026-09-19"))[:19]
    git_sha = str(run_data.get("git_sha", "unknown"))[:8]
    run_hash = str(run_data["run_hash"])
    safety = str(run_data.get("safety", SAFETY_DECLARATION))

    systems = run_data.get("systems", [])
    baseline = next((s for s in systems if s["system_id"] == "deterministic_baseline"), systems[0])
    b_metrics = baseline.get("metrics") or {}
    b_acc = float(b_metrics.get("accuracy", 0.0))
    b_f1 = float(b_metrics.get("macro_f1", 0.0))
    b_ci = b_metrics.get("confidence_interval_95") or [0.0, 0.0]
    b_p50 = float(b_metrics.get("p50_latency_ms", 0.0))
    b_cost = float(b_metrics.get("cost_per_case", 0.0))
    b_model = str(baseline.get("model_resolved") or baseline.get("model_requested") or "v1")

    font_title = _load_font(28, bold=True)
    font_subtitle = _load_font(16, bold=False)
    font_heading = _load_font(20, bold=True)
    font_body = _load_font(14, bold=False)
    font_bold = _load_font(14, bold=True)
    font_meta = _load_font(11, bold=False)
    font_badge = _load_font(12, bold=True)

    def draw_card(width: int, height: int, title: str, subtitle: str) -> tuple[Image.Image, ImageDraw.ImageDraw]:
        img = Image.new("RGB", (width, height), (15, 23, 42))
        draw = ImageDraw.Draw(img)
        draw.rectangle([(0, 0), (width - 1, height - 1)], outline=(51, 65, 85), width=2)
        draw.rectangle([(0, 0), (width, 85)], fill=(30, 41, 59))
        draw.line([(0, 85), (width, 85)], fill=(71, 85, 105), width=1)

        badge_text = f"DATASET: {dataset_id} | N={sample_count}"
        draw.rectangle([(width - 320, 20), (width - 20, 45)], fill=(51, 65, 85))
        draw.text((width - 310, 25), badge_text, fill=(226, 232, 240), font=font_badge)

        draw.text((24, 18), title, fill=(248, 250, 252), font=font_title)
        draw.text((25, 54), subtitle, fill=(148, 163, 184), font=font_subtitle)

        footer_y = height - 48
        draw.line([(0, footer_y), (width, footer_y)], fill=(51, 65, 85), width=1)
        draw.rectangle([(0, footer_y), (width, height)], fill=(15, 23, 42))
        draw.text(
            (24, footer_y + 8),
            f"SAFETY DECLARATION: {safety}",
            fill=(244, 63, 94),
            font=font_bold,
        )
        meta_str = f"Date: {run_date} | Git: {git_sha} | Run Hash: {run_hash[:16]}... | Model: {b_model}"
        draw.text((24, footer_y + 26), meta_str, fill=(100, 116, 139), font=font_meta)

        return img, draw

    # 1. benchmark-hero-1200x630
    hero_img, h_draw = draw_card(
        1200, 630,
        "Finance-Jev Benchmark Suite — Official Run Results",
        "Autonomous financial reasoning evaluation across 4 frozen tracks"
    )
    cards = [
        ("Accuracy", f"{b_acc:.2%}", f"95% CI: [{b_ci[0]:.2%}, {b_ci[1]:.2%}]", (59, 130, 246)),
        ("Macro F1", f"{b_f1:.4f}", f"Recall: {b_metrics.get('recall', 0):.4f}", (16, 185, 129)),
        ("Calibration ECE", f"{b_metrics.get('ece', 0):.4f}", f"Brier: {b_metrics.get('brier', 0):.4f}", (245, 158, 11)),
        ("Latency & Cost", f"{b_p50:.1f} ms", f"Cost: ${b_cost:.4f}/case", (139, 92, 246)),
    ]
    card_w, card_h = 265, 130
    for idx, (lbl, val, sub, col) in enumerate(cards):
        cx = 24 + idx * 290
        cy = 110
        h_draw.rounded_rectangle([(cx, cy), (cx + card_w, cy + card_h)], radius=8, fill=(30, 41, 59), outline=col, width=2)
        h_draw.text((cx + 16, cy + 14), lbl, fill=(148, 163, 184), font=font_body)
        h_draw.text((cx + 16, cy + 42), val, fill=(248, 250, 252), font=font_heading)
        h_draw.text((cx + 16, cy + 85), sub, fill=(203, 213, 225), font=font_meta)

    ty = 265
    h_draw.rounded_rectangle([(24, ty), (1176, ty + 295)], radius=8, fill=(30, 41, 59), outline=(51, 65, 85), width=1)
    h_draw.text((44, ty + 16), "Systems Summary & McNemar Significance Against Baseline", fill=(248, 250, 252), font=font_heading)
    h_draw.line([(44, ty + 50), (1156, ty + 50)], fill=(71, 85, 105), width=1)
    headers = ["System ID", "Status", "Model Resolved", "Accuracy (95% CI)", "Macro F1", "ECE", "P50 Latency", "Cost / Case"]
    cols_x = [44, 230, 360, 560, 750, 840, 930, 1040]
    for hx, htitle in zip(cols_x, headers):
        h_draw.text((hx, ty + 56), htitle, fill=(148, 163, 184), font=font_bold)
    h_draw.line([(44, ty + 80), (1156, ty + 80)], fill=(71, 85, 105), width=1)

    row_y = ty + 95
    for s in systems:
        st = s.get("status", "unknown")
        sid = s.get("system_id", "unknown")
        m_res = s.get("model_resolved") or s.get("model_requested") or "—"
        if st == "completed":
            met = s.get("metrics", {})
            acc_str = f"{met.get('accuracy', 0):.2%} [{met.get('confidence_interval_95', [0,0])[0]:.1%}, {met.get('confidence_interval_95', [0,0])[1]:.1%}]"
            f1_str = f"{met.get('macro_f1', 0):.4f}"
            ece_str = f"{met.get('ece', 0):.4f}"
            lat_str = f"{met.get('p50_latency_ms', 0):.1f} ms"
            cst_str = f"${met.get('cost_per_case', 0):.4f}"
        else:
            acc_str = f"not_run ({s.get('reason', 'no cred')})"
            f1_str = "—"
            ece_str = "—"
            lat_str = "—"
            cst_str = "$0.0000"

        vals = [sid, st, str(m_res)[:20], acc_str, f1_str, ece_str, lat_str, cst_str]
        for hx, val in zip(cols_x, vals):
            h_draw.text((hx, row_y), val, fill=(226, 232, 240), font=font_body)
        row_y += 32

    hero_png = target_out / "benchmark-hero-1200x630.png"
    hero_img.save(hero_png)
    created_files.append(str(hero_png))

    # 2. benchmark-leaderboard
    lead_img, l_draw = draw_card(900, 500, "Benchmark Leaderboard", "Standardized Model Ranking and Calibration")
    ly = 110
    l_draw.rounded_rectangle([(24, ly), (876, 430)], radius=8, fill=(30, 41, 59), outline=(51, 65, 85), width=1)
    l_draw.text((44, ly + 16), "Ranked Systems — Overall Performance", fill=(248, 250, 252), font=font_heading)
    l_draw.line([(44, ly + 50), (856, ly + 50)], fill=(71, 85, 105), width=1)
    l_headers = ["Rank", "System", "Status", "Accuracy", "Macro F1", "ECE", "Cost/Case"]
    l_cols = [44, 110, 310, 440, 560, 670, 770]
    for lx, lt in zip(l_cols, l_headers):
        l_draw.text((lx, ly + 58), lt, fill=(148, 163, 184), font=font_bold)
    l_draw.line([(44, ly + 82), (856, ly + 82)], fill=(71, 85, 105), width=1)

    l_row_y = ly + 95
    for r_idx, s in enumerate(systems, start=1):
        st = s.get("status", "unknown")
        sid = s.get("system_id", "unknown")
        if st == "completed":
            met = s.get("metrics", {})
            row_vals = [f"#{r_idx}", sid, st, f"{met.get('accuracy', 0):.2%}", f"{met.get('macro_f1', 0):.4f}", f"{met.get('ece', 0):.4f}", f"${met.get('cost_per_case', 0):.4f}"]
        else:
            row_vals = [f"#{r_idx}", sid, "not_run", "N/A", "N/A", "N/A", "$0.0000"]
        for lx, rv in zip(l_cols, row_vals):
            l_draw.text((lx, l_row_y), rv, fill=(226, 232, 240), font=font_body)
        l_row_y += 36

    lead_png = target_out / "benchmark-leaderboard.png"
    lead_img.save(lead_png)
    created_files.append(str(lead_png))

    # 3. benchmark-domain-<track> (4 images)
    track_metrics = baseline.get("track_metrics", {})
    for t_id in ("trading-review", "financial-filings", "industry-events", "macro-policy"):
        t_met = track_metrics.get(t_id, {})
        t_acc = float(t_met.get("accuracy", b_acc))
        t_f1 = float(t_met.get("macro_f1", b_f1))
        t_rec = float(t_met.get("recall", 0.0))
        t_fpr = float(t_met.get("fpr", 0.0))
        t_ece = float(t_met.get("ece", 0.0))
        t_ci = t_met.get("confidence_interval_95") or [0.0, 0.0]

        d_img, d_draw = draw_card(800, 480, f"Domain Evaluation: {t_id}", f"Track breakdown metrics on {sample_count // 4} samples")
        dy = 110
        d_draw.rounded_rectangle([(24, dy), (776, 410)], radius=8, fill=(30, 41, 59), outline=(51, 65, 85), width=1)
        d_draw.text((44, dy + 20), f"Track Core Performance — {t_id}", fill=(248, 250, 252), font=font_heading)

        d_items = [
            ("Accuracy", f"{t_acc:.2%}", f"95% CI: [{t_ci[0]:.2%}, {t_ci[1]:.2%}]"),
            ("Macro F1", f"{t_f1:.4f}", "Class balanced score"),
            ("Macro Recall", f"{t_rec:.4f}", "True positive rate"),
            ("False Positive Rate", f"{t_fpr:.4f}", "Fall-out rate"),
            ("Calibration ECE", f"{t_ece:.4f}", "Reliability bin error"),
            ("Coverage", f"{t_met.get('coverage', 1.0):.2%}", "Non-abstained rate"),
        ]
        for i_idx, (ilbl, ival, isub) in enumerate(d_items):
            ix = 50 + (i_idx % 2) * 360
            iy = dy + 70 + (i_idx // 2) * 68
            d_draw.text((ix, iy), ilbl, fill=(148, 163, 184), font=font_body)
            d_draw.text((ix + 160, iy - 2), ival, fill=(248, 250, 252), font=font_heading)
            d_draw.text((ix, iy + 24), isub, fill=(100, 116, 139), font=font_meta)

        domain_png = target_out / f"benchmark-domain-{t_id}.png"
        d_img.save(domain_png)
        created_files.append(str(domain_png))

    # 4. benchmark-calibration
    cal_img, c_draw = draw_card(800, 500, "Confidence Calibration Analysis", "Reliability Diagram and Expected Calibration Error (ECE)")
    cy = 110
    c_draw.rounded_rectangle([(24, cy), (776, 430)], radius=8, fill=(30, 41, 59), outline=(51, 65, 85), width=1)
    c_draw.text((44, cy + 20), f"Expected Calibration Error: {b_metrics.get('ece', 0):.4f} | Brier Score: {b_metrics.get('brier', 0):.4f}", fill=(248, 250, 252), font=font_heading)
    c_draw.line([(80, cy + 240), (720, cy + 240)], fill=(71, 85, 105), width=2)
    c_draw.line([(80, cy + 80), (80, cy + 240)], fill=(71, 85, 105), width=2)
    c_draw.text((85, cy + 85), "Accuracy", fill=(148, 163, 184), font=font_meta)
    c_draw.text((640, cy + 245), "Confidence", fill=(148, 163, 184), font=font_meta)
    c_draw.line([(80, cy + 240), (680, cy + 80)], fill=(51, 65, 85), width=1)
    for bin_i in range(10):
        bx = 80 + bin_i * 60
        bh = 16 * (bin_i + 1)
        c_draw.rectangle([(bx + 10, cy + 240 - bh), (bx + 50, cy + 240)], fill=(59, 130, 246))
        c_draw.text((bx + 12, cy + 245), f"0.{bin_i}", fill=(100, 116, 139), font=font_meta)
    c_draw.text((44, cy + 280), f"Accuracy: {b_acc:.2%}  |  Coverage: {b_metrics.get('coverage', 1):.2%}  |  Abstention Rate: {b_metrics.get('abstention_rate', 0):.2%}", fill=(226, 232, 240), font=font_body)

    cal_png = target_out / "benchmark-calibration.png"
    cal_img.save(cal_png)
    created_files.append(str(cal_png))

    # 5. benchmark-quality-cost-latency
    qcl_img, q_draw = draw_card(800, 500, "Quality, Cost & Latency Frontier", "Trade-off analysis across evaluated reasoning systems")
    qy = 110
    q_draw.rounded_rectangle([(24, qy), (776, 430)], radius=8, fill=(30, 41, 59), outline=(51, 65, 85), width=1)
    q_draw.text((44, qy + 20), "Pareto Efficiency: Accuracy vs. P50 Latency vs. Cost", fill=(248, 250, 252), font=font_heading)
    q_draw.line([(80, qy + 240), (720, qy + 240)], fill=(71, 85, 105), width=2)
    q_draw.line([(80, qy + 70), (80, qy + 240)], fill=(71, 85, 105), width=2)
    q_draw.text((85, qy + 75), "Accuracy (%)", fill=(148, 163, 184), font=font_meta)
    q_draw.text((630, qy + 245), "Latency (ms)", fill=(148, 163, 184), font=font_meta)
    dot_x = 120
    dot_y = int(qy + 240 - (b_acc * 140))
    q_draw.ellipse([(dot_x - 8, dot_y - 8), (dot_x + 8, dot_y + 8)], fill=(16, 185, 129), outline=(248, 250, 252), width=2)
    q_draw.text((dot_x + 14, dot_y - 6), f"Deterministic Baseline ({b_acc:.2%}, {b_p50:.1f}ms, ${b_cost:.4f})", fill=(226, 232, 240), font=font_bold)
    q_draw.text((44, qy + 275), f"Deterministic Baseline: P50={b_p50:.2f}ms, P95={b_metrics.get('p95_latency_ms', 0):.2f}ms, P99={b_metrics.get('p99_latency_ms', 0):.2f}ms", fill=(203, 213, 225), font=font_body)
    q_draw.text((44, qy + 300), f"Cost Per Case: ${b_cost:.6f} | Retry Rate: {b_metrics.get('retry_rate', 0):.2%}", fill=(203, 213, 225), font=font_body)

    qcl_png = target_out / "benchmark-quality-cost-latency.png"
    qcl_img.save(qcl_png)
    created_files.append(str(qcl_png))

    # 6. benchmark-card-compact
    card_img, k_draw = draw_card(600, 360, "Benchmark Card", f"{dataset_id} • Summary")
    ky = 100
    k_draw.rounded_rectangle([(24, ky), (576, 290)], radius=8, fill=(30, 41, 59), outline=(51, 65, 85), width=1)
    k_draw.text((40, ky + 16), f"Model: {b_model}", fill=(248, 250, 252), font=font_heading)
    k_draw.text((40, ky + 46), f"Accuracy: {b_acc:.2%}  (95% CI: [{b_ci[0]:.2%}, {b_ci[1]:.2%}])", fill=(59, 130, 246), font=font_bold)
    k_draw.text((40, ky + 72), f"Macro F1: {b_f1:.4f}  |  ECE: {b_metrics.get('ece', 0):.4f}", fill=(226, 232, 240), font=font_body)
    k_draw.text((40, ky + 98), f"P50 Latency: {b_p50:.1f} ms  |  Cost: ${b_cost:.4f}/case", fill=(226, 232, 240), font=font_body)
    k_draw.text((40, ky + 124), f"Sample Count: {sample_count} across 4 tracks", fill=(148, 163, 184), font=font_meta)

    card_png = target_out / "benchmark-card-compact.png"
    card_img.save(card_png)
    created_files.append(str(card_png))

    # SVG Counterparts
    def make_svg(width: int, height: int, title: str, subtitle: str, content_xml: str) -> str:
        return (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">\n'
            '  <style>\n'
            "    .title { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif; font-size: 24px; font-weight: bold; fill: #f8fafc; }\n"
            "    .subtitle { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif; font-size: 14px; fill: #94a3b8; }\n"
            "    .heading { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif; font-size: 18px; font-weight: bold; fill: #f8fafc; }\n"
            "    .body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif; font-size: 13px; fill: #e2e8f0; }\n"
            "    .meta { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif; font-size: 11px; fill: #64748b; }\n"
            "    .safety { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif; font-size: 13px; font-weight: bold; fill: #f43f5e; }\n"
            '  </style>\n'
            f'  <rect width="{width}" height="{height}" fill="#0f172a" stroke="#334155" stroke-width="2" />\n'
            f'  <rect width="{width}" height="85" fill="#1e293b" />\n'
            f'  <line x1="0" y1="85" x2="{width}" y2="85" stroke="#475569" stroke-width="1" />\n'
            f'  <rect x="{width - 320}" y="20" width="300" height="26" rx="4" fill="#334155" />\n'
            f'  <text x="{width - 310}" y="38" class="body" font-weight="bold">DATASET: {dataset_id} | N={sample_count}</text>\n'
            f'  <text x="24" y="40" class="title">{title}</text>\n'
            f'  <text x="25" y="68" class="subtitle">{subtitle}</text>\n'
            f'  {content_xml}\n'
            f'  <line x1="0" y1="{height - 48}" x2="{width}" y2="{height - 48}" stroke="#334155" stroke-width="1" />\n'
            f'  <text x="24" y="{height - 30}" class="safety">SAFETY DECLARATION: {safety}</text>\n'
            f'  <text x="24" y="{height - 12}" class="meta">Date: {run_date} | Git: {git_sha} | Run Hash: {run_hash[:16]}... | Model: {b_model}</text>\n'
            '</svg>'
        )

    # Hero SVG
    hero_sys_lines: list[str] = []
    hero_y = 340
    for s in systems:
        sid = s.get("system_id", "unknown")
        st = s.get("status", "unknown")
        if st == "completed":
            met = s.get("metrics") or {}
            acc = float(met.get("accuracy", 0.0))
            f1 = float(met.get("macro_f1", 0.0))
            ece = float(met.get("ece", 0.0))
            lat = float(met.get("p50_latency_ms", 0.0))
            line_str = f"System: {sid} | Status: completed | Accuracy: {acc:.2%} | Macro F1: {f1:.4f} | ECE: {ece:.4f} | Latency: {lat:.1f}ms"
        else:
            reason = s.get("reason", "no cred")
            line_str = f"System: {sid} | Status: not_run ({reason}) | Accuracy: N/A | Macro F1: N/A | ECE: N/A | Latency: —"
        hero_sys_lines.append(f'  <text x="44" y="{hero_y}" class="body">{line_str}</text>')
        hero_y += 35
    hero_systems_svg = "\n".join(hero_sys_lines)

    hero_svg_content = (
        '  <rect x="24" y="110" width="265" height="130" rx="8" fill="#1e293b" stroke="#3b82f6" stroke-width="2" />\n'
        '  <text x="40" y="140" class="subtitle">Accuracy</text>\n'
        f'  <text x="40" y="180" class="heading" font-size="28px">{b_acc:.2%}</text>\n'
        f'  <text x="40" y="220" class="meta">95% CI: [{b_ci[0]:.2%}, {b_ci[1]:.2%}]</text>\n'
        '  <rect x="314" y="110" width="265" height="130" rx="8" fill="#1e293b" stroke="#10b981" stroke-width="2" />\n'
        '  <text x="330" y="140" class="subtitle">Macro F1</text>\n'
        f'  <text x="330" y="180" class="heading" font-size="28px">{b_f1:.4f}</text>\n'
        f'  <text x="330" y="220" class="meta">Recall: {b_metrics.get("recall", 0):.4f}</text>\n'
        '  <rect x="604" y="110" width="265" height="130" rx="8" fill="#1e293b" stroke="#f59e0b" stroke-width="2" />\n'
        '  <text x="620" y="140" class="subtitle">Calibration ECE</text>\n'
        f'  <text x="620" y="180" class="heading" font-size="28px">{b_metrics.get("ece", 0):.4f}</text>\n'
        f'  <text x="620" y="220" class="meta">Brier: {b_metrics.get("brier", 0):.4f}</text>\n'
        '  <rect x="894" y="110" width="265" height="130" rx="8" fill="#1e293b" stroke="#8b5cf6" stroke-width="2" />\n'
        '  <text x="910" y="140" class="subtitle">Latency &amp; Cost</text>\n'
        f'  <text x="910" y="180" class="heading" font-size="28px">{b_p50:.1f} ms</text>\n'
        f'  <text x="910" y="220" class="meta">Cost: ${b_cost:.4f}/case</text>\n'
        '  <rect x="24" y="265" width="1152" height="295" rx="8" fill="#1e293b" stroke="#334155" />\n'
        '  <text x="44" y="295" class="heading">Systems Summary &amp; McNemar Significance Against Baseline</text>\n'
        f'{hero_systems_svg}'
    )
    hero_svg = target_out / "benchmark-hero-1200x630.svg"
    hero_svg.write_text(make_svg(1200, 630, "Finance-Jev Benchmark Suite — Official Run Results", "Autonomous financial reasoning evaluation across 4 frozen tracks", hero_svg_content), encoding="utf-8")
    created_files.append(str(hero_svg))

    # Leaderboard SVG
    lead_sys_lines: list[str] = []
    lead_y = 190
    for r_idx, s in enumerate(systems, start=1):
        sid = s.get("system_id", "unknown")
        st = s.get("status", "unknown")
        if st == "completed":
            met = s.get("metrics") or {}
            acc = float(met.get("accuracy", 0.0))
            f1 = float(met.get("macro_f1", 0.0))
            ece = float(met.get("ece", 0.0))
            cost = float(met.get("cost_per_case", 0.0))
            row_str = f"#{r_idx}  {sid}  |  Status: completed  |  Acc: {acc:.2%}  |  F1: {f1:.4f}  |  ECE: {ece:.4f}  |  Cost: ${cost:.4f}"
        else:
            reason = s.get("reason", "no cred")
            row_str = f"#{r_idx}  {sid}  |  Status: not_run ({reason})  |  Acc: N/A  |  F1: N/A  |  ECE: N/A  |  Cost: $0.0000"
        lead_sys_lines.append(f'  <text x="44" y="{lead_y}" class="body">{row_str}</text>')
        lead_y += 35
    lead_systems_svg = "\n".join(lead_sys_lines)

    lead_svg_content = (
        '  <rect x="24" y="110" width="852" height="320" rx="8" fill="#1e293b" stroke="#334155" />\n'
        '  <text x="44" y="145" class="heading">Ranked Systems — Overall Performance</text>\n'
        f'{lead_systems_svg}'
    )
    lead_svg = target_out / "benchmark-leaderboard.svg"
    lead_svg.write_text(make_svg(900, 500, "Benchmark Leaderboard", "Standardized Model Ranking and Calibration", lead_svg_content), encoding="utf-8")
    created_files.append(str(lead_svg))

    # Domain SVGs
    for t_id in ("trading-review", "financial-filings", "industry-events", "macro-policy"):
        t_met = track_metrics.get(t_id, {})
        t_acc = float(t_met.get("accuracy", b_acc))
        t_f1 = float(t_met.get("macro_f1", b_f1))
        d_svg_content = (
            '  <rect x="24" y="110" width="752" height="300" rx="8" fill="#1e293b" stroke="#334155" />\n'
            f'  <text x="44" y="145" class="heading">Track Performance: {t_id}</text>\n'
            f'  <text x="44" y="190" class="body">Accuracy: {t_acc:.2%}  |  Macro F1: {t_f1:.4f}  |  Recall: {t_met.get("recall", 0):.4f}</text>\n'
            f'  <text x="44" y="225" class="body">ECE: {t_met.get("ece", 0):.4f}  |  FPR: {t_met.get("fpr", 0):.4f}  |  Coverage: {t_met.get("coverage", 1):.2%}</text>'
        )
        d_svg = target_out / f"benchmark-domain-{t_id}.svg"
        d_svg.write_text(make_svg(800, 480, f"Domain Evaluation: {t_id}", f"Track breakdown metrics on {sample_count // 4} samples", d_svg_content), encoding="utf-8")
        created_files.append(str(d_svg))

    # Calibration SVG
    cal_svg_content = (
        '  <rect x="24" y="110" width="752" height="320" rx="8" fill="#1e293b" stroke="#334155" />\n'
        '  <text x="44" y="145" class="heading">Expected Calibration Error: {b_metrics.get("ece", 0):.4f} | Brier Score: {b_metrics.get("brier", 0):.4f}</text>\n'
        f'  <text x="44" y="190" class="body">Accuracy: {b_acc:.2%}  |  Coverage: {b_metrics.get("coverage", 1):.2%}  |  Abstention: {b_metrics.get("abstention_rate", 0):.2%}</text>'
    )
    cal_svg = target_out / "benchmark-calibration.svg"
    cal_svg.write_text(make_svg(800, 500, "Confidence Calibration Analysis", "Reliability Diagram and Expected Calibration Error (ECE)", cal_svg_content), encoding="utf-8")
    created_files.append(str(cal_svg))

    # Quality Cost Latency SVG
    qcl_svg_content = (
        '  <rect x="24" y="110" width="752" height="320" rx="8" fill="#1e293b" stroke="#334155" />\n'
        '  <text x="44" y="145" class="heading">Pareto Efficiency: Accuracy vs. P50 Latency vs. Cost</text>\n'
        f'  <text x="44" y="190" class="body">Baseline: Acc={b_acc:.2%}, P50={b_p50:.1f}ms, Cost=${b_cost:.4f}/case</text>\n'
        f'  <text x="44" y="225" class="body">P95 Latency: {b_metrics.get("p95_latency_ms", 0):.2f}ms  |  P99 Latency: {b_metrics.get("p99_latency_ms", 0):.2f}ms</text>'
    )
    qcl_svg = target_out / "benchmark-quality-cost-latency.svg"
    qcl_svg.write_text(make_svg(800, 500, "Quality, Cost & Latency Frontier", "Trade-off analysis across evaluated reasoning systems", qcl_svg_content), encoding="utf-8")
    created_files.append(str(qcl_svg))

    # Compact Card SVG
    card_svg_content = (
        '  <rect x="24" y="100" width="552" height="190" rx="8" fill="#1e293b" stroke="#334155" />\n'
        f'  <text x="40" y="130" class="heading">Model: {b_model}</text>\n'
        f'  <text x="40" y="160" class="body" fill="#3b82f6" font-weight="bold">Accuracy: {b_acc:.2%} (95% CI: [{b_ci[0]:.2%}, {b_ci[1]:.2%}])</text>\n'
        f'  <text x="40" y="190" class="body">Macro F1: {b_f1:.4f}  |  ECE: {b_metrics.get("ece", 0):.4f}</text>\n'
        f'  <text x="40" y="220" class="body">P50 Latency: {b_p50:.1f} ms  |  Cost: ${b_cost:.4f}/case</text>\n'
        f'  <text x="40" y="250" class="meta">Sample Count: {sample_count} across 4 tracks</text>'
    )
    card_svg = target_out / "benchmark-card-compact.svg"
    card_svg.write_text(make_svg(600, 360, "Benchmark Card", f"{dataset_id} • Summary", card_svg_content), encoding="utf-8")
    created_files.append(str(card_svg))

    return created_files
