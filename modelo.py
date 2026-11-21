"""Modelo de datos del mini calendario: eventos y persistencia en JSON.

No depende de tkinter, así que se puede importar y probar desde Jupyter
o con `python -m unittest` sin que se abra ninguna ventana.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

# Colores disponibles. La GUI traduce el nombre a un código hex;
# en el JSON solo se guarda el nombre.
COLORES = ["azul", "verde", "rojo", "naranja", "morado", "gris"]
COLOR_POR_DEFECTO = "azul"

RUTA_POR_DEFECTO = Path(__file__).with_name("eventos.json")


@dataclass
class Evento:
    titulo: str
    fecha: str                 # ISO "YYYY-MM-DD"
    todo_el_dia: bool = True
    inicio: str | None = None  # "HH:MM" o None
    fin: str | None = None     # "HH:MM" o None
    color: str = COLOR_POR_DEFECTO
    anual: bool = False        # se repite cada año (cumpleaños, aniversarios)
    notas: str = ""
    # Solo para anuales: mostrar los años cumplidos. Va al final para no cambiar el orden de
    # los campos anteriores; los JSON antiguos, que no lo tienen, toman el valor por defecto.
    mostrar_edad: bool = True

    # --- helpers ---------------------------------------------------------

    @property
    def fecha_date(self) -> date:
        return date.fromisoformat(self.fecha)

    def ocurre_en(self, dia: date) -> bool:
        """True si el evento cae en `dia` (teniendo en cuenta los anuales)."""
        f = self.fecha_date
        if self.anual:
            # Un cumpleaños del 29 de febrero se celebra el 28 en años no bisiestos.
            if f.month == 2 and f.day == 29 and not _es_bisiesto(dia.year):
                return dia.month == 2 and dia.day == 28
            return (f.month, f.day) == (dia.month, dia.day) and dia.year >= f.year
        return f == dia

    def hora_texto(self) -> str:
        if self.todo_el_dia or not self.inicio:
            return "Todo el día"
        return f"{self.inicio}–{self.fin}" if self.fin else self.inicio

    def anios(self, dia: date) -> int | None:
        """Para eventos anuales con la edad activada: años cumplidos en `dia` (si no, None)."""
        if not (self.anual and self.mostrar_edad):
            return None
        return dia.year - self.fecha_date.year

    def validar(self) -> None:
        """Comprueba que el evento es coherente y normaliza fecha y horas.

        Lanza ValueError con un mensaje legible si algo está mal. Si todo está bien, deja la
        fecha como "AAAA-MM-DD" y las horas como "HH:MM" con dos cifras ("9:5" -> "09:05"):
        el orden y las comparaciones se hacen sobre el texto, y "10:00" < "9:00" como texto.
        """
        if not isinstance(self.titulo, str) or not self.titulo.strip():
            raise ValueError("El título no puede estar vacío.")
        try:
            # Desde Python 3.11, fromisoformat también acepta "20261121"; se reescribe con guiones.
            self.fecha = date.fromisoformat(self.fecha).isoformat()
        except (TypeError, ValueError):
            raise ValueError(f"Fecha no válida: '{self.fecha}'. Tiene que ser una fecha que exista, "
                             "con el formato AAAA-MM-DD.") from None
        if self.color not in COLORES:
            raise ValueError(f"Color desconocido: '{self.color}'. Usa uno de: {', '.join(COLORES)}.")
        # En un JSON editado a mano, "false" (con comillas) es un texto no vacío y Python lo
        # trataría como verdadero: un evento con "anual": "false" se repetiría cada año.
        for campo in ("todo_el_dia", "anual", "mostrar_edad"):
            valor = getattr(self, campo)
            if not isinstance(valor, bool):
                raise ValueError(f'El campo "{campo}" tiene que ser true o false (sin comillas), '
                                 f"no {json.dumps(valor, ensure_ascii=False, default=str)}.")
        if self.todo_el_dia:
            return
        if not self.inicio:
            raise ValueError("Indica una hora de inicio o marca 'Todo el día'.")
        self.inicio = _normalizar_hora(self.inicio)
        if self.fin:
            self.fin = _normalizar_hora(self.fin)
            if self.fin <= self.inicio:
                raise ValueError("La hora de fin debe ser posterior a la de inicio.")


def _normalizar_hora(texto: str) -> str:
    """'9:5' -> '09:05'. Lanza ValueError si no es una hora válida."""
    try:
        t = datetime.strptime(texto.strip(), "%H:%M")
    except (AttributeError, ValueError):
        raise ValueError(f"Hora no válida: '{texto}'. Usa el formato HH:MM.") from None
    return f"{t.hour:02d}:{t.minute:02d}"


def _es_bisiesto(anio: int) -> bool:
    return anio % 4 == 0 and (anio % 100 != 0 or anio % 400 == 0)


# --- persistencia ----------------------------------------------------------

class ErrorDatos(Exception):
    """eventos.json no se puede usar: JSON mal formado o algún evento inválido."""


def cargar(ruta: Path = RUTA_POR_DEFECTO) -> list[Evento]:
    """Lee y valida los eventos del JSON. Si el fichero no existe, devuelve lista vacía.

    Si el fichero está roto o algún evento es inválido (p. ej. editado a mano con una fecha
    imposible), lanza ErrorDatos con un mensaje que dice qué evento falla y por qué.
    Nunca modifica el fichero.
    """
    try:
        # "utf-8-sig" lee igual un fichero con o sin BOM (la marca que añaden algunos editores y
        # `Set-Content -Encoding UTF8` en Windows PowerShell 5.1). guardar() escribe sin BOM.
        with open(ruta, encoding="utf-8-sig") as f:
            datos = json.load(f)
    except FileNotFoundError:
        return []
    except json.JSONDecodeError as err:
        raise ErrorDatos(f"El fichero no es JSON válido (línea {err.lineno}, columna {err.colno}): {err.msg}.") from None
    except UnicodeDecodeError:
        raise ErrorDatos("El fichero no está guardado en UTF-8.") from None

    # La lista "eventos" es obligatoria: guardar() siempre la escribe. Si faltara (p. ej. la clave
    # mal escrita a mano) y se abriera la app vacía, al guardar el primer evento se sobrescribiría
    # el fichero y se perderían todos los demás.
    if not isinstance(datos, dict) or not isinstance(datos.get("eventos"), list):
        raise ErrorDatos('El fichero debe ser un objeto con la lista "eventos" (en minúsculas): '
                         '{"eventos": [...]}.')
    lista = datos["eventos"]

    campos = Evento.__dataclass_fields__
    eventos = []
    for n, e in enumerate(lista, start=1):
        nombre = f"evento nº {n}"
        try:
            if not isinstance(e, dict):
                raise ValueError("no tiene el formato {\"titulo\": ..., \"fecha\": ...}.")
            if e.get("titulo"):
                nombre += f" («{e['titulo']}»)"
            faltan = [c for c in ("titulo", "fecha") if c not in e]
            if faltan:
                raise ValueError(f"le falta el campo {', '.join(faltan)}.")
            # Se ignoran claves desconocidas para que un JSON de una versión futura no rompa esta.
            evento = Evento(**{k: v for k, v in e.items() if k in campos})
            evento.validar()   # también normaliza horas ("9:00" -> "09:00") y fecha
        except (TypeError, ValueError) as err:
            raise ErrorDatos(f"Problema en el {nombre}: {err}") from None
        eventos.append(evento)
    return eventos


def guardar(eventos: list[Evento], ruta: Path = RUTA_POR_DEFECTO) -> None:
    """Escribe todos los eventos al JSON (ordenados por fecha y hora)."""
    ordenados = sorted(eventos, key=lambda e: (e.fecha, e.inicio or ""))
    datos = {"version": 1, "eventos": [asdict(e) for e in ordenados]}
    # Se escribe en un temporal y luego se renombra: si falla a medias, no se pierde el JSON anterior.
    tmp = ruta.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=2)
    tmp.replace(ruta)


# --- consultas -------------------------------------------------------------

def _clave_orden(e: Evento) -> tuple:
    # Primero los de todo el día, después por hora de inicio, después por título.
    return (not (e.todo_el_dia or not e.inicio), e.inicio or "", e.titulo.lower())


def eventos_del_dia(eventos: list[Evento], dia: date) -> list[Evento]:
    return sorted((e for e in eventos if e.ocurre_en(dia)), key=_clave_orden)


def eventos_por_dia(eventos: list[Evento], desde: date, hasta: date) -> dict[date, list[Evento]]:
    """Diccionario {dia: [eventos]} para cada día del intervalo cerrado [desde, hasta]."""
    resultado: dict[date, list[Evento]] = {}
    dia = desde
    while dia <= hasta:
        resultado[dia] = eventos_del_dia(eventos, dia)
        dia += timedelta(days=1)
    return resultado


def inicio_semana(dia: date) -> date:
    """Lunes de la semana a la que pertenece `dia`."""
    return dia - timedelta(days=dia.weekday())
