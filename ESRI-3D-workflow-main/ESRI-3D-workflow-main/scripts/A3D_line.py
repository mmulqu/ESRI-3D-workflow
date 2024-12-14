import json
import scripts.A3D_common_lib as A3D_common_lib
import scripts.bm_common_lib as bm_common_lib
import scripts.A3D_wm2ws as A3D_wm2ws


def get_default_line_symbol_3D():
    json_string = """{
        "symbol": {
            "type": "LineSymbol3D",
            "symbolLayers": [
                {
                  "type": "Path",
                  "material": {
                    "color": [
                      255,
                      0,
                      0
                    ]
                  },
                  "join": "bevel",
                  "width": 10,
                  "height": 10
                }
            ]
        }
    }"""

    default_line_symbol_3D_dict = json.loads(json_string)

    return default_line_symbol_3D_dict


def get_simple_3Dline_renderer():
    json_string = """{
        "renderer": {
            "authoringInfo": {
                "lengthUnit": "meters"
            },
            "type": "simple",
            "symbol": {
                "type": "LineSymbol3D",
                "symbolLayers": [
                    {
                      "type": "Path",
                      "material": {
                        "color": [
                          255,
                          0,
                          0
                        ]
                      },
                      "join": "bevel",
                      "width": 10,
                      "height": 10
                    }
                ]
            }
        }
    }"""

    line3d_renderer_dict = json.loads(json_string)

    return line3d_renderer_dict


def update_line_symbol_3D(color, size):
    default_line_symbol_3D = get_default_line_symbol_3D()['symbol']
    default_line_symbol_3D['symbolLayers'][0]['material']['color'] = color
    default_line_symbol_3D['symbolLayers'][0]['height'] = size * 2
    default_line_symbol_3D['symbolLayers'][0]['width'] = size * 2

    return default_line_symbol_3D


def set_3D_line_layer_definition(added_layer, layer_info, geom_type, global_info):
    existing_renderer = layer_info.rendering_info.type
    lyr_properties = layer_info.layer_properties

    # check if we have a buffer attribute
    buffer_attr_list = bm_common_lib.get_info_from_json("settings_3dbasemaps.json", "web_scene_info",
                                                        "buffer_attributes")
    buffer_attribute = A3D_common_lib.get_first_attribute(layer_info.url, buffer_attr_list)

    if buffer_attribute:
        # TODO buffer by attribute renderer - for now buffer by 2x symbol size
        pass
    else:
        # only simple and uniqueValue is supported at the moment
        if existing_renderer == 'simple':
            if layer_info.rendering_info.symbol.type == 'esriSLS':
                # get symbol point color and size from layer_info
                try:
                    existing_symbol_color = layer_info.rendering_info.symbol.color
                    existing_symbol_size = layer_info.rendering_info.symbol.width
                except:
                    existing_symbol_color = [0, 0, 255]
                    existing_symbol_size = 6

                rgb_list = [existing_symbol_color[0], existing_symbol_color[1], existing_symbol_color[2]]

                # replace symbol with LineSymbol3D
                layer_info.rendering_info.symbol = update_line_symbol_3D(rgb_list, existing_symbol_size)

        elif existing_renderer == 'uniqueValue':
            # get unique value renderer from layer_info
            try:
                lyr_unique_values = layer_info.rendering_info.uniqueValueInfos
            except:
                lyr_unique_values = None

            if lyr_unique_values:
                # replace symbol with PointSymbol3D
                for unique_value in lyr_unique_values:
                    if unique_value.symbol.type == 'esriSLS':
                        existing_symbol_color = unique_value.symbol.color
                        existing_symbol_size = unique_value.symbol.width

                        rgb_list = [existing_symbol_color[0], existing_symbol_color[1], existing_symbol_color[2]]
                        unique_value.symbol = update_line_symbol_3D(rgb_list, existing_symbol_size)
            else:
                default_line_renderer = get_simple_3Dline_renderer()['renderer']
                added_layer['layerDefinition']['drawingInfo']['renderer'] = default_line_renderer


    # TODO support more symbology options

    #else:
    #    default_line_renderer = get_simple_3Dline_renderer()['renderer']
    #    added_layer['layerDefinition']['drawingInfo']['renderer'] = default_line_renderer

    # set 3D line labeling
    do_label = False
    try:
        lbl_info = layer_info.labeling_info

        # if label info then translate to web scene specs
        if lbl_info:
            updated_lbl_info = A3D_wm2ws.translate_lbl_info(lbl_info, 'esriServerLinePlacementAboveAlong')
            added_layer['layerDefinition']['drawingInfo']['labelingInfo'] = updated_lbl_info
            do_label = True
        else:
            # if no labeling info in the layer, try and overwrite it with default name label
            has_attrs, num_fs = A3D_common_lib.check_attributes(layer_info.url, ['name'])
            if has_attrs:
                lbl_info = A3D_wm2ws.get_default_labeling_info()['labelingInfo']
                lbl_info[0]['labelPlacement'] = 'esriServerLinePlacementAboveAlong'
                added_layer['layerDefinition']['drawingInfo']['labelingInfo'] = lbl_info
                do_label = True
    except:
        pass

    # set elevationInfo
    A3D_wm2ws.set_elevation_info(added_layer, layer_info, geom_type, global_info, do_label, None)
