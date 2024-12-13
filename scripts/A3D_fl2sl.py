# feature layer to a scene layer

import scripts.A3D_common_lib as A3D_common_lib
import scripts.bm_common_lib as bm_common_lib
import scripts.A3D_fl2sl_trees as A3D_fl2sl_trees
import scripts.A3D_fl2sl_street_signs as A3D_fl2sl_street_signs
import json
import urllib.request
import urllib.parse
from arcgis.features import FeatureLayer
import arcpy


def delete_associated_scene_layer(global_info, layer_info):
    success = False

    # search on input item title
    query = "title:" + layer_info.title
    arcpy.AddMessage("Searching user content using: " + query)
    print("Searching user content using: " + query)

    search_result = global_info.gis.content.search(query=query, max_items=-1)
    #    arcpy.AddMessage(search_result)

    # delete associated scene service and scene package
    if len(search_result) > 0:
        for result in search_result:
            if layer_info.title == result.title and (result.type == "Scene Service" or result.type == "Scene Package") \
                    and result.owner == global_info.input_item_info.item_owner:
                result.delete()
                arcpy.AddMessage("Deleted associated scene layer item: " + result.title + " of type: " + result.type)
                print("Deleted associated scene layer item: " + result.title + " of type: " + result.type)
                success = True

    return success


# delete associated scene layer by wild card search on item title
def delete_associated_scene_items(global_info, layer_info):
    success = False

    # search on input item title
    wild_card_search = layer_info.title + "*"
    query = "title:" + wild_card_search
    arcpy.AddMessage("Searching user content using wildcard: " + query)
    print("Searching user content using wildcard: " + query)

    search_result = global_info.gis.content.search(query=query, max_items=-1)
    #    pprint(search_result)

    # delete associated scene service and scene package
    if len(search_result) > 0:
        for result in search_result:
            if global_info.unique_tag in result.title and \
                    (result.type == "Scene Service" or result.type == "Scene Package")\
                    and result.owner == global_info.input_item_info.item_owner:
                result.delete()
                arcpy.AddMessage("Deleted associated scene layer item: " + result.title + " of type: " + result.type)
                print("Deleted associated scene layer item: " + result.title + " of type: " + result.type)
                success = True

    return success


def publish_slpk(global_info, slpk_filepath, item_folder):

    gis = global_info.gis

    if item_folder:
        folder_name = A3D_common_lib.get_foldername_user(gis.users.me, item_folder)
        uploaded_item = gis.content.add({'type': 'Scene Package'}, data=slpk_filepath, folder=folder_name)
        arcpy.AddMessage("Uploaded " + uploaded_item.title + " to the following folder: " + folder_name)
        print("Uploaded " + uploaded_item.title + " to the following folder: " + folder_name)
        arcpy.AddMessage("Publishing " + uploaded_item.title + " to the following folder: " + folder_name + "...")
        print("Publishing " + uploaded_item.title + " to the following folder: " + folder_name + "...")
        published_item = uploaded_item.publish()
        arcpy.AddMessage("Published " + published_item.title + " to the following folder: " + folder_name)
        print("Published " + published_item.title + " to the following folder: " + folder_name)
    else:
        uploaded_item = gis.content.add({'type': 'Scene Package'}, data=slpk_filepath)
        arcpy.AddMessage("Uploaded " + uploaded_item.title + " to the home folder.")
        print("Uploaded " + uploaded_item.title + " to the home folder.")
        published_item = uploaded_item.publish()
        arcpy.AddMessage("Published " + published_item.title + " to the home folder.")
        print("Published " + published_item.title + " to the home folder.")

    return published_item


def build_scene_layer_cache(token, url):
    '''
         rebuild the cache of the scene layer
         :param token: login token
         :param url: encoded_service_url
         :return: job id
     '''
    try:
        job_id = None

        rebuild_cache_url = url + "/rebuildCache"
        rebuild_cache_url = rebuild_cache_url.replace("rest/services", "rest/admin/services")

        rebuild_cache_dict = {
            "layers": 0,
            "f": "json",
            "token": token
        }

        json_response = urllib.request.urlopen(rebuild_cache_url,
                                               urllib.parse.urlencode(rebuild_cache_dict).encode("utf-8"))
        response = json.loads(json_response.read())

        try:
            job_id = response.get('jobId')
        except:
            arcpy.AddMessage("Failed to rebuild cache for scene layer.")
            print("Failed to rebuild cache for scene layer.")

        return job_id

    except:
        arcpy.AddMessage("Failed to rebuild cache for scene layer.")
        print("Failed to rebuild cache for scene layer.")
        return None


