"""
Event Bus — Sistema pub/sub para coordinación entre agentes.

Implementa el componente "event bus" que pide la rúbrica para la integración
con Antigravity. Cada agente puede:
  - publicar eventos (publish)
  - suscribirse a eventos por nombre (subscribe)

Es una implementación in-memory thread-safe, suficiente para la demo y
extensible a Redis/RabbitMQ en producción.
"""
from __future__ import annotations
from collections import defaultdict
from threading import Lock
from typing import Callable

from core.mcp_messages import SystemEvent, AgentName


EventHandler = Callable[[SystemEvent], None]


class EventBus:
    """Bus pub/sub thread-safe."""

    def __init__(self) -> None:
        self._subscribers: dict[str, list[EventHandler]] = defaultdict(list)
        self._lock = Lock()
        self._event_log: list[SystemEvent] = []

    def subscribe(self, event_name: str, handler: EventHandler) -> None:
        """Suscribe un handler a un evento específico."""
        with self._lock:
            self._subscribers[event_name].append(handler)

    def publish(self, event: SystemEvent) -> None:
        """Publica un evento a todos los suscriptores."""
        with self._lock:
            self._event_log.append(event)
            handlers = list(self._subscribers.get(event.event_name, []))
        # Ejecutamos handlers fuera del lock para evitar deadlocks
        for handler in handlers:
            try:
                handler(event)
            except Exception as e:
                # En producción usar logging; aquí lo silenciamos para no romper
                print(f"[WARN] Error en handler de evento '{event.event_name}': {e}")

    def emit(self, source: AgentName, event_name: str, **data) -> SystemEvent:
        """Helper: construye y publica un evento en una sola llamada."""
        event = SystemEvent(source=source, event_name=event_name, data=data)
        self.publish(event)
        return event

    def get_event_log(self) -> list[SystemEvent]:
        """Devuelve el log completo de eventos (para auditoría)."""
        with self._lock:
            return list(self._event_log)


# Instancia global (singleton para simplicidad)
event_bus = EventBus()
