# A3D common functions and classes
import arcpy
import datetime
import json
import numpy as np
import urllib.request
import urllib.parse
from pprint import pprint
from arcgis.features import FeatureLayer
from arcgis.geometry import Geometry
from arcgis.features import FeatureSet
from scripts.bm_common_lib import unit_conversion


class GlobalInfo(object):
    def __init__(self, gis, item_id, web_scene_id, rpk_id):
        self.start_time = None
        self.gis = gis
        self.token = None
        self.input_item_id = item_id
        self.input_web_scene_id = web_scene_id
        self.rpk_id = rpk_id
        self.object_units = None
        self.scene_service_item_id = None
        self.input_item_info = None
        self.web_scene_title_postfix = None
        self.web_scene_description_prefix = None
        self.unique_tag = None
        self.token = None
        self.my_username = None
        self.root_url = None
        self.org_content_users_url = None
        self.org_content_items_url = None
        self.org_portal_url = None
        self.web_scene_layer_id = None
        self.layer_offset = 0


class ItemInfo(object):
    def __init__(self, item, folder):
        self.item_title = item.title
        self.item_folder = folder
        self.item_type = item.type
        self.item_id = item.id
        self.item = item
        self.item_owner = item.owner
        self.access = item.access


class LayerInfo(object):
    def __init__(self):
        self.layer_no_id = None
        self.layer_id = None
        self.item_id = None
        self.layer_def = None
        self.layer_type = None
        self.opacity = None
        self.popup_info = None
        self.title = None
        self.url = None
        self.visibility = None
        self.group_layer = False
        self.sub_layer_info_list = False
        self.layer_properties = None
        self.rendering_info = None
        self.labeling_info = None
        self.associated_layers = None
        self.process_layer = True
        self.elevation_attribute = None
        self.extrude_attribute = None
        self.floor_height = None
        self.floor_attribute = None
        self.basement_attribute = None
        self.levelid_attribute = None


class SpatialInfo(object):
    def __init__(self):
        self.fs_df = None
        self.fs_dict = None
        self.has_z = None
        self.wkid = None
        self.linear_unit = None
        self.object_id_field_name = None
        self.url = None
        self.service_url = None


class RelationshipInfo(object):
    def __init__(self):
        self.origin_id = None
        self.foreign_id = None
        self.origin_name = None
        self.foreign_name = None
        self.origin_key_field = None
        self.foreign_key_field = None
        self.origin_url = None
        self.foreign_url = None


def is_number(s):
    try:
        float(s)
        return True
    except ValueError:
        return False
        pass


def set_global_info(gis, input_item_id, input_web_scene_id, rpk_id):
    global_info = GlobalInfo(gis, input_item_id, input_web_scene_id, rpk_id)

    now = datetime.datetime.now()
    ts = ('{:%Y%m%d-%H%M}'.format(datetime.datetime.now()))  # Date Stamp for the name
    current_time = now.strftime("%d/%m/%Y at %H:%M:%S")
    arcpy.AddMessage("Start Time = " + current_time + " (UTC)")
    print("Start Time = " + current_time + " (UTC)")

    global_info.start_time = ts
    global_info.web_scene_title_postfix = " 3D - (" + ts + ")"
    global_info.web_scene_description_prefix = "A web scene generated from "
    global_info.unique_tag = None

    global_info.token = arcpy.GetSigninToken().get('token')
     #global_info.token = gis._con.token
    global_info.my_username = gis.users.me.username

    # create url parameters
    global_info.root_url = gis.url
    global_info.org_content_users_url = global_info.root_url + r'/sharing/rest/content/users/'
    global_info.org_content_items_url = global_info.root_url + r'/sharing/rest/content/items/'
    global_info.org_portal_url = global_info.root_url + r'/sharing/rest/portals/'

    return global_info


def get_foldername_user(gis_user, folder_id):
    folder_name = None
    for fld in gis_user.folders:
        if fld['id'] == folder_id:
            folder_name = fld['title']
            break

    return folder_name


def get_first_attribute(url, attr_list):
    get_z = True
    expression = '1=1'
    lyr = FeatureLayer(url)

    try:
        lyr_info = lyr.query(where=expression, returnIdsOnly=True)
        object_id_field_name = lyr_info.get('objectIdFieldName')
        object_ids = lyr_info.get('objectIds')

        if len(object_ids) > 0:
            expression = object_id_field_name + "=" + str(object_ids[0])
            fs = lyr.query(where=expression, return_z=get_z)

            if len(fs.features) > 0:
                feature_attrs_dict = fs.features[0].attributes
                feature_attrs_list = list(feature_attrs_dict.keys())
                feature_attrs_lower_list = list()
                for fa in feature_attrs_list:
                    feature_attrs_lower_list.append(fa.lower())

                # attributes are case sensitive!
                for attr in attr_list:
                    if attr in feature_attrs_list:
                        return attr

                return None
            else:
                return None
        else:
            return None
    except:
        return None


