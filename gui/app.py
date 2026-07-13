"""Ventana principal de recordIt (CustomTkinter).

Aspecto inspirado en grabadoras modernas (tema oscuro, forma de onda en vivo,
botón circular de grabar y cronómetro grande). Una sola vista a dos columnas:
izquierda «Grabar» (onda + botón), derecha «Grabaciones» (lista + acciones).

CustomTkinter es Tkinter por debajo (un solo runtime de Python, empaquetable con
PyInstaller). Todo el trabajo pesado (grabar, transcribir, API) corre en hilos de
fondo; la UI se actualiza por cola + after() y nunca se toca desde un hilo.
"""
import collections
import multiprocessing
import os
import queue
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path
from tkinter import Canvas, Menu, StringVar, messagebox

import customtkinter as ctk

from recordit import (acta, audio, claude_auth, config, integracion, pdf, preproceso,
                      registro, rutas, transcripcion, transcripcion_vivo)
from recordit import __version__ as VERSION

# --- Paleta ----------------------------------------------------------------
FONDO = ("#f2f5f7", "#15181c")
TARJETA = ("#ffffff", "#1e242b")
TEXTO = ("#1f2a33", "#e8edf1")
MUTED = ("#5b6b76", "#8b97a1")
SEL = ("#d8eef5", "#10333f")
HOVER = ("#eef3f6", "#243038")
CANVAS_BG = ("#ffffff", "#1e242b")
BASE_LINE = ("#cdd6dc", "#3a444d")
TEAL = "#3a7ca5"
TEAL_HOVER = "#326c90"
ONDA = "#5a9fc4"
ONDA_ACTIVA = "#ff9f45"
CORAL = "#ef5f4c"
CORAL_HOVER = "#d94f3d"
VERDE = "#3ba55d"
AMBAR = "#e0a83e"  # transcripción en curso (dot ◐)

# glifo y color del punto de estado por cada estado de rutas.estado_reunion
_PUNTO_ESTADO = {
    "sin_transcribir": ("○", MUTED),
    "generando": ("◐", AMBAR),
    "transcrita": ("●", TEAL),
    "con_acta": ("●", TEAL),
}

AUTOR = "RecordIt"
SOPORTE = "¿Has encontrado un error? Abre una incidencia en el repositorio del proyecto."

MODELOS = {"Opus (más capaz)": "claude-opus-4-8",
           "Sonnet (más rápido)": "claude-sonnet-4-6"}
MODELOS_INV = {v: k for k, v in MODELOS.items()}


def _modo_oscuro() -> bool:
    return ctk.get_appearance_mode() == "Dark"


def _col(par):
    """Resuelve una tupla (claro, oscuro) al color del modo actual."""
    return par[1] if _modo_oscuro() else par[0]


def _dir_assets() -> Path:
    """Carpeta de imágenes, tanto en dev como empaquetado (PyInstaller)."""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return Path(base) / "gui" / "assets"
    return Path(__file__).resolve().parent / "assets"


def _variante_oscura(img):
    """Variante para fondos oscuros: recolorea la parte navy (oscura) a un tono
    claro, conservando el acento cian y la transparencia."""
    img = img.convert("RGBA")
    px = img.load()
    for y in range(img.height):
        for x in range(img.width):
            r, g, b, a = px[x, y]
            if a == 0:
                continue
            es_cian = b > 110 and g > 110 and r < 130
            luminancia = 0.299 * r + 0.587 * g + 0.114 * b
            if not es_cian and luminancia < 120:
                px[x, y] = (232, 237, 241, a)
    return img


def _tintar(img, rgb):
    """Devuelve la silueta del icono en un único color `rgb`, conservando alfa.

    Ideal para botones de color: un icono monocromo contrasta y es coherente,
    a diferencia del original bicolor (navy+cian) que se ensucia sobre el teal.
    """
    img = img.convert("RGBA")
    r0, g0, b0 = rgb
    px = img.load()
    for y in range(img.height):
        for x in range(img.width):
            a = px[x, y][3]
            if a > 0:
                px[x, y] = (r0, g0, b0, a)
    return img


def _abrir_en_explorador(ruta: Path) -> None:
    if os.name == "nt":
        os.startfile(ruta)  # noqa: A002
    elif sys.platform == "darwin":
        subprocess.run(["open", str(ruta)])
    else:
        subprocess.run(["xdg-open", str(ruta)])


