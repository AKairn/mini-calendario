"""Tests de la GUI: vistas, navegación, casos extremos (muchos eventos, títulos largos) y formulario.

Se saltan automáticamente si no hay pantalla (p. ej. en un servidor Linux sin X).
En GitHub Actions corren en el runner de Windows, que sí tiene escritorio.
Ejecutar con:  python -m unittest -v
"""

import importlib.util
import shutil
import tempfile
import unittest
from datetime import date, timedelta
from importlib.machinery import SourceFileLoader
from pathlib import Path

import modelo
from modelo import Evento

AQUI = Path(__file__).parent
TITULO_LARGO = ("Reunión de seguimiento del proyecto de análisis de datos con el equipo de "
                "bioinformática y revisión de los resultados preliminares del modelo")
PALABRA_LARGA = "Supercalifragilisticoespialidosamentelarguísimo"


def _cargar_calendario():
    # calendario.pyw no tiene extensión .py, así que no se puede hacer `import calendario`.
    spec = importlib.util.spec_from_loader("calendario", SourceFileLoader("calendario", str(AQUI / "calendario.pyw")))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _hay_pantalla() -> bool:
    try:
        import tkinter
        raiz = tkinter.Tk()
        raiz.destroy()
        return True
    except Exception:
        return False


def _todos(widget):
    """Todos los descendientes de un widget."""
    for hijo in widget.winfo_children():
        yield hijo
        yield from _todos(hijo)


