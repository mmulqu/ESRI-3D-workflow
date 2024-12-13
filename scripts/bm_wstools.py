__author__ = "Gert van Maren"

import arcpy
from arcgis.gis import GIS
import os
import scripts.im_modifications as im_mod
import scripts.A2Dto3D as A2Dto3D
import scripts.bm_layer_lib as bm_layer_lib
from scripts.bm_settings import *
import scripts.bm_common_lib as bm_common_lib
import importlib
importlib.reload(A2Dto3D)  # force reload of the module


def parameter(display_name, name, datatype, parameter_type, direction, multi_value, default_value, enabled,
              category):
    '''
    The parameter implementation makes it a little difficult to
    quickly create parameters with defaults. This method
    pre-populates some of these values to make life easier while
    also allowing setting a default value. Life should be easy...
    '''

    # create parameter with a few default properties
    if category:
        param = arcpy.Parameter(
            displayName=display_name,
            name=name,
            datatype=datatype,
            parameterType=parameter_type,
            direction=direction,
            multiValue=multi_value,
            category=category)
    else:
        param = arcpy.Parameter(
            displayName=display_name,
            name=name,
            datatype=datatype,
            parameterType=parameter_type,
            direction=direction,
            multiValue=multi_value)

    # set new parameter to a default value
    param.value = default_value
    param.enabled = enabled

    # return complete parameter object
    return param


# set mesh modification tool
def get_parameter_info_set_mesh_modification(tool_label):
    '''
    This function sets the UI parameters for the ShareAsIndicator tool.
    :param tool_label:
    :return:
    '''

    # unfortunately we need to use globals as it is the only way to share info between
    # the pyt calls and reduce calls to the org
    global gis
    global web_scene_objs

    web_scenes = parameter("Web Scene", "SelectWebScene", "GPString",
                           "Required", "Input", False, None, True, None)

    mesh_layer = parameter("Integrated Mesh", "selectLayer", "GPString",
                           "Required", "Input", False, None, True, None)

    modification_type = parameter("Modification Type", "ModificationType", 'GPString',
                                  "Required", "Input", False, None, True, None)

    polygon_fc = parameter("Input Features", "selectpolyLayer",
                           ["DEFeatureClass", "GPFeatureLayer"],
                           "Optional", "Input", False, None, True, None)

    operation_type = parameter("Operation Type", "OperationType", 'GPString',
                               "Optional", "Input", False, None, True, None)

    previous_scene = parameter("Previous Scene", "PreviousScene", "GPString",
                               "Required", "Input", False, None, False, None)

    # out_layer = parameter("Output feature class", "layer", "DEFeatureClass",
    #                       "Required", "Output", False, None, True, None)

    modification_type.filter.list = ["Add", "Remove"]
    operation_type.filter.list = ["Clip", "Mask", "Replace"]
    modification_type.enabled = False
    polygon_fc.enabled = False
    operation_type.enabled = False
    polygon_fc.value = None
    operation_type.value = None

    # get Online GIS connection -> store as global
    token = arcpy.GetSigninToken()
    if token:
        gis = GIS("pro")
        scene_list = list()

        # get list of web scenes with integrated mesh layers
        layer_type = "IntegratedMeshLayer"
        web_scene_objs = bm_layer_lib.get_mesh_web_scenes(gis, gis.properties.id, [gis.users.me.username],
                                                          layer_type)
        for ws in web_scene_objs:
            webscene_name = ws.title + " (id: " + ws.id + ")"
            scene_list.append(webscene_name)

        web_scenes.filter.list = sorted(scene_list)

    params = [web_scenes, mesh_layer, modification_type, polygon_fc, operation_type, previous_scene]
    return params


def update_parameter_info_set_mesh_modification(params, supported_versions):

    if params[0].value:
        # if the scene changes
        if params[0].value != params[5].value:
            params[1].value = None
            params[1].filter.list = []
            params[5].value = params[0].value
            params[3].enabled = False
            params[4].enabled = False
            params[3].value = None
            params[4].value = None

            if len(params[0].filter.list) > 0:
                # get mesh layer for selected scene
                selected_scene = bm_layer_lib.select_map_scene_by_title(web_scene_objs, params[0].value)
                mesh_list = bm_layer_lib.get_mesh_layers_from_web_scene(gis, selected_scene)
                if len(mesh_list) > 0:
                    params[1].filter.list = sorted(mesh_list)
                    params[2].enabled = True
                else:
                    params[1].value = "not found!"
                    params[2].enabled = False

                params[3].enabled = False
                params[4].enabled = False
                params[3].value = None
                params[4].value = None
        else:
            if params[2].value == "Add":
                params[3].enabled = True
                params[4].enabled = True
            else:
                params[3].enabled = False
                params[4].enabled = False
                params[3].value = None
                params[4].value = None
    return