def check_attributes(url, attr_list):
    get_z = True
    expression = '1=1'
    lyr = FeatureLayer(url)

    try:
        lyr_info = lyr.query(where=expression, returnIdsOnly=True)
        object_id_field_name = lyr_info.get('objectIdFieldName')
        object_ids = lyr_info.get('objectIds')

        if len(object_ids) > 0:
            expression = object_id_field_name + "=" + str(object_ids[0])
            fs = lyr.query(where=expression, return_z=get_z)

            if len(fs.features) > 0:
                feature_attrs_dict = fs.features[0].attributes
                feature_attrs_list = list(feature_attrs_dict.keys())
                feature_attrs_lower_list = list()
                for fa in feature_attrs_list:
                    feature_attrs_lower_list.append(fa.lower())

                if all(elem in feature_attrs_lower_list for elem in attr_list):
                    return True, len(object_ids)
                else:
                    return False, len(object_ids)
            else:
                return False, len(object_ids)
        else:
            return False, 0
    except:
        return False, 0


def get_vertex_list_from_feature_sdf(fs_df,  geom_type, has_z):
    vertex_list = []
    shapes = fs_df['SHAPE']

    for shape in shapes:
        xyz_list = []
        x = shape.get('x', 0)
        y = shape.get('y', 0)

        xyz_list.append(x)
        xyz_list.append(y)

        if has_z:
            z = shape.get('z', 0)
            xyz_list.append(z)

        vertex_list.append(xyz_list)

    return vertex_list


def get_spatial_info_from_service_url(url):
    try:
        linear_unit = 'meter'
        fl = FeatureLayer(url)
        spatial_info = SpatialInfo()

        # spatial data frame
        expression = '1=1'
        fs = fl.query(where=expression, return_z=True)
        spatial_info.has_z = fs.has_z
        spatial_info.fs_df = fs.sdf
        spatial_info.fs_dict = fs.to_dict()
        spatial_info.object_id_field_name = fs.object_id_field_name
        spatial_info.url = url

        for feature in fs.features:
            try:
                linear_unit = Geometry(feature.geometry).as_arcpy.spatialReference.linearUnitName
                break
            except:
                arcpy.AddMessage("Failed to retrieve linear units from service url: " + url +
                                 ". Assuming meters as linear unit.")
                print("Failed to retrieve linear units from service url: " + url + ". Assuming meters as linear unit.")
                linear_unit = 'meter'
                break

        if 'feet' in linear_unit.lower() or 'foot' in linear_unit.lower():
            spatial_info.linear_unit = 'feet'
        else:
            spatial_info.linear_unit = 'meter'

        # get spatial ref
        try:
            spatial_ref = fs.spatial_reference

            try:
                spatial_info.wkid = spatial_ref.get('latestWkid')
            except:
                spatial_info.wkid = spatial_ref.get('wkid')
        except:
            arcpy.AddMessage("Found no spatial reference for service url: " + url)
            print("Found no spatial reference for service url: " + url)

        return spatial_info

    except:
        return None


def is_typeof_scene_service(item, typeof):
    typeof_layer = False

    try:
        layers = item.layers
        zero_layer = layers[0]
        lp = zero_layer.properties

        l_type = lp.layerType
        if l_type == typeof:
            typeof_layer = True
    except:
        typeof_layer = None

    return typeof_layer


def get_layer_info(layer, layer_info, item_id):
    do_continue = False
    layer_info.url = layer.url

    if 'FeatureServer' in layer_info.url:
        feature_layer = FeatureLayer(layer.url)

        # first check if we have FeatureLayer properties
        try:
            # get info from feature layer properties
            layer_info.layer_properties = feature_layer.properties
            layer_info.item_id = item_id
            layer_info.layer_type = feature_layer.properties.type
            layer_info.title = feature_layer.properties.name
            layer_info.rendering_info = feature_layer.properties.drawingInfo.renderer
            try:
                layer_info.labeling_info = feature_layer.properties.drawingInfo.labelingInfo
            except:
                pass

            do_continue = True
        except:
            do_continue = False

    if 'SceneServer' in layer_info.url:
        # first check if we have SceneLayer properties
        try:
            # get info from layer properties
            layer_info.layer_properties = layer.properties
            layer_info.item_id = item_id
            layer_info.layer_type = layer.properties.layerType
            layer_info.title = layer.properties.name
            layer_info.rendering_info = layer.properties.drawingInfo.renderer

            try:
                layer_info.labeling_info = layer.properties.drawingInfo.labelingInfo
            except:
                pass

            do_continue = True
        except:
            do_continue = False

    if 'MapServer' in layer_info.url:
        # it is a map

        try:
            feature_layer = FeatureLayer(layer.url)

            try:
                # get info from feature layer properties
                layer_info.layer_properties = feature_layer.properties
                layer_info.item_id = item_id
                layer_info.layer_type = feature_layer.properties.type
                layer_info.title = feature_layer.properties.name
                layer_info.rendering_info = feature_layer.properties.drawingInfo.renderer
                try:
                    layer_info.labeling_info = feature_layer.properties.drawingInfo.labelingInfo
                except:
                    pass

                do_continue = True
            except:
                do_continue = False
        except:
            do_continue = False

    if do_continue:
        # overwrite with possible map layer item info
        try:
            layer_info.item_id = layer.itemId
        except:
            pass

        try:
            layer_info.layer_type = layer.layerType
        except:
            pass

        try:
            layer_info.title = layer.title
        except:
            pass

        try:
            layer_info.layer_def = layer.layerDefinition
        except:
            pass

        try:
            layer_info.rendering_info = layer.layerDefinition.drawingInfo.renderer
        except:
            pass

        try:
            layer_info.labeling_info = layer.layerDefinition.drawingInfo.labelingInfo
        except:
            pass

        try:
            layer_info.opacity = layer.opacity
        except:
            layer_info.opacity = 1

        try:
            layer_info.popup_info = layer.popupInfo
        except:
            pass

        try:
            layer_info.visibility = layer.visbility
        except:
            layer_info.visibility = True

    else:
        arcpy.AddWarning("Failed to get layer info for " + layer.title + "...")
        print("Failed to get layer info for " + layer.title + "...")

    return do_continue