def get_valid_service_name(global_info, name):

    portal_id = A3D_common_lib.get_portal_id(global_info.token, global_info.org_portal_url)
    portal_url = global_info.org_portal_url + "/" + portal_id

    if portal_id:
        # check item_name
        name_available = A3D_common_lib.check_service_name(global_info.token, portal_url, name, "sceneService")

        if not name_available:
            # check with unique_tag
            service_item_name = name + " " + global_info.unique_tag
            name_available = A3D_common_lib.check_service_name(global_info.token, portal_url, service_item_name,
                                                               "sceneService")

            if not name_available:
                service_item_name = global_info.input_item_info.item_title + " " + \
                                          global_info.unique_tag + "_" + \
                                          global_info.start_time

                name_available = A3D_common_lib.check_service_name(global_info.token, portal_url, service_item_name,
                                                                   "sceneService")

                if name_available:
                    return service_item_name
                else:
                    return 'failed'
            else:
                return service_item_name
        else:
            return name

    else:
        return 'failed'


def publish_scene_layer(global_info, item_id, name, update):
    '''
         publish the scene layer
         :param global_info: global info
         :item_id: id of the layer item
         :param name: layer name
         :param update: update scene service True / False
         :return: return services dictionary
    '''
    scene_service_item_name = get_valid_service_name(global_info, name)

    if scene_service_item_name != 'failed':
        try:
            # can only publish as owner
            url = global_info.org_content_users_url + "/" + global_info.my_username

            if global_info.input_item_info.item.owner == global_info.my_username:
                if global_info.input_item_info.item_folder:
                    publish_url = url + "/" + global_info.input_item_info.item_folder + "/publish"
                else:
                    publish_url = url + "/publish"
            else:
                publish_url = url + "/publish"

            publish_dict = {
                "itemid": item_id,
                "filetype": "featureService",
                "publishParameters": {"name": scene_service_item_name},
                "outputType": "sceneService",
                "buildInitialCache": 'false',
                "f": "json",
                "token": global_info.token
            }

            if update:  # create new scene service
                publish_dict["overwrite"] = 'true'

            json_response = urllib.request.urlopen(publish_url, urllib.parse.urlencode(publish_dict).encode("utf-8"))
            #pprint(json_response)
            response = json.loads(json_response.read())
            #pprint(response)

            try:
                services_dict = response.get('services')[0]
                job_id = services_dict.get('jobId')
                service_item_id = services_dict.get('serviceItemId')
                service_url = services_dict.get('serviceurl')
                service_url = service_url.replace(" ", "%20")
                encoded_service_url = services_dict.get('encodedServiceURL')

                # check status of publishing
                status = A3D_common_lib.check_item_status(global_info.token, url,
                                                          service_item_id, job_id)

                if status.lower() == 'completed':
                    return service_item_id, service_url
            except:
                arcpy.AddMessage("Failed to retrieve the services dictionary.")
                print("Failed to retrieve the services dictionary.")

            return None, None
        except:
            arcpy.AddMessage("Failed to retrieve the services dictionary.")
            print("Failed to retrieve the services dictionary.")
            return None, None


# convert point feature layer into scene layer
def convert_point_layer_to_scene_layer(global_info, new_layer_info):
    new_layer_info_list = None
    rc = "no_return"
    sign_attrs = ['assetid', 'attachid', 'assettype',
                  'height', 'width', 'style',
                  'text', 'angle', 'disttotop']  # with these attributes we assume street signs
    tree_attrs = ['genus', 'height', 'diameter']  # with these attributes we assume trees
    tree_attrs = bm_common_lib.get_info_from_json("settings_3dbasemaps.json", "web_scene_info",
                                                  "tree_attributes")

    # check attributes against required attributes for street signs
    # arcpy.AddMessage("Checking " + new_layer_info.title + " for street sign creation.")
    has_attrs, num_fs = A3D_common_lib.check_attributes(new_layer_info.url, sign_attrs)

    # check if we can create street signs
    if has_attrs:
        arcpy.AddMessage(new_layer_info.title + " layer attributes allow for street sign creation.")
        print(new_layer_info.title + " layer attributes allow for street sign creation.")

        if num_fs > 0:
            # convert to sign layer and check on necessary attributes
            new_layer_info_list = A3D_fl2sl_street_signs.convert_point_layer_to_sign_layer(global_info,
                                                                                           new_layer_info,
                                                                                           sign_attrs)
            if new_layer_info_list:
                rc = "sign_scene_service"
        else:
            arcpy.AddMessage("Layer: " + new_layer_info.title +
                             " has zero features. Skipping...")
            print("Layer: " + new_layer_info.title +
                  " has zero features. Skipping...")

    # check attributes against required attributes for trees
    has_attrs, num_fs = A3D_common_lib.check_attributes(new_layer_info.url, tree_attrs)
    if has_attrs:
        arcpy.AddMessage(new_layer_info.title + " layer attributes allow for tree creation.")
        print(new_layer_info.title + " layer attributes allow for tree creation.")

        # if tree attributes are present, set in web scene spec
        scene_service_threshold = bm_common_lib.get_info_from_json("settings_3dbasemaps.json", "web_scene_info",
                                                                   "scene_service_threshold")

        if num_fs > 0:
            if num_fs > scene_service_threshold:
                # if over threshold -> convert to tree scene layer
                new_layer_info_list = A3D_fl2sl_trees.convert_point_layer_to_tree_layer(global_info,
                                                                                        new_layer_info,
                                                                                        tree_attrs)
                if new_layer_info_list:
                    rc = "tree_scene_service"
                else:
                    rc = "tree_feature_service"
        else:
            arcpy.AddMessage("Layer: " + new_layer_info.title +
                             " has zero features. Skipping...")
            print("Layer: " + new_layer_info.title +
                  " has zero features. Skipping...")

    return rc, new_layer_info_list


