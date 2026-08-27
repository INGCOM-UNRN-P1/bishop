"""Modelos de datos para la representación y visualización de memoria en BISHOP."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class VariableMemoria:
    """Representa una variable asignada en Stack o Data segment."""
    nombre: str
    tipo: str
    direccion: str              # Ej: "0x7fffffffdf10"
    valor: str                  # Ej: "42", "0x5555555592a0", "'A'"
    es_puntero: bool = False
    direccion_apuntada: Optional[str] = None
    tamanio_bytes: int = 4

    def to_dict(self) -> Dict[str, Any]:
        return {
            "nombre": self.nombre,
            "tipo": self.tipo,
            "direccion": self.direccion,
            "valor": self.valor,
            "es_puntero": self.es_puntero,
            "direccion_apuntada": self.direccion_apuntada,
            "tamanio_bytes": self.tamanio_bytes,
        }


@dataclass
class BloqueHeap:
    """Representa un bloque de memoria dinámica asignado con malloc/calloc."""
    direccion: str              # Ej: "0x5555555592a0"
    tamanio_bytes: int
    linea_asignacion: Optional[int] = None
    esta_liberado: bool = False
    contenido: str = "..."
    punteros_referenciantes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "direccion": self.direccion,
            "tamanio_bytes": self.tamanio_bytes,
            "linea_asignacion": self.linea_asignacion,
            "esta_liberado": self.esta_liberado,
            "contenido": self.contenido,
            "punteros_referenciantes": self.punteros_referenciantes,
        }


@dataclass
class StackFrameMemoria:
    """Representa un frame de la pila con sus variables locales."""
    funcion: str
    direccion_base: str         # $rbp / $ebp
    direccion_tope: str         # $rsp / $esp
    linea_actual: Optional[int] = None
    variables: List[VariableMemoria] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "funcion": self.funcion,
            "direccion_base": self.direccion_base,
            "direccion_tope": self.direccion_tope,
            "linea_actual": self.linea_actual,
            "variables": [v.to_dict() for v in self.variables],
        }


@dataclass
class SnapshotMemoria:
    """Estado completo de la memoria del proceso en un instante específico."""
    archivo: Path
    linea: int
    frames: List[StackFrameMemoria] = field(default_factory=list)
    heap: List[BloqueHeap] = field(default_factory=list)
    total_bytes_heap_activos: int = 0
    fugas_detectadas: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "archivo": str(self.archivo),
            "linea": self.linea,
            "total_frames": len(self.frames),
            "total_bloques_heap": len(self.heap),
            "total_bytes_heap_activos": self.total_bytes_heap_activos,
            "fugas_detectadas": self.fugas_detectadas,
            "frames": [f.to_dict() for f in self.frames],
            "heap": [b.to_dict() for b in self.heap],
        }