def get_layers_info(layers):
    sub_layer_info_list = list()
    item_url_list = list()

    i = 0

    for layer in layers:
        sub_layer_info = LayerInfo()
        sub_layer_info.layer_no_id = i
        if get_layer_info(layer, sub_layer_info, layer.itemId):
            sub_layer_info_list.append(sub_layer_info)
            item_url_list.append(layer.url)

            i += 1

            # add url list to each layer_info
            for li in sub_layer_info_list:
                li.associated_layers = item_url_list

    return sub_layer_info_list


def check_item_status(token, url, item_id, job_id):
    '''
        checks the status of the item
        :param token: login token
        :param url: base url used to check status of item
        :param item_id: id of the item
        :param job_id: job_id to check
        :return: status as string
    '''

    status_url = url + "/items/" + item_id + "/status"

    status_dict = {
        "jobId": job_id,
        "f": "json",
        "token": token
    }

    t = datetime.datetime.now()
    second_count = 0
    last_print = 0

    status = 'started'

    while status.lower() != 'completed':
        json_response = urllib.request.urlopen(status_url, urllib.parse.urlencode(status_dict).encode("utf-8"))
        response = json.loads(json_response.read())

        status = response.get("status")
        delta_seconds = (datetime.datetime.now() - t).seconds
        if delta_seconds and delta_seconds != second_count:
            second_count = delta_seconds
            if delta_seconds - last_print == 10:
                arcpy.AddMessage("Status: " + status + ". Processing time for job: " + job_id +
                                 " is " + str(second_count) + " seconds.")
                print("Status: " + status + ". Processing time for job: " + job_id +
                      " is " + str(second_count) + " seconds.")
                last_print = delta_seconds

    return status


def check_job_status(token, url, job_id):
    '''
        checks the status of the job
        :param token: login token
        :param url: base url used to check status of job
        :param job_id: job_id to check
        :return: status as string
    '''
    status_url = url + "/jobs/" + job_id
    status_url = status_url.replace("rest/services", "rest/admin/services")

    job_dict = {
        "f": "json",
        "token": token
    }

    t = datetime.datetime.now()
    second_count = 0
    last_print = 0

    status = 'started'
    arcpy.AddMessage("Status: starting cache rebuild.")
    print("Status: starting cache rebuild.")

    while status.lower() != 'completed':
        json_response = urllib.request.urlopen(status_url, urllib.parse.urlencode(job_dict).encode("utf-8"))
        response = json.loads(json_response.read())
        status = response.get("status")

        delta_seconds = (datetime.datetime.now() - t).seconds
        if delta_seconds and delta_seconds != second_count:
            second_count = delta_seconds
            if delta_seconds - last_print > 9:
                arcpy.AddMessage("Status: " + status + ". Processing time for job: " + job_id + " is " + str(
                    second_count) + " seconds.")
                print("Status: " + status + ". Processing time for job: " + job_id + " is " + str(
                    second_count) + " seconds.")
                last_print = delta_seconds

        if status.lower() == 'failed':
            raise Exception("Cache rebuild failed!")

    return status


def get_default_polygon_rings():
    json_string = """{
        "rings": [
                    [
                        [
                            0,
                            0,
                            0
                        ],
                        [
                            0,
                            0,
                            0
                        ],
                        [
                            0,
                            0,
                            0
                        ],
                        [
                            0,
                            0,
                            0
                        ],
                        [
                            0,
                            0,
                            0
                        ]
                    ]
                ]
    }"""

    default_polygon_rings_dict = json.loads(json_string)

    return default_polygon_rings_dict


def buffer_point_geometry(x_coord, y_coord):
    default_polygon_rings_dict = get_default_polygon_rings()['rings']

    # first point
    default_polygon_rings_dict[0][0][0] = float(x_coord - 1)
    default_polygon_rings_dict[0][0][1] = float(y_coord - 1)

    # second point
    default_polygon_rings_dict[0][1][0] = float(x_coord - 1)
    default_polygon_rings_dict[0][1][1] = float(y_coord + 1)

    # third point
    default_polygon_rings_dict[0][2][0] = float(x_coord + 1)
    default_polygon_rings_dict[0][2][1] = float(y_coord + 1)

    # fourth point
    default_polygon_rings_dict[0][3][0] = float(x_coord + 1)
    default_polygon_rings_dict[0][3][1] = float(y_coord - 1)

    # last point
    default_polygon_rings_dict[0][0][0] = float(x_coord - 1)
    default_polygon_rings_dict[0][0][1] = float(y_coord - 1)

    return default_polygon_rings_dict


