"""
main.py — Punto de entrada del sistema multiagente.

Inicia una conversación CLI con el agente de ventas. El usuario escribe
mensajes en la terminal y el Orchestrator coordina los agentes para
gestionar el flujo completo.

Uso:
    python main.py                    # Modo conversacional interactivo
    python main.py --metrics          # Imprime métricas y sale
    python main.py --demo             # Ejecuta un script de demo predefinido
"""
from __future__ import annotations
import sys
import json
import argparse
from pathlib import Path

# Asegurar que el paquete sea importable
sys.path.insert(0, str(Path(__file__).resolve().parent))

from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.table import Table

from config import validate_config, EXECUTION_MODE
from agents.orchestrator import Orchestrator
from core.shared_state import SharedState, ConversationStage
from core.metrics import metrics


console = Console()


def print_banner() -> None:
    console.print(Panel.fit(
        "[bold cyan]🧵 Fábrica de Ropa - Sistema Multiagente[/bold cyan]\n"
        "[dim]Grupo 01 · Automatización Inteligente de Procesos[/dim]\n\n"
        f"Modo: [yellow]{EXECUTION_MODE}[/yellow] · "
        "Escribe [bold]/salir[/bold] para terminar · "
        "[bold]/estado[/bold] para ver el estado · "
        "[bold]/metricas[/bold] para métricas",
        title="Bienvenido",
        border_style="cyan",
    ))


def print_state(state: SharedState) -> None:
    snap = state.snapshot()
    console.print(Panel(
        json.dumps(snap, indent=2, ensure_ascii=False, default=str),
        title=f"Estado · etapa={state.stage.value}",
        border_style="yellow",
    ))


def print_metrics() -> None:
    summary = metrics.summary()
    if summary.get("total_invocations", 0) == 0:
        console.print("[yellow]Aún no hay métricas registradas.[/yellow]")
        return

    console.print(Panel(
        f"[bold]Total invocaciones:[/bold] {summary['total_invocations']}\n"
        f"[bold]Tasa de éxito:[/bold] {summary['success_rate'] * 100:.1f}%\n"
        f"[bold]Tokens estimados (totales):[/bold] {summary['total_tokens_estimate']}\n"
        f"[bold]Latencia promedio:[/bold] {summary['avg_latency_ms']:.2f} ms",
        title="📊 Métricas globales",
        border_style="green",
    ))

    table = Table(title="Por agente", show_header=True, header_style="bold magenta")
    table.add_column("Agente")
    table.add_column("Inv.", justify="right")
    table.add_column("Éxito %", justify="right")
    table.add_column("Lat. avg (ms)", justify="right")
    table.add_column("Lat. max (ms)", justify="right")
    table.add_column("Tokens", justify="right")
    for agent_name, stats in summary["by_agent"].items():
        table.add_row(
            agent_name,
            str(stats["invocations"]),
            f"{stats['success_rate'] * 100:.0f}",
            f"{stats['avg_latency_ms']:.1f}",
            f"{stats['max_latency_ms']:.1f}",
            str(stats["tokens_estimate"]),
        )
    console.print(table)


def chat_loop() -> None:
    """Bucle de chat interactivo."""
    ok, msg = validate_config()
    if not ok:
        console.print(f"[bold red]{msg}[/bold red]")
        sys.exit(1)
    console.print(f"[green]{msg}[/green]")

    print_banner()

    orchestrator = Orchestrator()
    state = SharedState()

    while True:
        try:
            user_msg = console.input("\n[bold blue]👤 Tú:[/bold blue] ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Sesión terminada.[/dim]")
            break

        if not user_msg:
            continue

        # Comandos meta
        if user_msg.lower() == "/salir":
            console.print("[dim]Hasta luego![/dim]")
            break
        if user_msg.lower() == "/estado":
            print_state(state)
            continue
        if user_msg.lower() == "/metricas":
            print_metrics()
            continue

        # Procesar con el orquestador
        try:
            reply = orchestrator.handle_user_message(user_msg, state)
        except Exception as e:
            console.print(f"[bold red]Error procesando mensaje:[/bold red] {e}")
            continue

        console.print(Panel(Markdown(reply), title="🤖 Asistente", border_style="cyan"))

        # Si el flujo terminó, ofrecer ver métricas
        if state.stage in (ConversationStage.COMPLETE, ConversationStage.REJECTED):
            console.print("\n[dim]Flujo finalizado. Usa /metricas o /estado, o /salir.[/dim]")


def run_demo() -> None:
    """Ejecuta un script de demo predefinido para mostrar el flujo completo."""
    console.print("[bold magenta]🎬 Ejecutando demo automatizado...[/bold magenta]\n")
    orchestrator = Orchestrator()
    state = SharedState()
    scripted_messages = [
        "hola necesito 50 polos con bordado para mi empresa",
        "Mi nombre es Juan Pérez",
        "juan.perez@example.com",
        "polo deportivo cuello redondo con diseño del Bayern Munich",
        "25 de talla S y 25 de talla M",
        "rojo",
        "bordado",
        "2026-06-27",
        "sí, confirmo",
    ]
    for msg in scripted_messages:
        console.print(f"[bold blue]👤 Tú:[/bold blue] {msg}")
        reply = orchestrator.handle_user_message(msg, state)
        console.print(Panel(Markdown(reply), title="🤖 Asistente", border_style="cyan"))
        if state.stage in (ConversationStage.COMPLETE, ConversationStage.REJECTED):
            break

    console.print("\n")
    print_state(state)
    print_metrics()


def main() -> None:
    parser = argparse.ArgumentParser(description="Sistema multiagente Fábrica de Ropa")
    parser.add_argument("--metrics", action="store_true", help="Mostrar métricas y salir")
    parser.add_argument("--demo", action="store_true", help="Ejecutar demo predefinido")
    args = parser.parse_args()

    if args.metrics:
        print_metrics()
        return
    if args.demo:
        run_demo()
        return
    chat_loop()


if __name__ == "__main__":
    main()
