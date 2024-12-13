import arcpy
import scripts.A3D_common_lib as A3D_common_lib
import scripts.A3D_fl2sl as A3D_fl2sl
import json
import urllib.request
import urllib.parse

# TREE SPECIFIC FUNCTIONS


def get_tree_drawing_info():
    json_string = """{
            "drawingInfo": {
              "renderer": {
                "type": "uniqueValue",
                "visualVariables": [
                  {
                    "type": "sizeInfo",
                    "field": "HEIGHT",
                    "axis": "height",
                    "valueUnit": "feet"
                  },
                  {
                    "type": "sizeInfo",
                    "field": "WIDTH",
                    "axis": "widthAndDepth",
                    "valueUnit": "feet"
                  }
                ],
                "field1": "GENUS",
                "defaultSymbol": {
                  "type": "styleSymbolReference",
                  "styleName": "esriRealisticTreesStyle",
                  "name": "Fagus"
                },
                "uniqueValueInfos": [
                  {
                    "symbol": {
                      "type": "styleSymbolReference",
                      "styleName": "esriRealisticTreesStyle",
                      "name": "Abies"
                    },
                    "value": "Abies"
                  },
                  {
                    "symbol": {
                      "type": "styleSymbolReference",
                      "styleName": "esriRealisticTreesStyle",
                      "name": "Acacia"
                    },
                    "value": "Acacia"
                  },
                  {
                    "symbol": {
                      "type": "styleSymbolReference",
                      "styleName": "esriRealisticTreesStyle",
                      "name": "Acer"
                    },
                    "value": "Acer"
                  },
                  {
                    "symbol": {
                      "type": "styleSymbolReference",
                      "styleName": "esriRealisticTreesStyle",
                      "name": "Acer Saccharum"
                    },
                    "value": "Acer Saccharum"
                  },
                  {
                    "symbol": {
                      "type": "styleSymbolReference",
                      "styleName": "esriRealisticTreesStyle",
                      "name": "Aesculus"
                    },
                    "value": "Aesculus"
                  },
                  {
                    "symbol": {
                      "type": "styleSymbolReference",
                      "styleName": "esriRealisticTreesStyle",
                      "name": "Agave"
                    },
                    "value": "Agave"
                  },
                  {
                    "symbol": {
                      "type": "styleSymbolReference",
                      "styleName": "esriRealisticTreesStyle",
                      "name": "Aiphanes"
                    },
                    "value": "Aiphanes"
                  },
                  {
                    "symbol": {
                      "type": "styleSymbolReference",
                      "styleName": "esriRealisticTreesStyle",
                      "name": "Alnus"
                    },
                    "value": "Alnus"
                  },
                  {
                    "symbol": {
                      "type": "styleSymbolReference",
                      "styleName": "esriRealisticTreesStyle",
                      "name": "Amelanchier"
                    },
                    "value": "Amelanchier"
                  },
                  {
                    "symbol": {
                      "type": "styleSymbolReference",
                      "styleName": "esriRealisticTreesStyle",
                      "name": "Aralia"
                    },
                    "value": "Aralia"
                  },
                  {
                    "symbol": {
                      "type": "styleSymbolReference",
                      "styleName": "esriRealisticTreesStyle",
                      "name": "Arbutus"
                    },
                    "value": "Arbutus"
                  },
                  {
                    "symbol": {
                      "type": "styleSymbolReference",
                      "styleName": "esriRealisticTreesStyle",
                      "name": "Betula"
                    },
                    "value": "Betula"
                  },
                  {
                    "symbol": {
                      "type": "styleSymbolReference",
                      "styleName": "esriRealisticTreesStyle",
                      "name": "Bulbophyllum"
                    },
                    "value": "Bulbophyllum"
                  },
                  {
                    "symbol": {
                      "type": "styleSymbolReference",
                      "styleName": "esriRealisticTreesStyle",
                      "name": "Buxus"
                    },
                    "value": "Buxus"
                  },
                  {
                    "symbol": {
                      "type": "styleSymbolReference",
                      "styleName": "esriRealisticTreesStyle",
                      "name": "Calocedrus"
                    },
                    "value": "Calocedrus"
                  },
                  {
                    "symbol": {
                      "type": "styleSymbolReference",
                      "styleName": "esriRealisticTreesStyle",
                      "name": "Carnegiea"
                    },
                    "value": "Carnegiea"
                  },
                  {
                    "symbol": {
                      "type": "styleSymbolReference",
                      "styleName": "esriRealisticTreesStyle",
                      "name": "Carya"
                    },
                    "value": "Carya"
                  },
                  {
                    "symbol": {
                      "type": "styleSymbolReference",
                      "styleName": "esriRealisticTreesStyle",
                      "name": "Castanea"
                    },
                    "value": "Castanea"
                  },
                  {
                    "symbol": {
                      "type": "styleSymbolReference",
                      "styleName": "esriRealisticTreesStyle",
                      "name": "Casuarina"
                    },
                    "value": "Casuarina"
                  },
                  {
                    "symbol": {
                      "type": "styleSymbolReference",
                      "styleName": "esriRealisticTreesStyle",
                      "name": "Cercocarpus"
                    },
                    "value": "Cercocarpus"
                  },
                  {
                    "symbol": {
                      "type": "styleSymbolReference",
                      "styleName": "esriRealisticTreesStyle",
                      "name": "Chamaedorea"
                    },
                    "value": "Chamaedorea"
                  },
                  {
                    "symbol": {
                      "type": "styleSymbolReference",
                      "styleName": "esriRealisticTreesStyle",
                      "name": "Chilopsis"
                    },
                    "value": "Chilopsis"
                  },
                  {
                    "symbol": {
                      "type": "styleSymbolReference",
                      "styleName": "esriRealisticTreesStyle",
                      "name": "Citrus"
                    },
                    "value": "Citrus"
                  },
                  {
                    "symbol": {
                      "type": "styleSymbolReference",
                      "styleName": "esriRealisticTreesStyle",
                      "name": "Cocos"
                    },
                    "value": "Cocos"
                  },
                  {
                    "symbol": {
                      "type": "styleSymbolReference",
                      "styleName": "esriRealisticTreesStyle",
                      "name": "Cordyline"
                    },
                    "value": "Cordyline"
                  },
                  {
                    "symbol": {
                      "type": "styleSymbolReference",
                      "styleName": "esriRealisticTreesStyle",
                      "name": "Cornus"
                    },
                    "value": "Cornus"
                  },
                  {
                    "symbol": {
                      "type": "styleSymbolReference",
                      "styleName": "esriRealisticTreesStyle",
                      "name": "Convallaria"
                    },
                    "value": "Convallaria"
                  },
                  {
                    "symbol": {
                      "type": "styleSymbolReference",
                      "styleName": "esriRealisticTreesStyle",
                      "name": "Crataegus"
                    },
                    "value": "Crataegus"
                  },
                  {
                    "symbol": {
                      "type": "styleSymbolReference",
                      "styleName": "esriRealisticTreesStyle",
                      "name": "Cupressus"
                    },
                    "value": "Cupressus"
                  },
                  {
                    "symbol": {
                      "type": "styleSymbolReference",
                      "styleName": "esriRealisticTreesStyle",
                      "name": "Echinodorus"
                    },
                    "value": "Echinodorus"
                  },
                  {
                    "symbol": {
                      "type": "styleSymbolReference",
                      "styleName": "esriRealisticTreesStyle",
                      "name": "Eucalyptus"
                    },
                    "value": "Eucalyptus"
                  },
                  {
                    "symbol": {
                      "type": "styleSymbolReference",
                      "styleName": "esriRealisticTreesStyle",
                      "name": "Fagus"
                    },
                    "value": "Fagus"
                  },
                  {
                    "symbol": {
                      "type": "styleSymbolReference",
                      "styleName": "esriRealisticTreesStyle",
                      "name": "Ficus"
                    },
                    "value": "Ficus"
                  },
                  {
                    "symbol": {
                      "type": "styleSymbolReference",
                      "styleName": "esriRealisticTreesStyle",
                      "name": "Frangula"
                    },
                    "value": "Frangula"
                  },
                  {
                    "symbol": {
                      "type": "styleSymbolReference",
                      "styleName": "esriRealisticTreesStyle",
                      "name": "Fraxinus"
                    },
                    "value": "Fraxinus"
                  },
                  {
                    "symbol": {
                      "type": "styleSymbolReference",
                      "styleName": "esriRealisticTreesStyle",
                      "name": "Fremontodendron"
                    },
                    "value": "Fremontodendron"
                  },
                  {
                    "symbol": {
                      "type": "styleSymbolReference",
                      "styleName": "esriRealisticTreesStyle",
                      "name": "Hamamelis"
                    },
                    "value": "Hamamelis"
                  },
                  {
                    "symbol": {
                      "type": "styleSymbolReference",
                      "styleName": "esriRealisticTreesStyle",
                      "name": "Helianthus"
                    },
                    "value": "Helianthus"
                  },
                  {
                    "symbol": {
                      "type": "styleSymbolReference",
                      "styleName": "esriRealisticTreesStyle",
                      "name": "Juglans"
                    },
                    "value": "Juglans"
                  },
                  {
                    "symbol": {
                      "type": "styleSymbolReference",
                      "styleName": "esriRealisticTreesStyle",
                      "name": "Juniperus"
                    },
                    "value": "Juniperus"
                  },
                  {
                    "symbol": {
                      "type": "styleSymbolReference",
                      "styleName": "esriRealisticTreesStyle",
                      "name": "Larix"
                    },
                    "value": "Larix"
                  },
                  {
                    "symbol": {
                      "type": "styleSymbolReference",
                      "styleName": "esriRealisticTreesStyle",
                      "name": "Laurus"
                    },
                    "value": "Laurus"
                  },
                  {
                    "symbol": {
                      "type": "styleSymbolReference",
                      "styleName": "esriRealisticTreesStyle",
                      "name": "Ligustrum"
                    },
                    "value": "Ligustrum"
                  },
                  {
                    "symbol": {
                      "type": "styleSymbolReference",
                      "styleName": "esriRealisticTreesStyle",
                      "name": "Liquidambar"
                    },
                    "value": "Liquidambar"
                  },
                  {
                    "symbol": {
                      "type": "styleSymbolReference",
                      "styleName": "esriRealisticTreesStyle",
                      "name": "Magnolia"
                    },
                    "value": "Magnolia"
                  },
                  {
                    "symbol": {
                      "type": "styleSymbolReference",
                      "styleName": "esriRealisticTreesStyle",
                      "name": "Musa"
                    },
                    "value": "Musa"
                  },
                  {
                    "symbol": {
                      "type": "styleSymbolReference",
                      "styleName": "esriRealisticTreesStyle",
                      "name": "Opuntia"
                    },
                    "value": "Opuntia"
                  },
                  {
                    "symbol": {
                      "type": "styleSymbolReference",
                      "styleName": "esriRealisticTreesStyle",
                      "name": "Other"
                    },
                    "value": "Other"
                  },
                  {
                    "symbol": {
                      "type": "styleSymbolReference",
                      "styleName": "esriRealisticTreesStyle",
                      "name": "Parkinsonia"
                    },
                    "value": "Parkinsonia"
                  },
                  {
                    "symbol": {
                      "type": "styleSymbolReference",
                      "styleName": "esriRealisticTreesStyle",
                      "name": "Phlebodium"
                    },
                    "value": "Phlebodium"
                  },
                  {
                    "symbol": {
                      "type": "styleSymbolReference",
                      "styleName": "esriRealisticTreesStyle",
                      "name": "Phoenix"
                    },
                    "value": "Phoenix"
                  },
                  {
                    "symbol": {
                      "type": "styleSymbolReference",
                      "styleName": "esriRealisticTreesStyle",
                      "name": "Phyllostachys"
                    },
                    "value": "Phyllostachys"
                  },
                  {
                    "symbol": {
                      "type": "styleSymbolReference",
                      "styleName": "esriRealisticTreesStyle",
                      "name": "Philodendron"
                    },
                    "value": "Philodendron"
                  },
                  {
                    "symbol": {
                      "type": "styleSymbolReference",
                      "styleName": "esriRealisticTreesStyle",
                      "name": "Picea"
                    },
                    "value": "Picea"
                  },
                  {
                    "symbol": {
                      "type": "styleSymbolReference",
                      "styleName": "esriRealisticTreesStyle",
                      "name": "Pinus"
                    },
                    "value": "Pinus"
                  },
                  {
                    "symbol": {
                      "type": "styleSymbolReference",
                      "styleName": "esriRealisticTreesStyle",
                      "name": "Pinus Sylvestris"
                    },
                    "value": "Pinus Sylvestris"
                  },
                  {
                    "symbol": {
                      "type": "styleSymbolReference",
                      "styleName": "esriRealisticTreesStyle",
                      "name": "Platanus"
                    },
                    "value": "Platanus"
                  },
                  {
                    "symbol": {
                      "type": "styleSymbolReference",
                      "styleName": "esriRealisticTreesStyle",
                      "name": "Populus"
                    },
                    "value": "Populus"
                  },
                  {
                    "symbol": {
                      "type": "styleSymbolReference",
                      "styleName": "esriRealisticTreesStyle",
                      "name": "Prunus"
                    },
                    "value": "Prunus"
                  },
                  {
                    "symbol": {
                      "type": "styleSymbolReference",
                      "styleName": "esriRealisticTreesStyle",
                      "name": "Pseudotsuga"
                    },
                    "value": "Pseudotsuga"
                  },
                  {
                    "symbol": {
                      "type": "styleSymbolReference",
                      "styleName": "esriRealisticTreesStyle",
                      "name": "Quercus"
                    },
                    "value": "Quercus"
                  },
                  {
                    "symbol": {
                      "type": "styleSymbolReference",
                      "styleName": "esriRealisticTreesStyle",
                      "name": "Quercus Rubra"
                    },
                    "value": "Quercus Rubra"
                  },
                  {
                    "symbol": {
                      "type": "styleSymbolReference",
                      "styleName": "esriRealisticTreesStyle",
                      "name": "Rhamnus"
                    },
                    "value": "Rhamnus"
                  },
                  {
                    "symbol": {
                      "type": "styleSymbolReference",
                      "styleName": "esriRealisticTreesStyle",
                      "name": "Rhododendron"
                    },
                    "value": "Rhododendron"
                  },
                  {
                    "symbol": {
                      "type": "styleSymbolReference",
                      "styleName": "esriRealisticTreesStyle",
                      "name": "Robinia"
                    },
                    "value": "Robinia"
                  },
                  {
                    "symbol": {
                      "type": "styleSymbolReference",
                      "styleName": "esriRealisticTreesStyle",
                      "name": "Rosa"
                    },
                    "value": "Rosa"
                  },
                  {
                    "symbol": {
                      "type": "styleSymbolReference",
                      "styleName": "esriRealisticTreesStyle",
                      "name": "Sabal"
                    },
                    "value": "Sabal"
                  },
                  {
                    "symbol": {
                      "type": "styleSymbolReference",
                      "styleName": "esriRealisticTreesStyle",
                      "name": "Salix"
                    },
                    "value": "Salix"
                  },
                  {
                    "symbol": {
                      "type": "styleSymbolReference",
                      "styleName": "esriRealisticTreesStyle",
                      "name": "Sansevieria"
                    },
                    "value": "Sansevieria"
                  },
                  {
                    "symbol": {
                      "type": "styleSymbolReference",
                      "styleName": "esriRealisticTreesStyle",
                      "name": "Sassafras"
                    },
                    "value": "Sassafras"
                  },
                  {
                    "symbol": {
                      "type": "styleSymbolReference",
                      "styleName": "esriRealisticTreesStyle",
                      "name": "Sequoia"
                    },
                    "value": "Sequoia"
                  },
                  {
                    "symbol": {
                      "type": "styleSymbolReference",
                      "styleName": "esriRealisticTreesStyle",
                      "name": "Sequoiadendron"
                    },
                    "value": "Sequoiadendron"
                  },
                  {
                    "symbol": {
                      "type": "styleSymbolReference",
                      "styleName": "esriRealisticTreesStyle",
                      "name": "Spartium"
                    },
                    "value": "Spartium"
                  },
                  {
                    "symbol": {
                      "type": "styleSymbolReference",
                      "styleName": "esriRealisticTreesStyle",
                      "name": "Sorbus"
                    },
                    "value": "Sorbus"
                  },
                  {
                    "symbol": {
                      "type": "styleSymbolReference",
                      "styleName": "esriRealisticTreesStyle",
                      "name": "Taxodium"
                    },
                    "value": "Taxodium"
                  },
                  {
                    "symbol": {
                      "type": "styleSymbolReference",
                      "styleName": "esriRealisticTreesStyle",
                      "name": "Tilia"
                    },
                    "value": "Tilia"
                  },
                  {
                    "symbol": {
                      "type": "styleSymbolReference",
                      "styleName": "esriRealisticTreesStyle",
                      "name": "Umbellularia"
                    },
                    "value": "Umbellularia"
                  },
                  {
                    "symbol": {
                      "type": "styleSymbolReference",
                      "styleName": "esriRealisticTreesStyle",
                      "name": "Ulmus"
                    },
                    "value": "Ulmus"
                  },
                  {
                    "symbol": {
                      "type": "styleSymbolReference",
                      "styleName": "esriRealisticTreesStyle",
                      "name": "Washingtonia"
                    },
                    "value": "Washingtonia"
                  },
                  {
                    "symbol": {
                      "type": "styleSymbolReference",
                      "styleName": "esriRealisticTreesStyle",
                      "name": "GenericDead"
                    },
                    "value": "GenericDead"
                  },
                  {
                    "symbol": {
                      "type": "styleSymbolReference",
                      "styleName": "esriRealisticTreesStyle",
                      "name": "Stump"
                    },
                    "value": "Stump"
                  },
                  {
                    "symbol": {
                      "type": "styleSymbolReference",
                      "styleName": "esriRealisticTreesStyle",
                      "name": "Yucca"
                    },
                    "value": "Yucca"
                  },
                  {
                    "symbol": {
                      "type": "styleSymbolReference",
                      "styleName": "esriRealisticTreesStyle",
                      "name": "Unknown"
                    },
                    "value": "Unknown"
                  },
                  {
                    "symbol": {
                      "type": "styleSymbolReference",
                      "styleName": "esriRealisticTreesStyle",
                      "name": "Rhododendron"
                    },
                    "value": "Lagerstroemia"
                  }
                ]
              }
            }
        }"""

    tree_drawing_info_dict = json.loads(json_string)

    return tree_drawing_info_dict


