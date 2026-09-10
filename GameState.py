import copy
import json


'''
A GameState is an independent snapshot of a game's state.

It holds plain data (room, objects, game-wide values) and does not reference
the game or the console it was taken from, so it can be copied, compared,
written to a file and loaded back into the same - or another - game instance:

  state = p8.get_state()    # snapshot
  p8.set_state(state)       # restore

  p8.save_state('100m.json')
  p8.load_state('100m.json')

Button presses are not part of a state: inputs are given per step, not stored.
'''

FORMAT_VERSION = 1


class GameState():
  def __init__(self, room, objects, attrs):
    self.room = list(room) # room position, e.g. (0, 0) for 100m
    self.objects = list(objects) # [{'type': str, 'attrs': {...}}, ...]
    self.attrs = dict(attrs) # game-wide values (frames, freeze, ...)

  def copy(self):
    return copy.deepcopy(self)

  def to_dict(self):
    return {
      'version': FORMAT_VERSION,
      'room': [int(x) for x in self.room],
      'objects': copy.deepcopy(self.objects),
      'attrs': copy.deepcopy(self.attrs)
    }

  @classmethod
  def from_dict(cls, data):
    if data.get('version', FORMAT_VERSION) != FORMAT_VERSION:
      raise ValueError(f"unsupported game state version: {data.get('version')}")
    return cls(data['room'], data['objects'], data['attrs'])

  # text / file representation

  def to_json(self):
    return json.dumps(self.to_dict())

  @classmethod
  def from_json(cls, text):
    return cls.from_dict(json.loads(text))

  def save(self, path):
    with open(path, 'w') as f:
      f.write(self.to_json())
    return path

  @classmethod
  def load(cls, path):
    with open(path) as f:
      return cls.from_json(f.read())

  # comparison / debug

  def __eq__(self, other):
    return isinstance(other, GameState) and self.to_dict() == other.to_dict()

  def __repr__(self):
    return f'[GameState] room: {tuple(self.room)}, objects: {len(self.objects)}, attrs: {sorted(self.attrs)}'


# attribute (de)serialization
#
# Attribute values are numbers, strings, booleans, lists, dicts or small
# helper objects (e.g. Celeste's Vector/Rect). Helper objects are stored as
# {'__type__': name, 'fields': {...}} and rebuilt through the game's registry
# of known types (see Celeste.set_state).

def encode_value(value):
  if value is None or isinstance(value, (bool, int, float, str)):
    return value
  if isinstance(value, (list, tuple)):
    return [encode_value(v) for v in value]
  if isinstance(value, dict):
    return {k: encode_value(v) for k, v in value.items()}
  return {'__type__': type(value).__name__, 'fields': encode_value(vars(value))}


def decode_value(value, registry):
  if isinstance(value, list):
    return [decode_value(v, registry) for v in value]
  if isinstance(value, dict):
    if '__type__' in value:
      cls = registry[value['__type__']]
      obj = cls.__new__(cls)
      for key, field in value['fields'].items():
        setattr(obj, key, decode_value(field, registry))
      return obj
    return {k: decode_value(v, registry) for k, v in value.items()}
  return value


def encode_attrs(attrs, skip=()):
  return {k: encode_value(v) for k, v in attrs.items() if k not in skip}


def decode_attrs(attrs, registry):
  return {k: decode_value(v, registry) for k, v in attrs.items()}
