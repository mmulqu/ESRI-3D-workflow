# Prototype - Publish a web scene from a web map

import scripts.A3D_common_lib as A3D_common_lib
import scripts.A3D_wm2ws as A3D_wm2ws
import scripts.A3D_fl2sl as A3D_fl2sl
import arcpy
import copy
import json

def layers2scene(global_info, layer_info_list):
    '''
        processes the layer found in the map or feature layer collection to improve 3D visualization.
        Feature layers with tree attributes are symbolized with tree web style or converted to
        scene layers when after threshold param
        Feature layers with street sign attributes are converted to scene layers

        :param global_info: global_info object
        :param layer_info_list: list of layer info objects
        :return: True or False
    '''

    try:
        arcpy.AddMessage("Checking if any feature layers can be converted to scene layers...")
        print("Checking if any feature layers can be converted to scene layers...")
        updated_layer_info_list = A3D_fl2sl.convert_to_scene_layers(global_info, layer_info_list)

        if global_info.input_web_scene_id != "no_scene":
            # get the web scene item (existing or newly created)
            web_scene_item = A3D_wm2ws.get_web_scene_item(global_info)

            if web_scene_item.owner == global_info.my_username:
                # update the web scene with the layers from the input item
                arcpy.AddMessage("Adding layers to scene with id: " + web_scene_item.id)
                print("Adding layers to scene with id: " + web_scene_item.id)

                A3D_wm2ws.add_scene_layers(global_info, web_scene_item, updated_layer_info_list)
            else:
                arcpy.AddMessage("Can't update web scene.It is owned by: " + web_scene_item.owner + ".")
                print("Can't update web scene.It is owned by: " + web_scene_item.owner + ".")

            return True
        else:
            arcpy.AddMessage("No web scene created.")
            print("No web scene created.")
    except:
        raise Exception("Error in layers2scene!")


def auto2D_3D(gis_org,
              item_id,
              web_scene_id,
              rpk_id,
              units,
              scene_service_item_id,
              fixed_layer_id,
              offset):
    '''
        takes the layers from a webmap or feature layer collection and adds them to a scene.
        Layer rendering is  modified in the web scene definition to improve 3D visualization.
        Point Feature layers with defined tree attributes are rendered using the Esri Tree webstyle
        When there are more than scene_layer_threshold features, an additional scene service is created.
        Point Feature layers with defined street sign attributes are converted to scene layers and
        added to the web scene.

        - If the input web scene is can't be found and web_scene_id != "no_scene",
          a new web scene is created in the folder of the input item.

        - If web_scene_id == "no_scene": only street signs and trees scene layers are created / updated

        - a point feature layer requires the 'genus', 'height', 'diameter' attributes to be able to rendered as 3D trees
            - a tree point feature layer require an associated scene layer to be present.
            - if the tree point feature layer is part of a feature layer collection, there needs to be a view layer on
              the point layer which has an associated scene layer.
        - a point feature layer requires the 'assetid', 'attachid', 'assettype', 'height', 'width', 'style', 'text',
          'angle', 'disttotop' attributes to be able to rendered as 3D signs
            - for a street signs point feature layer, a new scene layer is created every time the script/notebook runs.

        The web scene is updated accordingly.

        :param gis_org: gis object
        :param item_id: id of the input item (webmap or feature layer (collection))
        :param web_scene_id: id of the input web scene
        :param rpk_id: rule package for sign scene layer creation
        :param units: units for the trees  / street sign objects / extrusion attribute
        :param scene_service_item_id: the id of the associated scene service item.
            If 'no_scene_service_item_id', it will search for an associated scene_service_item
        :param fixed_layer_id: the layer id of the tree/sign layer in the web scene. If 'create_layer_id', it will be
         created.
        :param offset: layer offset
        :return: True or False
    '''

    try:
        try:
            global_info = A3D_common_lib.set_global_info(gis_org, item_id, web_scene_id, rpk_id)
            global_info.object_units = units
            global_info.scene_service_item_id = scene_service_item_id
            global_info.web_scene_layer_id = fixed_layer_id
            global_info.layer_offset = float(offset)

            try:
                input_item = gis_org.content.get(str(global_info.input_item_id))

                if input_item:
                    try:
                        item_folder = input_item.ownerFolder
                    except:
                        item_folder = None

                    input_item_info = A3D_common_lib.ItemInfo(input_item, item_folder)
                    global_info.input_item_info = input_item_info

                    # check if we are dealing with Web Map
                    if input_item_info.item_type == 'Web Map':
                        arcpy.AddMessage("Reading layers from map with id: " + global_info.input_item_info.item_id)
                        print("Reading layers from map with id: " + global_info.input_item_info.item_id)
                        layer_info_list = A3D_wm2ws.get_layer_info_from_webmap(global_info.input_item_info.item)

                        if len(layer_info_list) > 0:
                            arcpy.AddMessage("Executing web map to web scene...")
                            print("Executing web map to web scene...")
                            success = layers2scene(global_info, layer_info_list)
                        else:
                            arcpy.AddMessage("Could not read any layers.")
                            print("Could not read any layers.")
                    elif "feature" in input_item_info.item_type.lower():
                        arcpy.AddMessage("Retrieving information from input layer...")
                        print("Retrieving information from input layer...")
                        layer_info_list = A3D_fl2sl.get_layer_info_from_item(global_info.input_item_info.item)

                        arcpy.AddMessage("Executing layers to web scene...")
                        print("Executing layers to web scene...")
                        success = layers2scene(global_info, layer_info_list)
                    else:
                        arcpy.AddMessage("Could not processing the item. Not a web map or feature layer")
                        print("Could not processing the item. Not a web map or feature layer")
                else:
                    arcpy.AddMessage("Could not find the item")
                    print("Could not find the item")
            except:
                arcpy.AddMessage("Could not find the item. check organization, login details and item id")
                print("Could not find the item. check organization, login details and item id")
        except:
            arcpy.AddError('Could not login using Pro authentication.Please verify in Pro that you are logged in')
            print('Could not login using Pro authentication.Please verify in Pro that you are logged in')
    except:
        raise Exception("Failed to publish web scene layer!")