def buffer_point_geometry_z(x_coord, y_coord, z_value):
    default_polygon_rings_dict = get_default_polygon_rings()['rings']

    # first point
    default_polygon_rings_dict[0][0][0] = float(x_coord - 1)
    default_polygon_rings_dict[0][0][1] = float(y_coord - 1)
    default_polygon_rings_dict[0][0][2] = float(z_value)

    # second point
    default_polygon_rings_dict[0][1][0] = float(x_coord - 1)
    default_polygon_rings_dict[0][1][1] = float(y_coord + 1)
    default_polygon_rings_dict[0][1][2] = float(z_value)

    # third point
    default_polygon_rings_dict[0][2][0] = float(x_coord + 1)
    default_polygon_rings_dict[0][2][1] = float(y_coord + 1)
    default_polygon_rings_dict[0][2][2] = float(z_value)

    # fourth point
    default_polygon_rings_dict[0][3][0] = float(x_coord + 1)
    default_polygon_rings_dict[0][3][1] = float(y_coord - 1)
    default_polygon_rings_dict[0][3][2] = float(z_value)

    # last point
    default_polygon_rings_dict[0][4][0] = float(x_coord - 1)
    default_polygon_rings_dict[0][4][1] = float(y_coord - 1)
    default_polygon_rings_dict[0][4][2] = float(z_value)

    return default_polygon_rings_dict


def buffer_point_features(spatial_info):
    fs_dict = spatial_info.fs_dict

    features = fs_dict.get('features')

    for feature in features:
        geometry = feature.get('geometry')

        # buffer geometry, Z is 0
        geometry['rings'] = buffer_point_geometry(geometry.get('x'), geometry.get('y'))

        # remove x, y, z point values
        del geometry['x']
        del geometry['y']

        try:
            del geometry['z']
        except:
            pass

        geometry['hasZ'] = False

    # set geometry type to 'esriGeometryPolygon'
    fs_dict['geometryType'] = 'esriGeometryPolygon'

    # turn into feature set
    buffered_fs = FeatureSet.from_dict(fs_dict)
    buffered_fs.has_z = False

    return buffered_fs


def buffer_point_features_z(spatial_info, z_list):
    buffered_fs = None
    fs_dict = spatial_info.fs_dict

    features = fs_dict.get('features')

    f = 0
    if len(features) == len(z_list):
        for feature in features:
            geometry = feature.get('geometry')

            # buffer geometry, Z is 0
            geometry['rings'] = buffer_point_geometry_z(geometry.get('x'), geometry.get('y'), z_list[f])

            # remove x, y, z point values
            del geometry['x']
            del geometry['y']

            try:
                del geometry['z']
            except:
                pass

            geometry['hasZ'] = True
            f += 1

        # set geometry type to 'esriGeometryPolygon'
        fs_dict['geometryType'] = 'esriGeometryPolygon'

        # turn into feature set
        buffered_fs = FeatureSet.from_dict(fs_dict)
        buffered_fs.has_z = True

    return buffered_fs


def get_related_item(item_id, items_url, token):

    if item_id:
        # find related Item (works only for feature service with associated scene service)
        related_item_dict = {
            "relationshipType": 'Service2Service',
            "direction": 'forward',
            "f": "json",
            "token": token
        }

        related_item_url = items_url + item_id + "/relatedItems"
        json_response = urllib.request.urlopen(related_item_url,
                                               urllib.parse.urlencode(related_item_dict).encode("utf-8"))
        # pprint(json_response)
        response = json.loads(json_response.read())
        # pprint(response)

        related_items_list = response.get('relatedItems')

        if len(related_items_list) == 1:
            related_item = related_items_list[0]
            related_item_id = related_item.get('id')
            related_item_type = related_item.get('type')
            related_item_url = related_item.get('url')
            related_item_url = related_item_url.replace(" ", "%20")
            if related_item_type == 'Scene Service':
                return related_item_id, related_item_url
            else:
                return None, None
        else:
            return None, None
    else:
        return None, None


def get_source_item(token, layer_info):
    source_layer_item_id = None

    if layer_info.item_id:
        # find the source item id
        sources_item_dict = {
            "f": "json",
            "token": token
        }

        sources_item_url = layer_info.url + "/sources"
        json_response = urllib.request.urlopen(sources_item_url,
                                               urllib.parse.urlencode(sources_item_dict).encode("utf-8"))
        # pprint(json_response)
        response = json.loads(json_response.read())
        # pprint(response)

        sources_layers_list = response.get('layers')

        if len(sources_layers_list) > 0:
            source_layer_item_id = sources_layers_list[0].get('serviceItemId')

    return source_layer_item_id


def get_view_layer_item(token, layer_info):
    view_layer_id = None

    try:
        has_view = layer_info.layer_properties.hasViews
    except:
        has_view = False

    if has_view:
        # get view layers
        # find related Item (works only for feature service with associated scene service)
        view_item_dict = {
            "f": "json",
            "token": token
        }

        views_item_url = layer_info.url + "/views"
        json_response = urllib.request.urlopen(views_item_url,
                                               urllib.parse.urlencode(view_item_dict).encode("utf-8"))
        # pprint(json_response)
        response = json.loads(json_response.read())
        # pprint(response)

        view_layers_list = response.get('layers')

        if len(view_layers_list) > 0:
            view_layer_id = view_layers_list[0].get('serviceItemId')

        # for view_layer in view_layers_list:
        #     if view_layer.get('name') == layer_info.title:
        #         view_layer_id = view_layer.get('serviceItemId')
        #         break   # grab the first view with the same name as the layer

    return view_layer_id


