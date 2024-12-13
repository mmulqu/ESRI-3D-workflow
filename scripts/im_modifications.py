import arcpy
import urllib
import json
import os
import arcgis
import scripts.bm_layer_lib as bm_layer_lib
from scripts.bm_common_lib import create_msg_body, msg, trace

ERROR = "error"


class FunctionError(Exception):
    pass


class NoLayers(Exception):
    pass


def get_full_path_from_layer(in_layer):
    dir_name = os.path.dirname(arcpy.Describe(in_layer).catalogPath)
    layer_name = arcpy.Describe(in_layer).name

    return os.path.join(dir_name, layer_name)


def set_modifications_via_rest(gis, item_id, polygon_features, mod_type, debug):
    success = False

    token = arcpy.GetSigninToken()
    if token:
        # debug
        items_url = r'https://www.arcgis.com/sharing/rest/content/users/awesome3d/items/'
        item_id = '47d170cd382349c995013fecaf482e8a'

        resources_url = items_url + item_id + "/resources"
        update_resources_url = items_url + item_id + "/updateResources"

        mod = '''[
                  {
                    "geometry" : {
                      "hasZ" : true,
                      "rings" : [
                        [
                          [
                            -98.643873,
                            29.698762,
                            403.7777999999962
                          ],
                          [
                            -98.643681,
                            29.698771,
                            403.43409999999858
                          ],
                          [
                            -98.643517,
                            29.698703,
                            401.3747000000003
                          ],
                          [
                            -98.643493,
                            29.69854,
                            400.493100000006962
                          ],
                          [
                            -98.643563,
                            29.698456,
                            400.654099999999744
                          ],
                          [
                            -98.643818,
                            29.698499,
                            402.822400000004563
                          ],
                          [
                            -98.643873,
                            29.698762,
                            403.7777999999962
                          ]
                        ]
                      ]
                    },
                    "type" : "replace"
                  }
                ]'''

        # file_name = r'D:\Gert\Work\Esri\Solutions\LocalGovernment\3DBaseScenes\work2.7\3DBase' \
        #             r'maps27\settings\test_update_resources.json'
        # fileobj = open(file_name, 'rb')

        query_dict = {
            "resourcesPrefix": "modifications",
            "fileName": "4f2c813980ce4edb5a5a77ae51b57883.json",
            "text": mod,
            "f": "json",
            "token": token['token']
        }

        json_response = urllib.request.urlopen(update_resources_url, urllib.parse.urlencode(query_dict).encode("utf-8"))
        response = json.loads(json_response.read())
        print(response)
    else:
        arcpy.AddWarning("Couldn't retrieve token!")

    return success


def get_polygon_geometry_as_json(temp_dir, polygon_features):
    try:
        # polygons to json
        if not os.path.exists(temp_dir):
            os.mkdir(temp_dir)

        json_file = os.path.join(temp_dir, "polygon_mod.json")

        if arcpy.Exists(json_file):
            arcpy.Delete_management(json_file)

        # convert input parcels to json
        arcpy.FeaturesToJSON_conversion(polygon_features, json_file,
                                        "FORMATTED", "Z_VALUES", "NO_M_VALUES", "NO_GEOJSON", "KEEP_INPUT_SR",
                                        "USE_FIELD_NAME")

        if arcpy.Exists(json_file):
            with open(json_file, "r") as content:
                polygon_dict = json.load(content)

            feature_list = polygon_dict.get('features')
            geometry_list = list()
            # step through features and get geometry and attributes
            for feature in feature_list:
                rings_dict = feature.get('geometry')
                geometry_list.append(rings_dict)

            return geometry_list
    except:
        return None


