"""
Recolector de métricas del sistema.

Captura las métricas cuantitativas que pide la rúbrica:
  - Latencia por agente (ms)
  - Token usage (input + output)
  - Tasa de éxito (success/error count)
  - Conteo de invocaciones por agente

Persiste a JSONL para análisis posterior.
"""
from __future__ import annotations
import json
import time
from contextlib import contextmanager
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Optional


@dataclass
class AgentInvocation:
    """Registro de una invocación a un agente."""
    agent_name: str
    started_at: datetime
    latency_ms: float
    success: bool
    input_chars: int = 0
    output_chars: int = 0
    tokens_estimate: int = 0  # Estimación: chars/4 (aprox para inglés/español)
    error: Optional[str] = None
    session_id: Optional[str] = None


class MetricsCollector:
    """Recolector central de métricas."""

    def __init__(self, log_path: Optional[Path] = None):
        self._invocations: list[AgentInvocation] = []
        self._lock = Lock()
        self.log_path = log_path

    @contextmanager
    def measure(self, agent_name: str, input_text: str = "", session_id: Optional[str] = None):
        """
        Context manager para medir una invocación.

        Uso:
            with metrics.measure("ValidatorAgent", input_text=msg) as record:
                output = agent.run(msg)
                record.output_chars = len(output)
        """
        record = AgentInvocation(
            agent_name=agent_name,
            started_at=datetime.now(),
            latency_ms=0.0,
            success=False,
            input_chars=len(input_text),
            session_id=session_id,
        )
        start = time.perf_counter()
        try:
            yield record
            record.success = True
        except Exception as e:
            record.error = f"{type(e).__name__}: {e}"
            raise
        finally:
            record.latency_ms = (time.perf_counter() - start) * 1000
            # Estimación de tokens: ~4 chars/token (heurística común)
            record.tokens_estimate = (record.input_chars + record.output_chars) // 4
            self._save(record)

    def _save(self, record: AgentInvocation) -> None:
        with self._lock:
            self._invocations.append(record)
            if self.log_path:
                self.log_path.parent.mkdir(parents=True, exist_ok=True)
                with open(self.log_path, "a", encoding="utf-8") as f:
                    d = asdict(record)
                    d["started_at"] = record.started_at.isoformat()
                    f.write(json.dumps(d, ensure_ascii=False) + "\n")

    def summary(self) -> dict:
        """Resumen agregado de métricas para reporte."""
        with self._lock:
            invs = list(self._invocations)

        if not invs:
            return {"total_invocations": 0}

        by_agent: dict[str, list[AgentInvocation]] = {}
        for inv in invs:
            by_agent.setdefault(inv.agent_name, []).append(inv)

        summary = {
            "total_invocations": len(invs),
            "total_success": sum(1 for i in invs if i.success),
            "total_errors": sum(1 for i in invs if not i.success),
            "success_rate": round(sum(1 for i in invs if i.success) / len(invs), 3),
            "total_tokens_estimate": sum(i.tokens_estimate for i in invs),
            "avg_latency_ms": round(sum(i.latency_ms for i in invs) / len(invs), 2),
            "by_agent": {}
        }

        for agent, items in by_agent.items():
            latencies = [i.latency_ms for i in items]
            summary["by_agent"][agent] = {
                "invocations": len(items),
                "success_rate": round(sum(1 for i in items if i.success) / len(items), 3),
                "avg_latency_ms": round(sum(latencies) / len(latencies), 2),
                "min_latency_ms": round(min(latencies), 2),
                "max_latency_ms": round(max(latencies), 2),
                "tokens_estimate": sum(i.tokens_estimate for i in items),
            }
        return summary


# Instancia global
from config import METRICS_LOG_PATH
metrics = MetricsCollector(log_path=METRICS_LOG_PATH)
