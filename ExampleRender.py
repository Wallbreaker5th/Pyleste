if __name__ == '__main__':
  import os

  # import PICO-8 emulator and Celeste
  from PICO8 import PICO8
  from Carts.Celeste import Celeste

  # useful Celeste utils
  import CelesteUtils as utils

  os.makedirs('renders', exist_ok=True)
  os.makedirs('saves', exist_ok=True)

  # create a PICO-8 instance with Celeste loaded
  p8 = PICO8(Celeste)
  utils.load_room(p8, 0) # load 100m
  utils.skip_player_spawn(p8)

  # render the current state, 4x scale
  p8.save_render('renders/100m.png', scale=4)
  before = p8.render_png()

  # save the state, then walk right for 20 frames
  state = p8.get_state()
  p8.save_state('saves/100m.json')
  p8.set_inputs(r=True, x=True)
  for f in range(20):
    p8.step()
  p8.save_render('renders/100m_walk.png', scale=4)

  # load the state back and render again - this is the same picture as before
  p8.load_state('saves/100m.json')
  p8.save_render('renders/100m_restored.png', scale=4)

  print(state)
  print(f"same image after loading the state back: {p8.render_png() == before}")
