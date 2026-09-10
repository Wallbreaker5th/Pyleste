import copy
import math

from GameState import GameState, encode_attrs, decode_attrs


def sin(x):
  return math.sin(-math.pi*2*x)

class Vector():
  def __init__(self, x, y):
    self.x = x
    self.y = y

class Rect():
  def __init__(self, x, y, w, h):
    self.x = x
    self.y = y
    self.w = w
    self.h = h

class Celeste():
  def __init__(self, pico8):
    # every game keeps a reference to its own console instead of using globals
    self.p8 = pico8

    # game globals
    self.room = Vector(0, 0)
    self.objects = []
    self.freeze = 0
    self.delay_restart = 0
    self.next_rm = False # [change] decouple next room from object loop

    self.max_djump = 1

    self.k_left = 0
    self.k_right = 1
    self.k_up = 2
    self.k_down = 3
    self.k_jump = 4
    self.k_dash = 5

    self.tiles = {
      1: self.player_spawn,
      8: self.key,
      11: self.platform,
      12: self.platform,
      18: self.spring,
      20: self.chest,
      22: self.balloon,
      23: self.fall_floor,
      26: self.fruit,
      28: self.fly_fruit,
      64: self.fake_wall,
      #86: self.message,
      #96: self.big_chest,
      #118: self.flag
    }

    # types used when restoring a saved game state (see get_state/set_state)
    self.object_types = {
      'player_spawn': self.player_spawn,
      'player': self.player,
      'balloon': self.balloon,
      'platform': self.platform,
      'fruit': self.fruit,
      'fly_fruit': self.fly_fruit,
      'fake_wall': self.fake_wall,
      'spring': self.spring,
      'fall_floor': self.fall_floor,
      'key': self.key,
      'chest': self.chest
    }
    self.value_types = {'Vector': Vector, 'Rect': Rect}

  # entry point

  def _init(self):
    self.frames = 0
    self.load_room(0, 0)

  # main update loop

  def _update(self):
    self.frames = (self.frames + 1) % 30

    if self.freeze > 0:
      self.freeze -= 1
      return

    if self.delay_restart > 0:
      self.delay_restart -= 1
      if self.delay_restart == 0:
        self.load_room(self.room.x, self.room.y)

    for o in self.objects:
      o.move(o.spd.x, o.spd.y)
      if callable(getattr(o, 'update', None)):
        o.update()

    # [change] decouple next room from object loop
    if self.next_rm:
      self.next_rm = False
      lvl_id = self.level_index()
      n_objs = len(self.objects)
      self.load_room(lvl_id % 8, math.floor(lvl_id / 8))
      # simulate loading jank
      if lvl_id > 0:
        for o in self.objects[n_objs - 1:]:
          o.move(o.spd.x, o.spd.y)
          if callable(getattr(o, 'update', None)):
            o.update()

    # [change] remove destroyed objects after update calls
    while self.objects.count(None) > 0: self.objects.remove(None)

  # main draw loop (not actually for drawing)

  def _draw(self):
    if self.freeze > 0:
      return

    for o in self.objects:
      if callable(getattr(o, 'draw', None)):
        o.draw()

  # room stuff

  def level_index(self):
    return self.room.x + self.room.y * 8

  def restart_room(self):
    self.delay_restart=15

  def next_room(self, loop=False):
    # [change] decouple next room from object loop
    self.room = Vector((self.level_index() + 1) % 8, math.floor((self.level_index() + 1) / 8))
    self.next_rm = True

  def load_room(self, x, y):
    self.has_dashed = False
    self.has_key = False
    self.objects = []
    self.room.x = x
    self.room.y = y
    for tx in range(16):
      for ty in range(16):
        tile = self.p8.mget(self.room.x * 16 + tx, self.room.y * 16 + ty)
        if tile in self.tiles:
          self.init_object(self.tiles[tile], tx * 8, ty * 8, tile)

  # object base class

  class base_obj():
    def __init__(self, x, y, tile=None):
      self.collideable = True,
      self.solids = False
      self.spr = tile
      self.flip = Vector(False, False)
      self.x = x
      self.y = y
      self.hitbox = Rect(0, 0, 8, 8)
      self.spd = Vector(0.0, 0.0)
      self.rem = Vector(0.0, 0.0)

    def is_solid(self, ox, oy):
      if oy > 0 and not self.check(self.game.platform, ox, 0) and self.check(self.game.platform, ox, oy):
        return True
      return self.game.tile_flag_at(self.x + self.hitbox.x + ox, self.y + self.hitbox.y + oy, self.hitbox.w, self.hitbox.h, 0)\
        or self.check(self.game.fall_floor, ox, oy)\
        or self.check(self.game.fake_wall, ox, oy)

    def is_ice(self, ox, oy):
      return self.game.tile_flag_at(self.x + self.hitbox.x + ox, self.y + self.hitbox.y + oy, self.hitbox.w, self.hitbox.h, 4)

    def check(self, obj, ox, oy):
      for other in self.game.objects:
        if type(other) == obj and other != self and other.collideable and \
         other.x + other.hitbox.x + other.hitbox.w > self.x + self.hitbox.x + ox and \
         other.y + other.hitbox.y + other.hitbox.h > self.y + self.hitbox.y + oy and \
         other.x + other.hitbox.x < self.x + self.hitbox.x + self.hitbox.w + ox and \
         other.y + other.hitbox.y < self.y + self.hitbox.y + self.hitbox.h + oy:
          return other
      return None

    def move(self, ox, oy):
      self.rem.x += ox
      amt = math.floor(self.rem.x + 0.5)
      self.rem.x -= amt
      self.move_x(amt, 0)
      self.rem.y += oy
      amt = math.floor(self.rem.y + 0.5)
      self.rem.y -= amt
      self.move_y(amt)

    def move_x(self, amt, start):
      if self.solids:
        step = self.game.sign(amt)
        for i in range(start, abs(amt) + 1):
          if not self.is_solid(step, 0):
            self.x += step
          else:
            self.spd.x = 0
            self.rem.x = 0
            break
      else:
        self.x += amt

    def move_y(self, amt):
      if self.solids:
        step = self.game.sign(amt)
        for i in range(abs(amt) + 1):
          if not self.is_solid(0, step):
            self.y += step
          else:
            self.spd.y = 0
            self.rem.y = 0
            break
      else:
        self.y += amt

    def __str__(self):
      return f'[{self.__class__.__name__}] x: {self.x}, y: {self.y}, rem: {{{self.rem.x:.4f}, {self.rem.y:.4f}}}, spd: {{{self.spd.x:.4f}, {self.spd.y:.4f}}}'

    def __deepcopy__(self, memo):
      # [change] copies (e.g. the ones searched from) must reference the same
      # game, rather than deep copying it along with the object
      copy_of_self = type(self).__new__(type(self))
      memo[id(self)] = copy_of_self
      for key, value in self.__dict__.items():
        setattr(copy_of_self, key, value if key == 'game' else copy.deepcopy(value, memo))
      return copy_of_self

  # objects

  class player_spawn(base_obj):
    def init(self):
      self.spr = 3
      self.target = self.y
      self.y = 128
      self.spd.y = -4
      self.state = 0
      self.delay = 0

    def update(self):
      # jumping up
      if self.state == 0:
        if self.y < self.target + 16:
          self.state = 1
          self.delay = 3
      # falling
      elif self.state == 1:
        self.spd.y += 0.5
        if self.spd.y > 0:
          if self.delay > 0:
            # stall at peak
            self.spd.y = 0
            self.delay -= 1
          elif self.y > self.target:
            # clamp at target y
            self.y = self.target
            self.spd = Vector(0.0, 0.0)
            self.state = 2
            self.delay = 5
      # landing and spawning player object
      elif self.state == 2:
        self.delay -= 1
        if self.delay < 0:
          self.game.destroy_object(self)
          self.game.init_object(self.game.player, self.x, self.y)

  class player(base_obj):
    def init(self):
      self.p_jump = False
      self.p_dash = False
      self.grace = 0
      self.jbuffer = 0
      self.djump = 1
      self.dash_time = 0
      self.dash_effect_time = 0
      self.dash_target = Vector(0.0, 0.0)
      self.dash_accel = Vector(0.0, 0.0)
      self.hitbox = Rect(1, 3, 6, 5)
      self.solids = True
      # [change] animation state, used when rendering
      self.spr = 1
      self.spr_off = 0.0

    def update(self):
      # horizontal input
      h_input = 1 if self.game.p8.btn(self.game.k_right) else -1 if self.game.p8.btn(self.game.k_left) else 0

      # spike collision
      if self.game.spikes_at(self.x + self.hitbox.x, self.y + self.hitbox.y, self.hitbox.w, self.hitbox.h, self.spd.x, self.spd.y):
        self.game.kill_player(self)

      # bottom death
      if self.y > 128:
        self.game.kill_player(self)

      # on ground check
      on_ground = self.is_solid(0, 1)

      # jump and dash inmput
      jump = self.game.p8.btn(self.game.k_jump) and not self.p_jump
      dash = self.game.p8.btn(self.game.k_dash) and not self.p_dash
      self.p_jump = self.game.p8.btn(self.game.k_jump)
      self.p_dash = self.game.p8.btn(self.game.k_dash)

      # jump buffer
      if jump:
        self.jbuffer = 4
      elif self.jbuffer > 0:
        self.jbuffer -= 1

      # grace frames and dash restoration
      if on_ground:
        self.grace = 6
        self.djump = self.game.max_djump
      elif self.grace > 0:
        self.grace -= 1

      # dash effect timer (for dash-triggered events, e.g., berry blocks)
      self.dash_effect_time -= 1

      if self.dash_time > 0:
        self.dash_time -= 1
        self.spd.x = self.game.appr(self.spd.x, self.dash_target.x, self.dash_accel.x)
        self.spd.y = self.game.appr(self.spd.y, self.dash_target.y, self.dash_accel.y)
      else:
        maxrun = 1
        accel = (0.6 if not self.is_ice(0, 1) else 0.05) if on_ground else 0.4
        deccel = 0.15

        # set x speed
        self.spd.x = self.game.appr(self.spd.x, h_input * maxrun, accel) if abs(self.spd.x) <= 1 else self.game.appr(self.spd.x, self.game.sign(self.spd.x) * maxrun, deccel)

        # facing direction
        if self.spd.x != 0:
          self.flip.x = self.spd.x < 0

        # terminal vel + wall sliding
        maxfall = 2 if not (h_input != 0 and self.is_solid(h_input, 0) and not self.is_ice(h_input, 0)) else 0.4

        # apply gravity
        if not on_ground:
          self.spd.y = self.game.appr(self.spd.y, maxfall, 0.21 if abs(self.spd.y) > 0.15 else 0.105)

        # jump
        if self.jbuffer > 0:
          if self.grace > 0:
            self.jbuffer = 0
            self.grace = 0
            self.spd.y = -2
          else:
            wall_dir = -1 if self.is_solid(-3, 0) else 1 if self.is_solid(3, 0) else 0
            if wall_dir != 0:
              self.jbuffer = 0
              self.spd.y = -2
              self.spd.x = -wall_dir * (maxrun + 1)

        # dash
        d_full = 5
        d_half = 3.5355339059

        if self.djump > 0 and dash:
          self.djump -= 1
          self.dash_time = 4
          self.game.has_dashed = True
          self.dash_effect_time = 10
          # vertical input
          v_input = -1 if self.game.p8.btn(self.game.k_up) else 1 if self.game.p8.btn(self.game.k_down) else 0
          # calculate dash speeds
          self.spd.x = h_input * (d_full if v_input == 0 else d_half) if h_input != 0 else (0 if v_input != 0 else -1 if self.flip.x else 1)
          self.spd.y = v_input * (d_full if h_input == 0 else d_half) if v_input != 0 else 0
          # effects
          self.game.freeze = 2
          # dash target speeds and accels
          self.dash_target.x = 2 * self.game.sign(self.spd.x)
          self.dash_target.y = (2 if self.spd.y >= 0 else 1.5) * self.game.sign(self.spd.y)
          self.dash_accel.x = 1.5 if self.spd.y == 0 else 1.06066017177
          self.dash_accel.y = 1.5 if self.spd.x == 0 else 1.06066017177

      # animation (kept in the update loop, like vanilla, so that it only
      # depends on the game state and not on when the game is rendered)
      self.spr_off += 0.25
      if not on_ground:
        self.spr = 5 if self.is_solid(h_input, 0) else 3 # wall slide or mid air
      elif self.game.p8.btn(self.game.k_down):
        self.spr = 6 # crouch
      elif self.game.p8.btn(self.game.k_up):
        self.spr = 7 # look up
      elif self.spd.x != 0 and h_input != 0:
        self.spr = 1 + int(self.spr_off % 4) # walk
      else:
        self.spr = 1 # stand

      # exit level off the top
      if self.y < -4:
        self.game.next_room()

    def draw(self):
      if self.x < -1 or self.x > 121:
        self.x = self.game.clamp(self.x, -1, 121)
        self.spd.x = 0

  class balloon(base_obj):
    def init(self):
      self.timer = 0
      # [change] remove rng, expand hitbox to cover balloon oscillation cycle
      self.hitbox = Rect(-1, -1 - 2, 10, 10 + 4)

    def update(self):
      if self.spr == 22:
        hit = self.check(self.game.player, 0, 0)
        if hit and hit.djump < self.game.max_djump:
          hit.djump = self.game.max_djump
          self.spr = 0
          self.timer = 60
      elif self.timer > 0:
        self.timer -= 1
      else:
        self.spr = 22

  class platform(base_obj):
    def init(self):
      self.x -= 4
      self.hitbox.w = 16
      self.last = self.x
      self.dir = -1 if self.spr == 11 else 1

    def update(self):
      self.spd.x = self.dir * 0.65
      if self.x < -16:
        self.x = 128
      elif self.x > 128:
        self.x = -16
      if not self.check(self.game.player, 0, 0):
        hit = self.check(self.game.player, 0, -1)
        if hit:
          hit.move_x(self.x - self.last, 1)
      self.last = self.x

  class fruit(base_obj):
    def init(self):
      self.start = self.y
      self.off = 0

    def update(self):
      hit = self.check(self.game.player, 0, 0)
      if hit:
        hit.djump = self.game.max_djump
        self.game.destroy_object(self)
      self.off += 1
      self.y = self.start + sin(self.off / 40) * 2.5

  class fly_fruit(base_obj):
    def init(self):
      self.fly = False
      self.step = 0.5
      self.solids = False
      self.start = self.y

    def update(self):
      if self.fly:
        self.spd.y = self.game.appr(self.spd.y, -3.5, 0.25)
        if self.y < -16:
          self.game.destroy_object(self)
      else:
        if self.game.has_dashed:
          self.fly = True
        self.step += 0.05
        self.spd.y = sin(self.step) * 0.5
      hit = self.check(self.game.player, 0, 0)
      if hit:
        hit.djump = self.game.max_djump
        self.game.destroy_object(self)

  class fake_wall(base_obj):
    def update(self):
      self.hitbox.w = 18
      self.hitbox.h = 18
      hit = self.check(self.game.player, -1, -1)
      if hit and hit.dash_effect_time > 0:
        hit.spd.x = -self.game.sign(hit.spd.x) * 1.5
        hit.spd.y = -1.5
        hit.dash_time = -1
        self.game.init_object(self.game.fruit, self.x + 4, self.y + 4, 26)
        self.game.destroy_object(self)
      self.hitbox.w = 16
      self.hitbox.h = 16

  class spring(base_obj):
    def init(self):
      self.hide_in = 0
      self.hide_for = 0

    def update(self):
      if self.hide_for > 0:
        self.hide_for -= 1
        if self.hide_for <= 0:
          self.delay = 0
      elif self.spr == 18:
        hit = self.check(self.game.player, 0, 0)
        if hit and hit.spd.y >= 0:
          self.spr = 19
          hit.y = self.y - 4
          hit.spd.x *= 0.2
          hit.spd.y = -3
          hit.djump = self.game.max_djump
          self.delay = 10
          below = self.check(self.game.fall_floor, 0, 1)
          if below:
            self.game.break_fall_floor(below)
      elif self.delay > 0:
        self.delay -= 1
        if self.delay <= 0:
          self.spr = 18
      if self.hide_in > 0:
        self.hide_in -= 1
        if self.hide_in <= 0:
          self.hide_for = 60
          self.spr = 0

  class fall_floor(base_obj):
    def init(self):
      self.state = 0

    def update(self):
      if self.state == 0:
        if self.check(self.game.player, 0, -1) or self.check(self.game.player, -1, 0) or self.check(self.game.player, 1, 0):
          self.game.break_fall_floor(self)
      elif self.state == 1:
        self.delay -= 1
        if self.delay <= 0:
          self.state = 2
          self.delay = 60
          self.collideable = False
          self.spr = 0
      elif self.state == 2:
        self.delay -= 1
        if self.delay <= 0 and not self.check(self.game.player, 0, 0):
          self.state = 0
          self.collideable = True
          self.spr = 23

  def break_spring(self, obj):
    obj.hide_in = 15

  def break_fall_floor(self, obj):
    if obj.state == 0:
      obj.state = 1
      obj.delay = 15
      hit = obj.check(self.spring, 0, -1)
      if hit:
        self.break_spring(hit)

  class key(base_obj):
    def update(self):
      if self.check(self.game.player, 0, 0):
        self.game.destroy_object(self)
        self.game.has_key = True

  class chest(base_obj):
    def init(self):
      self.x -= 4
      self.timer = 20

    def update(self):
      if self.game.has_key:
        self.timer -= 1
        if self.timer <= 0:
          f = self.game.init_object(self.game.fruit, self.x, self.y - 4, 26)
          # [change] remove rng, expand fruit hitbox to cover all outcomes
          f.hitbox.x -= 1
          f.hitbox.w += 3
          self.game.destroy_object(self)

  # object handling stuff

  def init_object(self, obj, x, y, tile=None):
    o = obj(x, y, tile)
    o.game = self # [change] objects know their game instead of using a global
    self.objects.append(o)
    if callable(getattr(o, 'init', None)):
      o.init()
    return o

  def destroy_object(self, obj):
    # [change] remove from list later so update loop doesn't skip
    self.objects[self.objects.index(obj)] = None

  # game state

  def get_state(self):
    # a snapshot of everything needed to continue the game later on
    objects = [{'type': type(o).__name__, 'attrs': encode_attrs(vars(o), skip=('game',))}
      for o in self.objects if o is not None]
    attrs = {
      'frames': self.frames,
      'freeze': self.freeze,
      'delay_restart': self.delay_restart,
      'next_rm': self.next_rm,
      'max_djump': self.max_djump,
      'has_dashed': self.has_dashed,
      'has_key': self.has_key
    }
    return GameState(room=(self.room.x, self.room.y), objects=objects, attrs=attrs)

  def set_state(self, state):
    # restore a snapshot into this game (it may come from another instance)
    registry = dict(self.object_types, **self.value_types)
    self.room = Vector(*state.room)
    for key, value in state.attrs.items():
      setattr(self, key, value)
    self.objects = []
    for obj in state.objects:
      o = self.object_types[obj['type']].__new__(self.object_types[obj['type']])
      o.game = self
      for key, value in decode_attrs(obj['attrs'], registry).items():
        setattr(o, key, value)
      self.objects.append(o)

  def kill_player(self, obj):
    self.destroy_object(obj)
    self.restart_room()

  # helper functions

  def get_player(self):
    for o in self.objects:
      if type(o) == self.player_spawn or type(o) == self.player:
        return o

  def clamp(self, val, a, b):
    return max(a, min(b, val))

  def appr(self, val, target, amt):
    return max(val - amt, target) if val > target else min(val + amt, target)

  def sign(self, x):
    return 1 if x > 0 else -1 if x < 0 else 0

  def tile_flag_at(self, x, y, w, h, flag):
    for i in range(max(0, int(x / 8)), int(min(15, (x + w - 1) / 8)) + 1):
      for j in range(max(0, int(y / 8)), int(min(15, (y + h - 1) / 8)) + 1):
        if self.p8.fget(self.tile_at(i, j), flag):
          return True
    return False

  def tile_at(self, x, y):
    return self.p8.mget(self.room.x * 16 + x, self.room.y * 16 + y)

  def spikes_at(self, x, y, w, h, spdx, spdy):
    for i in range(max(0, int(x / 8)), int(min(15, (x + w - 1) / 8)) + 1):
      for j in range(max(0, int(y / 8)), int(min(15, (y + h - 1) / 8)) + 1):
        tile = self.tile_at(i, j)
        if (tile == 17 and ((y + h - 1) % 8 >= 6 or y + h == j * 8 + 8) and spdy >= 0) or \
         (tile == 27 and y % 8 <= 2 and spdy <= 0) or \
         (tile == 43 and x % 8 <= 2 and spdx <= 0) or \
         (tile == 59 and ((x + w - 1) % 8 >= 6 or x + w == i * 8 + 8) and spdx >= 0):
          return True
    return False

  # rendering

  # draw the current game state onto the console's screen
  # this is what the render interface (PICO8.render) uses; it does not touch
  # the simulation (vanilla draws clouds, particles and maddy's hair from its
  # draw loop, Pyleste does not simulate those)
  def _render(self):
    p8 = self.p8
    p8.cls(0) # background
    # room terrain: background tiles first, then the solid terrain over them
    rx, ry = self.room.x * 16, self.room.y * 16
    p8.map(rx, ry, 0, 0, 16, 16, 4)
    for o in self.objects:
      if type(o) == self.platform: # cloud platforms are drawn behind the terrain
        self.draw_object(o)
    p8.map(rx, ry, 0, 0, 16, 16, 2)
    for o in self.objects:
      if type(o) != self.platform:
        self.draw_object(o)

  # draw a single object with its sprite(s)
  def draw_object(self, obj):
    if obj is None or not obj.spr:
      return
    if type(obj) == self.fake_wall:
      self.p8.spr(obj.spr, obj.x, obj.y, 2, 2) # 2x2 blocks
    elif type(obj) == self.platform:
      self.p8.spr(11, obj.x, obj.y - 1, 2, 1) # cloud platform
    elif type(obj) == self.fly_fruit:
      self.p8.spr(obj.spr, obj.x, obj.y, 1, 1, obj.flip.x, obj.flip.y)
      wing = 45 if self.has_dashed or sin(obj.step) >= 0 else 47 if obj.y > obj.start else 46
      self.p8.spr(wing, obj.x - 6, obj.y - 2, 1, 1, True)
      self.p8.spr(wing, obj.x + 6, obj.y - 2)
    else:
      self.p8.spr(obj.spr, obj.x, obj.y, 1, 1, obj.flip.x, obj.flip.y)

  # [change] sprite sheet (128x128 pixels, one hex digit per pixel), from the cart's __gfx__ section
  @property
  def gfx_data(self):
    return '''
000000000000000000000000088888800000000000000000000000000000000000aaaaa0000aaa000000a0000007707770077700000060000000600000060000000000000888888008888880888888880888888008888800000000000888888000a000a0000a0a000000a0000777777677777770000060000000600000060000
000000008888888888888888888ffff888888888888888800888888088f1ff1800a909a0000a0a000000a000776666666776777700060000000060000006000000000000888ffff8888ffff888f1ff18888ffff88ffff8808888888888fffff8009aaa900009a9000000a0007677766676666677000600000000600000060000
0000000088f1ff1888f1ff1808fffff088f1ff1881ff1f80888ffff888fffff80000a0000000a0000000a00000000000000000000006000000060000000060000000000008fffff008fffff00033330008fffff00fffff8088fffff8083333800099a0000009a0000000a0000000000000000000000600000006000000006000
00000000003333000033330007000070073333000033337008f1ff10003333000009a0000000a0000000a0000000000000000000000060000006000000006000000000000070070000700070000000000000070000007000077333700070070000aaa0000009a0000000a0000000000000000000000060000006000000006000
555555550000000000000000000000000000000000000000008888004999999449999994499909940300b0b0666566650300b0b000000000000000007000000055555555000000000000000000000000000000000000000008888880911111199111411991140919003b330067656765003b3300007700000770070007000007
550000550000000000000000000000000aaaaaa0000000000878888091111119911191194940041902888820677067700288882000777070077700000000000055000055007000700499994000000000a998888a1111111108888880911111199494041900000044089888800700070078988887077777700770000000000000
55000055007000700050050000000000a988888a100000010888888091111119911409499400000008888980070007007888898707777770000070000000000055000055067706770005500000000000aaaaaaaa1111111108888880911111199111911991400499088988800000000008898880077777700000077000000000
55555555567656760050050000000000a980088a144444410088880091111119911411199140411902888820000000000288882007077700000707700700007055555555566656660005500004999940a988888a1444444100000000499999944999999444004994002882000000000000288200000000007000000000000000
5777777557777777777777777777777577cccccccccccccccccccc7757777775555555555555555555555555550000000777777000000000000000000000000077777777777777777777777777777777777cccccccccccccccccc777777777775555555555555550055555556670000077777777000777770000000000000000
777c77777777ccccc777777ccccc7777777cccccccccccccccccc77777777777555555555555550000555555677770007777777700776670000000000000000077cccc77777cccccccc77cccccccc7777777cccccccccccccccc7777777cc7775555555555555000000555556660000077773377076777000000000000000000
77cccc7777cccccccccccccccccccc777777cccccccccccccccc777777cccc775555555555550000000055555500000077773377077660000777770000000000777cc77777cc77ccccccccccccc7cc77777cccccccccccccccccc77777cccc775555555555500000000005556670000073773337077770000777767007700000
7777777777cc77cccccccccccccccc77777cccccccccccccccccc77777c7cc77555555555500000000000055677770007333bb370000000000000077007777705777777577cccccccccccccccccccc7777cccccccccccccccccccc7777cccc77555555555000000000000005666000000333bb30000000000000000000077777
77cccc7777cccccccccccccccccccc77577777777777777777777775777ccc775555555550000000000000050000066603333330000000000000000000000000777ccc7777cccccccccccccccccccc77777777777777777777777777777cc7775055555555000000000000550007777603b333300000000000ee0ee000000000
777ccc7777cc7cccccccccccc77ccc777777ccc7777777777ccc7777777cc77755550055555000000000055500000766033333300000000000eeeee00000003077ccc77777ccccccccccccccc77ccc77777ccccc7c7777ccccccc77777ccc777555500555555000000005555000000550333b33000000000000e8e00000000b0
77ccc777777cccccccc77cccccccc777777ccccccc7777c7ccccc77777cccc7755555555555550000005555500000666003333000000b00000eeeee000000b30777cc7777777ccccc777777ccccc77777777ccc7777777777ccc777777cccc775505555555555500005555550007777600044000000b000000ee3ee003000b00
777cc777777777777777777777777777777777777777777777777777777cc7775555555555555550055555550000076600044000030b00300000b00000b0b30077cccc77577777777777777777777775577777777777777777777775577777755555555555555555555555550000005500999900030330300000b00000303300
5777755777577775077777777777777777777770077777700000000000000000cccccccc000000000000000000000000000000000000000000000000000000007777777777777777700007770000777000007777700077770000000000000000c77ccccc00000000000000000000000000000000000000000000000000000000
7777cc7777cc777770cc777cccc777ccccc7770770c777070000000000000000c77cc7cc00000000000000000000000000000000000000000000000000000000777cccccccccc77770c777cccc777ccccc777c0770777c070000000000000000cccccccc00000000000000000000000000006000000000000000000000000000
77cccccccccccc77707770000777000007770007777700070002eeeeeeee2000cccccccc0000000000000000000000000006060000000000000000000000000057cc77ccccc7cc7577770000777000007770000777700007002eeeeeeeeee200cc7ccccc00000000000000000000000000d00060000000000000000000000000
577c77ccccccc7757000000000000000000c000770000c0700eeeeeeeeeeee00ccccc7cc0000000000000000000000000d00000c000000000000000000000000777cccccccccc7777000000000000000000000077000000700e22222e2e22e00cccccccc000000000000000000000000d000000c000000000000000000000000
777cccccccccc7777000000000000000000000077000000700eeeeeeeeeeee000000000000000000000000000000000c0000000c000600000000000000000000577cccccccccc7777000000c000000000000000770cc000700e22e2222e22e00000000000000000000000000000000d000000000c060d0000000000000000000
57cc7cccc77ccc7570000000000cc0000000000770cc000700eeeeeeeeeeee0000000000000000000000000000000c00000000000d000d00000000000000000077ccccccc77ccc7770c00000000cc00000000c0770000c0700eee222e22eee0000000000000000000000000000000c0000000000000000000000000000000000
777cccccccccc7777000000000000000000000077000000700eeeeeeeeeeee005555555506666600666666006600c000666666000666660066666600666666007777cc7777cc777770000000000000000000000770c0000700eeeeeeeeeeee00555555556666666066666660660c000066666660666666606666666066666660
777777777777777770000000c0000000000000077000000700ee77eee7777e00555555556600066066000000660000006600000066000000006600006600000057777577775577757000000000000000000000077000c007077777777777777055555555dd000000dddd0000dd000000dddd0000ddddddd000dd0000dddd0000
000000000000000070000000000000000000000770000007007777005000000000000005dd000dd0dd000000dd0000d0dd000000000000d000dd0000dd00000000aaaaaaaaaaaa00700000000000000000000007700c0007070000705500000000000055ddddddd0dddddd00ddddddd0dddddd00ddddddd000dd0000dddddd00
0a999999999999a0700000000000c00000000007700000077077000755500000000005550ddddd00ddddddd0ddddddd0ddddddd00ddddd0000dd0000ddddddd0a99aaaaaaaaaa99a7000000cc0000000000000077000cc077077bb07555500000000555500000000000000000000000000000000000000000000000000000000
a9aaaaaaaaaaaa9a7000000cc0000000000c00077000cc07700bbb0755555555555555550000000000000c000000000000000000000000000000c00000000000a99999999999999a70c00000000000000000000770c00007700bbb075555555555555555000000000000c00000000000000000000000000000000c0000000000
a99999999999999a700000000000000000000007700000070700007055555555555555550000000000cc0000000000000000000000000000000000c000000000a99999999999999a07777777777777777777777007777770007777005555555555555555000000000c000000000000000000000000000000000000c000000000
aaaaaaaaaaaaaaaa07777777777777777777777007777770004bbb00004b000000400bbb00000000c0000000000000000000000000000000000000c000000000a49494a11a49494a70007770000077700000777770007777004bbbbb004bb000004bbbbb0000000100000000000000000000000000000000000000c00c000000
a494a4a11a4a494a70c777ccccc777ccccc7770770c7770704200bbb042bbbbb042bbb00000000c0000000000000000000000000000000000000001010c00000a49444aaaa44494a70777ccccc777ccccc777c0770777c07040000000400bbb004000000000001000000000000000000000000000000000000000001000c0000
a49999aaaa99994a7777000007770000077700077777000704000000040000000400000000000100000000000000000000000000000000000000000000010000a49444999944494a77700000777000007770000777700c0742000000420000004200000000000100000000000000000000000000000000000000000000001000
a494a444444a494a7000000000000000000000077000000740000000400000004000000000000000000000000000000000000000000000000000000000000000a49499999999494a0777777777777777777777700777777040000000400000004000000000010000000000000000000000000000000000000000000000000010
00000000000000008242525252528452339200001323232352232323232352230000000000000000b302000013232352526200a282834252522323232323232300000000000000a20182920013232352363636462535353545550000005525355284525262b20000000000004252525262828282425284525252845252525252
00000000000085868242845252525252b1006100b1b1b1b103b1b1b1b1b103b100000000000000111102000000a282425233000000a213233300009200008392000000000000110000a2000000a28213000000002636363646550000005525355252528462b2a300000000004252845262828382132323232323232352528452
000000000000a201821323525284525200000000000000007300000000007300000000000000b343536300410000011362b2000000000000000000000000a2000000000000b302b2002100000000a282000000000000000000560000005526365252522333b28292001111024252525262019200829200000000a28213525252
0000000000000000a2828242525252840000000000000000b10000000000b1000000000000000000b3435363930000b162273737373737373737374711000061000000110000b100b302b20000006182000000000000000000000000005600005252338282828201a31222225252525262820000a20011111100008283425252
0000000000000093a382824252525252000061000011000000000011000000001100000000000000000000020182001152222222222222222222222232b200000000b302b200000000b10000000000a200000000000000009300000000000000846282828283828282132323528452526292000000112434440000a282425284
00000000000000a2828382428452525200000000b302b2936100b302b20061007293a30000000000000000b1a282931252845252525252232323232362b20000000000b10000001100000000000000000000000093000086820000a3000000005262828201a200a282829200132323236211111111243535450000b312525252
00000000000000008282821323232323820000a300b1a382930000b100000000738283931100000000000011a382821323232323528462829200a20173b20061000000000000b302b2000061000000000000a385828286828282828293000000526283829200000000a20000000000005222222232263636460000b342525252
00000011111111a3828201b1b1b1b1b182938282930082820000000000000000b100a282721100000000b372828283b12222223213233361000086920000000000100000000000b1000000000000000086938282828201920000a20182a37686526282829300000000000000000000005252845252328283920000b342845252
00008612222232828382829300000000828282828283829200000000000061001100a382737200000000b373a2829211525284628382a2000000a2000000000000021111111111111111111111110061828282a28382820000000000828282825262829200000000000000000000000052525252526201a2000000b342525252
00000113235252225353536300000000828300a282828201939300001100000072828292b1039300000000b100a282125223526292000000000000a3000000000043535353535353535353535363b2008282920082829200061600a3828382a28462000000000000000000000000000052845252526292000011111142525252
0000a28282132362b1b1b1b1000000009200000000a28282828293b372b2000073820100110382a30000001100828213621013336100000000000082930000000002828382828202828282828272b20083820000a282d3000717f38282920000526200000000000093000000000000005252525284620000b312223213528452
000000828392b30300000000002100000000000000000082828282b303b20000b1a282837203820193000072a38292b16271000000000000930000838200000000b1a282820182b1a28283a28273b200828293000082122232122232820000a3233300000000000082920000000000002323232323330000b342525232135252
000000a28200b37300000000a37200000010000000111111118283b373b200a300008282730392008283007382830011629300000000000082000082829200000000009261a28200008261008282000001920000000213233342846282243434000000000000000082000085860000008382829200000000b342528452321323
0000100082000082000000a2820300002222321111125353630182829200008300009200b1030000a28200008282001262829200000000a3829200828200000000858600008282a3828293008292610082001000001222222252525232253535000000f3100000a3820000a2010000008292000000009300b342525252522222
0400122232b200839321008683039300528452222262c000a28282820000a38210000000a3738000008293008292001362820000000000828300a3820100000000a282828292a2828283828282000000343434344442528452525252622535350000001263000083829300008200c1008210d3e300a38200b342525252845252
1232425262b28682827282820103820052525252846200000082829200008282320000008382930000a28201820000b1628393000000008282008282829300000000008382000000a28201820000000035353535454252525252528462253535000000032444008282820000829300002222223201828393b342525252525252
525252525262b2b1b1b1132323526200845223232323232352522323233382825252525252525252525284522333b2822323232323526282820000b34252525252845252525252848452525262838242528452522333828292425223232352520000000000000000000000000000000000000000000000000000000000000000
525252845262b2000000b1b1b142620023338276000000824233b2a282018283525252845252232323235262b1b10083921000a382426283920000b3422323232323232323232323232323526201821352522333b1b1018241133383828242840000000000000000000000000000000000000000000000000000000000000000
525252525262b20000000000a242627682828392000011a273b200a382729200525252525233b1b1b1b11333000000825353536382426282410000b30382a2a2a1829200a2828382820182426200a2835262b1b10000831232b2000080014252000000000000a300000000000000000000000000000000000000000000000000
528452232333b20000001100824262928201a20000b3720092000000830300002323525262b200000000b3720000a382828283828242522232b200b373928000000100110092a2829211a2133300a3825262b2000000a21333b20000868242520000000000000100009300000000000000000000000000000000000000000000
525262122232b200a37672b2a24262838292000000b30300000000a3820300002232132333b200000000b303829300a2838292019242845262b200000000000000a2b302b2a36182b302b200110000825262b200000000b1b10000a283a2425200000000a30082000083000000000000000000000094a4b4c4d4e4f400000000
525262428462b200a28303b2214262928300000000b3030000000000a203e3415252222232b200000000b30392000000829200000042525262b2000000000000000000b100a2828200b100b302b211a25262b200000000000000000092b3428400000000827682000001009300000000000000000095a5b5c5d5e5f500000000
232333132362b221008203b2711333008293858693b3031111111111114222225252845262b200001100b303b2000000821111111142528462b2000000000000000000000000110176851100b1b3026184621111111100000061000000b3135200000000828382670082768200000000000000000096a6b6c6d6e6f600000000
82000000a203117200a203b200010193828283824353235353535353535252845252525262b200b37200b303b2000000824353535323235262b20000110000000000000000b30282828372b26100b100525232122232b200000000000000b14200000000a28282123282839200000000000000000097a7b7c7d7e7f700000000
9200110000135362b2001353535353539200a2000001828282829200b34252522323232362b261b30300b3030000000092b1b1b1b1b1b34262b200b372b20000001100000000b1a2828273b200000000232333132333b200001111000000b342000000868382125252328293a300000000000000000000000000000000000000
00b372b200a28303b2000000a28293b3000000000000a2828382827612525252b1b1b1b173b200b30393b30361000000000000000000b34262b271b303b20000b302b211000000110092b100000000a3b1b1b1b1b1b10011111232110000b342000000a282125284525232828386000000000000000000000000000000000000
80b303b20000820311111111008283b311111111110000829200928242528452000000a3820000b30382b37300000000000000000000b3426211111103b2000000b1b302b200b372b200000000000082b21000000000b31222522363b200b3138585868292425252525262018282860000000000000000000000000000000000
00b373b20000a21353535363008292b32222222232111102b20000a21323525200000001839200b3038282820000000011111111930011425222222233b20000100000b10000b303b200000000858682b27100000000b3425233b1b1000000b182018283001323525284629200a2820000000000000000000000000000000000
9300b100000000b1b1b1b1b100a200b323232323235363b100000000b1b1135200000000820000b30382839200000000222222328283432323232333b2000000329300000000b373b200000000a20182111111110000b31333b100a30061000000a28293f3123242522333020000820000000000000000000000000000000000
829200001000410000000000000000b39310d30000a28200000000000000824200000086827600b30300a282760000005252526200828200a30182a2006100a362820000000000b100000093a382838222222232b20000b1b1000083000000860000122222526213331222328293827600000000000000000000000000000000
017685a31222321111111111002100b322223293000182930000000080a301131000a383829200b373000083920000005284526200a28282828392000000008262839321000000000000a3828282820152845262b261000093000082a300a3821000135252845222225252523201838200000000000000000000000000000000
828382824252522222222232007100b352526282a38283820000000000838282320001828200000083000082010000005252526271718283820000000000a382628201729300000000a282828382828252528462b20000a38300a382018283821222324252525252525284525222223200000000000000000000000000000000
'''.replace('\n', '')

  @property
  def map_data(self):
    return '''
2331252548252532323232323300002425262425252631323232252628282824252525252525323328382828312525253232323233000000313232323232323232330000002432323233313232322525252525482525252525252526282824252548252525262828282824254825252526282828283132323225482525252525
252331323232332900002829000000242526313232332828002824262a102824254825252526002a2828292810244825282828290000000028282900000000002810000000372829000000002a2831482525252525482525323232332828242525254825323338282a283132252548252628382828282a2a2831323232322525
252523201028380000002a0000003d24252523201028292900282426003a382425252548253300002900002a0031252528382900003a676838280000000000003828393e003a2800000000000028002425253232323232332122222328282425252532332828282900002a283132252526282828282900002a28282838282448
3232332828282900000000003f2020244825262828290000002a243300002a2425322525260000000000000000003125290000000021222328280000000000002a2828343536290000000000002839242526212223202123313232332828242548262b000000000000001c00003b242526282828000000000028282828282425
2340283828293a2839000000343522252548262900000000000030000000002433003125333d3f00000000000000003100001c3a3a31252620283900000000000010282828290000000011113a2828313233242526103133202828282838242525262b000000000000000000003b2425262a2828670016002a28283828282425
263a282828102829000000000000312525323300000000110000370000003e2400000037212223000000000000000000395868282828242628290000000000002a2828290000000000002123283828292828313233282829002a002a2828242525332b0c00000011110000000c3b314826112810000000006828282828282425
252235353628280000000000003a282426003d003a3900270000000000002125001a000024252611111111000000002c28382828283831332800000017170000002a000000001111000024261028290028281b1b1b282800000000002a2125482628390000003b34362b000000002824252328283a67003a28282829002a3132
25333828282900000000000000283824252320201029003039000000005824480000003a31323235353536675800003c282828281028212329000000000000000000000000003436003a2426282800003828390000002a29000000000031323226101000000000282839000000002a2425332828283800282828390000001700
2600002a28000000003a283a2828282425252223283900372858390068283132000000282828282820202828283921222829002a28282426000000000000000000000000000020382828312523000000282828290000000000163a67682828003338280b00000010382800000b00003133282828282868282828280000001700
330000002867580000281028283422252525482628286720282828382828212200003a283828102900002a28382824252a0000002838242600000017170000000000000000002728282a283133390000282900000000000000002a28282829002a2839000000002a282900000000000028282838282828282828290000000000
0000003a2828383e3a2828283828242548252526002a282729002a28283432250000002a282828000000002810282425000000002a282426000000000000000000000000000037280000002a28283900280000003928390000000000282800000028290000002a2828000000000000002a282828281028282828675800000000
0000002838282821232800002a28242532322526003a2830000000002a28282400000000002a281111111128282824480000003a28283133000000000000171700013f0000002029000000003828000028013a28281028580000003a28290000002a280c0000003a380c00000000000c00002a2828282828292828290000003a
00013a2123282a313329001111112425002831263a3829300000000000002a310000000000002834222236292a0024253e013a3828292a00000000000000000035353536000020000000003d2a28671422222328282828283900582838283d00003a290000000028280000000000000000002a28282a29000058100012002a28
22222225262900212311112122222525002a3837282900301111110000003a2800013f0000002a282426290000002425222222232900000000000000171700002a282039003a2000003a003435353535252525222222232828282810282821220b10000000000b28100000000b0000002c00002838000000002a283917000028
2548252526111124252222252525482500012a2828673f242222230000003828222223000012002a24260000001224252525252600000000171700000000000000382028392827080028676820282828254825252525262a28282122222225253a28013d0000006828390000000000003c0168282800171717003a2800003a28
25252525252222252525252525252525222222222222222525482667586828282548260000270000242600000021252525254826171700000000000000000000002a2028102830003a282828202828282525252548252600002a2425252548252821222300000028282800000000000022222223286700000000282839002838
2532330000002432323232323232252525252628282828242532323232254825253232323232323225262828282448252525253300000000000000000000005225253232323233313232323233282900262829286700000000002828313232322525253233282800312525482525254825254826283828313232323232322548
26282800000030402a282828282824252548262838282831333828290031322526280000163a28283133282838242525482526000000000000000000000000522526000016000000002a10282838390026281a3820393d000000002a3828282825252628282829003b2425323232323232323233282828282828102828203125
3328390000003700002a3828002a2425252526282828282028292a0000002a313328111111282828000028002a312525252526000000000000000000000000522526000000001111000000292a28290026283a2820102011111121222328281025252628382800003b24262b002a2a38282828282829002a2800282838282831
28281029000000000000282839002448252526282900282067000000000000003810212223283829003a1029002a242532323367000000000000000000004200252639000000212300000000002122222522222321222321222324482628282832323328282800003b31332b00000028102829000000000029002a2828282900
2828280016000000162a2828280024252525262700002a2029000000000000002834252533292a0000002a00111124252223282800002c46472c00000042535325262800003a242600001600002425252525482631323331323324252620283822222328292867000028290000000000283800111100001200000028292a1600
283828000000000000003a28290024254825263700000029000000000000003a293b2426283900000000003b212225252526382867003c56573c4243435363633233283900282426111111111124252525482526201b1b1b1b1b24252628282825252600002a28143a2900000000000028293b21230000170000112867000000
2828286758000000586828380000313232323320000000000000000000272828003b2426290000000000003b312548252533282828392122222352535364000029002a28382831323535353522254825252525252300000000003132332810284825261111113435361111111100000000003b3133111111111127282900003b
2828282810290000002a28286700002835353536111100000000000011302838003b3133000000000000002a28313225262a282810282425252662636400000000160028282829000000000031322525252525252667580000002000002a28282525323535352222222222353639000000003b34353535353536303800000017
282900002a0000000000382a29003a282828283436200000000000002030282800002a29000011110000000028282831260029002a282448252523000000000039003a282900000000000000002831322525482526382900000017000058682832331028293b2448252526282828000000003b201b1b1b1b1b1b302800000017
283a0000000000000000280000002828283810292a000000000000002a3710281111111111112136000000002a28380b2600000000212525252526001c0000002828281000000000001100002a382829252525252628000000001700002a212228282908003b242525482628282912000000001b00000000000030290000003b
3829000000000000003a102900002838282828000000000000000000002a2828223535353535330000000000002828393300000000313225252533000000000028382829000000003b202b00682828003232323233290000000000000000312528280000003b3132322526382800170000000000000000110000370000000000
290000000000000000002a000000282928292a0000000000000000000000282a332838282829000000000000001028280000000042434424252628390000000028002a0000110000001b002a2010292c1b1b1b1b0000000000000000000010312829160000001b1b1b313328106700000000001100003a2700001b0000000000
00000100000011111100000000002a3a2a0000000000000000000000002a2800282829002a000000000000000028282800000000525354244826282800000000290000003b202b39000000002900003c000000000000000000000000000028282800000000000000001b1b2a2829000001000027390038300000000000000000
1111201111112122230000001212002a00010000000000000000000000002900290000000000000000002a6768282900003f01005253542425262810673a3900013f0000002a3829001100000000002101000000000000003a67000000002a382867586800000100000000682800000021230037282928300000000000000000
22222222222324482611111120201111002739000017170000001717000000000001000000001717000000282838393a0021222352535424253328282838290022232b00000828393b27000000001424230000001200000028290000000000282828102867001717171717282839000031333927101228370000000000000000
254825252526242526212222222222223a303800000000000000000000000000001717000000000000003a28282828280024252652535424262828282828283925262b00003a28103b30000000212225260000002700003a28000000000000282838282828390000005868283828000022233830281728270000000000000000
00000000000000008242525252528452339200001323232352232323232352230000000000000000b302000013232352526200a2828342525223232323232323
00000000000000a20182920013232352363636462535353545550000005525355284525262b20000000000004252525262828282425284525252845252525252
00000000000085868242845252525252b1006100b1b1b1b103b1b1b1b1b103b100000000000000111102000000a282425233000000a213233300009200008392
000000000000110000a2000000a28213000000002636363646550000005525355252528462b2a300000000004252845262828382132323232323232352528452
000000000000a201821323525284525200000000000000007300000000007300000000000000b343536300410000011362b2000000000000000000000000a200
0000000000b302b2002100000000a282000000000000000000560000005526365252522333b28292001111024252525262019200829200000000a28213525252
0000000000000000a2828242525252840000000000000000b10000000000b1000000000000000000b3435363930000b162273737373737373737374711000061
000000110000b100b302b20000006182000000000000000000000000005600005252338282828201a31222225252525262820000a20011111100008283425252
0000000000000093a382824252525252000061000011000000000011000000001100000000000000000000020182001152222222222222222222222232b20000
0000b302b200000000b10000000000a200000000000000009300000000000000846282828283828282132323528452526292000000112434440000a282425284
00000000000000a2828382428452525200000000b302b2936100b302b20061007293a30000000000000000b1a282931252845252525252232323232362b20000
000000b10000001100000000000000000000000093000086820000a3000000005262828201a200a282829200132323236211111111243535450000b312525252
00000000000000008282821323232323820000a300b1a382930000b100000000738283931100000000000011a382821323232323528462829200a20173b20061
000000000000b302b2000061000000000000a385828286828282828293000000526283829200000000a20000000000005222222232263636460000b342525252
00000011111111a3828201b1b1b1b1b182938282930082820000000000000000b100a282721100000000b372828283b122222232132333610000869200000000
00100000000000b1000000000000000086938282828201920000a20182a37686526282829300000000000000000000005252845252328283920000b342845252
00008612222232828382829300000000828282828283829200000000000061001100a382737200000000b373a2829211525284628382a2000000a20000000000
00021111111111111111111111110061828282a28382820000000000828282825262829200000000000000000000000052525252526201a2000000b342525252
00000113235252225353536300000000828300a282828201939300001100000072828292b1039300000000b100a282125223526292000000000000a300000000
0043535353535353535353535363b2008282920082829200061600a3828382a28462000000000000000000000000000052845252526292000011111142525252
0000a28282132362b1b1b1b1000000009200000000a28282828293b372b2000073820100110382a3000000110082821362101333610000000000008293000000
0002828382828202828282828272b20083820000a282d3000717f38282920000526200000000000093000000000000005252525284620000b312223213528452
000000828392b30300000000002100000000000000000082828282b303b20000b1a282837203820193000072a38292b162710000000000009300008382000000
00b1a282820182b1a28283a28273b200828293000082122232122232820000a3233300000000000082920000000000002323232323330000b342525232135252
000000a28200b37300000000a37200000010000000111111118283b373b200a30000828273039200828300738283001162930000000000008200008282920000
0000009261a28200008261008282000001920000000213233342846282243434000000000000000082000085860000008382829200000000b342528452321323
0000100082000082000000a2820300002222321111125353630182829200008300009200b1030000a28200008282001262829200000000a38292008282000000
00858600008282a3828293008292610082001000001222222252525232253535000000f3100000a3820000a2010000008292000000009300b342525252522222
0400122232b200839321008683039300528452222262c000a28282820000a38210000000a3738000008293008292001362820000000000828300a38201000000
00a282828292a2828283828282000000343434344442528452525252622535350000001263000083829300008200c1008210d3e300a38200b342525252845252
1232425262b28682827282820103820052525252846200000082829200008282320000008382930000a28201820000b162839300000000828200828282930000
0000008382000000a28201820000000035353535454252525252528462253535000000032444008282820000829300002222223201828393b342525252525252
525252525262b2b1b1b1132323526200845223232323232352522323233382825252525252525252525284522333b2822323232323526282820000b342525252
52845252525252848452525262838242528452522333828292425223232352520000000000000000000000000000000000000000000000000000000000000000
525252845262b2000000b1b1b142620023338276000000824233b2a282018283525252845252232323235262b1b10083921000a382426283920000b342232323
2323232323232323232323526201821352522333b1b1018241133383828242840000000000000000000000000000000000000000000000000000000000000000
525252525262b20000000000a242627682828392000011a273b200a382729200525252525233b1b1b1b11333000000825353536382426282410000b30382a2a2
a1829200a2828382820182426200a2835262b1b10000831232b2000080014252000000000000a300000000000000000000000000000000000000000000000000
528452232333b20000001100824262928201a20000b3720092000000830300002323525262b200000000b3720000a382828283828242522232b200b373928000
000100110092a2829211a2133300a3825262b2000000a21333b20000868242520000000000000100009300000000000000000000000000000000000000000000
525262122232b200a37672b2a24262838292000000b30300000000a3820300002232132333b200000000b303829300a2838292019242845262b2000000000000
00a2b302b2a36182b302b200110000825262b200000000b1b10000a283a2425200000000a30082000083000000000000000000000094a4b4c4d4e4f400000000
525262428462b200a28303b2214262928300000000b3030000000000a203e3415252222232b200000000b30392000000829200000042525262b2000000000000
000000b100a2828200b100b302b211a25262b200000000000000000092b3428400000000827682000001009300000000000000000095a5b5c5d5e5f500000000
232333132362b221008203b2711333008293858693b3031111111111114222225252845262b200001100b303b2000000821111111142528462b2000000000000
000000000000110176851100b1b3026184621111111100000061000000b3135200000000828382670082768200000000000000000096a6b6c6d6e6f600000000
82000000a203117200a203b200010193828283824353235353535353535252845252525262b200b37200b303b2000000824353535323235262b2000011000000
0000000000b30282828372b26100b100525232122232b200000000000000b14200000000a28282123282839200000000000000000097a7b7c7d7e7f700000000
9200110000135362b2001353535353539200a2000001828282829200b34252522323232362b261b30300b3030000000092b1b1b1b1b1b34262b200b372b20000
001100000000b1a2828273b200000000232333132333b200001111000000b342000000868382125252328293a300000000000000000000000000000000000000
00b372b200a28303b2000000a28293b3000000000000a2828382827612525252b1b1b1b173b200b30393b30361000000000000000000b34262b271b303b20000
b302b211000000110092b100000000a3b1b1b1b1b1b10011111232110000b342000000a282125284525232828386000000000000000000000000000000000000
80b303b20000820311111111008283b311111111110000829200928242528452000000a3820000b30382b37300000000000000000000b3426211111103b20000
00b1b302b200b372b200000000000082b21000000000b31222522363b200b3138585868292425252525262018282860000000000000000000000000000000000
00b373b20000a21353535363008292b32222222232111102b20000a21323525200000001839200b3038282820000000011111111930011425222222233b20000
100000b10000b303b200000000858682b27100000000b3425233b1b1000000b182018283001323525284629200a2820000000000000000000000000000000000
9300b100000000b1b1b1b1b100a200b323232323235363b100000000b1b1135200000000820000b30382839200000000222222328283432323232333b2000000
329300000000b373b200000000a20182111111110000b31333b100a30061000000a28293f3123242522333020000820000000000000000000000000000000000
829200001000410000000000000000b39310d30000a28200000000000000824200000086827600b30300a282760000005252526200828200a30182a2006100a3
62820000000000b100000093a382838222222232b20000b1b1000083000000860000122222526213331222328293827600000000000000000000000000000000
017685a31222321111111111002100b322223293000182930000000080a301131000a383829200b373000083920000005284526200a282828283920000000082
62839321000000000000a3828282820152845262b261000093000082a300a3821000135252845222225252523201838200000000000000000000000000000000
828382824252522222222232007100b352526282a38283820000000000838282320001828200000083000082010000005252526271718283820000000000a382
628201729300000000a282828382828252528462b20000a38300a382018283821222324252525252525284525222223200000000000000000000000000000000
'''.replace('\n', '')

  @property
  def flag_data(self):
    return '''
0000000000000000000000000000000004020000000000000000000200000000030303030303030304040402020000000303030303030303040404020202020200001313131302020302020202020002000013131313020204020202020202020000131313130004040202020202020200001313131300000002020202020202
0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
'''.replace('\n', '')

  def __str__(self):
    spikes = {17: 'ʌʌ', 27: 'vv', 43: '> ', 59: ' <'}
    objs = {
      self.spring: 'ΞΞ',
      self.fall_floor: '▒▒',
      self.balloon: '()',
      self.key: '¤¬',
      self.chest: '╔╗',
      self.fruit: '{}',
      self.fly_fruit: '{}',
      self.fake_wall: '▓▓',
      self.platform: 'oo',
      self.player: ':D',
      self.player_spawn: ':D'
    }
    # init map
    map_str = (['  '] * 16 + ['\n']) * 16
    # draw walls and spikes
    for tx in range(16):
      for ty in range(16):
        pos = tx + 17 * ty
        tile = self.p8.mget(self.room.x * 16 + tx, self.room.y * 16 + ty)
        if self.p8.fget(tile, 4):
          map_str[pos] = '░░'
        elif self.p8.fget(tile, 0):
          map_str[pos] = '██'
        elif tile in spikes:
          map_str[pos] = spikes[tile]
    # draw objects
    for o in self.objects:
      if type(o) in objs:
        if o.spr == 0: continue # suppress
        ox, oy = round(o.x / 8), round(o.y / 8)
        pos = ox + 17 * oy
        if ox >= 0 and ox <= 15 and oy >= 0 and oy <= 15:
          map_str[pos] = objs[type(o)]
          # draw bigger objs (e.g., clouds)
          if type(o) == self.platform and ox + 1 <= 15:
            map_str[pos + 1] = objs[type(o)]
          elif type(o) == self.fly_fruit:
            if ox - 1 >= 0: map_str[pos - 1] = ' »'
            if ox + 1 <= 15: map_str[pos + 1] = '« '
          elif type(o) == self.fake_wall:
            if ox + 1 <= 15: map_str[pos + 1] = objs[type(o)]
            if oy + 1 <= 15: map_str[pos + 17] = objs[type(o)]
            if ox + 1 <= 15 and oy + 1 <= 15: map_str[pos + 18] = objs[type(o)]
    return ''.join(map_str)
