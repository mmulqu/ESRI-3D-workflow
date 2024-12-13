""" Settings that can be modified to customize the behavior of the gptools script """
import os as _os

# error name
# used when printing errors
ERROR = "error"
WARNING = "warning"

# global fields
UNDEFINED = "Undefined"
DIAMETER_FIELD = "util_diameter"
RADIUS_FIELD = "util_radius"
SLOPE_FIELD = "util_slope"
INVERTELEV_FIELD = "util_invertelev"
HEIGHT_FIELD = "util_height"

# Layer files for symbolizing results
HOLE_LYRX = _os.path.join(_os.path.dirname(_os.path.dirname(__file__)), 'layer_files', 'hole.lyrx')

LINE_LYRX = _os.path.join(_os.path.dirname(_os.path.dirname(__file__)), 'layer_files', 'line.lyrx')
LINE3D_LYRX = _os.path.join(_os.path.dirname(_os.path.dirname(__file__)), 'layer_files', 'line3D.lyrx')

LINE_ERROR_LYRX = _os.path.join(_os.path.dirname(_os.path.dirname(__file__)), 'layer_files', 'line_error.lyrx')
LINE3D_ERROR_LYRX = _os.path.join(_os.path.dirname(_os.path.dirname(__file__)), 'layer_files', 'line3D_error.lyrx')

POINT_ERROR_LYRX = _os.path.join(_os.path.dirname(_os.path.dirname(__file__)), 'layer_files', 'point_error.lyrx')
POINT3D_ERROR_LYRX = _os.path.join(_os.path.dirname(_os.path.dirname(__file__)), 'layer_files', 'point3D_error.lyrx')
