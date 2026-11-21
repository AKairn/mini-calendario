"""Tests del modelo. Ejecutar con:  python -m unittest -v"""

import codecs
import tempfile
import unittest
from datetime import date
from pathlib import Path

import modelo
from modelo import Evento


class TestEvento(unittest.TestCase):
    def test_evento_normal_solo_en_su_fecha(self):
        e = Evento("Dentista", "2026-11-17", todo_el_dia=False, inicio="10:00", fin="10:30")
        self.assertTrue(e.ocurre_en(date(2026, 11, 17)))
        self.assertFalse(e.ocurre_en(date(2026, 11, 18)))
        self.assertFalse(e.ocurre_en(date(2027, 11, 17)))

    def test_evento_anual_se_repite(self):
        e = Evento("Cumple Bestie", "1990-03-14", anual=True)
        self.assertTrue(e.ocurre_en(date(2026, 3, 14)))
        self.assertTrue(e.ocurre_en(date(2030, 3, 14)))
        self.assertFalse(e.ocurre_en(date(2026, 3, 15)))
        self.assertFalse(e.ocurre_en(date(1989, 3, 14)))  # antes de nacer no
        self.assertEqual(e.anios(date(2026, 3, 14)), 36)

    def test_anual_29_febrero(self):
        e = Evento("Bisiesto", "2000-02-29", anual=True)
        self.assertTrue(e.ocurre_en(date(2024, 2, 29)))
        self.assertTrue(e.ocurre_en(date(2026, 2, 28)))
        self.assertFalse(e.ocurre_en(date(2024, 2, 28)))

    def test_hora_texto(self):
        self.assertEqual(Evento("A", "2026-01-01").hora_texto(), "Todo el día")
        self.assertEqual(Evento("A", "2026-01-01", False, "09:00", "10:00").hora_texto(), "09:00–10:00")
        self.assertEqual(Evento("A", "2026-01-01", False, "09:00").hora_texto(), "09:00")

    def test_validar(self):
        Evento("Ok", "2026-01-01").validar()
        Evento("Ok", "2026-01-01", False, "09:00", "10:00").validar()
        with self.assertRaises(ValueError):
            Evento("", "2026-01-01").validar()
        with self.assertRaises(ValueError):
            Evento("X", "01/01/2026").validar()
        with self.assertRaises(ValueError):
            Evento("X", "2026-01-01", False, None).validar()
        with self.assertRaises(ValueError):
            Evento("X", "2026-01-01", False, "9h").validar()
        with self.assertRaises(ValueError):
            Evento("X", "2026-01-01", False, "10:00", "09:00").validar()
        with self.assertRaises(ValueError):
            Evento("X", "2026-01-01", color="fucsia").validar()

    def test_validar_normaliza_horas_de_una_cifra(self):
        # Regresión v0.3: "9:00"-"10:00" daba "fin anterior al inicio" porque se comparaba texto.
        e = Evento("X", "2026-01-01", False, "9:00", "10:00")
        e.validar()
        self.assertEqual((e.inicio, e.fin), ("09:00", "10:00"))
        e = Evento("X", "2026-01-01", False, " 9:5 ", "9:30")
        e.validar()
        self.assertEqual((e.inicio, e.fin), ("09:05", "09:30"))
        with self.assertRaises(ValueError):
            Evento("X", "2026-01-01", False, "10:00", "9:00").validar()

    def test_validar_normaliza_la_fecha(self):
        # Desde Python 3.11 fromisoformat acepta "20261121"; se guarda siempre con guiones.
        e = Evento("X", "2026-11-21")
        e.validar()
        self.assertEqual(e.fecha, "2026-11-21")
        for mala in ("2026-13-01", "2026-02-30", "21/11/2026", "", None):
            with self.assertRaises(ValueError, msg=repr(mala)):
                Evento("X", mala).validar()

    def test_mostrar_edad(self):
        dia = date(2026, 3, 14)
        self.assertEqual(Evento("A", "1990-03-14", anual=True).anios(dia), 36)
        self.assertIsNone(Evento("A", "1990-03-14", anual=True, mostrar_edad=False).anios(dia))
        self.assertIsNone(Evento("A", "1990-03-14", anual=False).anios(dia))

    def test_validar_exige_booleanos(self):
        # Regresión v0.3.1: "anual": "false" (con comillas) se tomaba como verdadero y el evento
        # se repetía cada año sin avisar.
        for campo in ("todo_el_dia", "anual", "mostrar_edad"):
            for malo in ("false", "true", "", 0, 1, None):
                with self.assertRaises(ValueError, msg=f"{campo}={malo!r}") as ctx:
                    Evento("X", "2026-01-01", **{campo: malo}).validar()
                self.assertIn(f'"{campo}"', str(ctx.exception))