@unittest.skipUnless(_hay_pantalla(), "no hay pantalla disponible para tkinter")
class TestGUI(unittest.TestCase):
    def setUp(self):
        self.cal = _cargar_calendario()
        self.tmp = tempfile.mkdtemp()
        self.ruta = Path(self.tmp) / "eventos.json"
        shutil.copy(AQUI / "eventos.ejemplo.json", self.ruta)
        self.app = self.cal.App(self.ruta)
        self.app.geometry("820x560")
        self.app.update()
        self.hoy = date.today()

    def tearDown(self):
        self.app.destroy()
        shutil.rmtree(self.tmp, ignore_errors=True)

    # --- utilidades -----------------------------------------------------------

    def _formulario(self):
        return [w for w in self.app.winfo_children() if isinstance(w, self.cal.FormularioEvento)][-1]

    def _mostrar(self, vista=None):
        self.app.mostrar(vista)
        self.app.update()

    def _paneles(self):
        return [h for h in self.app.contenido.winfo_children() if h.winfo_manager() == "grid"]

    def _textos(self, widget):
        return [w.cget("text") for w in _todos(widget) if w.winfo_class() == "Label"]

    def _anadir_eventos_hoy(self, n):
        for i in range(n):
            self.app.eventos.append(Evento(f"Evento de prueba {i}", self.hoy.isoformat(),
                                           todo_el_dia=False, inicio=f"{8 + i % 12:02d}:00",
                                           notas="Una nota bastante larga para ocupar espacio" if i % 2 else ""))

    def _celda_mes(self, dia):
        for c in self.app.contenido.winfo_children():
            if getattr(c, "dia", None) == dia:
                return c
        self.fail(f"no encuentro la celda del día {dia}")

    # --- vistas y navegación ----------------------------------------------------

    def test_todas_las_vistas_se_dibujan(self):
        for vista in self.cal.VISTAS:
            self._mostrar(vista)
            self.assertTrue(self.app.contenido.winfo_children(), f"la vista {vista} está vacía")
        self.app.siguiente(); self.app.update()
        self.app.anterior(); self.app.update()

    def test_cambiar_de_vista_no_arrastra_la_rejilla(self):
        # Regresión v0.1.1: tras ver Mes (rejilla de 7 columnas), Día salía diminuto
        # porque el frame de contenido conservaba la configuración de filas/columnas de Mes.
        for anterior in ["mes", "semana", "tres"]:
            self._mostrar(anterior)
            self._mostrar("dia")
            c = self.app.contenido
            panel = self._paneles()[0]
            self.assertGreater(c.winfo_width(), 100)
            self.assertGreater(panel.winfo_width(), 0.9 * c.winfo_width(), f"Día estrecho después de {anterior}")
            self.assertGreater(panel.winfo_height(), 0.9 * c.winfo_height(), f"Día bajo después de {anterior}")

        self._mostrar("mes")
        self._mostrar("tres")
        c = self.app.contenido
        paneles = self._paneles()
        self.assertEqual(len(paneles), 3)
        self.assertGreater(sum(p.winfo_width() for p in paneles), 0.9 * c.winfo_width())
        self.assertTrue(all(p.winfo_height() > 0.9 * c.winfo_height() for p in paneles))

    def test_la_app_abre_en_tres_dias_desde_hoy(self):
        self.assertEqual(self.app.vista, "tres")
        self.assertEqual(self.app.fecha, self.hoy)
        textos = [self._textos(p) for p in self._paneles()]
        self.assertIn("Hoy", textos[0])
        self.assertIn("Mañana", textos[1])
        self.assertIn("Pasado mañana", textos[2])

    def test_tres_dias_se_mueve_de_dia_en_dia(self):
        self.app.siguiente(); self.app.update()
        self.assertEqual(self.app.vista, "tres")
        self.assertEqual(self.app.fecha, self.hoy + timedelta(days=1))
        self.assertIn("Mañana", self._textos(self._paneles()[0]))
        self.app.anterior(); self.app.anterior(); self.app.update()
        self.assertIn("Ayer", self._textos(self._paneles()[0]))

    def test_boton_hoy_vuelve_a_hoy_sin_cambiar_de_vista(self):
        # Antes: tras navegar a otro mes y volver a Inicio, Semana y Día seguían en ese otro mes.
        self._mostrar("mes")
        self.app.siguiente(); self.app.siguiente(); self.app.update()
        self.assertNotEqual(self.app.fecha.month, self.hoy.month)
        self.app.ir_a_hoy(); self.app.update()
        self.assertEqual(self.app.vista, "mes")
        self.assertEqual(self.app.fecha, self.hoy)
        self._mostrar("semana")
        # Se compara el texto completo: comprobar solo que aparece el número del lunes no
        # servía (si el lunes es día 2, 6, 20 o 26, "2026" ya lo contiene).
        lunes = modelo.inicio_semana(self.hoy)
        self.assertEqual(self.app.etiqueta_periodo.cget("text"),
                         self.cal.texto_rango(lunes, lunes + timedelta(days=6)))

    # --- casos extremos -----------------------------------------------------------

    def test_mes_muestra_solo_los_eventos_que_caben_y_cuenta_el_resto(self):
        self._anadir_eventos_hoy(12)
        visibles_por_tamano = []
        for tamano in ["700x450", "820x560", "1400x900"]:
            self.app.geometry(tamano)
            self._mostrar("mes")
            self.app.update()
            celda = self._celda_mes(self.hoy)
            total = len(celda.etiquetas)
            visibles = [e for e in celda.etiquetas if e.winfo_manager()]
            self.assertGreaterEqual(len(visibles), 1, tamano)
            for e in visibles:
                self.assertLessEqual(e.winfo_y() + e.winfo_height(), celda.winfo_height(),
                                     f"evento cortado en la celda del mes con la ventana a {tamano}")
            self.assertEqual(celda.mas.cget("text"), f"+{total - len(visibles)} más", tamano)
            self.assertTrue(celda.mas.winfo_ismapped(), f"'+N más' no visible a {tamano}")
            visibles_por_tamano.append(len(visibles))
        self.assertGreater(visibles_por_tamano[-1], visibles_por_tamano[0],
                           "con la ventana grande deberían verse más eventos por celda")

    def test_mes_sin_contador_si_caben_todos(self):
        self._anadir_eventos_hoy(1)
        self._mostrar("mes")
        celda = self._celda_mes(self.hoy)
        self.assertEqual(celda.mas.cget("text"), "")

    def test_muchos_eventos_activan_el_scroll(self):
        self._anadir_eventos_hoy(20)
        for vista in ["dia", "tres", "semana"]:
            self.app.fecha = self.hoy
            self._mostrar(vista)
            listas = [w for w in _todos(self.app.contenido) if isinstance(w, self.cal.ListaDesplazable)]
            con_barra = [l for l in listas if l.barra_visible]
            self.assertTrue(con_barra, f"sin barra de desplazamiento en {vista} con 20 eventos")
            antes = con_barra[0].canvas.yview()
            con_barra[0].desplazar(+3); self.app.update()
            self.assertGreater(con_barra[0].canvas.yview()[0], antes[0], f"el scroll no se mueve en {vista}")

    def test_pocos_eventos_no_muestran_barra(self):
        self._mostrar("dia")
        listas = [w for w in _todos(self.app.contenido) if isinstance(w, self.cal.ListaDesplazable)]
        self.assertFalse(any(l.barra_visible for l in listas))

    def test_titulos_largos_no_ensanchan_las_columnas(self):
        for titulo in (TITULO_LARGO, PALABRA_LARGA):
            self.app.eventos.append(Evento(titulo, self.hoy.isoformat(), notas=TITULO_LARGO))
        for vista in ["tres", "semana", "mes", "dia"]:
            self.app.fecha = self.hoy
            self._mostrar(vista)
            c = self.app.contenido
            for p in self._paneles():
                self.assertLessEqual(p.winfo_x() + p.winfo_width(), c.winfo_width() + 2,
                                     f"una columna se sale de la ventana en {vista}")
            for etiqueta in (w for w in _todos(c) if w.winfo_class() == "Label" and w.winfo_ismapped()):
                wl = int(float(str(etiqueta.cget("wraplength"))))
                if wl:
                    self.assertLessEqual(wl, etiqueta.winfo_width(), f"texto más ancho que su etiqueta en {vista}")

    def test_barra_superior_no_pierde_botones_con_ventana_minima(self):
        self.app.geometry(f"{self.app.px(640)}x{self.app.px(420)}")
        for vista in self.cal.VISTAS:
            self._mostrar(vista)
            barra = self.app.etiqueta_periodo.master
            for w in barra.winfo_children():
                if w is self.app.etiqueta_periodo:
                    continue
                self.assertLessEqual(w.winfo_x() + w.winfo_width(), barra.winfo_width() + 1,
                                     f"botón '{w.cget('text')}' cortado en {vista} con la ventana mínima")

    def test_rueda_sobre_widget_interno_de_tk_no_falla(self):
        # Regresión v0.3: con el desplegable de Color abierto, winfo_containing lanzaba
        # KeyError('popdown') porque esa lista es un widget interno de Tk.
        def containing(*_a):
            raise KeyError("popdown")
        self.app.winfo_containing = containing

        class Ev:
            x_root = y_root = 10
            num, delta = 5, 0
        self.app._rueda(Ev())   # no debe lanzar nada

    def test_json_roto_avisa_y_no_abre_la_app(self):
        roto = Path(self.tmp) / "roto.json"
        roto.write_text('{"eventos": [{"titulo": "Cena", "fecha": "2026-13-01"}]}', encoding="utf-8")
        with self.assertRaises(modelo.ErrorDatos):
            self.cal.App(roto)
        avisos = []
        original = self.cal.avisar_error_datos
        self.cal.avisar_error_datos = lambda ruta, err: avisos.append((ruta, str(err)))
        try:
            self.cal.main(roto)
        finally:
            self.cal.avisar_error_datos = original
        self.assertEqual(len(avisos), 1)
        self.assertIn("«Cena»", avisos[0][1])
        self.assertIn("2026-13-01", roto.read_text(encoding="utf-8"), "no debe modificar el fichero")

    # --- formulario -------------------------------------------------------------

    def test_horas_de_una_cifra_desde_el_formulario(self):
        self.app.nuevo_evento(self.hoy)
        form = self._formulario()
        form.v_titulo.set("A las nueve")
        form.v_todo_el_dia.set(False); form._alternar_horas()
        form.v_inicio.set("9:00"); form.v_fin.set("10:00")
        form._guardar(); self.app.update()
        guardado = next(e for e in modelo.cargar(self.ruta) if e.titulo == "A las nueve")
        self.assertEqual((guardado.inicio, guardado.fin), ("09:00", "10:00"))

    def test_casilla_mostrar_edad(self):
        # 32 años: múltiplo de 4, así la fecha también existe si hoy es 29 de febrero.
        nacimiento = self.hoy.replace(year=self.hoy.year - 32).isoformat()
        for titulo, mostrar in (("Cumple con edad", True), ("Cumple sin edad", False)):
            self.app.nuevo_evento(self.hoy)
            form = self._formulario()
            self.assertIn("disabled", form.c_mostrar_edad.state(), "sin 'Se repite cada año' no aplica")
            form.v_anual.set(True); form._alternar_edad()
            self.assertNotIn("disabled", form.c_mostrar_edad.state())
            form.v_titulo.set(titulo)
            form.v_fecha.set(nacimiento)
            form.v_mostrar_edad.set(mostrar)
            form._guardar(); self.app.update()
            guardado = next(e for e in modelo.cargar(self.ruta) if e.titulo == titulo)
            self.assertEqual(guardado.mostrar_edad, mostrar)
        self._mostrar("tres")
        textos = self._textos(self._paneles()[0])
        # Los dos casos: sin el primero, el test pasaría aunque la edad no saliera nunca.
        self.assertIn("Cumple con edad (32)", textos)
        self.assertIn("Cumple sin edad", textos)
        self.assertNotIn("Cumple sin edad (32)", textos)

    def test_crear_editar_borrar_desde_formulario(self):
        self.app.nuevo_evento(self.hoy)
        form = self._formulario()
        form.v_titulo.set("Prueba GUI")
        form.v_todo_el_dia.set(False); form._alternar_horas()
        form.v_inicio.set("16:00"); form.v_fin.set("17:00")
        form.v_color.set("naranja")
        form._guardar(); self.app.update()
        self.assertIn("Prueba GUI", [e.titulo for e in modelo.cargar(self.ruta)])

        evento = next(e for e in self.app.eventos if e.titulo == "Prueba GUI")
        self.app.editar_evento(evento)
        form = self._formulario()
        form.v_titulo.set("Prueba editada")
        form._guardar(); self.app.update()
        self.assertIn("Prueba editada", [e.titulo for e in modelo.cargar(self.ruta)])

        self.app.borrar_evento(evento); self.app.update()
        self.assertNotIn("Prueba editada", [e.titulo for e in modelo.cargar(self.ruta)])

    def test_evento_invalido_no_se_guarda(self):
        import tkinter.messagebox as mb
        avisos = []
        original = mb.showwarning
        mb.showwarning = lambda *a, **k: avisos.append(a)
        try:
            self.app.nuevo_evento(self.hoy)
            form = self._formulario()
            form.v_titulo.set("Mala"); form.v_todo_el_dia.set(False); form.v_inicio.set("25:99")
            form._guardar()
            form.destroy()
        finally:
            mb.showwarning = original
        self.assertTrue(avisos)
        self.assertNotIn("Mala", [e.titulo for e in self.app.eventos])


if __name__ == "__main__":
    unittest.main()