def get_polygon_json_file(polygon_features, temp_dir, operation_type):
    try:
        json_file = None

        if polygon_features:
            polygon_full_path = get_full_path_from_layer(polygon_features)

            # get json from polygon layer
            json_polygon_list = get_polygon_geometry_as_json(temp_dir, polygon_full_path)

            if len(json_polygon_list) > 0:
                json_geometry_dict_list = list()
                for geom in json_polygon_list:
                    json_geometry_dict = dict()
                    json_geometry_dict['geometry'] = geom
                    json_geometry_dict['type'] = operation_type
                    json_geometry_dict_list.append(json_geometry_dict)

                # write as geometry mod json file
                if not os.path.exists(temp_dir):
                    os.mkdir(temp_dir)

                json_file = os.path.join(temp_dir, "geometry_mod.json")

                if arcpy.Exists(json_file):
                    arcpy.Delete_management(json_file)

                with open(json_file, 'w') as outfile:
                    json.dump(json_geometry_dict_list, outfile)

                return json_file
            else:
                arcpy.AddWarning("Can't load polygon feature layer!")
                return json_file
        else:
            return json_file
    except:
        arcpy.AddWarning("Can't load polygon feature layer!")
        return None


def get_scene_modification(gis, scene_id, mesh_layer):

    scene_mod = None

    try:
        scene_item = gis.content.get(str(scene_id))
        ws_mod_string = None

        # get layer resource entry
        web_scene_obj = arcgis.mapping.WebScene(scene_item)
        for layer in web_scene_obj['operationalLayers']:
            if layer['title'] == mesh_layer and layer['layerType'] == 'IntegratedMeshLayer':
                try:
                    ws_mod_string = layer['modifications']
                except:
                    ws_mod_string = None
                break

        if ws_mod_string:
            # get all resources
            try:
                res_man = scene_item.resources
                res_list = res_man.list()

                # check if layer resource is in resource list
                if len(res_list) > 0:
                    for mod in res_list:
                        if mod.get('resource') in ws_mod_string:
                            # get the resource json
                            mod_json = res_man.get(file=mod.get('resource'), try_json=True)

                            arcpy.AddMessage("Found mesh modification resource...")
                            scene_mod = bm_layer_lib.SceneModification(ws_mod_string,
                                                                       mod.get('resource'),
                                                                       mod_json)
                            break
                else:
                    arcpy.AddWarning("Web scene has no resources...")
            except:
                arcpy.AddWarning("Could not get web scene item resources...")

        return scene_mod
    except:
        arcpy.AddWarning("Could not get web scene item resources...")
        return scene_mod


def update_scene_operational_layers(gis, scene_id, mesh_layer, mod_type, mod_string):
    success = False

    try:
        scene_item = gis.content.get(str(scene_id))

        # get layer resource entry
        web_scene_obj = arcgis.mapping.WebScene(scene_item)
        ops_layers_json = web_scene_obj['operationalLayers']

        for layer in ops_layers_json:
            if layer['title'] == mesh_layer and layer['layerType'] == 'IntegratedMeshLayer':
                try:
                    if mod_type == "remove":
                        layer.pop('modifications', 'No Key found')

                    if mod_type == "add":
                        layer['modifications'] = mod_string
                except:
                    arcpy.AddWarning("Web scene has no modifications for mesh layer...")

                success = True
                break

        if success:
            web_scene_obj['operationalLayers'] = ops_layers_json
            web_scene_obj.update()
        else:
            arcpy.AddWarning("Couldn't find " + mesh_layer + " in web scene...")

        return success
    except:
        arcpy.AddWarning("Could not get web scene item resources...")
        return success


