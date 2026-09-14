"""Adaptador de BISHOP para el protocolo de plugins de RIPLEY."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from bishop.core.tracer import capturar_snapshot_gdb


class BishopPlugin:
    """Expone el snapshot de memoria de BISHOP como observaciones JSON."""

    name = "bishop"
    version = "0.1.0"

    def is_available(self) -> bool:
        return True

    def execute(self, workspace: Path, manifest_config: Dict[str, Any]) -> Dict[str, Any]:
        archivos = sorted(Path(workspace).rglob("*.c"))
        observaciones = []
        reportes = []
        for archivo in archivos:
            snapshot = capturar_snapshot_gdb(
                archivo,
                linea_corte=manifest_config.get("line"),
            )
            reporte = snapshot.to_dict()
            reportes.append(reporte)
            for bloque in snapshot.heap:
                if bloque.esta_liberado or bloque.punteros_referenciantes:
                    continue
                observaciones.append({
                    "rule_code": "BISHOP001",
                    "severity": "warning",
                    "file": str(archivo),
                    "line": bloque.linea_asignacion or 1,
                    "message": f"Bloque de heap huérfano de {bloque.tamanio_bytes} bytes.",
                    "suggestion": "Liberar el bloque y conservar una referencia válida.",
                    "source_plugin": self.name,
                })
        return {
            "ok": not observaciones,
            "observaciones": observaciones,
            "reportes": reportes,
        }