class App:
    def __init__(self, root: ctk.CTk):
        self.root = root
        self.root.title("recordIt")
        self.root.geometry("1000x660")
        self.root.minsize(900, 600)
        self.root.configure(fg_color=FONDO)
        try:  # icono de ventana/taskbar
            import tkinter as tk
            self._icono_win = tk.PhotoImage(file=str(_dir_assets() / "appicon.png"))
            self.root.iconphoto(True, self._icono_win)
        except Exception:  # noqa: BLE001
            pass

        self.cola: "queue.Queue" = queue.Queue()
        self.evento_parada = None
        self.inicio_grabacion = None
        self.grabando = False
        self.trabajando = False
        self.nombre_sel = None
        self.botones_grab = {}
        self.transcribiendo = set()  # bases con transcripción en curso (dot ◐)
        self._mic_idx = {}
        self.niveles = collections.deque(maxlen=400)

        self.f_marca = ctk.CTkFont(size=22, weight="bold")
        self.f_seccion = ctk.CTkFont(size=15, weight="bold")
        self.f_base = ctk.CTkFont(size=13)
        self.f_sub = ctk.CTkFont(size=12)
        self.f_timer = ctk.CTkFont(size=40, weight="bold")
        self.f_boton = ctk.CTkFont(size=30, weight="bold")

        # Si es un AppImage, se integra en el escritorio (icono en el menú).
        integracion.integrar_escritorio(_dir_assets() / "appicon.png")
        self._construir()
        self._refrescar_microfonos()
        self._refrescar_grabaciones()
        # Intenta conectar con Claude automáticamente desde el sistema (CLI/entorno).
        if not claude_auth.conectado():
            claude_auth.conectar()
        self._actualizar_estado_acta()
        self.root.after(60, self._dibujar_onda)
        self.root.after(50, self._drenar_cola)

    def _cargar_imagenes(self):
        """Carga logo e iconos como CTkImage (claro/oscuro). Si falla, queda vacío
        y la interfaz usa texto/caracteres como reserva."""
        self.logo_img = None
        self.iconos = {}
        self._png = {}  # PIL crudos, para tintar bajo demanda
        try:
            from PIL import Image
        except Exception:  # noqa: BLE001
            return
        d = _dir_assets()
        try:
            self.logo_img = ctk.CTkImage(
                light_image=Image.open(d / "logo_clear_64.png"),
                dark_image=Image.open(d / "logo_dark_64.png"), size=(173, 46))
        except Exception:  # noqa: BLE001
            self.logo_img = None
        for nombre in ("micro", "transcribir", "acta", "carpeta", "ajustes", "grabaciones"):
            try:
                base = Image.open(d / f"{nombre}.png").convert("RGBA")
                self._png[nombre] = base
                self.iconos[nombre] = ctk.CTkImage(
                    light_image=base, dark_image=_variante_oscura(base), size=(20, 20))
            except Exception:  # noqa: BLE001
                pass

    def _icono_tintado(self, nombre, rgb, size=20):
        """CTkImage del icono `nombre` en un único color (igual en claro/oscuro)."""
        base = self._png.get(nombre)
        if base is None:
            return None
        tinta = _tintar(base, rgb)
        return ctk.CTkImage(light_image=tinta, dark_image=tinta, size=(size, size))

    # --- estructura -----------------------------------------------------
    def _construir(self):
        self._cargar_imagenes()
        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_rowconfigure(1, weight=1)

        # Cabecera: marca + ajustes.
        cab = ctk.CTkFrame(self.root, fg_color="transparent")
        cab.grid(row=0, column=0, sticky="we", padx=22, pady=(16, 4))
        cab.grid_columnconfigure(0, weight=1)
        izq = ctk.CTkFrame(cab, fg_color="transparent")
        izq.grid(row=0, column=0, sticky="w")
        if self.logo_img is not None:
            ctk.CTkLabel(izq, text="", image=self.logo_img).pack(anchor="w")
        else:
            ctk.CTkLabel(izq, text="recordIt", font=self.f_marca, text_color=TEAL).pack(anchor="w")
        ctk.CTkLabel(izq, text="Grabar · Transcribir · Acta", font=self.f_sub,
                     text_color=MUTED).pack(anchor="w")
        self.lbl_conexion = ctk.CTkLabel(cab, text="", font=self.f_sub, text_color=MUTED)
        self.lbl_conexion.grid(row=0, column=1, sticky="e", padx=(0, 12))
        ctk.CTkButton(cab, text="  Ajustes", image=self.iconos.get("ajustes"), compound="left",
                      width=110, height=36, command=self._on_ajustes,
                      fg_color="transparent", border_width=1, border_color=MUTED,
                      text_color=MUTED, hover_color=SEL,
                      font=self.f_base).grid(row=0, column=2, sticky="e")

        # Cuerpo a dos columnas.
        cuerpo = ctk.CTkFrame(self.root, fg_color="transparent")
        cuerpo.grid(row=1, column=0, sticky="nsew", padx=22, pady=(4, 6))
        cuerpo.grid_columnconfigure(0, weight=3, uniform="col")
        cuerpo.grid_columnconfigure(1, weight=2, uniform="col")
        cuerpo.grid_rowconfigure(0, weight=1)
        self._construir_panel_grabar(cuerpo)
        self._construir_panel_biblioteca(cuerpo)

        # Barra de estado (ancho completo).
        estado = ctk.CTkFrame(self.root, fg_color="transparent")
        estado.grid(row=2, column=0, sticky="we", padx=22, pady=(0, 14))
        estado.grid_columnconfigure(0, weight=1)
        self.lbl_estado = ctk.CTkLabel(estado, text="Listo.", font=self.f_sub,
                                       text_color=MUTED, anchor="w")
        self.lbl_estado.grid(row=0, column=0, sticky="w")
        # Firma de autoría + versión.
        ctk.CTkLabel(estado, text=f"{AUTOR}  ·  v{VERSION}", font=self.f_sub,
                     text_color=MUTED, anchor="e").grid(row=0, column=1, sticky="e")
        self.barra_progreso = ctk.CTkProgressBar(estado, progress_color=TEAL, height=6)
        self.barra_progreso.set(0)
        self.barra_progreso.grid(row=1, column=0, columnspan=2, sticky="we", pady=(4, 0))

    def _construir_panel_grabar(self, master):
        t = ctk.CTkFrame(master, fg_color=TARJETA, corner_radius=18)
        t.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        t.grid_columnconfigure(0, weight=1)
        t.grid_rowconfigure(2, weight=1)

        fila_mic = ctk.CTkFrame(t, fg_color="transparent")
        fila_mic.grid(row=0, column=0, sticky="we", padx=18, pady=(18, 6))
        fila_mic.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(fila_mic, text="", image=self.iconos.get("micro")).grid(
            row=0, column=0, padx=(0, 8))
        self.var_mic = StringVar()
        self.menu_mic = ctk.CTkOptionMenu(
            fila_mic, variable=self.var_mic, values=["(sin micrófonos)"],
            command=self._on_mic_seleccion, fg_color=SEL, button_color=TEAL,
            button_hover_color=TEAL_HOVER, text_color=TEXTO,
            dynamic_resizing=False, anchor="w", font=self.f_sub)
        self.menu_mic.grid(row=0, column=1, sticky="we")
        ctk.CTkButton(fila_mic, text="↻", width=36,
                      command=lambda: self._refrescar_microfonos(reescanear=True),
                      fg_color="transparent", border_width=1, border_color=TEAL,
                      text_color=TEAL, hover_color=SEL, font=self.f_base).grid(row=0, column=2, padx=(8, 0))

        fila_g = ctk.CTkFrame(t, fg_color="transparent")
        fila_g.grid(row=1, column=0, sticky="w", padx=18, pady=(0, 6))
        ctk.CTkLabel(fila_g, text="Ganancia", font=self.f_base,
                     text_color=MUTED).pack(side="left", padx=(0, 10))
        self.var_ganancia = StringVar(value="Auto")
        ctk.CTkSegmentedButton(
            fila_g, values=["Auto", "x3", "Off"], variable=self.var_ganancia,
            width=200, selected_color=TEAL, selected_hover_color=TEAL_HOVER,
            font=self.f_sub).pack(side="left")

        self.canvas_onda = Canvas(t, highlightthickness=0, bd=0, bg=_col(CANVAS_BG))
        self.canvas_onda.grid(row=2, column=0, sticky="nsew", padx=18, pady=8)
        self.canvas_onda.bind("<Configure>", lambda e: self._dibujar_onda())

        self.lbl_tiempo = ctk.CTkLabel(t, text="00:00", font=self.f_timer, text_color=TEXTO)
        self.lbl_tiempo.grid(row=3, column=0, pady=(0, 4))
        self.btn_rec = ctk.CTkButton(
            t, text="●", width=88, height=88, corner_radius=44, command=self._toggle_grabar,
            fg_color=CORAL, hover_color=CORAL_HOVER, text_color="#ffffff", font=self.f_boton)
        self.btn_rec.grid(row=4, column=0, pady=(0, 4))
        self.lbl_rec = ctk.CTkLabel(t, text="Grabar", font=self.f_base, text_color=MUTED)
        self.lbl_rec.grid(row=5, column=0, pady=(0, 18))

    def _construir_panel_biblioteca(self, master):
        t = ctk.CTkFrame(master, fg_color=TARJETA, corner_radius=18)
        t.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        t.grid_columnconfigure(0, weight=1)
        t.grid_rowconfigure(2, weight=1)
        ctk.CTkLabel(t, text="  Grabaciones", image=self.iconos.get("grabaciones"),
                     compound="left", font=self.f_seccion, text_color=TEXTO,
                     anchor="w").grid(row=0, column=0, sticky="w", padx=18, pady=(18, 6))

        # Cabecera de columnas.
        hdr = ctk.CTkFrame(t, fg_color="transparent")
        hdr.grid(row=1, column=0, sticky="we", padx=20, pady=(0, 2))
        hdr.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(hdr, text="ARCHIVO", anchor="w", font=self.f_sub,
                     text_color=MUTED).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(hdr, text="TAMAÑO", anchor="e", font=self.f_sub,
                     text_color=MUTED).grid(row=0, column=1, sticky="e")

        self.lista = ctk.CTkScrollableFrame(t, fg_color="transparent")
        self.lista.grid(row=2, column=0, sticky="nsew", padx=10)
        self.lista.grid_columnconfigure(0, weight=1)

        acc = ctk.CTkFrame(t, fg_color="transparent")
        acc.grid(row=3, column=0, sticky="we", padx=18, pady=16)
        acc.grid_columnconfigure(0, weight=1)
        blanco = (255, 255, 255)
        teal_rgb = (10, 134, 168)
        ico_importar = self._icono_tintado("transcribir", teal_rgb, 22)
        ico_carpeta = self._icono_tintado("carpeta", teal_rgb, 22)
        comun = dict(height=44, corner_radius=10, anchor="w", compound="left",
                     font=self.f_base)

        # Importar audio externo (siempre disponible).
        ctk.CTkButton(acc, text="   ＋ Importar audio…", image=ico_importar,
                      command=self._on_importar, fg_color="transparent",
                      border_width=1, border_color=TEAL, text_color=TEAL,
                      hover_color=SEL, **comun).grid(row=0, column=0, columnspan=2,
                                                     sticky="we", pady=(0, 8))

        # Acción principal adaptativa + menú de acciones secundarias (⋯).
        fila_acc = ctk.CTkFrame(acc, fg_color="transparent")
        fila_acc.grid(row=1, column=0, sticky="we", pady=(0, 8))
        fila_acc.grid_columnconfigure(0, weight=1)
        self.btn_primario = ctk.CTkButton(fila_acc, text="Selecciona una grabación",
                                          command=self._accion_primaria, fg_color=TEAL,
                                          hover_color=TEAL_HOVER, state="disabled", **comun)
        self.btn_primario.grid(row=0, column=0, sticky="we")
        self.btn_menu = ctk.CTkButton(fila_acc, text="⋯", width=44, height=44,
                                      corner_radius=10, command=self._menu_secundario,
                                      fg_color="transparent", border_width=1,
                                      border_color=TEAL, text_color=TEAL, hover_color=SEL,
                                      font=self.f_base, state="disabled")
        self.btn_menu.grid(row=0, column=1, padx=(8, 0))

        ctk.CTkButton(acc, text="   Abrir carpeta", image=ico_carpeta,
                      command=self._on_abrir_carpeta, fg_color="transparent",
                      border_width=1, border_color=TEAL, text_color=TEAL,
                      hover_color=SEL, **comun).grid(row=2, column=0, columnspan=2, sticky="we")

    # --- forma de onda --------------------------------------------------
    def _dibujar_onda(self):
        c = getattr(self, "canvas_onda", None)
        if c is None:
            return
        c.configure(bg=_col(CANVAS_BG))
        c.delete("all")
        w, h = c.winfo_width(), c.winfo_height()
        if w <= 1 or h <= 1:
            return
        mid = h / 2
        if not self.niveles:
            c.create_line(14, mid, w - 14, mid, fill=_col(BASE_LINE), width=2)
            return
        ancho, sep = 4, 3
        paso = ancho + sep
        max_barras = max(1, (w - 28) // paso)
        vals = list(self.niveles)[-max_barras:]
        n = len(vals)
        for i, frac in enumerate(vals):
            bh = max(2.0, frac * (h * 0.82))
            xi = 14 + i * paso + ancho / 2
            color = ONDA_ACTIVA if i >= n - 6 else ONDA
            c.create_line(xi, mid - bh / 2, xi, mid + bh / 2, fill=color, width=ancho,
                          capstyle="round")

    # --- estado ---------------------------------------------------------
    def _actualizar_estado_acta(self):
        conectado = claude_auth.conectado()
        if conectado:
            self.lbl_conexion.configure(text="● Claude conectado", text_color=VERDE)
        else:
            self.lbl_conexion.configure(text="● Sin conexión", text_color=MUTED)
        self._actualizar_accion_primaria()

    def _seleccion(self):
        return self.nombre_sel

    def _estado_sel(self):
        """Estado de la grabación seleccionada, o None si no hay selección."""
        if not self.nombre_sel:
            return None
        base = rutas.base_desde_audio(rutas.dir_grabaciones() / self.nombre_sel)
        return rutas.estado_reunion(base, base in self.transcribiendo)

    # Etiqueta y color del botón principal según el estado seleccionado.
    _ACCION_PRIMARIA = {
        None: ("Selecciona una grabación", None),
        "generando": ("Generando…", None),
        "sin_transcribir": ("Transcribir", "_on_transcribir"),
        "transcrita": ("Generar acta…", "_on_generar_acta"),
        "con_acta": ("Generar PDF", "_on_generar_pdf"),
    }

    def _accion_primaria(self):
        _, metodo = self._ACCION_PRIMARIA.get(self._estado_sel(), (None, None))
        if metodo:
            getattr(self, metodo)()

    def _actualizar_accion_primaria(self):
        estado = self._estado_sel()
        etiqueta, metodo = self._ACCION_PRIMARIA.get(estado, (None, None))
        habilitado = metodo is not None and not self.trabajando
        # 'Generar acta' exige conexión con Claude.
        if estado == "transcrita" and not claude_auth.conectado():
            habilitado = False
        self.btn_primario.configure(text=etiqueta, state="normal" if habilitado else "disabled")
        hay_menu = estado in ("transcrita", "con_acta") and not self.trabajando
        self.btn_menu.configure(state="normal" if hay_menu else "disabled")

    def _menu_secundario(self):
        estado = self._estado_sel()
        if estado not in ("transcrita", "con_acta"):
            return
        m = Menu(self.root, tearoff=0)
        m.add_command(label="Volver a transcribir", command=self._on_transcribir)
        if estado == "con_acta":
            m.add_command(label="Volver a generar acta…", command=self._on_generar_acta)
        x = self.btn_menu.winfo_rootx()
        y = self.btn_menu.winfo_rooty() + self.btn_menu.winfo_height()
        try:
            m.tk_popup(x, y)
        finally:
            m.grab_release()

    # --- micrófonos y grabaciones --------------------------------------
    def _refrescar_microfonos(self, reescanear=False):
        # No reinicializar PortAudio durante una grabación: rompería el stream.
        micros = audio.listar_microfonos(reescanear=reescanear and not self.trabajando)
        self._mic_idx = {etq: idx for idx, etq, _ in micros}
        self._mic_nombre = {etq: nom for _, etq, nom in micros}
        etiquetas = [etq for _, etq, _ in micros] or ["(sin micrófonos)"]
        self.menu_mic.configure(values=etiquetas)
        # Restaurar el último micrófono usado (por nombre, estable entre reinicios).
        guardado = config.microfono()
        seleccion = next((etq for etq in etiquetas if self._mic_nombre.get(etq) == guardado), None)
        if seleccion is None:
            actual = self.var_mic.get()
            seleccion = actual if actual in etiquetas else etiquetas[0]
        self.var_mic.set(seleccion)

    def _on_mic_seleccion(self, etiqueta):
        nombre = self._mic_nombre.get(etiqueta)
        if nombre:
            config.guardar_microfono(nombre)

    def _dispositivo_actual(self):
        return self._mic_idx.get(self.var_mic.get())

    def _refrescar_grabaciones(self):
        for w in self.lista.winfo_children():
            w.destroy()
        self.botones_grab = {}
        grabaciones = rutas.listar_grabaciones()
        for n, wav in enumerate(grabaciones):
            mb = wav.stat().st_size / (1024 * 1024)
            nombre = wav.name
            fila = ctk.CTkFrame(self.lista, fg_color="transparent", corner_radius=10)
            fila.grid(row=n, column=0, sticky="we", pady=2)
            fila.grid_columnconfigure(1, weight=1)
            base = rutas.base_desde_audio(wav)
            glifo, color = _PUNTO_ESTADO[rutas.estado_reunion(base, base in self.transcribiendo)]
            lbl_p = ctk.CTkLabel(fila, text=glifo, width=16, font=self.f_base, text_color=color)
            lbl_p.grid(row=0, column=0, padx=(10, 2), pady=8)
            lbl_n = ctk.CTkLabel(fila, text=nombre, anchor="w", font=self.f_base,
                                 text_color=TEXTO)
            lbl_n.grid(row=0, column=1, sticky="we", padx=(2, 6), pady=8)
            lbl_s = ctk.CTkLabel(fila, text=f"{mb:.1f} MB", anchor="e", font=self.f_sub,
                                 text_color=MUTED)
            lbl_s.grid(row=0, column=2, sticky="e", padx=(0, 12))
            for wdg in (fila, lbl_p, lbl_n, lbl_s):
                wdg.bind("<Button-1>", lambda e, nb=nombre: self._seleccionar(nb))
                wdg.bind("<Enter>", lambda e, nb=nombre: self._hover(nb, True))
                wdg.bind("<Leave>", lambda e, nb=nombre: self._hover(nb, False))
            self.botones_grab[nombre] = fila
        if self.nombre_sel in self.botones_grab:
            self._seleccionar(self.nombre_sel)
        else:
            self.nombre_sel = None

    def _seleccionar(self, nombre):
        self.nombre_sel = nombre
        for nb, fila in self.botones_grab.items():
            fila.configure(fg_color=SEL if nb == nombre else "transparent")
        self._actualizar_accion_primaria()

    def _hover(self, nombre, entra):
        fila = self.botones_grab.get(nombre)
        if fila is not None and nombre != self.nombre_sel:
            fila.configure(fg_color=HOVER if entra else "transparent")

    # --- grabación ------------------------------------------------------
    def _toggle_grabar(self):
        if self.grabando:
            if self.evento_parada:
                self.evento_parada.set()
            return
        salida = rutas.dir_grabaciones() / audio.nombre_archivo()
        self.evento_parada = threading.Event()
        self.inicio_grabacion = time.time()
        self.grabando = True
        self.niveles.clear()
        self.btn_rec.configure(text="■")
        self.lbl_rec.configure(text="Detener")
        self.lbl_tiempo.configure(text="00:00", text_color=CORAL)
        self.lbl_estado.configure(text=f"Grabando en {salida.name}…")

        ganancia = {"Auto": None, "Off": 1.0}.get(self.var_ganancia.get(), 3.0)
        dispositivo = self._dispositivo_actual()
        base = rutas.base_desde_audio(salida)
        frecuencia = audio.frecuencia_soportada(dispositivo, 44100, 1)
        vivo = transcripcion_vivo.crear(base, frecuencia)
        if vivo:
            self.lbl_estado.configure(
                text=f"Grabando en {salida.name}… (transcribiendo en 2º plano)")

        def trabajo():
            def nivel(pico_db, ganancia_db):
                self.cola.put(("nivel", pico_db))
            try:
                audio.grabar(salida, evento_parada=self.evento_parada, nivel_callback=nivel,
                             dispositivo=dispositivo, ganancia=ganancia,
                             muestras_callback=vivo.alimentar if vivo else None)
                if vivo:
                    self.cola.put(("estado", "Grabación guardada. Terminando transcripción…"))
                    self.cola.put(("fin_grabacion_vivo", str(salida), vivo.finalizar()))
                else:
                    self.cola.put(("fin_grabacion", str(salida)))
            except Exception as exc:  # noqa: BLE001
                if vivo is not None:
                    try:
                        vivo.finalizar()
                    except Exception:  # noqa: BLE001 — importa el error de grabación, no este
                        pass
                self.cola.put(("error_grabacion", str(exc)))

        threading.Thread(target=trabajo, daemon=True).start()

    # --- transcripción --------------------------------------------------
    def _on_transcribir(self):
        nombre = self._seleccion()
        if not nombre:
            messagebox.showinfo("recordIt", "Selecciona una grabación de la lista.")
            return
        wav = rutas.dir_grabaciones() / nombre
        self._lanzar_transcripcion(rutas.base_desde_audio(wav), wav)

    def _lanzar_transcripcion(self, base, wav):
        """Transcribe `wav` en segundo plano marcando el estado 'generando'.

        Reutilizado por el botón Transcribir y por la importación. Añade la
        reunión a self.transcribiendo (dot ◐) y la quita al terminar/fallar.
        """
        if self.trabajando:
            return
        self.trabajando = True
        self.transcribiendo.add(base)
        self._refrescar_grabaciones()

        def trabajo():
            try:
                frio = not transcripcion.modelo_en_cache("large-v3")
                self.cola.put(("estado", "Preprocesando audio…"))
                limpio = rutas.ruta_clean(base)
                preproceso.preprocesar(wav, limpio)
                if frio:
                    self.cola.put(("estado", "Descargando modelo large-v3 (~3 GB, solo la 1ª vez; "
                                             "puede tardar 10–20 min, no cierres la ventana)…"))
                else:
                    self.cola.put(("estado", "Transcribiendo…"))
                transcripcion.transcribir(
                    limpio, rutas.ruta_transcripcion(base), rutas.ruta_timestamps(base),
                    progreso_callback=lambda a, t: self.cola.put(("progreso", a, t)))
                self.cola.put(("fin_transcripcion", base, True))
            except Exception as exc:  # noqa: BLE001
                self.cola.put(("fin_transcripcion", base, False))
                self._encolar_error(exc)

        threading.Thread(target=trabajo, daemon=True).start()

    # --- acta -----------------------------------------------------------
    def _on_generar_acta(self):
        nombre = self._seleccion()
        if not nombre:
            messagebox.showinfo("recordIt", "Selecciona una grabación de la lista.")
            return
        base = rutas.base_desde_audio(rutas.dir_grabaciones() / nombre)
        txt = rutas.ruta_transcripcion(base)
        if not txt.exists():
            messagebox.showinfo("recordIt", "Primero transcribe esta grabación.")
            return
        metodo, key = claude_auth.estado()
        if metodo is None:
            messagebox.showinfo(
                "recordIt",
                "No has conectado con Claude.\n\nVe a «⚙ Ajustes» y pulsa "
                "«Conectar con Claude» para poder generar el acta.")
            return
        if self.trabajando:
            return
        self.trabajando = True
        modelo = config.modelo_acta()
        fecha_iso, fecha = self._fechas(base)
        transcripcion_texto = txt.read_text(encoding="utf-8")

        def trabajo():
            try:
                self.cola.put(("estado", "Redactando el acta con Claude…"))
                md = acta.redactar_acta(transcripcion_texto, fecha=fecha, base=base,
                                        metodo=metodo, api_key=key, modelo=modelo)
                rutas.ruta_acta_md(base, fecha_iso).write_text(md, encoding="utf-8")
                self.cola.put(("acta_lista", base))
            except Exception as exc:  # noqa: BLE001
                self._encolar_error(exc)

        threading.Thread(target=trabajo, daemon=True).start()

    # --- PDF ------------------------------------------------------------
    def _fechas(self, base):
        """(fecha_iso, fecha_legible) de la reunión: del nombre si la lleva, si no hoy."""
        import re
        from datetime import datetime
        meses = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
                 "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
        hoy = datetime.now()
        m = re.search(r"\d{4}-\d{2}-\d{2}", base)
        fecha_iso = m.group(0) if m else hoy.strftime("%Y-%m-%d")
        anio, mes, dia = (int(x) for x in fecha_iso.split("-"))
        return fecha_iso, f"{dia} de {meses[mes - 1]} de {anio}"

    def _buscar_acta_md(self, base):
        """Devuelve el acta .md más reciente de la reunión, o None."""
        actas = sorted(rutas.dir_reunion(base).glob("acta*.md"),
                       key=lambda p: p.stat().st_mtime, reverse=True)
        return actas[0] if actas else None

    def _transcribir_sync(self, wav, base):
        """Preprocesa y transcribe (uso dentro de un hilo). Idempotente: si ya hay
        transcripción no la rehace."""
        if rutas.ruta_transcripcion(base).exists():
            return
        frio = not transcripcion.modelo_en_cache("large-v3")
        self.cola.put(("estado", "Preprocesando audio…"))
        limpio = rutas.ruta_clean(base)
        preproceso.preprocesar(wav, limpio)
        if frio:
            self.cola.put(("estado", "Descargando modelo large-v3 (~3 GB, solo la 1ª vez; "
                                     "puede tardar 10–20 min, no cierres la ventana)…"))
        else:
            self.cola.put(("estado", "Transcribiendo…"))
        transcripcion.transcribir(
            limpio, rutas.ruta_transcripcion(base), rutas.ruta_timestamps(base),
            progreso_callback=lambda a, t: self.cola.put(("progreso", a, t)))

    def _on_generar_pdf(self):
        nombre = self._seleccion()
        if not nombre:
            messagebox.showinfo("recordIt", "Selecciona una grabación de la lista.")
            return
        base = rutas.base_desde_audio(rutas.dir_grabaciones() / nombre)
        md = self._buscar_acta_md(base)
        # Si hay que generar el acta, necesitamos conexión con Claude (no autoarreglable).
        metodo, key = (None, None)
        if md is None:
            metodo, key = claude_auth.estado()
            if metodo is None:
                messagebox.showinfo(
                    "recordIt",
                    "Para el PDF hace falta el acta, y para el acta hay que conectar con "
                    "Claude.\n\nVe a «⚙ Ajustes» y pulsa «Conectar con Claude».")
                return
        if self.trabajando:
            return
        self.trabajando = True
        wav = rutas.dir_grabaciones() / nombre
        modelo = config.modelo_acta()
        fecha_iso, fecha = self._fechas(base)

        def trabajo():
            try:
                ruta_md = md
                if ruta_md is None:
                    # Encadena lo que falte: transcripción -> acta -> PDF.
                    self._transcribir_sync(wav, base)
                    self.cola.put(("estado", "Redactando el acta con Claude…"))
                    texto = rutas.ruta_transcripcion(base).read_text(encoding="utf-8")
                    md_txt = acta.redactar_acta(texto, fecha=fecha, base=base,
                                                metodo=metodo, api_key=key, modelo=modelo)
                    ruta_md = rutas.ruta_acta_md(base, fecha_iso)
                    ruta_md.write_text(md_txt, encoding="utf-8")
                self.cola.put(("estado", "Generando el PDF del acta…"))
                pdf.generar(ruta_md, ruta_md.with_suffix(".pdf"))
                self.cola.put(("pdf_listo", base))
            except Exception as exc:  # noqa: BLE001
                self._encolar_error(exc)

        threading.Thread(target=trabajo, daemon=True).start()

    # --- carpeta y ajustes ---------------------------------------------
    def _on_abrir_carpeta(self):
        nombre = self._seleccion()
        if not nombre:
            _abrir_en_explorador(rutas.dir_grabaciones())
            return
        base = rutas.base_desde_audio(rutas.dir_grabaciones() / nombre)
        _abrir_en_explorador(rutas.dir_reunion(base))

    def _encolar_error(self, exc):
        """Registra el traceback completo en el log y encola el aviso al usuario.

        Debe llamarse dentro de un bloque `except`: la GUI solo veía `str(exc)`
        (p. ej. «__spec__»), inútil para depurar el `.exe`. El detalle técnico
        va al log y se le indica al usuario dónde está.
        """
        ruta = registro.registrar_excepcion(f"Fallo en operación: {exc!r}")
        self.cola.put(("error", f"{exc}\n\nDetalle técnico guardado en:\n{ruta}"))

    def _texto_conexion(self):
        metodo, _ = claude_auth.estado()
        if metodo == "cli":
            return "✓ Conectado mediante Claude Code (CLI)"
        if metodo == "api":
            return "✓ Conectado mediante la API de Anthropic"
        return "○ Sin conectar"

    def _mostrar_guia_claude(self, parent):
        """Diálogo con los pasos para instalar y autenticar el CLI `claude`."""
        comando = claude_auth.COMANDO_INSTALACION
        if os.name == "nt":
            pasos = (
                "Para generar actas, recordIt necesita el CLI de Claude Code\n"
                "(la app de escritorio de Claude no basta). Pasos:\n\n"
                f"1. Instálalo (necesitas Node.js):\n     {comando}\n\n"
                "2. Inicia sesión con la MISMA cuenta que tu app de Claude:\n"
                "     claude login\n\n"
                "3. Reabre recordIt (o pulsa «Conectar con Claude» de nuevo)."
            )
        else:
            pasos = (
                "Para generar actas, recordIt necesita el CLI de Claude Code.\n\n"
                f"1. Instálalo:\n     {comando}\n\n"
                "2. Inicia sesión:\n     claude login\n\n"
                "3. Pulsa «Conectar con Claude» de nuevo."
            )

        dlg = ctk.CTkToplevel(parent)
        dlg.title("Conectar con Claude")
        dlg.transient(parent)
        dlg.after(120, dlg.grab_set)
        ctk.CTkLabel(dlg, text=pasos, font=self.f_base, justify="left",
                     anchor="w").pack(fill="x", padx=22, pady=(22, 8))

        def copiar():
            self.root.clipboard_clear()
            self.root.clipboard_append(comando)

        botones = ctk.CTkFrame(dlg, fg_color="transparent")
        botones.pack(fill="x", padx=22, pady=(0, 20))
        ctk.CTkButton(botones, text="Copiar comando", command=copiar,
                      fg_color=TEAL, hover_color=TEAL_HOVER).pack(side="left")
        ctk.CTkButton(botones, text="Abrir guía",
                      command=lambda: webbrowser.open(claude_auth.URL_AYUDA),
                      fg_color="transparent", border_width=1).pack(side="left", padx=8)
        ctk.CTkButton(botones, text="Cerrar", command=dlg.destroy,
                      fg_color="transparent").pack(side="right")

    def _on_ajustes(self):
        actual = config.cargar()
        dlg = ctk.CTkToplevel(self.root)
        dlg.title("Ajustes")
        dlg.geometry("460x420")
        dlg.transient(self.root)
        dlg.after(120, dlg.grab_set)

        ctk.CTkLabel(dlg, text="Conexión con Claude", font=self.f_seccion,
                     anchor="w").pack(fill="x", padx=22, pady=(22, 2))
        lbl_estado = ctk.CTkLabel(dlg, text=self._texto_conexion(), font=self.f_base,
                                  anchor="w", text_color=MUTED)
        lbl_estado.pack(fill="x", padx=22)

        def conectar():
            metodo, _msg = claude_auth.conectar()
            if metodo:
                lbl_estado.configure(text=self._texto_conexion())
                self._actualizar_estado_acta()
            else:
                self._mostrar_guia_claude(dlg)

        ctk.CTkButton(dlg, text="Conectar con Claude", command=conectar, fg_color=TEAL,
                      hover_color=TEAL_HOVER, font=self.f_base).pack(padx=22, pady=(8, 0))

        ctk.CTkLabel(dlg, text="Modelo del acta (al usar la API)", font=self.f_base,
                     anchor="w").pack(fill="x", padx=22, pady=(16, 4))
        modelo_actual = actual.get("modelo_acta", config.MODELO_POR_DEFECTO)
        var_modelo = StringVar(value=MODELOS_INV.get(modelo_actual, "Opus (más capaz)"))
        ctk.CTkSegmentedButton(dlg, values=list(MODELOS.keys()), variable=var_modelo,
                               selected_color=TEAL, selected_hover_color=TEAL_HOVER).pack(padx=22)

        ctk.CTkLabel(dlg, text="Tema", font=self.f_base,
                     anchor="w").pack(fill="x", padx=22, pady=(16, 4))
        var_tema = StringVar(value="Oscuro" if _modo_oscuro() else "Claro")
        ctk.CTkSegmentedButton(dlg, values=["Claro", "Oscuro"], variable=var_tema,
                               command=self._on_tema, selected_color=TEAL,
                               selected_hover_color=TEAL_HOVER).pack(padx=22)

        ctk.CTkLabel(dlg, text=SOPORTE, font=self.f_sub, text_color=MUTED,
                     wraplength=410, justify="left", anchor="w").pack(
            fill="x", padx=22, pady=(18, 0))

        botones = ctk.CTkFrame(dlg, fg_color="transparent")
        botones.pack(side="bottom", fill="x", padx=22, pady=20)

        def guardar():
            actual["modelo_acta"] = MODELOS.get(var_modelo.get(), config.MODELO_POR_DEFECTO)
            config.guardar(actual)
            self._actualizar_estado_acta()
            dlg.destroy()

        ctk.CTkButton(botones, text="Guardar", command=guardar, fg_color=TEAL,
                      hover_color=TEAL_HOVER).pack(side="right")
        ctk.CTkButton(botones, text="Cerrar", command=dlg.destroy, fg_color="transparent",
                      border_width=1, border_color=MUTED, text_color=MUTED,
                      hover_color=SEL).pack(side="right", padx=8)

    def _on_tema(self, valor):
        ctk.set_appearance_mode("dark" if valor == "Oscuro" else "light")
        self.root.after(60, self._repintar_tema)

    def _repintar_tema(self):
        # Los widgets CTk con color en tupla (claro, oscuro) ya conmutan solos;
        # solo el canvas de la onda (Tkinter puro) necesita repintarse a mano.
        self._dibujar_onda()

    # --- bucle de eventos de la cola -----------------------------------
    def _drenar_cola(self):
        hubo_nivel = False
        try:
            while True:
                evento = self.cola.get_nowait()
                tipo = evento[0]
                if tipo == "nivel":
                    self.niveles.append(max(0.0, min(1.0, (evento[1] + 60.0) / 60.0)))
                    hubo_nivel = True
                elif tipo == "fin_grabacion":
                    self.grabando = False
                    self.btn_rec.configure(text="●")
                    self.lbl_rec.configure(text="Grabar")
                    self.lbl_tiempo.configure(text_color=TEXTO)
                    self.lbl_estado.configure(text="Grabación guardada.")
                    self._refrescar_grabaciones()
                    self._actualizar_accion_primaria()
                elif tipo == "fin_grabacion_vivo":
                    self.grabando = False
                    self.btn_rec.configure(text="●")
                    self.lbl_rec.configure(text="Grabar")
                    self.lbl_tiempo.configure(text_color=TEXTO)
                    self.lbl_estado.configure(
                        text="Grabación guardada y transcripción lista."
                        if evento[2] else
                        "Grabación guardada (la transcripción en vivo falló; usa «Transcribir»).")
                    self._refrescar_grabaciones()
                    self._actualizar_accion_primaria()
                elif tipo == "error_grabacion":
                    self.grabando = False
                    self.btn_rec.configure(text="●")
                    self.lbl_rec.configure(text="Grabar")
                    self.lbl_tiempo.configure(text="00:00", text_color=TEXTO)
                    self.lbl_estado.configure(text="No se pudo grabar.")
                    messagebox.showerror(
                        "recordIt",
                        "No se pudo abrir el micrófono seleccionado:\n\n"
                        f"{evento[1]}\n\nPrueba con otro dispositivo del desplegable.")
                elif tipo == "estado":
                    self.lbl_estado.configure(text=evento[1])
                elif tipo == "progreso":
                    actual, total = evento[1], evento[2]
                    self.barra_progreso.set((actual / total) if total else 0)
                elif tipo == "fin_trabajo":
                    self.trabajando = False
                    self.barra_progreso.set(0)
                    self.lbl_estado.configure(text=evento[1])
                elif tipo == "fin_transcripcion":
                    base, ok = evento[1], evento[2]
                    self.trabajando = False
                    self.transcribiendo.discard(base)
                    self.barra_progreso.set(0)
                    self.lbl_estado.configure(
                        text=f"Transcripción lista: {base}" if ok else "No se pudo transcribir.")
                    self._refrescar_grabaciones()
                    self._actualizar_accion_primaria()
                elif tipo == "acta_lista":
                    self.trabajando = False
                    self.lbl_estado.configure(text=f"Acta generada: {evento[1]}")
                    messagebox.showwarning(
                        "Revisa el acta",
                        "El acta se generó a partir de una transcripción automática.\n"
                        "Revísala antes de difundirla.")
                    # Al cerrar el aviso, abrir la carpeta donde quedó el acta.
                    _abrir_en_explorador(rutas.dir_reunion(evento[1]))
                    self._actualizar_accion_primaria()
                elif tipo == "pdf_listo":
                    self.trabajando = False
                    self.lbl_estado.configure(text=f"PDF generado: {evento[1]}")
                    _abrir_en_explorador(rutas.dir_reunion(evento[1]))
                    self._actualizar_accion_primaria()
                elif tipo == "error":
                    self.trabajando = False
                    self.barra_progreso.set(0)
                    self.lbl_estado.configure(text="Error.")
                    messagebox.showerror("recordIt", evento[1])
                    self._actualizar_accion_primaria()
        except queue.Empty:
            pass

        if hubo_nivel:
            self._dibujar_onda()
        if self.grabando and self.inicio_grabacion:
            t = int(time.time() - self.inicio_grabacion)
            self.lbl_tiempo.configure(text=f"{t // 60:02d}:{t % 60:02d}")
        self.root.after(50, self._drenar_cola)


def main():
    # En el binario congelado puede haber subprocesos (multiprocessing); esto evita
    # que un hijo re-ejecute la app. Configura además el log y sanea stdout/stderr.
    multiprocessing.freeze_support()
    registro.configurar()
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
    try:
        # className fija el WM_CLASS para que el escritorio agrupe la ventana con
        # la entrada .desktop (StartupWMClass=recordit) y muestre el icono.
        root = ctk.CTk(className="recordit")
    except Exception:  # noqa: BLE001
        root = ctk.CTk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