def get_item_data(item_id, items_url, token):

    if item_id:
        # gets the item data
        item_data_dict = {
            "f": "json",
            "token": token
        }

        item_data_url = items_url + item_id + "/data"
        json_response = urllib.request.urlopen(item_data_url,
                                               urllib.parse.urlencode(item_data_dict).encode("utf-8"))
        if json_response.status == 200:
            # pprint(json_response)
            try:
                response = json.loads(json_response.read())
                #pprint(response)

                try:
                    item_data_layers = response.get('layers')
                    return item_data_layers
                except:
                    return None
            except:
                return None
        else:
            return None
    else:
        return None


def check_z_values(url, geom_type):

    z_values = False
    expression = '1=1'
    get_z = True

    lyr = FeatureLayer(url)

    fs = lyr.query(where=expression, return_z=get_z)

    if len(fs.features) > 0:
        for feature in fs:
            feature_geom = feature.geometry

            if 'polygon' in geom_type.lower():
                poly_rings = feature_geom.get('rings')
                for vertex in poly_rings[0]:
                    # we assume z values useful if 1 z != 0
                    if vertex[2] != 0:
                        z_values = True
                        break

            if 'line' in geom_type.lower():
                line_paths = feature_geom.get('paths')
                for vertex in line_paths[0]:
                    # we assume z values useful if 1 z != 0
                    if vertex[2] != 0:
                        z_values = True
                        break

            if 'point' in geom_type.lower():
                if feature_geom.get('z') != 0:
                    z_values = True
                    break
                pass

    return z_values


def get_layer_properties_by_url(item, url):
    item_layers = item.layers

    layer_properties = None

    for layer in item_layers:
        if layer.url == url:
            layer_properties = layer.properties
            break

    return layer_properties


def get_first_point_feature_layer(item):
    point_layer = None
    fc_layers = item.layers

    for layer in fc_layers:
        if layer.properties.geometryType == 'esriGeometryPoint':
            point_layer = layer
            break

    return point_layer


def is_point_feature_layer(item, max_layers):
    success = False
    fc_layers = item.layers

    if len(fc_layers) == max_layers:
        if fc_layers[0].properties.geometryType == 'esriGeometryPoint':
            success = True
        else:
            success = False
    else:
        success = False

    fc_tables = item.tables

    if len(fc_tables) > 0:
        success = False

    return success


def z_values_from_elevation_service(token, url, geom_dict):
    '''

    '''
    try:

        geom_def = json.dumps(geom_dict)

        params_dict = {
            "geometry": geom_def,
            "geometryType": "esriGeometryMultipoint",
            "returnFirstValueOnly": "true",
            "interpolation": "RSP_NearestNeighbor",
            "outFields": "ProductName",
            "f": "json",
            "token": token
        }

        json_response = urllib.request.urlopen(url,
                                               urllib.parse.urlencode(params_dict).encode("utf-8"))
        #pprint(json_response)
        response = json.loads(json_response.read())
        #pprint(response)

        try:
            samples_list = response['samples']
            vertex_list = []
            z_list = list()

            if len(samples_list) > 0:
                for point in samples_list:
                    xyz_list = list()
                    x_value = point['location']['x']
                    y_value = point['location']['y']

                    xyz_list.append(x_value)
                    xyz_list.append(y_value)

                    z_value = point['value']
                    xyz_list.append(z_value)
                    z_list.append(z_value)
                    vertex_list.append(xyz_list)

                return vertex_list, z_list
        except:
            arcpy.AddMessage("Failed retrieve z values.")
            print("Failed retrieve z values.")
            return None, None
    except:
        arcpy.AddMessage("Failed to rebuild cache for scene layer.")
        print("Failed to rebuild cache for scene layer.")
        return None, None


def print_custom(message, parent, print_type):
    if parent == "ArcGISPro":
        if print_type == "info":
            arcpy.AddMessage(message)
        elif print_type == "warning":
            arcpy.AddWarning(message)
        elif print_type == "error":
            arcpy.AddError(message)
        else:
            arcpy.AddMessage(message)
    else:
        if print_type == 'pretty':
            pprint(message)
        else:
            print(message)


def get_portal_id(token, url):
    '''
         gets the portal id
         :param token: login token
         :param url: encoded_service_url
         :return: portal_id
     '''
    try:

        portal_url = url + "/self"

        portal_dict = {
            "f": "json",
            "token": token
        }

        json_response = urllib.request.urlopen(portal_url,
                                               urllib.parse.urlencode(portal_dict).encode("utf-8"))
        response = json.loads(json_response.read())

        try:
            portal_id = response.get('id')
            return portal_id
        except:
            print("Failed to get portal id.")
            return None
    except:
        arcpy.AddMessage("Failed to get portal id.")
        print("Failed to get portal id.")

        return None


def get_item_info(token, item_url):
    item_info = None

    # find the source item id
    sources_item_dict = {
        "f": "json",
        "token": token
    }

    json_response = urllib.request.urlopen(item_url,
                                           urllib.parse.urlencode(sources_item_dict).encode("utf-8"))
    # pprint(json_response)
    response = json.loads(json_response.read())
    #pprint(response)

    return response


