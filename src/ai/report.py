from __future__ import annotations

import json
from pathlib import Path

from rich.console import Console

from src.ai.generator import generate_email, generate_report, generate_research_brief


console = Console()


def process_all(audited_file: str = "leads_audited.json", output_file: str = "leads_final.json") -> None:
    leads = json.loads(Path(audited_file).read_text(encoding="utf-8"))
    results = []

    for lead in leads:
        console.print(f"\n[cyan]AI içerik üretiliyor:[/cyan] {lead['name']}")
        lead["research_brief"] = generate_research_brief(lead)
        lead["ai_report"] = generate_report(lead)
        lead["ai_email"] = generate_email(lead)
        results.append(lead)
        console.print("[green]✓ araştırma özeti, rapor ve satış maili hazır[/green]")

    Path(output_file).write_text(
        json.dumps(results, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    console.print(f"\n[bold green]✅ AI içerikler hazır → {output_file}[/bold green]")


if __name__ == "__main__":
    process_all()
