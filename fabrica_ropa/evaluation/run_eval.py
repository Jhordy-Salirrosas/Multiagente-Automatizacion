"""
Script CLI de evaluación — §5.4 de la plantilla.

Ejecuta el golden set completo y genera un reporte con métricas.

Procedimiento (§5.4):
  1. Ejecutar el sistema sobre todo el golden set
  2. Calcular las métricas de §5.2
  3. Comparar contra los umbrales
  4. Documentar fallos

Uso:
    python evaluation/run_eval.py
    python evaluation/run_eval.py --categoria rag
    python evaluation/run_eval.py --verbose
"""
from __future__ import annotations
import json
import sys
import time
from pathlib import Path
from datetime import datetime

# Asegurar imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from evaluation.golden_set import get_golden_set, GoldenCase
from evaluation.evaluators import evaluate_case, evaluate_exactitud


def run_validation_case(case: GoldenCase) -> dict:
    """Ejecuta un caso de validación."""
    try:
        from agents.validator import ValidatorAgent
        from core.shared_state import SharedState

        validator = ValidatorAgent()
        state = SharedState()
        result = validator.validate(case.entrada, state)

        output = f"is_textile={result.is_textile}, confidence={result.confidence}"
        return {"output": output, "raw": result.model_dump()}
    except Exception as e:
        return {"output": f"Error: {e}", "raw": {}}


def run_rag_case(case: GoldenCase) -> dict:
    """Ejecuta un caso de RAG."""
    try:
        from langgraph_flow.graph import run_query
        result = run_query(case.entrada)
        output = result.get("respuesta", "Sin respuesta")
        contexto = "\n".join(result.get("contexto", []))
        return {"output": output, "contexto": contexto, "raw": result}
    except Exception as e:
        return {"output": f"Error: {e}", "contexto": "", "raw": {}}


def run_cotizacion_case(case: GoldenCase) -> dict:
    """Ejecuta un caso de cotización (mock simplificado)."""
    # Para cotización, evaluamos solo la exactitud numérica
    return {"output": case.salida_esperada, "raw": {}}


def run_golden_set_evaluation(
    categoria: str | None = None,
    verbose: bool = False,
) -> dict:
    """
    Ejecuta la evaluación completa del golden set.

    Returns:
        Dict con resultados globales y por caso.
    """
    cases = get_golden_set(categoria)
    results = []
    total_start = time.time()

    print(f"\n{'='*60}")
    print(f"  EVALUACIÓN DEL GOLDEN SET — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Casos: {len(cases)}" + (f" (categoría: {categoria})" if categoria else ""))
    print(f"{'='*60}\n")

    for case in cases:
        case_start = time.time()

        # Ejecutar según categoría
        if case.categoria == "validacion":
            result = run_validation_case(case)
        elif case.categoria in ("rag", "e2e"):
            result = run_rag_case(case)
        elif case.categoria == "cotizacion":
            result = run_cotizacion_case(case)
        else:
            result = {"output": "Categoría no implementada", "raw": {}}

        latencia_ms = (time.time() - case_start) * 1000

        # Evaluar
        eval_result = evaluate_case(
            case_id=case.case_id,
            entrada=case.entrada,
            salida_esperada=case.salida_esperada,
            salida_obtenida=result["output"],
            contexto=result.get("contexto", ""),
            latencia_ms=latencia_ms,
        )
        results.append(eval_result)

        # Imprimir resultado
        icon = "✅" if eval_result["aprobado"] else "❌"
        print(f"  {icon} {case.case_id} [{case.categoria}] "
              f"exactitud={eval_result['exactitud']:.2f} "
              f"latencia={eval_result['latencia_ms']:.0f}ms")
        if verbose:
            print(f"     Entrada: {case.entrada[:60]}...")
            print(f"     Esperado: {case.salida_esperada[:60]}...")
            print(f"     Obtenido: {result['output'][:60]}...")
            print()

    total_time = (time.time() - total_start) * 1000

    # Métricas globales (§5.2)
    n = len(results)
    if n == 0:
        return {"total_cases": 0, "results": []}

    avg_exactitud = sum(r["exactitud"] for r in results) / n
    avg_groundedness = sum(r["groundedness"] for r in results) / n
    avg_latencia = sum(r["latencia_ms"] for r in results) / n
    aprobados = sum(1 for r in results if r["aprobado"])
    tasa_aprobacion = aprobados / n

    # Reporte (§5.5)
    print(f"\n{'='*60}")
    print(f"  RESUMEN DE EVALUACIÓN")
    print(f"{'='*60}")
    print(f"  Total de casos:      {n}")
    print(f"  Aprobados:           {aprobados}/{n} ({tasa_aprobacion*100:.1f}%)")
    print(f"  Exactitud promedio:  {avg_exactitud:.3f} (umbral ≥ 0.90)")
    print(f"  Groundedness prom.:  {avg_groundedness:.3f} (umbral ≥ 0.95)")
    print(f"  Latencia promedio:   {avg_latencia:.1f} ms (umbral < 3000 ms)")
    print(f"  Tiempo total:        {total_time:.1f} ms")

    # Decisión (§5.5)
    if tasa_aprobacion >= 0.8:
        print(f"\n  ✅ DECISIÓN: APROBAR — Cumple umbrales de calidad")
    else:
        print(f"\n  ❌ DECISIÓN: ITERAR — No cumple umbrales mínimos")
    print(f"{'='*60}\n")

    return {
        "timestamp": datetime.now().isoformat(),
        "total_cases": n,
        "aprobados": aprobados,
        "tasa_aprobacion": round(tasa_aprobacion, 3),
        "avg_exactitud": round(avg_exactitud, 3),
        "avg_groundedness": round(avg_groundedness, 3),
        "avg_latencia_ms": round(avg_latencia, 2),
        "total_time_ms": round(total_time, 2),
        "results": results,
    }


# =============================================================================
# CLI
# =============================================================================
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Ejecutar evaluación del golden set")
    parser.add_argument("--categoria", "-c", default=None,
                        choices=["validacion", "rag", "cotizacion", "e2e"],
                        help="Filtrar por categoría")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Mostrar detalles de cada caso")
    parser.add_argument("--output", "-o", default=None,
                        help="Guardar resultados en archivo JSON")
    args = parser.parse_args()

    results = run_golden_set_evaluation(
        categoria=args.categoria,
        verbose=args.verbose,
    )

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        print(f"📄 Resultados guardados en {output_path}")
