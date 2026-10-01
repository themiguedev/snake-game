#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Juego de la Serpiente - Snake Game
Diseño moderno con tkinter, menú interactivo y movimiento interpolado a 60 FPS.

Pantallas (máquina de estados en self.screen):
  MENU        -> menú principal
  JUEGO       -> partida en curso
  PAUSA       -> partida en pausa
  GAME_OVER   -> fin de partida
  DIFICULTAD  -> selector de dificultad
  RECORDS     -> mejores puntuaciones
  AYUDA       -> instrucciones

Arquitectura de animación:
  - El bucle principal corre a FRAME_MS (~60 FPS) y mide el tiempo real transcurrido.
  - La lógica de la rejilla avanza por un acumulador de tiempo: el juego es igual de
    rápido en cualquier máquina, independientemente de los FPS reales.
  - Cada segmento se dibuja INTERPOLADO entre su celda anterior y la actual, así que
    el movimiento es continuo en vez de saltar de celda en celda.
  - El tablero es estático y se dibuja una sola vez; los objetos del canvas se
    reutilizan con coords() en lugar de destruirlos y recrearlos cada frame.
  - Los menús solo se redibujan cuando cambia la selección, no en cada frame.

El menú es navegable con las flechas + ENTER y también con el ratón (clic o hover).
"""

import json
import math
import os
import random
import sys
import time
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import Canvas, Frame, Label

# --------------------------------------------------------------------------
# Constantes globales
# --------------------------------------------------------------------------

APP_NAME = "SnakeGame"

# Estados de pantalla
MENU = 'menu'
DIFICULTAD = 'dificultad'
RECORDS = 'records'
AYUDA = 'ayuda'
JUEGO = 'juego'
PAUSA = 'pausa'
GAME_OVER = 'game_over'

# Dificultades: (tiempo por celda en ms, multiplicador de puntos, descripción)
DIFICULTADES = [
    ('Facil', 160, 1.0, 'Mas lento, para aprender'),
    ('Normal', 120, 1.5, 'El equilibrio clasico'),
    ('Dificil', 85, 2.0, 'Rapido y sin piedad'),
]


def ruta_datos():
    """Carpeta escribible para los récords (funciona igual congelado o no).

    Busca el AppData del usuario antes que la carpeta del ejecutable, que puede
    ser de solo lectura si el .exe se instala en Archivos de programa.
    """
    base = os.environ.get('APPDATA') or os.path.expanduser('~')
    carpeta = Path(base) / APP_NAME
    try:
        carpeta.mkdir(parents=True, exist_ok=True)
        return carpeta
    except OSError:
        # Último recurso: junto al script/ejecutable
        return Path(__file__).resolve().parent


class Particle:
    """Sistema de partículas para efectos visuales al comer.

    La física está expresada por segundo (no por frame) para que las partículas
    se vean igual sin importar los FPS a los que corra el juego.
    """

    #: Ajuste de escala: las constantes originales estaban pensadas por tick de 120 ms.
    BASE_TICK = 0.12

    def __init__(self, x, y, color):
        self.x = x
        self.y = y
        self.color = color
        # px por segundo
        self.vx = random.uniform(-3, 3) / self.BASE_TICK
        self.vy = random.uniform(-3, 3) / self.BASE_TICK
        self.life = 1.0
        # 1/s: decaimiento de la vida
        self.decay = random.uniform(0.02, 0.05) / self.BASE_TICK
        self.size = random.randint(3, 6)
        self.item = None  # id del óvalo en el canvas (se reutiliza)

    def update(self, dt):
        """Avanza la partícula dt segundos. Devuelve False cuando se agota."""
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.vy += 900 * dt  # gravedad ligera (px/s²)
        self.life -= self.decay * dt
        return self.life > 0


class SnakeGame:
    """Clase principal del juego de la serpiente."""

    # Configuración del juego
    CELL_SIZE = 25
    GRID_WIDTH = 24
    GRID_HEIGHT = 20
    GAME_SPEED = 120     # milisegundos entre avances de la rejilla (Normal)
    MIN_SPEED = 55       # límite de velocidad máxima alcanzable por nivel
    FRAME_MS = 16        # ~60 FPS
    MAX_DT = 0.25        # tope de dt para evitar saltos si la ventana se bloquea
    MAX_PARTICLES = 120  # cota para no degradar los FPS
    MAX_RECORDS = 8      # récords que se guardan

    # Colores modernos
    COLORS = {
        'bg': '#1a1a2e',
        'grid': '#16213e',
        'snake_head': '#00d9ff',
        'snake_body': '#00b4d8',
        'snake_border': '#0077b6',
        'food': '#ff6b6b',
        'food_glow': '#ff8585',
        'text': '#eeeeee',
        'text_dim': '#8a8fa3',
        'accent': '#ffd700',
        'game_over': '#ff4757',
        'ui_bg': '#0f3460',
        'menu_sel': '#0f3460',
        'ok': '#2ed573',
    }

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Snake Game - Edicion Moderna")
        self.root.configure(bg=self.COLORS['bg'])

        # Dimensiones
        self.width = self.GRID_WIDTH * self.CELL_SIZE
        self.height = self.GRID_HEIGHT * self.CELL_SIZE

        # Centrar ventana
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        x = max(0, (screen_w - self.width - 40) // 2)
        y = max(0, (screen_h - self.height - 120) // 2)
        self.root.geometry(f"{self.width + 40}x{self.height + 120}+{x}+{y}")
        self.root.resizable(False, False)

        # Estado de pantalla
        self.screen = MENU
        self.dif_index = 1                      # Normal por defecto
        self.records = self._cargar_records()

        self._create_ui()
        self._setup_game()
        self._bind_controls()

        self.mostrar_menu()

    # ==================================================================
    # Interfaz
    # ==================================================================

    def _create_ui(self):
        """Crea la interfaz de usuario."""
        main_frame = Frame(self.root, bg=self.COLORS['bg'], padx=20, pady=20)
        main_frame.pack(fill=tk.BOTH, expand=True)

        self.title_label = Label(
            main_frame,
            text="SNAKE GAME",
            font=('Helvetica', 24, 'bold'),
            bg=self.COLORS['bg'],
            fg=self.COLORS['accent']
        )
        self.title_label.pack(pady=(0, 10))

        # Panel de información
        info_frame = Frame(main_frame, bg=self.COLORS['ui_bg'], padx=15, pady=8)
        info_frame.pack(fill=tk.X, pady=(0, 10))

        self.score_label = Label(
            info_frame,
            text="Puntuacion: 0",
            font=('Helvetica', 12, 'bold'),
            bg=self.COLORS['ui_bg'],
            fg=self.COLORS['text']
        )
        self.score_label.pack(side=tk.LEFT)

        self.level_label = Label(
            info_frame,
            text="Nivel: 1",
            font=('Helvetica', 12, 'bold'),
            bg=self.COLORS['ui_bg'],
            fg=self.COLORS['food']
        )
        self.level_label.pack(side=tk.RIGHT)

        # Canvas del juego
        canvas_frame = Frame(main_frame, bg=self.COLORS['grid'], bd=3, relief=tk.RIDGE)
        canvas_frame.pack()

        self.canvas = Canvas(
            canvas_frame,
            width=self.width,
            height=self.height,
            bg=self.COLORS['bg'],
            highlightthickness=0
        )
        self.canvas.pack()

        # Instrucciones
        self.instructions = Label(
            main_frame,
            text="Flechas: mover  |  ESPACIO: pausa  |  R: reiniciar  |  ESC: menu",
            font=('Helvetica', 9),
            bg=self.COLORS['bg'],
            fg=self.COLORS['text_dim']
        )
        self.instructions.pack(pady=(10, 0))

    def _bind_controls(self):
        """Configura controles de teclado y ratón."""
        self.root.bind('<Key>', self._handle_key)
        self.canvas.bind('<Button-1>', self._handle_click)
        self.canvas.bind('<Motion>', self._handle_motion)
        self.root.focus_set()

    # ==================================================================
    # Navegación de menús
    # ==================================================================

    def _menu_root(self, titulo, subtitulo=None, volver=None):
        """Dibuja el armazón común de una pantalla de menú y devuelve la Y libre."""
        self.canvas.delete('all')
        self._clickables = []
        self._grid_drawn = False
        self.canvas.create_text(
            self.width // 2, 52, text=titulo,
            font=('Helvetica', 26, 'bold'), fill=self.COLORS['accent']
        )
        y = 100
        if subtitulo:
            self.canvas.create_text(
                self.width // 2, y, text=subtitulo,
                font=('Helvetica', 11), fill=self.COLORS['text_dim']
            )
            y += 40
        if volver:
            self.canvas.create_text(
                self.width // 2, self.height - 26,
                text="ENTER / ESC  -  volver", font=('Helvetica', 9),
                fill=self.COLORS['text_dim']
            )
        return y

    def _menu_items(self, y_ini, items, seleccionado):
        """Dibuja las opciones navegables y registra sus zonas de clic.

        items: lista de (etiqueta, descripcion, callback)
        """
        alto = 46
        ancho = 380
        x0 = (self.width - ancho) // 2
        y = y_ini
        for i, (etiqueta, descripcion, callback) in enumerate(items):
            seleccionado_ahora = (i == seleccionado)
            relleno = self.COLORS['menu_sel'] if seleccionado_ahora else self.COLORS['bg']
            borde = self.COLORS['accent'] if seleccionado_ahora else self.COLORS['ui_bg']
            color_txt = self.COLORS['accent'] if seleccionado_ahora else self.COLORS['text']

            self.canvas.create_rectangle(
                x0, y, x0 + ancho, y + alto,
                fill=relleno, outline=borde, width=2
            )
            prefijo = "> " if seleccionado_ahora else "   "
            self.canvas.create_text(
                x0 + ancho // 2, y + 16,
                text=prefijo + etiqueta,
                font=('Helvetica', 13, 'bold'), fill=color_txt
            )
            self.canvas.create_text(
                x0 + ancho // 2, y + 33,
                text=descripcion, font=('Helvetica', 8),
                fill=self.COLORS['text_dim']
            )

            self._clickables.append((x0, y, x0 + ancho, y + alto, i, callback))
            y += alto + 8
        return items

    def _cargar_records(self):
        """Lee los récords del disco (lista de dicts). Nunca lanza excepción."""
        ruta = ruta_datos() / 'records.json'
        try:
            with open(ruta, 'r', encoding='utf-8') as f:
                datos = json.load(f)
            if isinstance(datos, list):
                return datos[:self.MAX_RECORDS]
        except (OSError, ValueError):
            pass
        return []

    def _guardar_records(self):
        """Guarda los récords. Si falla, el juego sigue funcionando."""
        ruta = ruta_datos() / 'records.json'
        try:
            with open(ruta, 'w', encoding='utf-8') as f:
                json.dump(self.records[:self.MAX_RECORDS], f, ensure_ascii=False, indent=1)
            return True
        except OSError:
            return False

    def _registrar_record(self, puntuacion):
        """Añade la puntuación a los récords y devuelve True si entra en la tabla."""
        if puntuacion <= 0:
            return False
        entrada = {
            'score': puntuacion,
            'dif': DIFICULTADES[self.dif_index][0],
            'fecha': datetime.now().strftime('%d/%m/%Y'),
        }
        self.records.append(entrada)
        self.records.sort(key=lambda r: r.get('score', 0), reverse=True)
        self.records = self.records[:self.MAX_RECORDS]
        self._guardar_records()
        return entrada in self.records

    def mejor_record(self):
        """Mejor puntuación registrada (0 si no hay ninguna)."""
        return max((r.get('score', 0) for r in self.records), default=0)

    # ==================================================================
    # Pantallas de menú
    # ==================================================================

    def mostrar_menu(self, reset_sel=True):
        """Pantalla del menú principal.

        reset_sel=False al redibujar por un cambio de selección: si no, el
        redibujado volvería a poner el cursor en la primera opción.
        """
        self.screen = MENU
        if reset_sel:
            self.sel = 0
        self.title_label.config(text="SNAKE GAME", fg=self.COLORS['accent'])

        def jugar():
            self.screen = JUEGO
            self._setup_game()
            self._draw_grid()

        items = [
            ("JUGAR", f"Dificultad actual: {DIFICULTADES[self.dif_index][0]}", jugar),
            ("DIFICULTAD", "Elige la velocidad y el multiplicador", self.mostrar_dificultad),
            ("RECORDS", f"Mejor puntuacion: {self.mejor_record()}", self.mostrar_records),
            ("COMO JUGAR", "Controles y reglas", self.mostrar_ayuda),
            ("SALIR", "Cerrar el juego", self.salir),
        ]
        y = self._menu_root("SNAKE GAME", "Selecciona una opcion")
        self._menu_items(y, items, self.sel)

    def mostrar_dificultad(self, reset_sel=True):
        """Pantalla de selección de dificultad (reset_sel=False al redibujar)."""
        self.screen = DIFICULTAD
        if reset_sel:
            self.sel = self.dif_index

        def elegir(indice):
            def _f():
                self.dif_index = indice
                self.mostrar_menu()
            return _f

        items = [
            (nombre, f"{desc}  -  {ms} ms/celda, x{mult:g} puntos", elegir(i))
            for i, (nombre, ms, mult, desc) in enumerate(DIFICULTADES)
        ]
        items.append(("VOLVER", "Volver al menu principal", self.mostrar_menu))
        y = self._menu_root("DIFICULTAD", "Mas dificil = mas puntos por comida")
        self._menu_items(y, items, self.sel)

    def mostrar_records(self):
        """Pantalla de mejores puntuaciones."""
        self.screen = RECORDS
        self.sel = 0
        y = self._menu_root("RECORDS", "Mejores puntuaciones")

        if not self.records:
            self.canvas.create_text(
                self.width // 2, y + 60,
                text="Todavia no hay records.\nSe el primero en jugar.",
                font=('Helvetica', 13), fill=self.COLORS['text_dim'], justify='center'
            )
        else:
            self.canvas.create_text(
                self.width // 2 - 130, y + 6, text="PUESTO", font=('Helvetica', 9, 'bold'),
                fill=self.COLORS['text_dim']
            )
            self.canvas.create_text(
                self.width // 2 - 20, y + 6, text="PUNTOS", font=('Helvetica', 9, 'bold'),
                fill=self.COLORS['text_dim']
            )
            self.canvas.create_text(
                self.width // 2 + 90, y + 6, text="DIFICULTAD", font=('Helvetica', 9, 'bold'),
                fill=self.COLORS['text_dim']
            )
            self.canvas.create_text(
                self.width // 2 + 200, y + 6, text="FECHA", font=('Helvetica', 9, 'bold'),
                fill=self.COLORS['text_dim']
            )
            for i, r in enumerate(self.records):
                yy = y + 34 + i * 30
                color = self.COLORS['accent'] if i == 0 else self.COLORS['text']
                self.canvas.create_text(
                    self.width // 2 - 130, yy, text=f"{i + 1}",
                    font=('Helvetica', 12, 'bold'), fill=color
                )
                self.canvas.create_text(
                    self.width // 2 - 20, yy, text=f"{r.get('score', 0)}",
                    font=('Helvetica', 12, 'bold'), fill=color
                )
                self.canvas.create_text(
                    self.width // 2 + 90, yy, text=f"{r.get('dif', '?')}",
                    font=('Helvetica', 11), fill=self.COLORS['text_dim']
                )
                self.canvas.create_text(
                    self.width // 2 + 200, yy, text=f"{r.get('fecha', '')}",
                    font=('Helvetica', 11), fill=self.COLORS['text_dim']
                )

        self.canvas.create_text(
            self.width // 2, self.height - 26,
            text="ESC  -  volver al menu", font=('Helvetica', 9),
            fill=self.COLORS['text_dim']
        )
        self.canvas.create_text(
            self.width // 2, self.height - 52,
            text=f"Archivo: {ruta_datos() / 'records.json'}",
            font=('Helvetica', 7), fill=self.COLORS['text_dim']
        )

    def mostrar_ayuda(self):
        """Pantalla de instrucciones."""
        self.screen = AYUDA
        self.sel = 0
        y = self._menu_root("COMO JUGAR")

        lineas = [
            ("Flechas", "Mueve la serpiente"),
            ("ESPACIO", "Pausa / reanudar"),
            ("R", "Reiniciar la partida"),
            ("ESC", "Volver al menu"),
            ("", ""),
            ("Objetivo", "Come los puntos rojos para crecer"),
            ("Puntos", "10 x nivel x multiplicador de dificultad"),
            ("Nivel", "Sube cada 50 puntos y acelera el juego"),
            ("Cuidado", "Las paredes y tu propio cuerpo matan"),
        ]
        for clave, texto in lineas:
            if not clave and not texto:
                y += 14
                continue
            self.canvas.create_text(
                self.width // 2 - 190, y, text=clave, anchor='w',
                font=('Helvetica', 11, 'bold'), fill=self.COLORS['accent']
            )
            self.canvas.create_text(
                self.width // 2 - 80, y, text=texto, anchor='w',
                font=('Helvetica', 11), fill=self.COLORS['text']
            )
            y += 26

        self.canvas.create_text(
            self.width // 2, self.height - 26,
            text="ESC  -  volver", font=('Helvetica', 9),
            fill=self.COLORS['text_dim']
        )

    # ==================================================================
    # Navegación con teclado y ratón
    # ==================================================================

    def _accion_actual(self):
        """Callback de la opción seleccionada en el menú actual."""
        if not getattr(self, '_clickables', None):
            return None
        indice = min(self.sel, len(self._clickables) - 1)
        return self._clickables[indice][5]

    def _activar_seleccion(self):
        accion = self._accion_actual()
        if accion:
            accion()

    def _mover_seleccion(self, delta):
        """Mueve la selección del menú redibujando solo si cambia."""
        n = len(getattr(self, '_clickables', []))
        if n == 0:
            return
        nuevo = (self.sel + delta) % n
        if nuevo == self.sel:
            return
        self.sel = nuevo
        # Redibujar la pantalla actual conservando la selección
        if self.screen == MENU:
            self.mostrar_menu(reset_sel=False)
        elif self.screen == DIFICULTAD:
            self.mostrar_dificultad(reset_sel=False)
        # En RECORDS/AYUDA no hay opciones que mover

    def _handle_motion(self, event):
        """Resalta la opción bajo el cursor (hover del ratón)."""
        if self.screen not in (MENU, DIFICULTAD):
            return
        x, y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        for x0, y0, x1, y1, indice, _cb in getattr(self, '_clickables', []):
            if x0 <= x <= x1 and y0 <= y <= y1:
                if indice != self.sel:
                    self.sel = indice
                    if self.screen == MENU:
                        self.mostrar_menu(reset_sel=False)
                    else:
                        self.mostrar_dificultad(reset_sel=False)
                return

    def _handle_click(self, event):
        """Ejecuta la opción pulsada con el ratón."""
        if self.screen not in (MENU, DIFICULTAD):
            return
        x, y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        for x0, y0, x1, y1, _indice, cb in getattr(self, '_clickables', []):
            if x0 <= x <= x1 and y0 <= y <= y1:
                self.sel = _indice
                cb()
                return

    def salir(self):
        """Cierra el juego limpiamente."""
        self.cerrar()

    def cerrar(self):
        """Cancela el bucle y destruye la ventana."""
        self._cancel_loop()
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    # ==================================================================
    # Entrada de teclado
    # ==================================================================

    def _handle_key(self, event):
        """Reparte el input según la pantalla activa."""
        key = event.keysym

        # ---- Menús ----
        if self.screen in (MENU, DIFICULTAD):
            if key in ('Up', 'k'):
                self._mover_seleccion(-1)
            elif key in ('Down', 'j'):
                self._mover_seleccion(1)
            elif key in ('Return', 'KP_Enter', 'space'):
                self._activar_seleccion()
            elif key == 'Escape':
                if self.screen == DIFICULTAD:
                    self.mostrar_menu()
                else:
                    self.salir()
            return

        if self.screen == RECORDS:
            if key in ('Escape', 'Return', 'KP_Enter', 'space'):
                self.mostrar_menu()
            return

        if self.screen == AYUDA:
            if key in ('Escape', 'Return', 'KP_Enter', 'space'):
                self.mostrar_menu()
            return

        # ---- Juego ----
        if self.screen == GAME_OVER:
            if key in ('Return', 'KP_Enter', 'r', 'R'):
                self._restart_game()
            elif key == 'Escape':
                self.mostrar_menu()
            elif key == 'space':
                self.mostrar_menu()
            return

        if key == 'Escape':
            self.mostrar_menu()
            return

        if key == 'space':
            self._toggle_pause()
            return
        if key in ('r', 'R'):
            self._restart_game()
            return

        if self.screen == PAUSA:
            return  # en pausa solo se aceptan las teclas de arriba

        # Direcciones (evitar reversión directa)
        if key == 'Up' and self.direction != (0, 1):
            self.next_direction = (0, -1)
        elif key == 'Down' and self.direction != (0, -1):
            self.next_direction = (0, 1)
        elif key == 'Left' and self.direction != (1, 0):
            self.next_direction = (-1, 0)
        elif key == 'Right' and self.direction != (-1, 0):
            self.next_direction = (1, 0)

    def _toggle_pause(self):
        """Alterna pausa del juego."""
        if self.screen == JUEGO:
            self.screen = PAUSA
        elif self.screen == PAUSA:
            self.screen = JUEGO
            # El tiempo transcurrido en pausa no debe contar
            self._last_frame = time.monotonic()

    # ==================================================================
    # Lógica del juego
    # ==================================================================

    def _setup_game(self):
        """Inicializa variables de la partida."""
        _, ms, multiplicador, _ = DIFICULTADES[self.dif_index]

        self.snake = [(self.GRID_WIDTH // 2, self.GRID_HEIGHT // 2)]
        self.direction = (1, 0)  # Derecha
        self.next_direction = (1, 0)
        self.food = None
        self.score = 0
        self.level = 1
        self.game_running = True
        self.particles = []
        self.food_pulse = 0.0
        self.puntos_por_comida = 10 * multiplicador

        # Estado de animación / interpolación
        self.speed_base = ms
        self.update_speed = ms
        self._speed_s = ms / 1000.0
        self._accumulator = 0.0
        self._interp = 1.0
        self._prev_snake = list(self.snake)
        self._last_frame = time.monotonic()
        self._after_id = None

        # Objetos reutilizables del canvas
        self._snake_items = []
        self._eye_items = []
        self._food_items = []
        self._food_pos = None
        self._game_over_flag = False
        self._nuevo_record = False
        self._grid_drawn = False
        self._clickables = []

        self._spawn_food()
        self._actualizar_hud()

    def _actualizar_hud(self):
        """Refresca las etiquetas de puntuación y nivel."""
        self.score_label.config(text=f"Puntuacion: {self.score}")
        self.level_label.config(text=f"Nivel: {self.level}")

    def _spawn_food(self):
        """Genera comida en posición aleatoria válida."""
        libre = [
            (x, y)
            for x in range(self.GRID_WIDTH)
            for y in range(self.GRID_HEIGHT)
            if (x, y) not in self.snake
        ]
        self.food = random.choice(libre) if libre else None

    def _create_particles(self, x, y):
        """Crea efectos de partículas al comer."""
        center_x = x * self.CELL_SIZE + self.CELL_SIZE // 2
        center_y = y * self.CELL_SIZE + self.CELL_SIZE // 2
        margen = self.MAX_PARTICLES - len(self.particles)
        for _ in range(max(0, min(12, margen))):
            self.particles.append(Particle(center_x, center_y, self.COLORS['food']))

    def _update(self):
        """Avanza la lógica del juego una celda (un 'tick')."""
        if not self.game_running:
            return

        self.direction = self.next_direction

        head = self.snake[0]
        new_head = (head[0] + self.direction[0], head[1] + self.direction[1])

        # Colisión con las paredes
        if (new_head[0] < 0 or new_head[0] >= self.GRID_WIDTH or
                new_head[1] < 0 or new_head[1] >= self.GRID_HEIGHT):
            self._game_over()
            return

        # Colisión consigo misma
        if new_head in self.snake[:-1]:
            self._game_over()
            return

        # Posición previa de cada segmento, para interpolar el movimiento
        self._prev_snake = list(self.snake)
        self.snake.insert(0, new_head)

        if new_head == self.food:
            self.score += int(self.puntos_por_comida * self.level)
            self._create_particles(new_head[0], new_head[1])
            self._spawn_food()

            # Subir de nivel cada 50 puntos
            if self.score >= self.level * 50:
                self.level += 1
                self.update_speed = max(
                    self.MIN_SPEED, self.speed_base - (self.level - 1) * 8
                )
                self._speed_s = self.update_speed / 1000.0
            self._actualizar_hud()
        else:
            self.snake.pop()

    def _fade_stipple(self, life):
        """Convierte la vida restante (0.0-1.0) en un bitmap de stipple válido.

        Tk solo acepta los bitmaps predefinidos gray12, gray25, gray50 y gray75,
        por lo que la transparencia se aproxima por tramos.
        """
        if life > 0.75:
            return 'gray75'
        if life > 0.50:
            return 'gray50'
        if life > 0.25:
            return 'gray25'
        return 'gray12'

    # ==================================================================
    # Render del juego
    # ==================================================================

    def _draw_grid(self):
        """Dibuja el tablero a cuadros UNA sola vez (es estático)."""
        self.canvas.delete('all')
        self._snake_items = []
        self._eye_items = []
        self._food_items = []
        self._food_pos = None
        self._clickables = []

        for i in range(self.GRID_WIDTH):
            for j in range(self.GRID_HEIGHT):
                x1 = i * self.CELL_SIZE
                y1 = j * self.CELL_SIZE
                self.canvas.create_rectangle(
                    x1, y1, x1 + self.CELL_SIZE, y1 + self.CELL_SIZE,
                    fill=self.COLORS['bg'] if (i + j) % 2 == 0 else self.COLORS['grid'],
                    outline=''
                )
        self._grid_drawn = True

    def _food_items_for(self, pos):
        """Crea (si hace falta) los dos óvalos de la comida y los devuelve."""
        if self._food_pos != pos or not self._food_items:
            for item in self._food_items:
                self.canvas.delete(item)
            glow = self.canvas.create_oval(0, 0, 0, 0, fill='',
                                           outline=self.COLORS['food_glow'], width=2)
            body = self.canvas.create_oval(0, 0, 0, 0, fill=self.COLORS['food'],
                                           outline=self.COLORS['food_glow'], width=2)
            self._food_items = [glow, body]
            self._food_pos = pos
        return self._food_items

    def _draw_food(self):
        """Dibuja la comida con efecto de pulso."""
        if not self.food:
            return
        pulse_size = math.sin(self.food_pulse) * 2 + 3
        fx = self.food[0] * self.CELL_SIZE + self.CELL_SIZE // 2
        fy = self.food[1] * self.CELL_SIZE + self.CELL_SIZE // 2
        mitad = self.CELL_SIZE // 2
        glow, body = self._food_items_for(self.food)

        self.canvas.coords(
            glow,
            fx - mitad - pulse_size, fy - mitad - pulse_size,
            fx + mitad + pulse_size, fy + mitad + pulse_size
        )
        self.canvas.coords(
            body,
            fx - mitad + 2, fy - mitad + 2,
            fx + mitad - 2, fy + mitad - 2
        )

    def _eye_centers(self, x, y):
        """Devuelve los dos centros de los ojos según la dirección actual."""
        eye_offset = 6
        if self.direction == (1, 0):      # Derecha
            return ((x + self.CELL_SIZE - eye_offset - 2, y + eye_offset),
                    (x + self.CELL_SIZE - eye_offset - 2, y + self.CELL_SIZE - eye_offset))
        if self.direction == (-1, 0):     # Izquierda
            return ((x + eye_offset + 2, y + eye_offset),
                    (x + eye_offset + 2, y + self.CELL_SIZE - eye_offset))
        if self.direction == (0, -1):     # Arriba
            return ((x + eye_offset, y + eye_offset + 2),
                    (x + self.CELL_SIZE - eye_offset, y + eye_offset + 2))
        # Abajo
        return ((x + eye_offset, y + self.CELL_SIZE - eye_offset - 2),
                (x + self.CELL_SIZE - eye_offset, y + self.CELL_SIZE - eye_offset - 2))

    def _draw_snake(self):
        """Dibuja la serpiente interpolando cada segmento hacia su celda actual."""
        t = self._interp
        cell = self.CELL_SIZE
        prev = self._prev_snake

        while len(self._snake_items) < len(self.snake):
            sombra = self.canvas.create_rectangle(0, 0, 0, 0, fill='#000000',
                                                  outline='', stipple='gray50')
            cuerpo = self.canvas.create_rectangle(0, 0, 0, 0,
                                                  fill=self.COLORS['snake_body'],
                                                  outline=self.COLORS['snake_border'],
                                                  width=1)
            detalle = self.canvas.create_oval(0, 0, 0, 0,
                                              fill=self.COLORS['snake_head'],
                                              outline='', stipple='gray75')
            self._snake_items.append([sombra, cuerpo, detalle])

        vivos = len(self.snake)
        cuerpo_cabeza = self._snake_items[0][1]

        for i, segment in enumerate(self.snake):
            sombra, cuerpo, detalle = self._snake_items[i]

            origen = prev[i] if i < len(prev) else None
            if origen is None or origen == segment:
                px, py = segment[0] * cell, segment[1] * cell
            else:
                px = (origen[0] + (segment[0] - origen[0]) * t) * cell
                py = (origen[1] + (segment[1] - origen[1]) * t) * cell

            if i == 0:
                self.canvas.coords(sombra, px + 2, py + 2,
                                   px + cell + 2, py + cell + 2)
                self.canvas.coords(cuerpo, px + 1, py + 1,
                                   px + cell - 1, py + cell - 1)
                self.canvas.itemconfig(cuerpo, fill=self.COLORS['snake_head'], width=2)
                self.canvas.coords(detalle, 0, 0, 0, 0)  # la cabeza no lleva detalle
            else:
                self.canvas.coords(sombra, px + 2, py + 2,
                                   px + cell + 2, py + cell + 2)
                self.canvas.coords(cuerpo, px + 2, py + 2,
                                   px + cell - 2, py + cell - 2)
                self.canvas.itemconfig(cuerpo, fill=self.COLORS['snake_body'], width=1)
                cx, cy = px + cell // 2, py + cell // 2
                self.canvas.coords(detalle, cx - 3, cy - 3, cx + 3, cy + 3)

        for i in range(vivos, len(self._snake_items)):
            for item in self._snake_items[i]:
                self.canvas.coords(item, 0, 0, 0, 0)

        # Ojos sobre la cabeza
        coords = self.canvas.coords(cuerpo_cabeza)
        head_x, head_y = coords[0] - 1, coords[1] - 1
        centros = self._eye_centers(head_x, head_y)

        while len(self._eye_items) < 2:
            blanco = self.canvas.create_oval(0, 0, 0, 0, fill='white', outline='')
            pupila = self.canvas.create_oval(0, 0, 0, 0, fill='black', outline='')
            self._eye_items.append([blanco, pupila])

        for (ex, ey), (blanco, pupila) in zip(centros, self._eye_items):
            self.canvas.coords(blanco, ex - 4, ey - 4, ex + 4, ey + 4)
            self.canvas.coords(pupila, ex - 2, ey - 2, ex + 2, ey + 2)

    def _draw_particles(self):
        """Dibuja las partículas reutilizando sus óvalos."""
        for p in self.particles:
            if p.life <= 0:
                continue
            if p.item is None:
                p.item = self.canvas.create_oval(0, 0, 0, 0, fill=p.color, outline='')
            self.canvas.itemconfig(p.item, fill=p.color, stipple=self._fade_stipple(p.life))
            self.canvas.coords(p.item, p.x - p.size, p.y - p.size,
                               p.x + p.size, p.y + p.size)

    def _draw(self):
        """Dibuja el estado de la partida. Solo toca los objetos dinámicos."""
        if not self._grid_drawn:
            self._draw_grid()

        for p in self.particles:
            if p.life <= 0 and p.item is not None:
                self.canvas.delete(p.item)
                p.item = None
        self.particles = [p for p in self.particles if p.life > 0]

        self.canvas.delete('overlay')
        self._draw_food()
        self._draw_snake()
        self._draw_particles()

        if self.screen == PAUSA:
            self._draw_overlay("PAUSA", "ESPACIO para continuar  -  ESC para el menu")
        elif self.screen == GAME_OVER:
            self._draw_overlay_game_over()

    def _draw_overlay(self, main_text, sub_text):
        """Overlay centrado con texto."""
        cx = self.width // 2
        cy = self.height // 2
        self.canvas.create_rectangle(
            0, cy - 70, self.width, cy + 70,
            fill='#000000', outline='', stipple='gray50', tags='overlay'
        )
        self.canvas.create_text(
            cx, cy - 20, text=main_text, font=('Helvetica', 28, 'bold'),
            fill=self.COLORS['game_over'], tags='overlay'
        )
        self.canvas.create_text(
            cx, cy + 25, text=sub_text, font=('Helvetica', 14),
            fill=self.COLORS['text'], tags='overlay'
        )

    def _draw_overlay_game_over(self):
        """Overlay de fin de partida, con récord si se ha conseguido."""
        cx = self.width // 2
        cy = self.height // 2
        self.canvas.create_rectangle(
            0, cy - 95, self.width, cy + 95,
            fill='#000000', outline='', stipple='gray50', tags='overlay'
        )
        self.canvas.create_text(
            cx, cy - 58, text="GAME OVER", font=('Helvetica', 28, 'bold'),
            fill=self.COLORS['game_over'], tags='overlay'
        )
        self.canvas.create_text(
            cx, cy - 18, text=f"Puntuacion: {self.score}",
            font=('Helvetica', 16, 'bold'), fill=self.COLORS['text'], tags='overlay'
        )
        if self._nuevo_record:
            self.canvas.create_text(
                cx, cy + 14, text="NUEVO RECORD!", font=('Helvetica', 14, 'bold'),
                fill=self.COLORS['accent'], tags='overlay'
            )
        else:
            self.canvas.create_text(
                cx, cy + 14, text=f"Mejor: {self.mejor_record()}",
                font=('Helvetica', 12), fill=self.COLORS['text_dim'], tags='overlay'
            )
        self.canvas.create_text(
            cx, cy + 52, text="R / ENTER: jugar de nuevo      ESC: menu",
            font=('Helvetica', 11), fill=self.COLORS['text'], tags='overlay'
        )

    # ==================================================================
    # Fin de partida / reinicio
    # ==================================================================

    def _game_over(self):
        """Maneja el fin de la partida."""
        self.game_running = False
        self._game_over_flag = True
        self.screen = GAME_OVER
        self._cancel_loop()
        self._nuevo_record = self._registrar_record(self.score)
        self._actualizar_hud()
        self._draw()
        self.title_label.config(text="GAME OVER", fg=self.COLORS['game_over'])
        self._last_frame = time.monotonic()
        self._game_loop()   # el overlay de game over se anima (partículas)

    def _restart_game(self):
        """Reinicia la partida con la dificultad actual."""
        self._cancel_loop()
        self.screen = JUEGO
        self._setup_game()
        self.title_label.config(text="SNAKE GAME", fg=self.COLORS['accent'])
        self._draw_grid()
        self._game_loop()

    # ==================================================================
    # Bucle principal
    # ==================================================================

    def _cancel_loop(self):
        """Cancela el frame pendiente (evita cadenas de 'after' duplicadas)."""
        if self._after_id is not None:
            try:
                self.root.after_cancel(self._after_id)
            except tk.TclError:
                pass
            self._after_id = None

    def _schedule_next(self, delay_ms):
        """Agenda exactamente un frame, reemplazando cualquier pendiente."""
        self._cancel_loop()
        self._after_id = self.root.after(max(1, int(delay_ms)), self._game_loop)

    def _game_loop(self):
        """Bucle principal: render a ~60 FPS y lógica por acumulador de tiempo.

        Se mantiene vivo en las pantallas de juego (incluida PAUSA y GAME_OVER,
        para que las partículas sigan animándose). En los menús el bucle se
        detiene: allí no hay nada que animar y no se consume CPU.
        """
        ahora = time.monotonic()
        dt = ahora - self._last_frame
        self._last_frame = ahora
        dt = min(dt, self.MAX_DT)

        en_juego = self.screen in (JUEGO, PAUSA, GAME_OVER)
        if not en_juego:
            return

        # La comida y las partículas se animan siempre
        self.food_pulse += dt * 9.0   # 0.15 por tick de 120 ms, expresado por segundo

        for p in self.particles:
            p.update(dt)

        if self.screen == JUEGO and self.game_running:
            self._accumulator += dt
            avances = 0
            # Máximo 4 avances por frame: evita espiral de la muerte si hay lag
            while self._accumulator >= self._speed_s and avances < 4:
                self._accumulator -= self._speed_s
                self._update()
                avances += 1
                if not self.game_running:
                    self._accumulator = 0.0
                    break
            if avances >= 4:
                self._accumulator = 0.0
            self._interp = min(1.0, self._accumulator / self._speed_s)
        else:
            self._interp = 1.0

        self._draw()

        consumido = (time.monotonic() - ahora) * 1000.0
        self._schedule_next(self.FRAME_MS - consumido)

    def run(self):
        """Inicia el juego."""
        self._last_frame = time.monotonic()
        self.root.mainloop()


def main():
    """Punto de entrada principal."""
    juego = SnakeGame()
    juego.run()


if __name__ == "__main__":
    main()