def update_messages_set_mesh_modification(params, tool_label, supported_versions):

    if params[0].value:
        selected_scene = bm_layer_lib.select_map_scene_by_title(web_scene_objs, params[0].value)
        mesh_list = bm_layer_lib.get_mesh_layers_from_web_scene(gis, selected_scene)

        if params[1].value == "not found!":
            params[1].setErrorMessage('Web scene has no integrated mesh layers! Please select a web scene with '
                                      'one or more integrated mesh layers')
        elif params[1].value not in mesh_list:
            if len(mesh_list) > 0:
                params[1].filter.list = sorted(mesh_list)
            else:
                params[1].setErrorMessage('Select integrated mesh layer!')
                params[1].value = "not found!"
                params[1].setErrorMessage('Web scene has no integrated mesh layers!')
        else:
            params[1].clearMessage()
        if params[2].value:
            if params[2].value == "Add":
                if params[3].value == "" or not params[3].value:
                    params[3].setErrorMessage('No layer selected!')

                if params[4].value == "" or not params[4].value:
                    params[4].setErrorMessage('Please set Operation Type.')
                else:
                    params[4].clearMessage()
            else:
                params[3].clearMessage()
                params[3].value = None
                params[4].clearMessage()
                params[4].value = None

    return


def execute_set_mesh_modification(parameters, tool):
    class NoOutput(Exception):
        pass

    try:
        """The source code of the tool."""
        (web_scenes, mesh_layer, modification_type, polygon_fc, operation_type, previous_scene) = \
            [p.valueAsText for p in parameters]

        pro_version = arcpy.GetInstallInfo()['Version']

        if int(pro_version[0]) >= 2 and int(pro_version[2]) >= 7 or int(pro_version[0]) >= 3:
            arcpy.AddMessage("ArcGIS Pro version: " + pro_version)
        else:
            raise ProVersionRequired

        # script variables
        aprx = arcpy.mp.ArcGISProject("CURRENT")
        home_directory = aprx.homeFolder

        if os.path.exists(os.path.join(home_directory, "p20")):  # it is a package
            home_directory = os.path.join(home_directory, "p20")

        log_directory = home_directory + "\\Logs"
        temp_directory = home_directory + "\\temp_files"
        bm_common_lib.set_up_logging(log_directory, SETMESHMODIFICATIONTOOL)

        selected_scene = bm_layer_lib.select_map_scene_by_title(web_scene_objs, web_scenes)

        if modification_type:
            modification_type = modification_type.lower()

        if operation_type:
            operation_type = operation_type.lower()

        success = im_mod.scene_modifications(aprx=None,
                                             gis=gis,
                                             scene_id=selected_scene.id,
                                             mesh_layer=mesh_layer,
                                             polygon_features=polygon_fc,
                                             modification_type=modification_type,
                                             operation_type=operation_type,
                                             temp_dir=temp_directory,
                                             debug=0)

    except ProVersionRequired:
        print("This functionality requires ArcGIS Pro 2.7 or higher")
        arcpy.AddError("This functionality requires ArcGIS Pro 2.7 or higher")

    except NoOutput:
        print("Can't create output. Exiting...")
        arcpy.AddError("Can't create output. Exiting...")


# TOOL CLASSES
class ProVersionRequired(Exception):
    pass


class SetMeshModification(object):

    def __init__(self):
        """Define the tool (tool name is the name of the class)."""
        self.label = "Modify Integrated Mesh in Web Scene"
        self.supported_versions = bm_common_lib.get_min_supported_version("web_scene_info")
        self.description = "Modifies an integrated mesh in a web scene."
        self.canRunInBackground = False
        self.tool = "ModifyMeshWebscene"

    def getParameterInfo(self):
        """Define parameter definitions"""
        return get_parameter_info_set_mesh_modification(self.label)

    def isLicensed(self):
        """Set whether tool is licensed to execute."""
        return True

    def updateParameters(self, params):
        """Modify the values and properties of parameters before internal
        validation is performed.  This method is called whenever a parameter
        has been changed."""
        update_parameter_info_set_mesh_modification(params, self.supported_versions)
        return

    def updateMessages(self, params):
        """Modify the messages created by internal validation for each tool
        parameter.  This method is called after internal validation."""
        update_messages_set_mesh_modification(params, self.label, self.supported_versions)
        return

    def execute(self, params, messages):
        execute_set_mesh_modification(params, self.tool)
        return