def check_service_name(token, url, name, service_type):
    '''
         checks if the service name is used or available for creation
         :param token: login token
         :param url: encoded_service_url
         :name name to be checked
         :return: True (available) or False (used)
     '''
    try:
        service_name_url = url + "/isServiceNameAvailable"
        service_name_dict = {
            "name": name,
            "type": service_type,
            "f": "json",
            "token": token
        }

        json_response = urllib.request.urlopen(service_name_url,
                                               urllib.parse.urlencode(service_name_dict).encode("utf-8"))
        response = json.loads(json_response.read())

        try:
            available = response.get('available')
            return available
        except:
            arcpy.AddMessage("Failed to check service name.")
            print("Failed to check service name.")
            return False

    except:
        arcpy.AddMessage("Failed to check service name.")
        print("Failed to check service name.")

        return None


def create_service(token, content_users_url, username, input_item, item_folder, create_parameters, service_type):
    '''
         creates a service from create_parameters
         :param token: login token
         :param content_users_url
         :param username
         :param input_item
         :param item_folder
         :param create_parameters: dictionary of required parameters
         :param service_type: type of service
     '''

    try:
        # can only publish as owner
        url = content_users_url + "/" + username

        if input_item.owner == username:
            if item_folder:
                create_service_url = url + "/" + item_folder + "/createService"
            else:
                create_service_url = url + "/createService"
        else:
            create_service_url = url + "/createService"

        create_service_url = create_service_url.replace(" ", "%20")

        create_service_dict = {
            "createParameters": json.dumps(create_parameters),
            "targetType": service_type,
            "f": "json",
            "token": token
        }

        json_response = urllib.request.urlopen(create_service_url,
                                               urllib.parse.urlencode(create_service_dict).encode("utf-8"))
        #pprint(json_response)
        response = json.loads(json_response.read())
        #pprint(response)

        try:
            if response.get('success'):
                return response
            else:
                arcpy.AddMessage("Failed to retrieve the createService response.")
                print("Failed to retrieve the createService response.")
                return None
        except:
            arcpy.AddMessage("Failed to retrieve the createService response.")
            print("Failed to retrieve the createService response.")
            return None
    except:
        arcpy.AddMessage("Failed to create a new feature service.")
        print("Failed to create a new feature service.")
        return None


def update_item(token, content_users_url, username, input_item, item_folder,
                snippet,
                description,
                tags,
                type_key_word):
    '''
         updates an item
         :param token: login token
         :param content_users_url
         :param username
         :param input_item
         :param item_folder
         :param snippet item summary
         :param description item description
         :param tags item tags
         :param type_key_word
     '''

    try:
        # can only publish as owner
        url = content_users_url + "/" + username

        if input_item.owner == username:
            if item_folder:
                update_url = url + "/" + item_folder + "/items/" + input_item.id + "/update"
            else:
                update_url = url + "/items/" + input_item.id + "/update"
        else:
            update_url = url + "/items/" + input_item.id + "/update"

        update_url = update_url.replace(" ", "%20")

        update_item_dict = {
            "title": input_item.title,
            "snippet": snippet,
            "description": description,
            "tags": tags,
            "typeKeywords": type_key_word,
            "f": "json",
            "token": token
        }

        json_response = urllib.request.urlopen(update_url,
                                               urllib.parse.urlencode(update_item_dict).encode("utf-8"))
        #pprint(json_response)
        response = json.loads(json_response.read())
        #pprint(response)

        try:
            return response.get('success')
        except:
            arcpy.AddMessage("Failed to update the item.")
            print("Failed to update the item.")

        return None
    except:
        arcpy.AddMessage("Failed to update the item.")
        print("Failed to update the item.")
        return None


def add_definition(token, content_users_url, username, input_item, item_folder, def_properties,
                   add_field_list,
                   remove_field_list):
    '''
         adds properties as definition
         :param token: login token
         :param content_users_url
         :param username
         :param input_item
         :param item_folder
         :param def_properties: definition properties
     '''

    try:
        # can only publish as owner
        add_def_url = input_item.url.replace("rest/services", "rest/admin/services")
        add_def_url = add_def_url + "/addToDefinition"
        add_def_url = add_def_url.replace(" ", "%20")

        add_to_definition_dict = dict()
        layers = list()
        def_properties_asdict = vars(def_properties)
        layers.append(def_properties_asdict.get('_mapping'))

        if add_field_list:
            if len(add_field_list) > 0:
                for f in add_field_list:
                    layers[0].get('fields').append(f.copy())

        if remove_field_list:
            if len(remove_field_list) > 0:
                for r in remove_field_list:
                    fields = layers[0].get('fields')
                    for lf in fields:
                        if lf.get('name') == r:
                            layers[0].get('fields').remove(lf)

        tables = list()
        add_to_definition_dict['layers'] = layers
        add_to_definition_dict['tables'] = tables

        add_def_dict = {
            "addToDefinition": json.dumps(add_to_definition_dict),
            "f": "json",
            "token": token
        }

        json_response = urllib.request.urlopen(add_def_url,
                                               urllib.parse.urlencode(add_def_dict).encode("utf-8"))
        #pprint(json_response)
        response = json.loads(json_response.read())
        #pprint(response)

        try:
            return response.get('success')
        except:
            arcpy.AddMessage("Failed to update the item.")
            print("Failed to update the item.")

        return None
    except:
        arcpy.AddMessage("Failed to update the item.")
        print("Failed to update the item.")
        return None