def set_scene_modification(aprx, gis, scene_id, mesh_layer, polygon_features,
                           modification_type, operation_type, ex_scene_mod,
                           temp_dir, debug):
    success = False

    try:
        # modify webscene resources
        scene_item = gis.content.get(str(scene_id))

        if scene_item:
            try:
                if modification_type == 'add':
                    json_file = get_polygon_json_file(polygon_features, temp_dir, operation_type)
                    if ex_scene_mod:
                        folder_name = os.path.dirname(ex_scene_mod.res_man_mod_string)
                        file_name = os.path.basename(ex_scene_mod.res_man_mod_string)

                        res_man = scene_item.resources
                        result = res_man.update(json_file, folder_name, file_name)
                        if result.get('success'):
                            arcpy.AddMessage("Updated existing mesh modifications successfully...")
                            success = True
                        else:
                            arcpy.AddMessage("Failed to update existing mesh modifications...")
                            success = False
                    else:
                        folder_name = "modifications"
                        file_name = os.path.basename(json_file)
                        mod_string = folder_name + "/" + file_name

                        # check resources / remove if existing necessary
                        res_man = scene_item.resources
                        res_list = res_man.list()

                        # check if layer resource is in resource list
                        if len(res_list) > 0:
                            for mod in res_list:
                                if folder_name in mod.get('resource') and file_name in mod.get('resource'):
                                    result = res_man.remove(mod_string)

                        # add resources
                        result = res_man.add(json_file, folder_name, file_name)
                        if result.get('success'):
                            # update operational layer
                            ws_mod_string = "./resources/" + mod_string
                            success = update_scene_operational_layers(gis, scene_id, mesh_layer, 'add',
                                                                      ws_mod_string)
                            if success:
                                arcpy.AddMessage("Added new mesh modifications successfully...")
                            else:
                                arcpy.AddMessage("Failed to add new mesh modifications...")
                                success = False
                        else:
                            arcpy.AddMessage("Failed to add new mesh modifications...")
                            success = False
                elif modification_type == 'remove':
                    if ex_scene_mod:
                        res_man = scene_item.resources
                        result = res_man.remove(ex_scene_mod.res_man_mod_string)
                        if result:
                            # update operational layer
                            success = update_scene_operational_layers(gis, scene_id, mesh_layer, 'remove', None)
                            arcpy.AddMessage("Removed existing mesh modifications successfully...")
                        else:
                            arcpy.AddMessage("Failed to remove existing mesh modifications...")
                            success = False
                    else:
                        success = update_scene_operational_layers(gis, scene_id, mesh_layer, 'remove', None)
                        arcpy.AddMessage("Removed existing mesh modifications successfully...")

                return success

            except:
                arcpy.AddWarning("Can't access resource manager")
                return False
        else:
            arcpy.AddWarning("Can't find web scene item!")
            return False

    except:
        return success


def scene_modifications(aprx, gis, scene_id, mesh_layer, polygon_features, modification_type,
                        operation_type, temp_dir, debug):
    try:
        success = False

        # check if mesh layer has existing modification
        ex_scene_mod = get_scene_modification(gis, scene_id, mesh_layer)

        success = set_scene_modification(aprx, gis, scene_id, mesh_layer, polygon_features,
                                         modification_type, operation_type, ex_scene_mod,
                                         temp_dir, debug)

        return success

    except ValueError:
        print("Input no flood value is not a number.")
        arcpy.AddError("Input no flood value is not a number.")

    except arcpy.ExecuteError:
        line, filename, synerror = trace()
        msg("Error on %s" % line, ERROR)
        msg("Error in file name:  %s" % filename, ERROR)
        msg("With error message:  %s" % synerror, ERROR)
        msg("ArcPy Error Message:  %s" % arcpy.GetMessages(2), ERROR)

    except FunctionError as f_e:
        messages = f_e.args[0]
        msg("Error in function:  %s" % messages["function"], ERROR)
        msg("Error on %s" % messages["line"], ERROR)
        msg("Error in file name:  %s" % messages["filename"], ERROR)
        msg("With error message:  %s" % messages["synerror"], ERROR)
        msg("ArcPy Error Message:  %s" % messages["arc"], ERROR)

    except:
        line, filename, synerror = trace()
        msg("Error on %s" % line, ERROR)
        msg("Error in file name:  %s" % filename, ERROR)
        msg("with error message:  %s" % synerror, ERROR)