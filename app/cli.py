import asyncio
import csv
from pathlib import Path
from typing import Annotated

import typer

from app.core.llm import LLMClient, LLMServiceError
from app.core.triage import TriageProcessingError, triage

cli = typer.Typer(
    help="Batch triage and prompt evaluation CLI for Ticket Triage Assistant."
)

CSV_FIELDNAMES = [
    "filename",
    "category",
    "priority",
    "summary",
    "reply_draft",
    "confidence",
    "needs_review",
    "prompt_version",
    "warning",
]


async def _process_batch_async(
    folder: Path,
    out_path: Path,
    client: LLMClient | None = None,
) -> tuple[int, int]:
    """Process all .txt files in folder, continuing past individual failures."""
    txt_files = sorted(folder.glob("*.txt"))
    succeeded = 0
    failed = 0

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=CSV_FIELDNAMES)
        writer.writeheader()

        for file_path in txt_files:
            try:
                message = file_path.read_text(encoding="utf-8")
                if not message.strip():
                    raise ValueError("File is empty.")

                result = await triage(message, client=client)
                writer.writerow(
                    {
                        "filename": file_path.name,
                        "category": result.category.value,
                        "priority": result.priority.value,
                        "summary": result.summary,
                        "reply_draft": result.reply_draft,
                        "confidence": result.confidence,
                        "needs_review": result.needs_review,
                        "prompt_version": result.prompt_version,
                        "warning": result.warning or "",
                    }
                )
                succeeded += 1
                typer.echo(
                    f"[OK]   {file_path.name} -> "
                    f"{result.category.value} | {result.priority.value}"
                )
            except (
                LLMServiceError,
                TriageProcessingError,
                OSError,
                ValueError,
            ) as exc:
                failed += 1
                typer.secho(
                    f"[FAIL] {file_path.name} -> {exc}",
                    fg=typer.colors.RED,
                    err=True,
                )

    return succeeded, failed


@cli.command("batch")
def batch_command(
    folder: Annotated[
        Path,
        typer.Argument(help="Directory containing .txt support messages."),
    ],
    out: Annotated[
        Path,
        typer.Option("--out", "-o", help="Destination CSV file for triage results."),
    ] = Path("results.csv"),
) -> None:
    """Triage every .txt file in a folder and write results to CSV (FR-18)."""
    if not folder.is_dir():
        typer.secho(f"Error: Directory not found: {folder}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    succeeded, failed = asyncio.run(_process_batch_async(folder=folder, out_path=out))
    typer.echo(
        f"\nBatch complete: {succeeded} succeeded, {failed} failed. Saved to {out}."
    )


def compute_evaluation_metrics(
    results_csv: Path,
    labels_csv: Path,
) -> dict[str, object]:
    """Compare predicted CSV against ground-truth labels and compute accuracy."""
    with labels_csv.open("r", encoding="utf-8", newline="") as f:
        labels_reader = csv.DictReader(f)
        ground_truth: dict[str, dict[str, str]] = {}
        for row in labels_reader:
            fname = row["filename"].strip()
            cat = (row.get("category") or row.get("expected_category") or "").strip()
            prio = (row.get("priority") or row.get("expected_priority") or "").strip()
            ground_truth[fname] = {"category": cat, "priority": prio}

    with results_csv.open("r", encoding="utf-8", newline="") as f:
        results_reader = csv.DictReader(f)
        predictions = {row["filename"].strip(): row for row in results_reader}

    total = 0
    category_correct = 0
    priority_correct = 0
    mismatches: list[str] = []

    for fname, expected in sorted(ground_truth.items()):
        if fname not in predictions:
            mismatches.append(f"{fname}: MISSING in {results_csv.name}")
            total += 1
            continue

        pred = predictions[fname]
        total += 1
        pred_cat = pred["category"].strip()
        pred_prio = pred["priority"].strip()

        cat_ok = pred_cat == expected["category"]
        prio_ok = pred_prio == expected["priority"]

        if cat_ok:
            category_correct += 1
        if prio_ok:
            priority_correct += 1

        if not (cat_ok and prio_ok):
            mismatches.append(
                f"{fname}: expected=({expected['category']}, {expected['priority']}) "
                f"got=({pred_cat}, {pred_prio})"
            )

    cat_acc = (category_correct / total * 100.0) if total > 0 else 0.0
    prio_acc = (priority_correct / total * 100.0) if total > 0 else 0.0

    return {
        "total": total,
        "category_correct": category_correct,
        "priority_correct": priority_correct,
        "category_accuracy": cat_acc,
        "priority_accuracy": prio_acc,
        "mismatches": mismatches,
    }


@cli.command("evaluate")
def evaluate_command(
    results_csv: Annotated[
        Path,
        typer.Argument(help="Path to generated results.csv."),
    ],
    labels_csv: Annotated[
        Path,
        typer.Argument(help="Path to ground-truth labels.csv."),
    ],
) -> None:
    """Compare batch results against labels.csv and print accuracy (FR-19)."""
    if not results_csv.is_file() or not labels_csv.is_file():
        typer.secho(
            "Error: Both results CSV and labels CSV must exist.",
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=1)

    metrics = compute_evaluation_metrics(results_csv, labels_csv)
    total = metrics["total"]
    cat_acc = metrics["category_accuracy"]
    prio_acc = metrics["priority_accuracy"]

    typer.echo("\n=== Prompt Evaluation Report ===")
    typer.echo(f"Evaluated tickets : {total}")
    typer.echo(
        f"Category accuracy : {cat_acc:.1f}% "
        f"({metrics['category_correct']}/{total}) [Target: >= 80.0%]"
    )
    typer.echo(
        f"Priority accuracy : {prio_acc:.1f}% "
        f"({metrics['priority_correct']}/{total}) [Target: >= 70.0%]"
    )

    mismatches: list[str] = metrics["mismatches"]  # type: ignore[assignment]
    if mismatches:
        typer.echo("\nMismatches for Error Analysis:")
        for item in mismatches:
            typer.echo(f"  - {item}")


if __name__ == "__main__":
    cli()
