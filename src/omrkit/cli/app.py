"""Modern Typer + Rich command-line interface for OMRKit."""

from __future__ import annotations

import contextlib
import json
import math
import os
from pathlib import Path
from time import perf_counter
from typing import Annotated

import typer
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table

from omrkit._version import __version__
from omrkit.core.auto_scanner import scan_file_auto
from omrkit.core.benchmark import run_benchmark
from omrkit.core.migrator import migrate_legacy_template_file
from omrkit.core.scanner import OMRScanner, ensure_unique_sheet_ids
from omrkit.generator.pdf_sheet import SheetGenerator
from omrkit.generator.presets import SheetSpec, get_sheet_preset, get_sheet_presets
from omrkit.grading.grader import ExamGrader
from omrkit.io.exporters import export_csv, export_excel, export_json, export_pdf_scorecard
from omrkit.io.loader import discover_documents, load_document, strip_exif_and_save
from omrkit.models.grading import AnswerKey, GradingPolicy
from omrkit.models.scan import BatchResult, SheetResult
from omrkit.models.template import Template
from omrkit.vision.grid_finder import detect_layout_from_blank

app = typer.Typer(
    name="omrkit",
    help=f"OMRKit v{__version__} — Modern Optical Mark Recognition engine, QR Auto-Scan, Sheet Generator, Psychometrics & Web Studio.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)
console = Console()


@app.command()
def scan(
    input_path: Annotated[
        Path,
        typer.Argument(help="Image file, PDF file, or directory containing sheets to scan."),
    ],
    template: Annotated[
        Path | None,
        typer.Option(
            "-t",
            "--template",
            help="Path to template.json/.yaml. Omit to auto-detect template from embedded sheet QR code.",
        ),
    ] = None,
    output: Annotated[
        Path,
        typer.Option(
            "-o", "--output", help="Directory where results and overlays will be written."
        ),
    ] = Path("outputs"),
    answer_key: Annotated[
        Path | None,
        typer.Option(
            "-k", "--answer-key", help="Optional answer_key.json/.yaml for immediate grading."
        ),
    ] = None,
    policy: Annotated[
        str,
        typer.Option("--policy", help="Grading preset: standard, yks_tyt, kpss, lgs, sat_legacy."),
    ] = "standard",
    formats: Annotated[
        str,
        typer.Option("--format", help="Comma-separated export formats: csv,json,xlsx,scorecards."),
    ] = "csv,json",
    overlay: Annotated[
        bool,
        typer.Option("--overlay/--no-overlay", help="Save color-coded verification overlay PNGs."),
    ] = True,
    workers: Annotated[
        int,
        typer.Option("-w", "--workers", help="Parallel worker processes (1 = sequential)."),
    ] = 1,
    dpi: Annotated[
        int,
        typer.Option("--dpi", help="PDF rasterization DPI."),
    ] = 200,
    recursive: Annotated[
        bool,
        typer.Option("-r", "--recursive", help="Recursively scan subdirectories."),
    ] = False,
) -> None:
    """Scan optical sheets (images or multi-page PDFs) with explicit template or QR auto-detection."""
    output.mkdir(parents=True, exist_ok=True)
    overlay_dir = output / "overlays" if overlay else None

    if template is not None:
        tmpl = Template.from_file(template)
        tmpl_label = tmpl.name
        scanner = OMRScanner(tmpl, dpi=dpi)
        with Progress(
            SpinnerColumn(),
            TextColumn("[bold cyan]{task.description}"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total}"),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task_id = progress.add_task("Scanning sheets...", total=None)

            def _on_progress(done: int, total: int, filename: str) -> None:
                progress.update(
                    task_id, total=total, completed=done, description=f"Scanned {filename}"
                )

            batch = scanner.scan_batch(
                input_path=input_path,
                workers=workers,
                recursive=recursive,
                save_overlay_dir=overlay_dir,
                progress_cb=_on_progress,
            )
    else:
        tmpl_label = "auto (QR)"
        files = discover_documents(input_path, recursive=recursive)
        t0 = perf_counter()
        all_sheets: list[SheetResult] = []
        for f in files:
            all_sheets.extend(scan_file_auto(f, dpi=dpi, save_overlay_dir=overlay_dir))
        ensure_unique_sheet_ids(all_sheets)
        elapsed = (perf_counter() - t0) * 1000.0
        succeeded = sum(1 for r in all_sheets if r.error is None)
        failed = sum(1 for r in all_sheets if r.error is not None)
        flagged = sum(1 for r in all_sheets if r.error is None and len(r.review_items) > 0)
        batch = BatchResult(
            template_name="auto",
            sheets=all_sheets,
            total_sheets=len(all_sheets),
            succeeded=succeeded,
            flagged_sheets=flagged,
            failed_sheets=failed,
            total_elapsed_ms=round(elapsed, 2),
            sheets_per_minute=round(
                (len(all_sheets) / (elapsed / 60000.0)) if elapsed > 0 else 0.0, 1
            ),
        )

    report = None
    if answer_key is not None:
        key = AnswerKey.from_file(answer_key)
        grader = ExamGrader(key, GradingPolicy.preset(policy))
        report = grader.grade_batch(batch.sheets)

    fmt_set = {f.strip().lower() for f in formats.split(",") if f.strip()}
    exported: list[str] = []
    if "csv" in fmt_set:
        exported.append(str(export_csv(batch.sheets, output / "results.csv", report=report)))
    if "json" in fmt_set:
        exported.append(str(export_json(batch.sheets, output / "results.json", report=report)))
    if "xlsx" in fmt_set:
        exported.append(str(export_excel(batch.sheets, output / "report.xlsx", report=report)))
    if "scorecards" in fmt_set and report is not None:
        sc_dir = output / "scorecards"
        for g in report.grades:
            export_pdf_scorecard(
                g, sc_dir / f"{g.sheet_id}_scorecard.pdf", exam_name=report.exam_name
            )
        exported.append(str(sc_dir))

    table = Table(title="OMRKit Scan Summary", show_header=False)
    table.add_column("Metric", style="cyan", no_wrap=True)
    table.add_column("Value", style="bold")
    table.add_row("Template", tmpl_label)
    table.add_row("Total Pages", str(batch.total_sheets))
    table.add_row("Succeeded", f"[green]{batch.succeeded}[/green]")
    table.add_row("Flagged for HITL Review", f"[yellow]{batch.flagged_sheets}[/yellow]")
    table.add_row("Failed", f"[red]{batch.failed_sheets}[/red]")
    table.add_row(
        "Throughput", f"{batch.sheets_per_minute:.1f} sheets/min ({batch.total_elapsed_ms:.0f} ms)"
    )
    if report is not None:
        table.add_row(
            "Mean Score", f"{report.analytics.mean_score} ({report.analytics.mean_percentage}%)"
        )
        if report.analytics.kr20_reliability is not None:
            table.add_row("KR-20 Reliability", str(report.analytics.kr20_reliability))
    for path_str in exported:
        table.add_row("Exported", path_str)
    console.print(table)


@app.command()
def generate(
    preset: Annotated[
        str,
        typer.Option("--preset", "-p", help="Sheet preset ID (run --list to inspect all)."),
    ] = "standard_mcq_40",
    output: Annotated[
        Path,
        typer.Option(
            "-o", "--output", help="Output directory for PDF, template.json, and answer_key.json."
        ),
    ] = Path("generated_sheet"),
    title: Annotated[
        str | None,
        typer.Option("--title", help="Custom header title on the generated PDF."),
    ] = None,
    questions: Annotated[
        int | None,
        typer.Option("--questions", "-q", help="Override number of questions (5-120)."),
    ] = None,
    list_presets: Annotated[
        bool,
        typer.Option("--list", help="List available built-in optical sheet presets."),
    ] = False,
) -> None:
    """Generate a print-ready ArUco + QR PDF optical sheet + pixel-exact matching template.json."""
    if list_presets:
        table = Table(title="Built-in Optical Sheet Presets")
        table.add_column("Preset ID", style="cyan")
        table.add_column("Questions")
        table.add_column("Options")
        table.add_column("Title")
        for pid, spec in get_sheet_presets().items():
            table.add_row(pid, str(spec.num_questions), "".join(spec.options), spec.title)
        console.print(table)
        return

    base = get_sheet_preset(preset).model_dump()
    if title is not None:
        base["title"] = title
    if questions is not None:
        base["num_questions"] = questions
        max_cols = 4 if len(base["options"]) >= 5 else 5
        min_rows = math.ceil(questions / max_cols)
        if base["questions_per_column"] < min_rows:
            base["questions_per_column"] = min(30, min_rows)
    spec = SheetSpec.model_validate(base)

    paths = SheetGenerator().generate_to_dir(spec, output)
    console.print(f"[green]Generated optical sheet bundle in '{output}':[/green]")
    for key, p in paths.items():
        console.print(f"  - [bold]{key}[/bold]: {p}")


@app.command("detect-layout")
def detect_layout(
    blank_sheet: Annotated[
        Path,
        typer.Argument(help="Path to a blank optical form image or PDF."),
    ],
    output: Annotated[
        Path,
        typer.Option("-o", "--output", help="Output path for auto-detected template.json."),
    ] = Path("detected_template.json"),
    name: Annotated[
        str | None,
        typer.Option("--name", help="Optional name for the generated template."),
    ] = None,
    dpi: Annotated[int, typer.Option("--dpi", help="PDF rasterization DPI.")] = 200,
) -> None:
    """Automatically detect circular bubble grids on a blank optical form and emit template.json."""
    page = load_document(blank_sheet, dpi=dpi)[0]
    tmpl, bubbles_found = detect_layout_from_blank(
        page.image_bgr, template_name=name or blank_sheet.stem
    )
    saved = tmpl.to_file(output)
    console.print(
        f"[green]Auto-detected {len(tmpl.blocks)} block(s) ({len(tmpl.all_field_ids())} fields, "
        f"{bubbles_found} bubbles)[/green] -> [bold]{saved}[/bold]"
    )


@app.command("migrate-template")
def migrate_template(
    legacy_json: Annotated[
        Path,
        typer.Argument(help="Path to a legacy OMRChecker v1 template.json file."),
    ],
    output: Annotated[
        Path,
        typer.Option("-o", "--output", help="Destination path for OMRKit v2 template.json."),
    ] = Path("template_v2.json"),
) -> None:
    """Migrate a legacy OMRChecker template.json into an OMRKit v2.0 template."""
    tmpl = migrate_legacy_template_file(legacy_json, output)
    console.print(
        f"[green]Migrated legacy template[/green] '{legacy_json.name}' -> [bold]{output}[/bold] "
        f"({len(tmpl.blocks)} blocks, {len(tmpl.all_field_ids())} fields, mode={tmpl.registration.mode})"
    )


@app.command()
def grade(
    results_json: Annotated[
        Path,
        typer.Argument(help="Path to results.json produced by `omrkit scan`."),
    ],
    answer_key: Annotated[
        Path,
        typer.Option("-k", "--answer-key", help="Path to answer_key.json or .yaml."),
    ],
    policy: Annotated[
        str,
        typer.Option("--policy", help="Grading preset: standard, yks_tyt, kpss, lgs, sat_legacy."),
    ] = "standard",
    output: Annotated[
        Path,
        typer.Option("-o", "--output", help="Output directory for graded reports."),
    ] = Path("graded_outputs"),
) -> None:
    """Grade previously scanned results and compute Classical Test Theory psychometrics."""
    raw = json.loads(results_json.read_text(encoding="utf-8"))
    raw_items = raw["sheets"] if isinstance(raw, dict) and "sheets" in raw else raw
    sheets = [SheetResult.model_validate(item) for item in raw_items]
    key = AnswerKey.from_file(answer_key)
    grader = ExamGrader(key, GradingPolicy.preset(policy))
    report = grader.grade_batch(sheets)

    output.mkdir(parents=True, exist_ok=True)
    export_json(sheets, output / "graded_report.json", report=report)
    export_csv(sheets, output / "graded_results.csv", report=report)
    with contextlib.suppress(RuntimeError):
        export_excel(sheets, output / "graded_report.xlsx", report=report)

    a = report.analytics
    console.print(
        f"[green]Graded {a.student_count} sheet(s)[/green] | "
        f"Mean: [bold]{a.mean_score}[/bold] ({a.mean_percentage}%) | "
        f"Median: {a.median_score} | Std: {a.std_score} | KR-20: {a.kr20_reliability}"
    )


@app.command()
def validate(
    template: Annotated[
        Path,
        typer.Argument(help="Path to template.json or template.yaml to validate."),
    ],
) -> None:
    """Validate an OMRKit template file and display layout summary."""
    tmpl = Template.from_file(template)
    console.print(
        f"[green]Valid OMRKit v{tmpl.version} template:[/green] [bold]{tmpl.name}[/bold] "
        f"({tmpl.page_width}x{tmpl.page_height}, mode={tmpl.registration.mode}, "
        f"blocks={len(tmpl.blocks)}, fields={len(tmpl.all_field_ids())})"
    )


@app.command()
def benchmark(
    preset: Annotated[
        str,
        typer.Option("--preset", "-p", help="Sheet preset to stress-test."),
    ] = "standard_mcq_40",
    samples: Annotated[
        int,
        typer.Option("--samples", "-n", help="Synthetic sheets per distortion scenario."),
    ] = 5,
) -> None:
    """Run synthetic distortion accuracy and speed benchmarks."""
    console.print(
        f"Running OMRKit benchmark on preset [cyan]{preset}[/cyan] ({samples} sheets/scenario)..."
    )
    rows = run_benchmark(preset_id=preset, samples_per_scenario=samples)
    table = Table(title="OMRKit Synthetic Accuracy & Throughput Benchmark")
    table.add_column("Scenario", style="cyan")
    table.add_column("Accuracy", justify="right", style="bold green")
    table.add_column("Fields", justify="right")
    table.add_column("Avg Conf", justify="right")
    table.add_column("HITL Flags", justify="right")
    table.add_column("Throughput", justify="right", style="magenta")

    for r in rows:
        table.add_row(
            r.scenario,
            f"{r.accuracy_pct:.2f}%",
            f"{r.correct_fields}/{r.total_fields}",
            f"{r.avg_confidence * 100:.1f}%",
            str(r.flagged_fields),
            f"{r.sheets_per_minute:.0f} OMR/min",
        )
    console.print(table)


@app.command("strip-exif")
def strip_exif(
    input_path: Annotated[
        Path,
        typer.Argument(help="Image file or folder to sanitize."),
    ],
    output: Annotated[
        Path,
        typer.Option("-o", "--output", help="Destination file or folder."),
    ],
    max_dim: Annotated[
        int | None,
        typer.Option("--max-dim", help="Optional max width/height in pixels."),
    ] = None,
) -> None:
    """Strip EXIF/GPS privacy metadata and bake orientation permanently into pixels."""
    if input_path.is_file():
        size = strip_exif_and_save(input_path, output, max_dimension=max_dim)
        console.print(
            f"[green]Sanitized[/green] {input_path.name} -> {output} ({size[0]}x{size[1]})"
        )
        return

    files = [p for p in discover_documents(input_path) if p.suffix.lower() != ".pdf"]
    for src in files:
        dst = output / src.name
        size = strip_exif_and_save(src, dst, max_dimension=max_dim)
        console.print(f"[green]Sanitized[/green] {src.name} -> {dst} ({size[0]}x{size[1]})")


@app.command()
def studio(
    host: Annotated[str, typer.Option("--host", help="Bind host address.")] = "127.0.0.1",
    port: Annotated[
        int | None,
        typer.Option("--port", help="HTTP port (defaults to $PORT or 8000)."),
    ] = None,
    reload: Annotated[
        bool, typer.Option("--reload", help="Enable auto-reload for development.")
    ] = False,
) -> None:
    """Launch OMRKit Web Studio + FastAPI REST API server."""
    try:
        import uvicorn
    except ImportError as exc:
        console.print(
            "[red]Web Studio requires optional dependencies.[/red] "
            "Install with: [bold]pip install 'omrkit[studio]'[/bold]"
        )
        raise typer.Exit(code=1) from exc

    resolved_port = port if port is not None else int(os.environ.get("PORT", "8000"))
    console.print(
        f"[bold green]OMRKit Studio[/bold green] listening on "
        f"[cyan]http://{host}:{resolved_port}[/cyan] "
        f"(OpenAPI docs: [cyan]http://{host}:{resolved_port}/docs[/cyan])"
    )
    uvicorn.run(
        "omrkit.api.app:create_app",
        factory=True,
        host=host,
        port=resolved_port,
        reload=reload,
    )
