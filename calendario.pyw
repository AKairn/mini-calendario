"""Mini calendario: ventana ligera para ver lo pendiente de los próximos días, la semana y el mes.

Solo usa la librería estándar (tkinter). Los datos viven en eventos.json, junto a este fichero.
Extensión .pyw para que en Windows se abra sin consola al ejecutarlo con pythonw.exe.
"""

from __future__ import annotations

import calendar
import sys
import tkinter as tk
from datetime import date, timedelta
from tkinter import messagebox, ttk

import modelo
from modelo import Evento

# --- constantes de presentación ---------------------------------------------

MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio",
         "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
DIAS_CORTOS = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
DIAS_LARGOS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
NOMBRES_RELATIVOS = {-1: "Ayer", 0: "Hoy", 1: "Mañana", 2: "Pasado mañana"}

COLORES_HEX = {
    "azul": "#3b6fd1",
    "verde": "#2e9e5b",
    "rojo": "#d1483b",
    "naranja": "#e08a2e",
    "morado": "#8a5cc9",
    "gris": "#7a7a7a",
}
FONDO = "#f7f7f7"
FONDO_HOY = "#fff4d6"
FONDO_FINDE = "#efefef"
FONDO_OTRO_MES = "#fafafa"
TEXTO_SUAVE = "#8a8a8a"
BORDE = "#d9d9d9"

FUENTE = ("Segoe UI", 10)
FUENTE_PEQ = ("Segoe UI", 9)
FUENTE_TITULO = ("Segoe UI", 13, "bold")
FUENTE_CABECERA = ("Segoe UI", 10, "bold")

DIAS_VISTA_TRES = 3

# Vistas: clave interna -> texto del botón (en el orden en que aparecen en la barra).
VISTAS = {"tres": "3 días", "dia": "Día", "semana": "Semana", "mes": "Mes"}


def activar_dpi_windows() -> None:
    """Evita que Windows escale la ventana como un mapa de bits borroso en pantallas con zoom (125 %, 150 %...).

    Hay que llamarlo ANTES de crear la ventana. Fuera de Windows no hace nada.
    """
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError, OSError):
            pass


def fecha_larga(d: date) -> str:
    return f"{DIAS_LARGOS[d.weekday()]} {d.day} de {MESES[d.month - 1]}"


def texto_rango(desde: date, hasta: date) -> str:
    """'16–22 de noviembre 2026', '30 nov – 6 dic 2026' o '29 dic 2026 – 4 ene 2027'."""
    if (desde.year, desde.month) == (hasta.year, hasta.month):
        return f"{desde.day}–{hasta.day} de {MESES[desde.month - 1]} {desde.year}"
    if desde.year == hasta.year:
        return f"{desde.day} {MESES[desde.month - 1][:3]} – {hasta.day} {MESES[hasta.month - 1][:3]} {hasta.year}"
    return (f"{desde.day} {MESES[desde.month - 1][:3]} {desde.year} – "
            f"{hasta.day} {MESES[hasta.month - 1][:3]} {hasta.year}")


def titulo_y_subtitulo(dia: date, hoy: date) -> tuple[str, str]:
    """Cabecera de cada columna de la vista 3 días: ('Mañana', 'domingo 22 de noviembre') o ('Jueves', '26 de noviembre')."""
    relativo = NOMBRES_RELATIVOS.get((dia - hoy).days)
    if relativo:
        return relativo, fecha_larga(dia)
    return DIAS_LARGOS[dia.weekday()].capitalize(), f"{dia.day} de {MESES[dia.month - 1]}"


def titulo_evento(e: Evento, dia: date) -> str:
    """Título con los años cumplidos si es anual y tiene la edad activada.

    La vista Mes no lo usa a propósito: en sus celdas no sobra espacio.
    """
    n = e.anios(dia)
    return f"{e.titulo} ({n})" if n else e.titulo


