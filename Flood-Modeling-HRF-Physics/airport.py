# FIX: These two lines force a compatible graphics mode for macOS
from panda3d.core import loadPrcFileData
loadPrcFileData('', 'gl-version 2 1')

# --- Main Application Code ---
from ursina import *

app = Ursina()

# --- Create the Airport Environment ---
ground = Entity(model='plane', scale=500, color=color.rgb(100, 120, 100), texture='white_cube', texture_scale=(100,100))
runway = Entity(model='cube', scale=(200, 0.1, 10), color=color.dark_gray, position=(0, 0.1, 0), collider='box')
shed_1 = Entity(model='cube', scale=(30, 10, 20), position=(-60, 5, 40), color=color.light_gray, texture='white_cube')
plane = Entity(position=(30, 1.2, 5), rotation_y=120)

# --- Build the Plane ---
Entity(parent=plane, model='cube', scale=(20, 2, 3), color=color.white) # Fuselage
Entity(parent=plane, model='cube', scale=(4, 0.5, 18), color=color.azure) # Wings
Entity(parent=plane, model='cube', scale=(2, 2.5, 1), position=(-9, 1.5, 0), color=color.azure) # Tail

# --- Lighting, Sky, and Controls ---
Sky()
EditorCamera()
PointLight(parent=camera, position=(0, 20, -10), color=color.white) # Add a light source
AmbientLight(color=color.rgba(100, 100, 100, 0.2)) # Add ambient light

app.run()