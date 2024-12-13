import json
import arcpy
import scripts.A3D_common_lib as A3D_common_lib
import scripts.A3D_wm2ws as A3D_wm2ws
import scripts.bm_common_lib as bm_common_lib
import scripts.A3D_fl2sl_trees as A3D_fl2sl_trees


def get_default_point_symbol_3D():
    json_string = """{
        "symbol": {
          "type": "PointSymbol3D",
          "symbolLayers": [
            {
              "type": "Object",
              "material": {
                "color": [
                  255,
                  0,
                  0
                ]
              },
              "resource": {
                "primitive": "sphere"
              },
              "height": 45
            }
          ]
        }
    }"""

    default_point_symbol_3D_dict = json.loads(json_string)

    return default_point_symbol_3D_dict


def get_simple_3Dpoint_renderer():
    json_string = """{
        "renderer": {
            "authoringInfo": {
                "lengthUnit": "meters"
            },
            "type": "simple",
            "symbol": {
              "type": "PointSymbol3D",
              "symbolLayers": [
                {
                  "type": "Object",
                  "material": {
                    "color": [
                      255,
                      0,
                      0
                    ]
                  },
                  "resource": {
                    "primitive": "sphere"
                  },
                  "height": 20
                }
              ]
            }
          }
    }"""

    point3d_renderer_dict = json.loads(json_string)

    return point3d_renderer_dict


def update_point_symbol_3D(color, size):
    default_point_symbol_3D = get_default_point_symbol_3D()['symbol']
    default_point_symbol_3D['symbolLayers'][0]['material']['color'] = color
    default_point_symbol_3D['symbolLayers'][0]['height'] = size * 4

    return default_point_symbol_3D


def set_3D_point_layer_definition(added_layer, layer_info, geom_type, global_info):
    existing_renderer = layer_info.rendering_info.type

    # if tree attributes are present, set in web scene spec
    tree_attrs = bm_common_lib.get_info_from_json("settings_3dbasemaps.json", "web_scene_info",
                                                  "tree_attributes")
    # check if we can render with Esri Tree webstyle
    has_attrs, num_fs = A3D_common_lib.check_attributes(layer_info.url, tree_attrs)
    if has_attrs:
        arcpy.AddMessage(layer_info.title + " layer attributes allow for tree rendering.")
        print(layer_info.title + " layer attributes allow for tree rendering.")

        # tree_attrs must represent: genus, height, crownspread in order
        tree_drawing_info = A3D_fl2sl_trees.get_tree_drawing_info()["drawingInfo"]
        tree_drawing_info['renderer']['visualVariables'][0]['valueUnit'] = global_info.object_units
        tree_drawing_info['renderer']['visualVariables'][0]['field'] = tree_attrs[1]
        tree_drawing_info['renderer']['visualVariables'][1]['valueUnit'] = global_info.object_units
        tree_drawing_info['renderer']['visualVariables'][1]['field'] = tree_attrs[2]
        tree_drawing_info['renderer']['field1'] = tree_attrs[0]

        added_layer['layerDefinition']['drawingInfo'] = tree_drawing_info
    else:
        # if not tree attrs -> only simple and uniqueValue is supported at the moment
        if existing_renderer == 'simple':
            # get symbol point color and size from layer_info
            if layer_info.rendering_info.symbol.type == 'esriSMS':
                try:
                    existing_symbol_color = layer_info.rendering_info.symbol.color
                    existing_symbol_size = layer_info.rendering_info.symbol.size
                except:
                    existing_symbol_color = [0, 0, 255]
                    existing_symbol_size = 10

                rgb_list = [existing_symbol_color[0], existing_symbol_color[1], existing_symbol_color[2]]
                # replace symbol with PointSymbol3D
                layer_info.rendering_info.symbol = update_point_symbol_3D(rgb_list, existing_symbol_size)
            else:
                del added_layer['layerDefinition']['drawingInfo']

        elif existing_renderer == 'uniqueValue':
            # get unique value renderer from layer_info
            try:
                lyr_unique_values = layer_info.rendering_info.uniqueValueInfos
            except:
                lyr_unique_values = None

            delete_drawing_info = False

            if lyr_unique_values:
                # replace symbol with PointSymbol3D
                for unique_value in lyr_unique_values:
                    if unique_value.symbol.type == 'esriSMS':
                        existing_symbol_color = unique_value.symbol.color
                        existing_symbol_size = unique_value.symbol.size

                        rgb_list = [existing_symbol_color[0], existing_symbol_color[1], existing_symbol_color[2]]
                        unique_value.symbol = update_point_symbol_3D(rgb_list, existing_symbol_size)

                    # TODO we don't translate esriPMS yet, go with layer drawingInfo
                    else:
                        delete_drawing_info = True
                        break

                if delete_drawing_info:
                    del added_layer['layerDefinition']['drawingInfo']
            else:
                default_point_renderer = get_simple_3Dpoint_renderer()['renderer']
                added_layer['layerDefinition']['drawingInfo']['renderer'] = default_point_renderer

        # TODO support more symbology options

    #else:
    #    default_point_renderer = get_simple_3Dpoint_renderer()['renderer']
    #    added_layer['layerDefinition']['drawingInfo']['renderer'] = default_point_renderer

    # set 3D point labeling
    do_label = False
    try:
        lbl_info = layer_info.labeling_info

        # if label info then translate to web scene specs
        if lbl_info:
            updated_lbl_info = A3D_wm2ws.translate_lbl_info(lbl_info, 'esriServerPointLabelPlacementAboveCenter')
            added_layer['layerDefinition']['drawingInfo']['labelingInfo'] = updated_lbl_info
            do_label = True
        else:
            # if no labeling info in the layer, try and overwrite it with default name label
            has_attrs, num_fs = A3D_common_lib.check_attributes(layer_info.url, ['name'])
            if has_attrs:
                lbl_info = A3D_wm2ws.get_default_labeling_info()['labelingInfo']
                lbl_info[0]['labelPlacement'] = 'esriServerPointLabelPlacementAboveCenter'
                added_layer['layerDefinition']['drawingInfo']['labelingInfo'] = lbl_info
                do_label = True
    except:
        pass

    A3D_wm2ws.set_elevation_info(added_layer, layer_info, geom_type, global_info, False, None)