def ajustar_al_ancho(etiqueta: tk.Label, minimo: int = 40) -> None:
    """Hace que el texto de la etiqueta se parta en líneas según el ancho que tenga en cada momento.

    Se empieza con un ancho de línea pequeño para que la etiqueta no pida más espacio del que hay
    (una etiqueta con un título largo sin partir ensancharía la columna entera). Después, cada vez que
    cambia de tamaño (<Configure>), el ancho de línea se iguala a su ancho real.
    """
    etiqueta.configure(wraplength=minimo)

    def al_cambiar(ev):
        nuevo = max(ev.width - 6, 10)
        if int(float(str(ev.widget.cget("wraplength")))) != nuevo:
            ev.widget.configure(wraplength=nuevo)

    etiqueta.bind("<Configure>", al_cambiar, add="+")


# --- lista con desplazamiento -------------------------------------------------

class ListaDesplazable(tk.Frame):
    """Contenedor con desplazamiento vertical. Los widgets se añaden a `self.interior`.

    La barra de desplazamiento solo aparece si el contenido no cabe. La rueda del ratón
    la gestiona la App (ver App._rueda), que busca la lista que hay bajo el puntero.
    """

    def __init__(self, padre, bg: str):
        super().__init__(padre, bg=bg)
        # width/height=1: que el Canvas no pida tamaño propio. Por defecto pide ~380×270 px
        # y eso ensancharía las columnas de la vista Semana más allá de la ventana.
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0, width=1, height=1)
        self.barra = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.barra_visible = False
        self.interior = tk.Frame(self.canvas, bg=bg)
        self._id = self.canvas.create_window(0, 0, window=self.interior, anchor="nw")
        self.canvas.configure(yscrollcommand=self._al_desplazar)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.interior.bind("<Configure>", self._actualizar_region)
        self.canvas.bind("<Configure>", self._al_redimensionar)

    def _al_redimensionar(self, ev):
        # El interior ocupa siempre el ancho visible del Canvas (así las etiquetas se parten bien).
        self.canvas.itemconfigure(self._id, width=ev.width)
        self._actualizar_region()

    def _actualizar_region(self, _ev=None):
        alto = max(self.interior.winfo_reqheight(), self.canvas.winfo_height())
        self.canvas.configure(scrollregion=(0, 0, self.canvas.winfo_width(), alto))

    def _al_desplazar(self, primero, ultimo):
        self.barra.set(primero, ultimo)
        cabe = float(primero) <= 0.0 and float(ultimo) >= 1.0
        if cabe and self.barra_visible:
            self.barra.pack_forget()
            self.barra_visible = False
        elif not cabe and not self.barra_visible:
            self.barra.pack(side="right", fill="y", before=self.canvas)
            self.barra_visible = True

    def desplazar(self, pasos: int):
        if self.barra_visible:
            self.canvas.yview_scroll(pasos * 2, "units")


# --- aplicación -------------------------------------------------------------

