import bpy
import gpu
from gpu_extras.batch import batch_for_shader

# region Variables

draw_handlers = {}

# endregion

# region Drawing

def hex_to_rgba(hex_str):
    """Convert a hex color string to an RGBA tuple."""
    hex_str = hex_str.lstrip('#')
    if len(hex_str) == 6:
        hex_str += 'ff'
    r, g, b, a = (int(hex_str[i:i+2], 16) / 255.0 for i in (0, 2, 4, 6))
    return (r, g, b, a)


def draw_border(color):
    """Draw a thick colored border around the viewport region."""
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    region = bpy.context.region
    width  = region.width
    height = region.height
    coords  = [(0, 0), (width, 0), (width, height), (0, height)]
    indices = [(0, 1), (1, 2), (2, 3), (3, 0)]
    batch   = batch_for_shader(shader, 'LINES', {"pos": coords}, indices=indices)
    pixel_size = bpy.context.preferences.system.pixel_size
    gpu.state.blend_set('ALPHA')
    gpu.state.line_width_set(10.0 * pixel_size)
    shader.bind()
    shader.uniform_float("color", color)
    batch.draw(shader)
    gpu.state.line_width_set(1.0)
    gpu.state.blend_set('NONE')

# endregion

# region Management

def enable_border(hex="#ff0000", key="default"):
    """Register a viewport border draw handler with the given color."""
    global draw_handlers
    if key not in draw_handlers:
        color = hex_to_rgba(hex)
        draw_handlers[key] = bpy.types.SpaceView3D.draw_handler_add(
            draw_border, (color,), 'WINDOW', 'POST_PIXEL'
        )


def disable_border(key="default"):
    """Remove a viewport border draw handler by key."""
    global draw_handlers
    if key in draw_handlers:
        bpy.types.SpaceView3D.draw_handler_remove(draw_handlers[key], 'WINDOW')
        del draw_handlers[key]


def disable_all_borders():
    """Remove all active viewport border draw handlers."""
    global draw_handlers
    for key in list(draw_handlers):
        bpy.types.SpaceView3D.draw_handler_remove(draw_handlers[key], 'WINDOW')
    draw_handlers.clear()

# endregion