def polygons_add_z(spatial_info, base_elev_attribute, object_units, converted):

    if converted:
        conv_factor = 1
    else:
        conv_factor = unit_conversion(spatial_info.linear_unit, object_units, 0)
    fs_dict = spatial_info.fs_dict
    features = fs_dict.get('features')

    f = 0
    if len(features) > 0:
        for ftr in features:
            geom = ftr.get('geometry')
            attr = ftr.get('attributes')
            base_elev = attr[base_elev_attribute]

            if is_number(str(base_elev)):
                if base_elev != 0:
                    z_value = base_elev*conv_factor
                else:
                    z_value = 0
            else:
                z_value = 0

            rings = geom.get('rings')

            for ring in rings:
                for point in ring:
                    point.append(z_value)

            geom['hasZ'] = True
            f += 1

        # set geometry type to 'esriGeometryPolygon'
        fs_dict['geometryType'] = 'esriGeometryPolygon'

        return True
    else:
        return False


def add_records_hosted_layer_via_rest(token, item_3D, spatial_info):
    success = False

    item_layers = item_3D.layers

    if len(item_layers) == 1:
        layer_url = item_layers[0].url
        apply_edits_url = layer_url + "/applyEdits"
        apply_edits_url = apply_edits_url.replace(" ", "%20")

        query_dict = {
            "adds": json.dumps(spatial_info.fs_dict.get('features')),
            "f": "json",
            "token": token
        }

        json_response = urllib.request.urlopen(apply_edits_url, urllib.parse.urlencode(query_dict).encode("utf-8"))
        response = json.loads(json_response.read())

        add_result_list = response["addResults"]

        count = 0
        for record_result in add_result_list:
            r_success = record_result["success"]
            if r_success:
                count += 1
        if count > 0:
            arcpy.AddMessage("Added: " + str(count) + " features to layer.")
            success = True
    else:
        arcpy.AddWarning("3D item has no layers!")

    return success


def create_feature_copies(spatial_info, num_copies_attribute, below_ground):
    try:
        fs_df = spatial_info.fs_df

        # duplicate features based on num_copies_attribute

        if not below_ground:
            fs_df[num_copies_attribute] = fs_df[num_copies_attribute].fillna(0)
            copies_fs_df = fs_df.loc[fs_df.index.repeat(fs_df[num_copies_attribute])].reset_index(drop=True)
        else:
            fs_df[num_copies_attribute] = fs_df[num_copies_attribute].fillna(0)
            copies_fs_df = fs_df.loc[fs_df.index.repeat(fs_df[num_copies_attribute])].reset_index(drop=True)

        # set index column name
        index_name = copies_fs_df.index.name

        if not index_name:
            copies_fs_df.index.name = 'index'

        # set orig_object_id and update object_id
        copies_fs_df['orig_object_id'] = copies_fs_df[spatial_info.object_id_field_name]

        return copies_fs_df

    except:
        arcpy.AddMessage("Failed to create a dataframe object from service url: " + spatial_info.url + ".")
        print("Failed to create a dataframe object from service url: " + spatial_info.url + ".")

        return None


def test_feature_copies(url, num_copies_attribute):
    try:
        expression = '1=1'
        get_z = False

        lyr = FeatureLayer(url)

        fs = lyr.query(where=expression, return_z=get_z)
        fs_df = fs.sdf

        # duplicate features based on num_copies_attribute
        copies_fs_df = fs_df.loc[fs_df.index.repeat(fs_df[num_copies_attribute])].reset_index(drop=True)

        # set index column name
        index_name = copies_fs_df.index.name

        if not index_name:
            copies_fs_df.index.name = 'index'

        # set orig_object_id and update object_id
        copies_fs_df['orig_object_id'] = copies_fs_df[fs.object_id_field_name]
        copies_fs_df[fs.object_id_field_name] = copies_fs_df.index + 1

        return copies_fs_df
    except:
        return None


def set_levelid_attribute(sdf, levelid_attribute, below_ground):

    # get unique list of index values
    object_id_list = sorted(sdf['orig_object_id'].unique())

    # select all rows for each object_id
    for object_id in object_id_list:

        mask = sdf['orig_object_id'] == object_id

        index = sdf.index
        mask_indices_list = index[mask].tolist()

        i = 0

        for indx in mask_indices_list:
            if not below_ground:
                i += 1
            else:
                i -= 1

            sdf.loc[index == indx, levelid_attribute] = int(i)

    sdf[levelid_attribute] = sdf[levelid_attribute].astype(int)



def set_id_attribute(sdf, id_attr, attr1, attr2):
    if not sdf[attr1].isnull().values.any():
        if not sdf[attr2].isnull().values.any():
            if np.array_equal(sdf[attr2], sdf[attr2].astype(int)):
                sdf[id_attr] = sdf[attr1].astype(int).astype(str).astype(int).astype(str) + "_" + \
                               sdf[attr2].astype(int).astype(str).astype(int).astype(str)
                success = True
            else:
                success = False
        else:
            arcpy.AddMessage("Found null values in: " + attr2)
            success = False
    else:
        arcpy.AddMessage("Found null values in: " + attr1)
        success = False

    return success