def set_tree_style_on_layer(token, url, item_id, folder, units, tree_attrs):
    '''
         set esri tree style on layer item as item data
         (to check: https://www.arcgis.com/sharing/rest/content/items/'item_id'/data)
         :param token: login token
         :param url: org_content_users_url + item owner name
         :param item_id: service_item_id
         :param folder: item folder
         :return: job id
     '''
    try:
        if folder:
            update_url = url + "/" + folder + "/items/" + item_id + "/update"
        else:
            update_url = url + "/items/" + item_id + "/update"

        # tree renderer json
        tree_renderer_json = '''
                {
                  "layers": [
                    {
                      "id": 0,
                      "layerDefinition": {
                        "drawingInfo": {                          
                        }
                      }
                    }
                  ]
                }
        '''

        tree_renderer_json_dict = json.loads(tree_renderer_json)
        tree_renderer_json_dict['layers'][0]['layerDefinition']['drawingInfo'] = get_tree_drawing_info()["drawingInfo"]

        # tree_attrs must represent: genus, height, crownspread in order
        tree_renderer = tree_renderer_json_dict['layers'][0]['layerDefinition']['drawingInfo']['renderer']
        tree_renderer['visualVariables'][0]['valueUnit'] = units
        tree_renderer['visualVariables'][0]['field'] = tree_attrs[1]
        tree_renderer['visualVariables'][1]['valueUnit'] = units
        tree_renderer['visualVariables'][1]['field'] = tree_attrs[2]
        tree_renderer['field1'] = tree_attrs[0]

        tree_renderer_json_dumps = json.dumps(tree_renderer_json_dict)

        update_dict = {
            "text": tree_renderer_json_dumps,
            "f": "json",
            "token": token
        }

        json_response = urllib.request.urlopen(update_url, urllib.parse.urlencode(update_dict).encode("utf-8"))
        response = json.loads(json_response.read())

        if response:
            try:
                success = response.get('success')

                if success:
                    return True
                else:
                    return False
            except:
                return False
        else:
            return False

    except:
        arcpy.AddMessage("Failed to set tree style scene layer.")
        return False