# convert point feature layers into scene layers
def convert_to_scene_layers(global_info, layer_info_list):
    if layer_info_list:
        li = 0

        # Step through layers in layer_info_list and convert if possible
        for layer_info in layer_info_list:
            if layer_info.group_layer:
                sli = 0
                for sub_layer_info in layer_info.sub_layer_info_list:
                    # only point features are processed
                    if sub_layer_info.layer_properties:
                        if sub_layer_info.layer_properties.geometryType == 'esriGeometryPoint':
                            arcpy.AddMessage("Checking if " + sub_layer_info.title + " has features...")
                            print("Checking if " + sub_layer_info.title + " has features...")

                            try:
                                # check if can convert to 3D trees or street signs scene layer
                                rc, new_layer_info_list = convert_point_layer_to_scene_layer(global_info,
                                                                                             sub_layer_info)
                                if "scene_service" in rc:
                                    # update the layer_info_list with the new layer
                                    if new_layer_info_list:
                                        arcpy.AddMessage("Converted" + sub_layer_info.title + " to scene layer...")
                                        print("Converted " + sub_layer_info.title + " to scene layer...")
                                        del layer_info.sub_layer_info_list[sli]
                                        layer_info.sub_layer_info_list.insert(sli, new_layer_info_list[0])
                                    else:
                                        # something failed in conversion, we don't want the original layer
                                        # added to the web scene
                                        layer_info.sub_layer_info_list[sli].process_layer = False
                                else:
                                    # process layer, attributes not ok for conversion
                                    layer_info.sub_layer_info_list[sli].process_layer = True

                            except:
                                arcpy.AddMessage(
                                    "Can't convert features in layer: " + layer_info.title + ". Skipping conversion...")
                                print("Can't convert features in layer: " +
                                      layer_info.title + ". Skipping conversion...")
                        else:
                            pass
                            # arcpy.AddMessage("Layer: " + sub_layer_info.title + " is not a point feature layer.")

                    sli += 1
            else:
                # only point features are processed
                if layer_info.layer_properties:
                    if layer_info.layer_properties.geometryType == 'esriGeometryPoint':

                        arcpy.AddMessage("Checking if " + layer_info.title + " has features...")
                        print("Checking if " + layer_info.title + " has features...")

                        try:
                            # check if can convert to 3D trees or street signs
                            rc, new_layer_info_list = convert_point_layer_to_scene_layer(global_info,
                                                                                         layer_info)

                            if "scene_service" in rc:
                                # update the layer_info_list with the new layer
                                if new_layer_info_list:
                                    del layer_info_list[li]
                                    layer_info_list.insert(li, new_layer_info_list[0])
                                    # there will be only 1 scene layer
                                else:
                                    # something failed in conversion, we don't want the original layer
                                    # added to the web scene
                                    layer_info_list[li].process_layer = False
                            else:
                                # process layer, attributes not ok for conversion
                                layer_info_list[li].process_layer = True

                        except:
                            arcpy.AddMessage("Can't convert features in layer: " + layer_info.title +
                                             ". Skipping conversion...")
                            print("Can't convert features in layer: " + layer_info.title +
                                  ". Skipping conversion...")
                    else:
                        pass
                        # arcpy.AddMessage("Layer: " + layer_info.title + " is not a point feature layer.")

                li += 1

    return layer_info_list


# get info from feature layer
def get_layer_info_from_item(item):
    layer_info_list = list()
    item_url_list = list()
    item_layers = item.layers

    i = 0

    for layer in item_layers:
        layer_info = A3D_common_lib.LayerInfo()
        layer_info.layer_no_id = i

        if A3D_common_lib.get_layer_info(layer, layer_info, item.id):
            layer_info_list.append(layer_info)
            item_url_list.append(layer.url)

            i += 1

    # add url list to each layer_info
    for li in layer_info_list:
        li.associated_layers = item_url_list

    return layer_info_list


