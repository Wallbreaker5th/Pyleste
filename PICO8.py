import math

from GameState import GameState


# the PICO-8 palette: 16 fixed colours, indexed 0 to 15
PALETTE = [
  (0x00, 0x00, 0x00), # 0  black
  (0x1d, 0x2b, 0x53), # 1  dark blue
  (0x7e, 0x25, 0x53), # 2  dark purple
  (0x00, 0x87, 0x51), # 3  dark green
  (0xab, 0x52, 0x36), # 4  brown
  (0x5f, 0x57, 0x4f), # 5  dark grey
  (0xc2, 0xc3, 0xc7), # 6  light grey
  (0xff, 0xf1, 0xe8), # 7  white
  (0xff, 0x00, 0x4d), # 8  red
  (0xff, 0xa3, 0x00), # 9  orange
  (0xff, 0xec, 0x27), # 10 yellow
  (0x00, 0xe4, 0x36), # 11 green
  (0x29, 0xad, 0xff), # 12 blue
  (0x83, 0x76, 0x9c), # 13 lavender
  (0xff, 0x77, 0xa8), # 14 pink
  (0xff, 0xcc, 0xaa), # 15 peach
]

SCREEN_W, SCREEN_H = 128, 128


class PICO8():
  """A PICO-8 console: cart memory, buttons, screen and step loop.

  Every console owns its cart, memory and screen, so any number of consoles
  can be simulated side by side.
  """

  def __init__(self, cart):
    self._btn_state = 0
    self._screen = None
    self._pal = None
    self.load_game(cart)

  # game functions

  def btn(self, i):
    return self._btn_state & (2 ** i) != 0

  def mset(self, x, y, tile):
    self._memory['map'][x + y * 128] = tile

  def mget(self, x, y):
    return self._memory['map'][x + y * 128]

  def fget(self, n, f=None):
    flags = self._memory['flags'][n]
    return flags if f == None else flags & 2 ** f != 0

  # console commands

  # load game from cart
  def load_game(self, cart):
    self._cart = cart
    self._game = self._cart(self)
    self._memory = {
      'map': [int(self._game.map_data[i:i + 2][::1 if i < 8192 else -1], 16) for i in range(0, len(self._game.map_data), 2)],
      'flags': [int(self._game.flag_data[i:i + 2], 16) for i in range(0, len(self._game.flag_data), 2)],
      'gfx': self.parse_gfx(getattr(self._game, 'gfx_data', None))
    }
    self._game._init()

  # the sprite sheet is 128x128 pixels, one hex digit per pixel
  @staticmethod
  def parse_gfx(gfx_data):
    if gfx_data is None:
      return None
    return [[int(c, 16) for c in gfx_data[y * 128:(y + 1) * 128]] for y in range(128)]

  # reload the current cart
  def reset(self):
    self.load_game(self._cart)

  # perform a game step
  def step(self):
    self._game._update()
    self._game._draw()

  # set button state from inputs
  def set_inputs(self, l=False, r=False, u=False, d=False, z=False, x=False):
    self.set_btn_state(l * 1 + r * 2 + u * 4 + d * 8 + z * 16 + x * 32)

  # set button state directly (0bxzdurl)
  def set_btn_state(self, state):
    self._btn_state = state

  # screen, following the PICO-8 drawing functions (colours are palette
  # indexes, sprite/tile pixels with colour 0 are transparent)

  def cls(self, color=0):
    self._screen = [color] * (SCREEN_W * SCREEN_H)

  # remap a colour while drawing (pal(8, 12) draws everything that would be
  # colour 8 in colour 12); pal() on its own clears the remapping again
  def pal(self, c0=None, c1=None):
    if c0 is None:
      self._pal = None
    else:
      self._pal = dict(self._pal or {})
      self._pal[c0] = c1

  def _color(self, color):
    return self._pal.get(color, color) if self._pal else color

  def pset(self, x, y, color):
    x, y = math.floor(x), math.floor(y)
    if 0 <= x < SCREEN_W and 0 <= y < SCREEN_H:
      self._get_screen()[y * SCREEN_W + x] = self._color(color)

  def rectfill(self, x1, y1, x2, y2, color):
    x1, y1 = max(0, math.floor(x1)), max(0, math.floor(y1))
    x2, y2 = min(SCREEN_W - 1, math.floor(x2)), min(SCREEN_H - 1, math.floor(y2))
    color = self._color(color)
    screen = self._get_screen()
    for y in range(y1, y2 + 1):
      for x in range(x1, x2 + 1):
        screen[y * SCREEN_W + x] = color

  # filled circle of radius r around (x, y)
  def circfill(self, x, y, r, color):
    color = self._color(color)
    screen = self._get_screen()
    for py in range(math.floor(y - r), math.floor(y + r) + 1):
      for px in range(math.floor(x - r), math.floor(x + r) + 1):
        if (px - x) ** 2 + (py - y) ** 2 > r * r:
          continue
        if 0 <= px < SCREEN_W and 0 <= py < SCREEN_H:
          screen[py * SCREEN_W + px] = color

  # draw a (w x h) block of sprites, sprite 0 is the top-left of the sheet
  def spr(self, n, x, y, w=1, h=1, flip_x=False, flip_y=False):
    gfx = self._memory['gfx']
    if gfx is None or n is None:
      return
    n = math.floor(n)
    if n < 0 or n > 255:
      return
    sx, sy = (n % 16) * 8, (n // 16) * 8
    x, y = math.floor(x), math.floor(y)
    screen = self._get_screen()
    for j in range(h * 8):
      ty = sy + (h * 8 - 1 - j if flip_y else j)
      for i in range(w * 8):
        color = gfx[ty][sx + (w * 8 - 1 - i if flip_x else i)]
        if color == 0:
          continue # transparent
        px, py = x + i, y + j
        if 0 <= px < SCREEN_W and 0 <= py < SCREEN_H:
          screen[py * SCREEN_W + px] = self._color(color)

  # draw a celw x celh area of the map, layer by layer
  # a tile belongs to every layer that its sprite flags name, so a tile is
  # drawn when the layers bitfield shares a bit with the tile's flags, and
  # tiles without any flags belong to the default layer (bit 0) - the vanilla
  # cart draws the background terrain with 4 and the terrain with 2
  def map(self, celx, cely, sx=0, sy=0, celw=16, celh=16, layers=0x1):
    for i in range(celw):
      for j in range(celh):
        tile = self.mget(celx + i, cely + j)
        flags = self.fget(tile) or 0x0
        if layers & (flags if flags & 0x7 else 0x1):
          self.spr(tile, sx + i * 8, sy + j * 8)

  def _get_screen(self):
    if self._screen is None:
      self._screen = [0] * (SCREEN_W * SCREEN_H)
    return self._screen

  # rendering

  # draw the current game state and return it as a PIL image
  # (scale is an integer upscale factor; the game is 128x128 pixels)
  def render(self, scale=1):
    if callable(getattr(self._game, '_render', None)):
      self._game._render()
    else:
      self._game._draw()
    return self.screen_image(scale)

  # the current screen contents as a PIL image
  def screen_image(self, scale=1):
    from PIL import Image
    image = Image.new('P', (SCREEN_W, SCREEN_H))
    image.putpalette([c for rgb in PALETTE for c in rgb] + [0] * (768 - 3 * len(PALETTE)))
    image.putdata(self._get_screen())
    if scale != 1:
      image = image.resize((SCREEN_W * int(scale), SCREEN_H * int(scale)), Image.NEAREST)
    return image

  # draw the current game state and return it as PNG bytes
  def render_png(self, scale=1):
    import io
    buffer = io.BytesIO()
    self.render(scale).save(buffer, 'PNG')
    return buffer.getvalue()

  # draw the current game state and write it to an image file
  def save_render(self, path, scale=1):
    self.render(scale).save(path)
    return path

  # game state

  # a GameState snapshot of the current game, independent of this console
  def get_state(self):
    return self._game.get_state()

  # restore a GameState (taken from this or any other console)
  def set_state(self, state):
    self._game.set_state(state)

  def save_state(self, path):
    return self.get_state().save(path)

  def load_state(self, path):
    state = GameState.load(path)
    self.set_state(state)
    return state

  @property
  def game(self):
    return self._game

  @property
  def input_display(self):
    l, r, u, d, z, x = ('▓▓' if self.btn(i) else '░░' for i in range(6))
    return f"        {u}\n{z}{x}  {l}{d}{r}"