class App(tk.Tk):
    def __init__(self, ruta=modelo.RUTA_POR_DEFECTO):
        # Se cargan los datos ANTES de crear la ventana: si el JSON está roto, modelo.cargar
        # lanza ErrorDatos y no queda ninguna ventana a medio crear (ver main()).
        eventos = modelo.cargar(ruta)
        activar_dpi_windows()
        super().__init__()
        self.ruta = ruta
        self.eventos: list[Evento] = eventos
        self.fecha = date.today()      # fecha de referencia de la vista actual (la misma para todas)
        self.vista = "tres"
        # Factor de escala de la pantalla (1.0 a 96 ppp, 1.5 con zoom del 150 %...).
        # Las fuentes en puntos ya escalan solas; esto es para los tamaños fijos en píxeles.
        self.escala = self.winfo_fpixels("1i") / 96

        self.title("Mini calendario")
        self.geometry(f"{self.px(820)}x{self.px(560)}")
        self.minsize(self.px(640), self.px(420))
        self.configure(bg=FONDO)
        self.option_add("*Font", FUENTE)
        self.bind("<Escape>", lambda _e: self.destroy())
        self.bind("<Left>", lambda _e: self.anterior())
        self.bind("<Right>", lambda _e: self.siguiente())
        self.bind("<n>", lambda _e: self.nuevo_evento())
        # Rueda del ratón: Windows/macOS usan <MouseWheel>; Linux, los botones 4 y 5.
        for secuencia in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.bind_all(secuencia, self._rueda)

        self._construir_barra()
        self.contenido: tk.Frame | None = None   # lo crea mostrar()
        self.mostrar("tres")
        # Al arrancar con Windows, que salga por encima de lo demás un momento.
        self.lift()
        self.attributes("-topmost", True)
        self._id_topmost = self.after(1500, lambda: self.attributes("-topmost", False))

    def destroy(self):
        # Si se cierra antes de 1,5 s, cancelar la orden pendiente; si no, se ejecutaría
        # sobre una ventana que ya no existe ("invalid command name ...<lambda>").
        if getattr(self, "_id_topmost", None):
            self.after_cancel(self._id_topmost)
        super().destroy()

    def px(self, n: int) -> int:
        """Píxeles ajustados al escalado de la pantalla."""
        return round(n * self.escala)

    # --- barra superior ---------------------------------------------------

    def _construir_barra(self):
        barra = tk.Frame(self, bg=FONDO)
        barra.pack(fill="x", padx=10, pady=8)

        ttk.Button(barra, text="◀", width=3, command=self.anterior).pack(side="left")
        ttk.Button(barra, text="▶", width=3, command=self.siguiente).pack(side="left", padx=(2, 8))
        ttk.Button(barra, text="Hoy", command=self.ir_a_hoy).pack(side="left")

        ttk.Button(barra, text="+ Nuevo", command=self.nuevo_evento).pack(side="right")
        self.var_vista = tk.StringVar(value=self.vista)
        # side="right" coloca de derecha a izquierda, por eso se recorren al revés.
        for clave, texto in reversed(list(VISTAS.items())):
            ttk.Radiobutton(barra, text=texto, value=clave, variable=self.var_vista,
                            command=lambda c=clave: self.mostrar(c)).pack(side="right", padx=3)

        # El título del periodo se coloca el ÚLTIMO a propósito: si la ventana es estrecha, el
        # empaquetador recorta lo último que se colocó, así se corta el título y no los botones.
        self.etiqueta_periodo = tk.Label(barra, text="", font=FUENTE_TITULO, bg=FONDO, anchor="w")
        self.etiqueta_periodo.pack(side="left", padx=14, fill="x", expand=True)

    # --- navegación ---------------------------------------------------------

    def mostrar(self, vista: str | None = None):
        if vista:
            self.vista = vista
            self.var_vista.set(vista)
        # Se destruye y se crea de nuevo el frame entero, no solo sus hijos: el frame guarda
        # la configuración de filas/columnas (columnconfigure/rowconfigure) de la vista anterior,
        # y si se reutilizaba, tras ver Mes (7 columnas) la vista Día ocupaba 1/7 del ancho.
        if self.contenido is not None:
            self.contenido.destroy()
        self.contenido = tk.Frame(self, bg=FONDO)
        self.contenido.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        {"tres": self._vista_tres, "dia": self._vista_dia,
         "semana": self._vista_semana, "mes": self._vista_mes}[self.vista]()

    def ir_a_hoy(self):
        """Vuelve a la fecha de hoy sin cambiar de vista."""
        self.fecha = date.today()
        self.mostrar()

    def anterior(self):
        self._desplazar(-1)

    def siguiente(self):
        self._desplazar(+1)

    def _desplazar(self, signo: int):
        if self.vista in ("tres", "dia"):
            self.fecha += timedelta(days=signo)
        elif self.vista == "semana":
            self.fecha += timedelta(days=7 * signo)
        elif self.vista == "mes":
            mes = self.fecha.month + signo
            anio = self.fecha.year + (mes - 1) // 12
            mes = (mes - 1) % 12 + 1
            self.fecha = date(anio, mes, min(self.fecha.day, calendar.monthrange(anio, mes)[1]))
        self.mostrar()

    def _rueda(self, ev):
        """Desplaza la lista de eventos que hay bajo el puntero, si la hay."""
        try:
            w = self.winfo_containing(ev.x_root, ev.y_root)
        except KeyError:
            # Bajo el puntero hay un widget interno de Tk que tkinter no conoce, como la lista
            # desplegable del Combobox de Color ("popdown"). Ahí no hay nada que desplazar.
            return
        while w is not None and not isinstance(w, ListaDesplazable):
            w = w.master
        if w is None:
            return
        if ev.num == 4:
            w.desplazar(-1)
        elif ev.num == 5:
            w.desplazar(+1)
        elif ev.delta:
            w.desplazar(-1 if ev.delta > 0 else +1)

    # --- vistas -------------------------------------------------------------

    def _vista_tres(self):
        hoy = date.today()
        dias = [self.fecha + timedelta(days=i) for i in range(DIAS_VISTA_TRES)]
        self.etiqueta_periodo.config(text=texto_rango(dias[0], dias[-1]))
        self.contenido.rowconfigure(0, weight=1)
        for i, dia in enumerate(dias):
            self.contenido.columnconfigure(i, weight=1, uniform="col")
            titulo, subtitulo = titulo_y_subtitulo(dia, hoy)
            self._panel_dia(self.contenido, dia, titulo, subtitulo, modo="apilado").grid(
                row=0, column=i, sticky="nsew", padx=(0 if i == 0 else self.px(6), 0))

    def _vista_dia(self):
        self.etiqueta_periodo.config(text=f"{fecha_larga(self.fecha).capitalize()} de {self.fecha.year}")
        self.contenido.columnconfigure(0, weight=1)
        self.contenido.rowconfigure(0, weight=1)
        self._panel_dia(self.contenido, self.fecha, None, modo="ancho").grid(row=0, column=0, sticky="nsew")

    def _vista_semana(self):
        lunes = modelo.inicio_semana(self.fecha)
        self.etiqueta_periodo.config(text=texto_rango(lunes, lunes + timedelta(days=6)))
        self.contenido.rowconfigure(0, weight=1)
        for i in range(7):
            dia = lunes + timedelta(days=i)
            self.contenido.columnconfigure(i, weight=1, uniform="col")
            panel = self._panel_dia(self.contenido, dia, f"{DIAS_CORTOS[i]} {dia.day}", modo="compacto")
            panel.grid(row=0, column=i, sticky="nsew", padx=1)

    def _vista_mes(self):
        anio, mes = self.fecha.year, self.fecha.month
        self.etiqueta_periodo.config(text=f"{MESES[mes - 1].capitalize()} {anio}")
        hoy = date.today()
        semanas = calendar.Calendar(firstweekday=0).monthdatescalendar(anio, mes)
        por_dia = modelo.eventos_por_dia(self.eventos, semanas[0][0], semanas[-1][-1])

        for c, nombre in enumerate(DIAS_CORTOS):
            tk.Label(self.contenido, text=nombre, font=FUENTE_CABECERA, bg=FONDO, fg=TEXTO_SUAVE
                     ).grid(row=0, column=c, sticky="ew", pady=(0, 2))
            self.contenido.columnconfigure(c, weight=1, uniform="col")

        for f, semana in enumerate(semanas, start=1):
            self.contenido.rowconfigure(f, weight=1, uniform="fila")
            for c, dia in enumerate(semana):
                self._celda_mes(dia, por_dia[dia], es_hoy=(dia == hoy), otro_mes=(dia.month != mes)
                                ).grid(row=f, column=c, sticky="nsew", padx=1, pady=1)

    # --- componentes --------------------------------------------------------

    def _panel_dia(self, padre, dia: date, titulo: str | None, subtitulo: str | None = None,
                   modo: str = "ancho") -> tk.Frame:
        """Cabecera + lista desplazable de eventos de un día.

        modo: "ancho" (vista Día: hora a la izquierda), "apilado" (vista 3 días: hora encima del
        título, para dejar todo el ancho al texto) o "compacto" (vista Semana: columnas estrechas).
        """
        compacto = modo == "compacto"
        es_hoy = dia == date.today()
        fondo = FONDO_HOY if es_hoy else "white"
        panel = tk.Frame(padre, bg=fondo, highlightbackground=BORDE, highlightthickness=1)

        cabecera = tk.Frame(panel, bg=fondo)
        cabecera.pack(fill="x", padx=8, pady=(6, 2))
        if compacto:
            tk.Label(cabecera, text=titulo, font=FUENTE_CABECERA, bg=fondo, anchor="w").pack(side="left")
            self._bind_recursivo(cabecera, lambda _e, d=dia: self._ir_a_dia(d))
        else:
            ttk.Button(cabecera, text="+", width=2, command=lambda: self.nuevo_evento(dia)
                       ).pack(side="right", anchor="n")
            if titulo:
                textos = tk.Frame(cabecera, bg=fondo)
                textos.pack(side="left", fill="x", expand=True)
                tk.Label(textos, text=titulo, font=FUENTE_CABECERA, bg=fondo, anchor="w").pack(fill="x")
                if subtitulo:
                    tk.Label(textos, text=subtitulo, fg=TEXTO_SUAVE, bg=fondo, font=FUENTE_PEQ, anchor="w"
                             ).pack(fill="x")

        lista = ListaDesplazable(panel, bg=fondo)
        lista.pack(fill="both", expand=True, pady=(0, 4))

        eventos = modelo.eventos_del_dia(self.eventos, dia)
        if not eventos:
            tk.Label(lista.interior, text="— nada —" if compacto else "Nada pendiente", fg=TEXTO_SUAVE,
                     bg=fondo, font=FUENTE_PEQ).pack(anchor="w", padx=10, pady=4)
        for e in eventos:
            self._fila_evento(lista.interior, e, dia, modo).pack(fill="x", padx=6, pady=2)
        return panel

    def _fila_evento(self, padre, e: Evento, dia: date, modo: str) -> tk.Frame:
        color = COLORES_HEX.get(e.color, COLORES_HEX["gris"])
        fila = tk.Frame(padre, bg="white", highlightbackground=BORDE, highlightthickness=1, cursor="hand2")
        tk.Frame(fila, bg=color, width=self.px(5)).pack(side="left", fill="y")
        if modo == "compacto":
            texto = titulo_evento(e, dia) if (e.todo_el_dia or not e.inicio) else f"{e.inicio}\n{titulo_evento(e, dia)}"
            etiqueta = tk.Label(fila, text=texto, bg="white", anchor="w", font=FUENTE_PEQ, justify="left")
            etiqueta.pack(side="left", fill="x", expand=True, padx=4, pady=2)
            ajustar_al_ancho(etiqueta)
        else:
            if modo == "ancho":
                tk.Label(fila, text=e.hora_texto(), bg="white", fg=TEXTO_SUAVE, width=12, anchor="w"
                         ).pack(side="left", anchor="n", padx=(6, 2), pady=4)
            textos = tk.Frame(fila, bg="white")
            textos.pack(side="left", fill="x", expand=True, padx=(0 if modo == "ancho" else 6, 6), pady=4)
            if modo == "apilado":
                tk.Label(textos, text=e.hora_texto(), bg="white", fg=TEXTO_SUAVE, font=FUENTE_PEQ, anchor="w"
                         ).pack(fill="x")
            titulo = tk.Label(textos, text=titulo_evento(e, dia), bg="white", anchor="w", justify="left")
            titulo.pack(fill="x")
            ajustar_al_ancho(titulo)
            if e.notas:
                notas = tk.Label(textos, text=e.notas, bg="white", fg=TEXTO_SUAVE, font=FUENTE_PEQ,
                                 anchor="w", justify="left")
                notas.pack(fill="x")
                ajustar_al_ancho(notas)
        self._bind_recursivo(fila, lambda _ev, ev=e: self.editar_evento(ev))
        return fila

    def _celda_mes(self, dia: date, eventos: list[Evento], es_hoy: bool, otro_mes: bool) -> tk.Frame:
        if es_hoy:
            fondo = FONDO_HOY
        elif otro_mes:
            fondo = FONDO_OTRO_MES
        elif dia.weekday() >= 5:
            fondo = FONDO_FINDE
        else:
            fondo = "white"
        celda = tk.Frame(self.contenido, bg=fondo, highlightbackground=BORDE, highlightthickness=1,
                         width=self.px(100), height=self.px(70), cursor="hand2")
        celda.grid_propagate(False)
        celda.pack_propagate(False)
        celda.dia = dia

        # Número del día a la izquierda y, si no caben todos, "+N más" a la derecha en la misma línea:
        # así el aviso se ve siempre, aunque la celda sea pequeña.
        cabecera = tk.Frame(celda, bg=fondo)
        cabecera.pack(fill="x")
        tk.Label(cabecera, text=str(dia.day), bg=fondo, anchor="w", padx=4,
                 font=FUENTE_CABECERA if es_hoy else FUENTE_PEQ,
                 fg="black" if (es_hoy or not otro_mes) else TEXTO_SUAVE).pack(side="left")
        celda.mas = tk.Label(cabecera, text="", bg=fondo, fg=TEXTO_SUAVE, font=FUENTE_PEQ, padx=4)
        celda.mas.pack(side="right")
        self._bind_recursivo(celda, lambda _ev, d=dia: self._ir_a_dia(d))

        # Se crean etiquetas para todos los eventos, pero solo se colocan las que caben.
        # Cuántas caben se recalcula cada vez que la celda cambia de tamaño (<Configure>):
        # con la ventana pequeña se ven menos y con la ventana maximizada, más.
        celda.cabecera = cabecera
        celda.etiquetas = []
        for e in eventos:
            color = COLORES_HEX.get(e.color, COLORES_HEX["gris"])
            texto = e.titulo if (e.todo_el_dia or not e.inicio) else f"{e.inicio} {e.titulo}"
            et = tk.Label(celda, text=texto, bg=color, fg="white", anchor="w", font=FUENTE_PEQ, padx=3)
            et.bind("<Button-1>", lambda _ev, ev=e: self.editar_evento(ev))
            celda.etiquetas.append(et)
        celda.bind("<Configure>", lambda _ev, c=celda: self._repartir_celda(c), add="+")
        return celda

    @staticmethod
    def _repartir_celda(celda) -> None:
        """Coloca en la celda del mes tantos eventos como quepan enteros y actualiza el "+N más"."""
        etiquetas = celda.etiquetas
        if not etiquetas:
            return
        borde = 2 * int(celda.cget("highlightthickness"))
        alto_libre = celda.winfo_height() - borde - celda.cabecera.winfo_reqheight()
        alto_linea = etiquetas[0].winfo_reqheight() + 2      # pady=1 arriba y abajo
        mostrar = min(len(etiquetas), max(0, alto_libre // alto_linea))
        for et in etiquetas:
            et.pack_forget()
        for et in etiquetas[:mostrar]:
            et.pack(fill="x", padx=3, pady=1)
        ocultos = len(etiquetas) - mostrar
        celda.mas.configure(text=f"+{ocultos} más" if ocultos else "")

    def _ir_a_dia(self, dia: date):
        self.fecha = dia
        self.mostrar("dia")

    @staticmethod
    def _bind_recursivo(widget, callback):
        widget.bind("<Button-1>", callback)
        for hijo in widget.winfo_children():
            App._bind_recursivo(hijo, callback)

    # --- eventos ------------------------------------------------------------

    def nuevo_evento(self, dia: date | None = None):
        if dia is None:
            dia = self.fecha
        FormularioEvento(self, Evento(titulo="", fecha=dia.isoformat()), es_nuevo=True)

    def editar_evento(self, evento: Evento):
        FormularioEvento(self, evento, es_nuevo=False)

    def guardar_evento(self, evento: Evento, es_nuevo: bool):
        if es_nuevo:
            self.eventos.append(evento)
        self._persistir()

    def borrar_evento(self, evento: Evento):
        self.eventos.remove(evento)
        self._persistir()

    def _persistir(self):
        try:
            modelo.guardar(self.eventos, self.ruta)
        except OSError as err:
            messagebox.showerror("Error al guardar", f"No se pudo escribir {self.ruta}:\n{err}", parent=self)
        self.mostrar()


# --- formulario ---------------------------------------------------------------

class FormularioEvento(tk.Toplevel):
    """Diálogo modal para crear o editar un evento. Modifica el objeto Evento in situ al guardar."""

    def __init__(self, app: App, evento: Evento, es_nuevo: bool):
        super().__init__(app)
        self.app = app
        self.evento = evento
        self.es_nuevo = es_nuevo
        self.title("Nuevo evento" if es_nuevo else "Editar evento")
        self.resizable(False, False)
        self.transient(app)
        self.configure(bg=FONDO)

        self.v_titulo = tk.StringVar(value=evento.titulo)
        self.v_fecha = tk.StringVar(value=evento.fecha)
        self.v_todo_el_dia = tk.BooleanVar(value=evento.todo_el_dia)
        self.v_inicio = tk.StringVar(value=evento.inicio or "")
        self.v_fin = tk.StringVar(value=evento.fin or "")
        self.v_color = tk.StringVar(value=evento.color)
        self.v_anual = tk.BooleanVar(value=evento.anual)
        self.v_mostrar_edad = tk.BooleanVar(value=evento.mostrar_edad)
        self.v_notas = tk.StringVar(value=evento.notas)

        cuerpo = ttk.Frame(self, padding=12)
        cuerpo.pack(fill="both", expand=True)
        cuerpo.columnconfigure(1, weight=1)

        def fila(r, etiqueta, widget):
            ttk.Label(cuerpo, text=etiqueta).grid(row=r, column=0, sticky="w", pady=3, padx=(0, 8))
            widget.grid(row=r, column=1, sticky="ew", pady=3)
            return widget

        entrada_titulo = fila(0, "Título", ttk.Entry(cuerpo, textvariable=self.v_titulo, width=34))
        fila(1, "Fecha (AAAA-MM-DD)", ttk.Entry(cuerpo, textvariable=self.v_fecha))
        ttk.Checkbutton(cuerpo, text="Todo el día", variable=self.v_todo_el_dia,
                        command=self._alternar_horas).grid(row=2, column=1, sticky="w", pady=3)

        horas = ttk.Frame(cuerpo)
        self.e_inicio = ttk.Entry(horas, textvariable=self.v_inicio, width=7)
        self.e_fin = ttk.Entry(horas, textvariable=self.v_fin, width=7)
        self.e_inicio.pack(side="left")
        ttk.Label(horas, text=" a ").pack(side="left")
        self.e_fin.pack(side="left")
        ttk.Label(horas, text="  (HH:MM)", foreground=TEXTO_SUAVE).pack(side="left")
        fila(3, "Horario", horas)

        fila(4, "Color", ttk.Combobox(cuerpo, textvariable=self.v_color, values=modelo.COLORES, state="readonly", width=10))
        ttk.Checkbutton(cuerpo, text="Se repite cada año (cumpleaños, aniversarios)", variable=self.v_anual,
                        command=self._alternar_edad).grid(row=5, column=1, sticky="w", pady=3)
        # Desmárcalo si no sabes el año de nacimiento: la edad saldría mal.
        self.c_mostrar_edad = ttk.Checkbutton(
            cuerpo, text="Mostrar la edad (años desde la fecha)", variable=self.v_mostrar_edad)
        self.c_mostrar_edad.grid(row=6, column=1, sticky="w", padx=(20, 0), pady=(0, 3))
        fila(7, "Notas", ttk.Entry(cuerpo, textvariable=self.v_notas))

        botones = ttk.Frame(cuerpo)
        botones.grid(row=8, column=0, columnspan=2, sticky="e", pady=(12, 0))
        if not es_nuevo:
            ttk.Button(botones, text="Borrar", command=self._borrar).pack(side="left", padx=(0, 16))
        ttk.Button(botones, text="Cancelar", command=self.destroy).pack(side="left", padx=4)
        ttk.Button(botones, text="Guardar", command=self._guardar).pack(side="left")

        self._alternar_horas()
        self._alternar_edad()
        # Colocar el diálogo sobre la ventana principal, no en la esquina de la pantalla.
        self.update_idletasks()
        self.geometry(f"+{app.winfo_rootx() + app.px(80)}+{app.winfo_rooty() + app.px(60)}")
        self.bind("<Return>", lambda _e: self._guardar())
        self.bind("<Escape>", lambda _e: self.destroy())
        entrada_titulo.focus_set()
        self.grab_set()

    def _alternar_horas(self):
        estado = "disabled" if self.v_todo_el_dia.get() else "normal"
        self.e_inicio.config(state=estado)
        self.e_fin.config(state=estado)

    def _alternar_edad(self):
        self.c_mostrar_edad.config(state="normal" if self.v_anual.get() else "disabled")

    def _guardar(self):
        todo_el_dia = self.v_todo_el_dia.get()
        candidato = Evento(
            titulo=self.v_titulo.get().strip(),
            fecha=self.v_fecha.get().strip(),
            todo_el_dia=todo_el_dia,
            inicio=None if todo_el_dia else (self.v_inicio.get().strip() or None),
            fin=None if todo_el_dia else (self.v_fin.get().strip() or None),
            color=self.v_color.get(),
            anual=self.v_anual.get(),
            notas=self.v_notas.get().strip(),
            mostrar_edad=self.v_mostrar_edad.get(),
        )
        try:
            candidato.validar()
        except ValueError as err:
            messagebox.showwarning("Revisa el evento", str(err), parent=self)
            return
        # validar() ya ha normalizado fecha y horas ("9:00" -> "09:00").
        # Copiamos los campos al evento original: la lista de la app guarda la misma referencia.
        self.evento.__dict__.update(candidato.__dict__)
        self.app.guardar_evento(self.evento, self.es_nuevo)
        self.destroy()

    def _borrar(self):
        if messagebox.askyesno("Borrar", f"¿Borrar «{self.evento.titulo}»?", parent=self):
            self.app.borrar_evento(self.evento)
            self.destroy()


def avisar_error_datos(ruta, err: Exception) -> None:
    """Ventana de error cuando eventos.json no se puede usar. Se ve aunque la app se abra con pythonw."""
    raiz = tk.Tk()
    raiz.withdraw()
    raiz.attributes("-topmost", True)   # que no quede escondida detrás de otras ventanas al iniciar sesión
    messagebox.showerror(
        "Mini calendario",
        f"No se puede abrir el calendario porque hay un problema en:\n{ruta}\n\n{err}\n\n"
        "Corrígelo (por ejemplo, en VS Code) y vuelve a abrir la app. No se ha modificado nada.",
        parent=raiz)
    raiz.destroy()


def main(ruta=modelo.RUTA_POR_DEFECTO) -> None:
    try:
        app = App(ruta)
    except modelo.ErrorDatos as err:
        avisar_error_datos(ruta, err)
        return
    app.mainloop()


if __name__ == "__main__":
    main()
