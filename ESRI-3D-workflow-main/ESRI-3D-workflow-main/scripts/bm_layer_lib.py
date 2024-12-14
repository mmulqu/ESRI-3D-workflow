import arcgis

ERROR = "error"


class NoLayers(Exception):
    pass


class FunctionError(Exception):

    """
    Raised when a function fails to run.
    """

    pass


class SceneModification(object):
    def __init__(self, web_scene_mod_string, res_man_mod_string, mod_json_dict):
        self.web_scene_mod_string = web_scene_mod_string
        self.res_man_mod_string = res_man_mod_string
        self.mod_json_dict = mod_json_dict


class SceneProperties(object):
    def __init__(self, title, scene_id):
        self.title = title
        self.id = scene_id


class MapProperties(object):
    def __init__(self, title, scene_id):
        self.title = title
        self.id = scene_id


def select_map_scene_by_title(web_objs, title):
    try:
        web_obj = None

        for s in web_objs:
            if s.title in title and s.id in title:
                web_obj = s
                break
        return web_obj

    except:
        return None


def get_mesh_layers_from_web_scene(gis, web_scene_obj):

    mesh_list = list()

    if web_scene_obj:
        scene_item = gis.content.get(str(web_scene_obj.id))

        # get layer resource entry
        web_scene = arcgis.mapping.WebScene(scene_item)
        for layer in web_scene['operationalLayers']:
            if layer['layerType'] == 'IntegratedMeshLayer':
                mesh_list.append(layer['title'])

    return mesh_list


def get_mesh_web_scenes(gis, org_id, username, layer_type):
    web_scene_obj_list = list()

    search_result = gis.content.search(query="*", item_type='Web Scene', outside_org=False, max_items=-1)

    for web_scene_item in search_result:
        scene_prop = SceneProperties(web_scene_item.title,
                                     web_scene_item.id)

        web_scene_obj_list.append(scene_prop)

    return web_scene_obj_list


def get_web_maps(gis, org_id, username):
    web_map_obj_list = list()

    search_result = gis.content.search(query="*", item_type='Web Map', outside_org=False, max_items=-1)

    for web_map_item in search_result:
        scene_prop = MapProperties(web_map_item.title,
                                   web_map_item.id)

        web_map_obj_list.append(scene_prop)

    return web_map_obj_list


def get_web_scenes(gis, org_id, username):
    web_scene_obj_list = list()

    search_result = gis.content.search(query="*", item_type='Web Scene', outside_org=False, max_items=-1)

    for web_scene_item in search_result:
        scene_prop = SceneProperties(web_scene_item.title,
                                     web_scene_item.id)

        web_scene_obj_list.append(scene_prop)

    return web_scene_obj_list