class TestPersistencia(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ruta = Path(self.tmp.name) / "eventos.json"

    def tearDown(self):
        self.tmp.cleanup()

    def test_cargar_sin_fichero_devuelve_lista_vacia(self):
        self.assertEqual(modelo.cargar(self.ruta), [])

    def test_guardar_y_cargar_ida_y_vuelta(self):
        eventos = [
            Evento("Cumple Bestie", "1990-03-14", anual=True, color="verde"),
            Evento("Dentista", "2026-11-17", todo_el_dia=False, inicio="10:00", fin="10:30", notas="Llevar tarjeta"),
        ]
        modelo.guardar(eventos, self.ruta)
        cargados = modelo.cargar(self.ruta)
        self.assertEqual(sorted(cargados, key=lambda e: e.titulo), sorted(eventos, key=lambda e: e.titulo))
        self.assertIn("Cumple Bestie", self.ruta.read_text(encoding="utf-8"))  # sin escapes \u

    def test_cargar_ignora_claves_desconocidas(self):
        self.ruta.write_text('{"eventos": [{"titulo": "X", "fecha": "2026-01-01", "campo_futuro": 1}]}', encoding="utf-8")
        self.assertEqual(modelo.cargar(self.ruta)[0].titulo, "X")

    def test_cargar_json_antiguo_sin_mostrar_edad(self):
        self.ruta.write_text('{"eventos": [{"titulo": "Cumple", "fecha": "1990-03-14", "anual": true}]}',
                             encoding="utf-8")
        self.assertTrue(modelo.cargar(self.ruta)[0].mostrar_edad)

    def test_cargar_normaliza_horas_guardadas_sin_cero(self):
        # Datos guardados con la v0.2, que permitía "9:00".
        self.ruta.write_text('{"eventos": [{"titulo": "X", "fecha": "2026-01-01", "todo_el_dia": false,'
                             ' "inicio": "9:00", "fin": "9:30"}]}', encoding="utf-8")
        e = modelo.cargar(self.ruta)[0]
        self.assertEqual((e.inicio, e.fin), ("09:00", "09:30"))

    def test_cargar_sin_lista_eventos_no_abre_vacio(self):
        # Regresión v0.3.1: con la clave mal escrita ("Eventos") se cargaba una lista vacía sin
        # avisar y, al guardar el primer evento, se sobrescribía el fichero: se perdía todo.
        for contenido in ('{"version": 1, "Eventos": [{"titulo": "Cumple", "fecha": "1990-03-14", "anual": true}]}',
                          '{"version": 1}', '{}', '{"eventos": null}', '{"eventos": {"titulo": "X"}}'):
            self.ruta.write_text(contenido, encoding="utf-8")
            with self.assertRaises(modelo.ErrorDatos, msg=contenido) as ctx:
                modelo.cargar(self.ruta)
            self.assertIn('"eventos"', str(ctx.exception), contenido)
            self.assertEqual(self.ruta.read_text(encoding="utf-8"), contenido, "cargar() no debe tocar el fichero")

    def test_cargar_fichero_con_bom(self):
        # Regresión v0.3.1: un fichero "UTF-8 con BOM" (p. ej. `Set-Content -Encoding UTF8` en
        # Windows PowerShell 5.1) no abría: "Unexpected UTF-8 BOM".
        contenido = '{"eventos": [{"titulo": "Cumpleaños", "fecha": "2026-01-01"}]}'
        self.ruta.write_bytes(codecs.BOM_UTF8 + contenido.encode("utf-8"))
        eventos = modelo.cargar(self.ruta)
        self.assertEqual([e.titulo for e in eventos], ["Cumpleaños"])
        modelo.guardar(eventos, self.ruta)
        self.assertFalse(self.ruta.read_bytes().startswith(codecs.BOM_UTF8), "guardar() no debe escribir BOM")

    def test_cargar_fichero_roto_lanza_error_legible(self):
        casos = {
            '{"eventos": [{"titulo": "X", "fe': "línea 1",                                       # JSON a medias
            '': "JSON válido",                                                                       # vacío
            '[1, 2]': '"eventos"',                                                                   # no es un objeto
            '{"eventos": [{"titulo": "Cena", "fecha": "2026-13-01"}]}': "«Cena»",                   # fecha imposible
            '{"eventos": [{"titulo": "Cena"}]}': "le falta el campo fecha",
            '{"eventos": [{"titulo": "Cena", "fecha": "2026-01-01", "color": "fucsia"}]}': "fucsia",
            '{"eventos": [{"titulo": "Cena", "fecha": "2026-01-01", "todo_el_dia": false,'
            ' "inicio": "25:00"}]}': "25:00",
            '{"eventos": ["texto suelto"]}': "evento nº 1",
            '{"eventos": [{"titulo": "Cena", "fecha": "2026-01-01", "anual": "false"}]}': '"anual"',
        }
        for contenido, se_espera in casos.items():
            self.ruta.write_text(contenido, encoding="utf-8")
            with self.assertRaises(modelo.ErrorDatos, msg=contenido) as ctx:
                modelo.cargar(self.ruta)
            self.assertIn(se_espera, str(ctx.exception), contenido)
            self.assertEqual(self.ruta.read_text(encoding="utf-8"), contenido, "cargar() no debe tocar el fichero")


class TestConsultas(unittest.TestCase):
    def setUp(self):
        self.eventos = [
            Evento("Reunión", "2026-11-17", todo_el_dia=False, inicio="12:00", fin="13:00"),
            Evento("Dentista", "2026-11-17", todo_el_dia=False, inicio="10:00", fin="10:30"),
            Evento("Festivo", "2026-11-17"),
            Evento("Cumple Bestie", "1990-11-17", anual=True),
            Evento("Otro día", "2026-11-18"),
        ]

    def test_eventos_del_dia_orden(self):
        hoy = modelo.eventos_del_dia(self.eventos, date(2026, 11, 17))
        self.assertEqual([e.titulo for e in hoy], ["Cumple Bestie", "Festivo", "Dentista", "Reunión"])

    def test_eventos_por_dia(self):
        d = modelo.eventos_por_dia(self.eventos, date(2026, 11, 16), date(2026, 11, 18))
        self.assertEqual(sorted(d), [date(2026, 11, 16), date(2026, 11, 17), date(2026, 11, 18)])
        self.assertEqual(d[date(2026, 11, 16)], [])
        self.assertEqual([e.titulo for e in d[date(2026, 11, 18)]], ["Otro día"])

    def test_inicio_semana(self):
        self.assertEqual(modelo.inicio_semana(date(2026, 11, 16)), date(2026, 11, 16))  # lunes
        self.assertEqual(modelo.inicio_semana(date(2026, 11, 22)), date(2026, 11, 16))  # domingo


if __name__ == "__main__":
    unittest.main()