# Add web map to web scene tool
def get_parameter_info_add_webmap_to_webscene(tool_label):
    '''
    This function sets the UI parameters for the tool.
    :param tool_label:
    :return:
    '''

    # unfortunately we need to use globals as it is the only way to share info between
    # the pyt calls and reduce calls to the org
    global gis
    global web_map_objs
    global web_scene_objs

    web_maps = parameter("Web Map", "SelectWebMap", "GPString",
                         "Required", "Input", False, None, True, None)

    web_scenes = parameter("Web Scene (optional)", "SelectWebScene", "GPString",
                           "Optional", "Input", False, None, True, None)

    extrusion_unit = parameter("Extrusion unit", "ExtrusionUnit", "GPString",
                               "Required", "Input", False, None, True, None)

    offset = parameter("Layer Offset", "LayerOffset", "GPDouble",
                       "Required", "Input", False, None, True, None)

    previous_map = parameter("Previous Map", "PreviousMap", "GPString",
                             "Required", "Input", False, None, False, None)

    previous_scene = parameter("Previous Scene", "PreviousScene", "GPString",
                               "Optional", "Input", False, None, False, None)

    offset.value = 0

    extrusion_unit.filter.list = ["Meters", "Feet", 'Centimeters', 'Inches']
    extrusion_unit.value = 'Meters'

    # get Online GIS connection -> store as global
    token = arcpy.GetSigninToken()
    if token:
        gis = GIS("pro")
        map_list = list()

        # get list of web maps
        web_map_objs = bm_layer_lib.get_web_maps(gis, gis.properties.id, [gis.users.me.username])
        for wm in web_map_objs:
            webmap_name = wm.title + " (id: " + wm.id + ")"
            map_list.append(webmap_name)

        web_maps.filter.list = sorted(map_list)

        scene_list = list()

        # get list of web maps
        web_scene_objs = bm_layer_lib.get_web_scenes(gis, gis.properties.id, [gis.users.me.username])
        for ws in web_scene_objs:
            webscene_name = ws.title + " (id: " + ws.id + ")"
            scene_list.append(webscene_name)

        web_scenes.filter.list = sorted(scene_list)

    params = [web_maps, web_scenes, extrusion_unit, offset, previous_map, previous_scene]
    return params


def update_parameter_info_add_webmap_to_webscene(params, supported_versions):
    if params[0].value:
        # if the map changes
        if params[0].value != params[4].value:
            params[4].value = params[0].value
        if params[1].value != params[5].value:
            params[5].value = params[1].value
    else:
        params[3].value = 0

    return


def update_messages_add_webmap_to_webscene(params, tool_label, supported_versions):

    return


def execute_add_webmap_to_webscene(parameters, tool):
    class NoOutput(Exception):
        pass

    try:
        """The source code of the tool."""
        (web_maps, web_scenes, extrusion_unit, offset, previous_map, previous_scene) = \
            [p.valueAsText for p in parameters]

        pro_version = arcpy.GetInstallInfo()['Version']

        if int(pro_version[0]) >= 2 and int(pro_version[2]) >= 8 or int(pro_version[0]) >= 3:
            arcpy.AddMessage("ArcGIS Pro version: " + pro_version)
        else:
            raise ProVersionRequired

        # script variables
        aprx = arcpy.mp.ArcGISProject("CURRENT")
        home_directory = aprx.homeFolder

        if os.path.exists(os.path.join(home_directory, "p20")):  # it is a package
            home_directory = os.path.join(home_directory, "p20")

        log_directory = home_directory + "\\Logs"
        temp_directory = home_directory + "\\temp_files"
        bm_common_lib.set_up_logging(log_directory, ADDWEBMAPTOWEBSCENETOOL)

        selected_map = bm_layer_lib.select_map_scene_by_title(web_map_objs, web_maps)
        selected_scene = bm_layer_lib.select_map_scene_by_title(web_scene_objs, web_scenes)

        input_sign_rpk_id = "sign_rpk_id"
        input_scene_service_item_id = "no_scene_service_item_id"
        fixed_layer_id = "create_layer_id"

        if selected_map:
            if selected_scene:
                scene_id = selected_scene.id
            else:
                scene_id = "no_scene_web_scene_id"

            success = A2Dto3D.auto2D_3D(gis_org=gis,
                                        item_id=selected_map.id,
                                        web_scene_id=scene_id,
                                        rpk_id=input_sign_rpk_id,
                                        units=extrusion_unit,
                                        scene_service_item_id=input_scene_service_item_id,
                                        fixed_layer_id=fixed_layer_id,
                                        offset=offset)

    except ProVersionRequired:
        print("This functionality requires ArcGIS Pro 2.7 or higher")
        arcpy.AddError("This functionality requires ArcGIS Pro 2.7 or higher")

    except NoOutput:
        print("Can't create output. Exiting...")
        arcpy.AddError("Can't create output. Exiting...")


class AddWebMapToWebScene(object):

    def __init__(self):
        """Define the tool (tool name is the name of the class)."""
        self.label = "Add Web Map to Web Scene"
        self.supported_versions = bm_common_lib.get_min_supported_version("web_scene_info")
        self.description = "Adds a web map to web scene."
        self.canRunInBackground = False
        self.tool = "AddWebMapToWebScene"

    def getParameterInfo(self):
        """Define parameter definitions"""
        return get_parameter_info_add_webmap_to_webscene(self.label)

    def isLicensed(self):
        """Set whether tool is licensed to execute."""
        return True

    def updateParameters(self, params):
        """Modify the values and properties of parameters before internal
        validation is performed.  This method is called whenever a parameter
        has been changed."""
        update_parameter_info_add_webmap_to_webscene(params, self.supported_versions)
        return

    def updateMessages(self, params):
        """Modify the messages created by internal validation for each tool
        parameter.  This method is called after internal validation."""
        update_messages_add_webmap_to_webscene(params, self.label, self.supported_versions)
        return

    def execute(self, params, messages):
        execute_add_webmap_to_webscene(params, self.tool)
        return