def set_level_elevation_attribute_level_id(sdf, elevation_attribute, default_floor_height,
                                           floor_height_attribute, conv_factor, level_attribute):

    # get unique list of index values
    object_id_list = sorted(sdf['orig_object_id'].unique())

    # select all rows for each object_id
    for object_id in object_id_list:
        mask = sdf['orig_object_id'] == object_id

        index = sdf.index
        mask_indices_list = index[mask].tolist()
        i = 0

        above_floor_elevation = 0
        below_floor_elevation = 0

        for indx in mask_indices_list:
            value_series = sdf.loc[index == indx, elevation_attribute]
            elevation_value = value_series.iloc[0]

            if i == 0:
                above_floor_elevation = elevation_value
                below_floor_elevation = elevation_value

            value_series = sdf.loc[index == indx, level_attribute]
            level_value = value_series.iloc[0].astype(int)

            if level_value < 0:
                below_ground = True
            else:
                below_ground = False

            value_series = sdf.loc[index == indx, floor_height_attribute]
            floor_height = value_series.iloc[0]

            # use default floor height from settings.json
            if np.isnan(floor_height):
                floor_height = default_floor_height
                sdf.loc[index == indx, floor_height_attribute] = default_floor_height

            if not below_ground:
                sdf.loc[index == indx, elevation_attribute] = above_floor_elevation * conv_factor
                above_floor_elevation += floor_height #  * conv_factor
            else:
                sdf.loc[index == indx, elevation_attribute] = (below_floor_elevation - floor_height) * conv_factor
                below_floor_elevation -= floor_height #  * conv_factor

            i += 1


def set_level_elevation_attribute(sdf, elevation_attribute, default_floor_height,
                                  conv_factor, below_ground):

    # get unique list of index values
    object_id_list = sorted(sdf['orig_object_id'].unique())

    # select all rows for each object_id
    for object_id in object_id_list:
        mask = sdf['orig_object_id'] == object_id

        index = sdf.index
        mask_indices_list = index[mask].tolist()
        i = 0

        floor_elevation = 0
        floor_height = default_floor_height

        for indx in mask_indices_list:
            value_series = sdf.loc[index == indx, elevation_attribute]
            elevation_value = value_series.iloc[0]

            if i == 0:
                floor_elevation = elevation_value

            if not below_ground:
                sdf.loc[index == indx, elevation_attribute] = floor_elevation * conv_factor
                floor_elevation += floor_height * conv_factor
            else:
                sdf.loc[index == indx, elevation_attribute] = (floor_elevation - default_floor_height) * conv_factor
                floor_elevation -= floor_height * conv_factor

            i += 1


def test_polygons_add_z(fs_dict, base_elev_attribute):

    features = fs_dict.get('features')

    if len(features) > 0:
        for ftr in features:
            geom = ftr.get('geometry')
            attr = ftr.get('attributes')
            base_elev = attr[base_elev_attribute]

            if is_number(str(base_elev)):
                z_value = base_elev
            else:
                z_value = 0

            rings = geom.get('rings')

            for ring in rings:
                for point in ring:
                    point.append(z_value)

            geom['hasZ'] = True

        # set geometry type to 'esriGeometryPolygon'
        fs_dict['geometryType'] = 'esriGeometryPolygon'

        return True
    else:
        return False


def get_relationship_info(global_info, layer_info, service_url):
    try:
        rel_info = None
        lyr_rel_info_list = layer_info.layer_properties.relationships
        lyr_table_rel_info_list = list()

        if lyr_rel_info_list:
            for r in lyr_rel_info_list:
                rel_info = RelationshipInfo()
                rel_info.origin_id = layer_info.layer_properties.id
                rel_info.foreign_id = r.relatedTableId
                rel_info.origin_name = layer_info.layer_properties.name
                rel_info.foreign_name = r.name
                rel_info.origin_key_field = r.keyField
                rel_info.origin_url = layer_info.url
                rel_info.foreign_url = service_url + "/" + \
                                       str(rel_info.foreign_id)

                # get table rel_info_
                table_rel_list = get_relationship_list_from_url(global_info.token,
                                                                rel_info.foreign_url)

                if table_rel_list:
                    for table_rel in table_rel_list:
                        if table_rel.get('relatedTableId') == rel_info.origin_id:
                            rel_info.foreign_key_field = table_rel.get('keyField')
                            break

                lyr_table_rel_info_list.append(rel_info)

        return lyr_table_rel_info_list

    except:
        return None


def get_relationship_list_from_url(token, url):
    '''
         gets layer relationship info
    '''

    try:
        rel_info_dict = {
            "f": "json",
            "token": token
        }

        layer_info_url = url

        json_response = urllib.request.urlopen(layer_info_url,
                                               urllib.parse.urlencode(rel_info_dict).encode("utf-8"))
        # pprint(json_response)
        response = json.loads(json_response.read())
        #pprint(response)

        try:
            if response.get('relationships'):
                relationship_list = response.get('relationships')

                if len(relationship_list) > 0:
                    return relationship_list

            else:
                arcpy.AddMessage("Found no relationship info.")
                print("Found no relationship info.")
                return None
        except:
            arcpy.AddMessage("Failed to relationship info.")
            print("Failed to retrieve relationship info.")
            return None
    except:
        arcpy.AddMessage("Failed to retrieve relationship info.")
        print("Failed to retrieve relationship info.")
        return None

    return response