# convert point feature layer into tree scene layer
def convert_point_layer_to_tree_layer(global_info, layer_info, tree_attrs):
    arcpy.AddMessage("Processing '" + layer_info.title + "' for 3D tree display.")

    global_info.unique_tag = "(web_style_trees)"

    if global_info.scene_service_item_id == 'no_scene_service_item_id':
        # check for associated scene service if none for input
        # arcpy.AddMessage("Checking if '" + layer_info.title + "' has associated scene layer...")
        related_item_id, related_item_url = A3D_common_lib.get_related_item(layer_info.item_id,
                                                                            global_info.org_content_items_url,
                                                                            global_info.token)

        # if no associated scene service -> check for view layer with associated scene service or created one
        if not related_item_id:
            # check for view layer and see if related scene service is present
            # arcpy.AddMessage("Checking if '" + layer_info.title + "' has associated view layer...")\
            try:
                is_view = layer_info.layer_properties.isView

                if is_view:
                    view_layer_id = layer_info.item_id
                else:
                    view_layer_id = A3D_common_lib.get_view_layer_item(global_info.token, layer_info)
            except:
                view_layer_id = A3D_common_lib.get_view_layer_item(global_info.token, layer_info)

            if view_layer_id:
                # arcpy.AddMessage("Checking if view layer for '" + layer_info.title + "' has associated scene layer...")
                related_item_id, related_item_url = A3D_common_lib.get_related_item(view_layer_id,
                                                                                    global_info.org_content_items_url,
                                                                                    global_info.token)
                if not related_item_id:
                    arcpy.AddMessage("View layer for: '" + layer_info.title + "' has no associated scene layer.")

                    # create scene service
                    arcpy.AddMessage("Creating scene layer for " + layer_info.title + "...")
                    related_item_id, related_item_url = A3D_fl2sl.publish_scene_layer(global_info,
                                                                                      view_layer_id,
                                                                                      layer_info.title,
                                                                                      False)
            else:
                max_layers = 1

                # if not view layer and not a feature collection -> create scene layer
                layer_item = global_info.gis.content.get(layer_info.item_id)
                if A3D_common_lib.is_point_feature_layer(layer_item, max_layers):
                    arcpy.AddMessage("Layer: '" + layer_info.title + "' has no associated scene layer.")

                    # create scene service
                    arcpy.AddMessage("Creating scene layer for " + layer_info.title + "...")
                    related_item_id, related_item_url = A3D_fl2sl.publish_scene_layer(global_info,
                                                                                      layer_info.item_id,
                                                                                      layer_info.title,
                                                                                      False)
                else:
                    related_item_id = None
                    arcpy.AddMessage("Layer: '" +
                                     layer_info.title + "' has no associated view layer. This is required to "
                                     "continue."
                                     "Please create a view layer for the point layer that "
                                     "represents the tree points.")
                    arcpy.AddMessage("Failed to process: '" + layer_info.title + "'.")
    else:
        related_item_id = global_info.gis.content.get(global_info.scene_service_item_id)
        related_item = global_info.gis.content.get(related_item_id)
        related_item_url = related_item.url

    # we have the scene service!
    if related_item_id:
        # push an update on the related scene service

        # rebuild cache to get updates
        arcpy.AddMessage("Rebuilding scene layer cache to process updates in " + layer_info.title + "...")
        job_id = A3D_fl2sl.build_scene_layer_cache(global_info.token, related_item_url)

        # check job status
        if job_id:
            status = A3D_common_lib.check_job_status(token=global_info.token,
                                                     url=related_item_url,
                                                     job_id=job_id)
            if status.lower() == 'completed':
                # set tree style
                arcpy.AddMessage("Updating rendering for scene layer of " + layer_info.title + "...")
                related_item = global_info.gis.content.get(related_item_id)
                try:
                    item_folder = related_item.ownerFolder
                except:
                    item_folder = None

                if related_item:
                    response = set_tree_style_on_layer(token=global_info.token,
                                                       url=global_info.org_content_users_url + related_item.owner,
                                                       item_id=related_item_id,
                                                       folder=item_folder,
                                                       units=global_info.object_units,
                                                       tree_attrs=tree_attrs)

                    if response:
                        # update layer_info
                        layer_info_list = A3D_fl2sl.get_layer_info_from_item(related_item)

                        # in this case, there will be only 1 scene layer so we want the scene item name as layer name
                        layer_info_list[0].title = related_item.title

                        if len(layer_info_list) > 0:
                            return layer_info_list
                        else:
                            return None
                    else:
                        arcpy.AddMessage("Can't update layer information...")
                        return None
                else:
                    return None
            else:
                return None
        else:
            return None
    else:
        return None

# END TREE SPECIFIC FUNCTIONS