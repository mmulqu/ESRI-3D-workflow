# Prototype - Publish a feature collection to a web scene

import scripts.A3D_common_lib as A3D_common_lib
import scripts.bm_common_lib as bm_common_lib
import scripts.A3D_point as A3D_point
import scripts.A3D_line as A3D_line
import scripts.A3D_poly as A3D_poly
import json
import copy
import arcgis
from string import Template
import arcpy


def get_default_labeling_info():
    json_string = """{
        "labelingInfo": [
            {
                "labelExpressionInfo": {
                    "expression": "$feature[\\"name\\"]"
                },
                "labelPlacement": "esriServerPointLabelPlacementAboveCenter",
                "symbol": {
                    "type": "LabelSymbol3D",
                        "symbolLayers": [
                            {
                                "type": "Text",
                                "halo": {
                                  "color": [
                                    0,
                                    0,
                                    0
                                  ],
                                  "transparency": 0,
                                  "size": 1
                                },
                                "material": {
                                  "color": [
                                    255,
                                    255,
                                    255
                                  ]
                                },
                                "size": 11
                            }
                        ]
                },
                "useCodedValues": true
            }
        ]
    }"""

    labeling_info_dict = json.loads(json_string)

    return labeling_info_dict


def get_elevation_info():
    json_string = """{
        "elevationInfo":
        {
            "featureExpressionInfo": {
                "expression": ""
            },
            "mode": "onTheGround",
            "offset": 0,
            "unit": "foot"
        }
    }"""

    elevation_info_dict = json.loads(json_string)

    return elevation_info_dict


def get_single_ops_layers():
    json_string = """{
        "operationalLayers": [
            {
                "title": "",
                "url": "",
                "itemId": "",
                "layerType": "",
                "visibility": true,
                "opacity": 1,
                "layerDefinition": {
                    "elevationInfo": {
                        "mode": "onTheGround",
                        "offset": 0
                    },
                    "featureReduction": {
                        "type": "selection"
                    },
                    "drawingInfo": {
                        "labelingInfo": [
                        ],
                        "renderer": {
                        }
                    },
                    "minScale": 0,
                    "maxScale": 0
                },
                "popupInfo": {
                }
            }
        ]    
    }"""

    single_ops_layers_dict = json.loads(json_string)

    return single_ops_layers_dict


def get_multi_ops_layers():
    json_string = """{
        "layers": [
            {
                "id": "",
                "opacity": 1,
                "title": "",
                "url": "",
                "visibility": true,
                "screenSizePerspective": true,
                "layerType": "",
                "itemId": "",                 
                "layerDefinition": {
                    "elevationInfo": {
                        "mode": "onTheGround",
                        "offset": 0
                    },
                    "featureReduction": {
                        "type": "selection"
                    },
                    "drawingInfo": {
                        "labelingInfo": [
                        ],
                        "renderer": {
                        }
                    },
                    "minScale": 0,
                    "maxScale": 0                    
                },
                "popupInfo": {
                }
            }
        ]
    }"""

    layer_dict = json.loads(json_string)

    return layer_dict


def get_group_operation_layers():
    json_string = """{
        "operationalLayers": [
            {
                "id": "",
                "layerType": "GroupLayer",
                "visibilityMode": "independent",
                "listMode": "show",
                "maxScale": 0,
                "minScale": 0,
                "opacity": 1,
                "title": "",
                "visibility": true,
                "layers": [
                ]
            }
        ]    
    }"""

    ops_layer_dict = json.loads(json_string)

    return ops_layer_dict


def get_web_scene_dictionary():

    web_scene_template = Template("""{
            "operationalLayers": [
            ],
            "baseMap": {
                "baseMapLayers": [
                    {
                        "id": "World_Imagery_2017",
                        "title": "World Imagery",
                        "url": "https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer",
                        "layerType": "ArcGISTiledMapServiceLayer"
                    },
                    {
                        "id": "VectorTile_7259",
                        "title": "Hybrid Reference Layer",
                        "layerType": "VectorTileLayer",
                        "styleUrl": "https://cdn.arcgis.com/sharing/rest/content/items/$id/resources/styles/root.json",
                        "isReference": true
                    }
                ],
                "id": "17aac011a9b-basemap-7",
                "title": "Imagery Hybrid",
                "elevationLayers": [
                    {
                        "id": "globalElevation",
                        "listMode": "hide",
                        "title": "Terrain3D",
                        "url": "https://elevation3d.arcgis.com/arcgis/rest/services/WorldElevation3D/Terrain3D/ImageServer",
                        "layerType": "ArcGISTiledElevationServiceLayer"
                    }
                ]
            },
            "ground": {
                "layers": [
                    {
                        "id": "globalElevation",
                        "listMode": "hide",
                        "title": "Terrain3D",
                        "url": "https://elevation3d.arcgis.com/arcgis/rest/services/WorldElevation3D/Terrain3D/ImageServer",
                        "layerType": "ArcGISTiledElevationServiceLayer"
                    }
                ],
                "transparency": 0,
                "navigationConstraint": {
                    "type": "stayAbove"
                }
            },
            "heightModelInfo": {
                "heightModel": "gravity_related_height",
                "heightUnit": "meter"
            },
            "version": "1.18",
            "authoringApp": "WebSceneViewer",
            "authoringAppVersion": "7.4.0.0",
            "initialState": {
                "environment": {
                    "lighting": {
                        "datetime": 1584273600000,
                        "displayUTCOffset": 0
                    },
                    "atmosphereEnabled": true,
                    "starsEnabled": true
                },
                "viewpoint": {
                    "camera": {
                        "position": {
                            "spatialReference": {
                                "latestWkid": 3857,
                                "wkid": 102100
                            },
                            "x": 0,
                            "y": 1959185.6694388972,
                            "z": 14834498.78284432
                          },
                        "heading": 0,
                        "tilt": 0.15033641811791382
                    }
                }
            },
            "spatialReference": {
                "latestWkid": 3857,
                "wkid": 102100
            },
            "viewingMode": "global"
        }""")

    # to get around clone_items issue with ids in Notebook
    item_id = '30d6b8271e1849' + 'cd9c3042060001f425'
    json_string = web_scene_template.substitute(id=item_id)
    web_scene_dict = json.loads(json_string)

    return web_scene_dict


def get_web_scene_dictionary_old():
    json_string = """{
        "operationalLayers": [
        ],
        "baseMap": {
            "baseMapLayers": [
                {
                    "id": "World_Imagery_2017",
                    "title": "World Imagery",
                    "url": "https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer",
                    "layerType": "ArcGISTiledMapServiceLayer"
                },
                {
                    "id": "VectorTile_7259",
                    "title": "Hybrid Reference Layer",
                    "layerType": "VectorTileLayer",
                    "styleUrl": "https://cdn.arcgis.com/sharing/rest/content/items/30d6b8271e1849cd9c3042060001f425/resources/styles/root.json",
                    "isReference": true
                }
            ],
            "id": "17aac011a9b-basemap-7",
            "title": "Imagery Hybrid",
            "elevationLayers": [
                {
                    "id": "globalElevation",
                    "listMode": "hide",
                    "title": "Terrain3D",
                    "url": "https://elevation3d.arcgis.com/arcgis/rest/services/WorldElevation3D/Terrain3D/ImageServer",
                    "layerType": "ArcGISTiledElevationServiceLayer"
                }
            ]
        },
        "ground": {
            "layers": [
                {
                    "id": "globalElevation",
                    "listMode": "hide",
                    "title": "Terrain3D",
                    "url": "https://elevation3d.arcgis.com/arcgis/rest/services/WorldElevation3D/Terrain3D/ImageServer",
                    "layerType": "ArcGISTiledElevationServiceLayer"
                }
            ],
            "transparency": 0,
            "navigationConstraint": {
                "type": "stayAbove"
            }
        },
        "heightModelInfo": {
            "heightModel": "gravity_related_height",
            "heightUnit": "meter"
        },
        "version": "1.18",
        "authoringApp": "WebSceneViewer",
        "authoringAppVersion": "7.4.0.0",
        "initialState": {
            "environment": {
                "lighting": {
                    "datetime": 1584273600000,
                    "displayUTCOffset": 0
                },
                "atmosphereEnabled": true,
                "starsEnabled": true
            },
            "viewpoint": {
                "camera": {
                    "position": {
                        "spatialReference": {
                            "latestWkid": 3857,
                            "wkid": 102100
                        },
                        "x": 0,
                        "y": 1959185.6694388972,
                        "z": 14834498.78284432
                      },
                    "heading": 0,
                    "tilt": 0.15033641811791382
                }
            }
        },
        "spatialReference": {
            "latestWkid": 3857,
            "wkid": 102100
        },
        "viewingMode": "global"
    }"""

    web_scene_dict = json.loads(json_string)

    return web_scene_dict


def set_elevation_info(added_layer, layer_info, geom_type, global_info, label, layer_item_info):
    # set elevationInfo
    # Check if input item has Z values
    #   if yes: set elevationInfo to absolute height
    #   if no: check if there is an elevation attribute
    #       if yes: set elevation to attribute
    #       if no: keep existing rendering

    # check if we have a elevation attribute
    lyr_properties = layer_info.layer_properties
    useful_z_values = False
    try:
        if lyr_properties.hasZ:
            useful_z_values = A3D_common_lib.check_z_values(layer_info.url, geom_type)
    except:
        pass

    # check if an elevation attribute is present
    if not useful_z_values:
        if layer_info.elevation_attribute:
            create_service = False
            if not create_service:
                expression = "$feature." + layer_info.elevation_attribute
                elevation_info = get_elevation_info()['elevationInfo']
                elevation_info['featureExpressionInfo']['expression'] = expression
                added_layer['layerDefinition']['elevationInfo'] = elevation_info
                added_layer['layerDefinition']['elevationInfo']['mode'] = 'absoluteHeight'

                if 'feet' in global_info.object_units.lower() or 'foot' in global_info.object_units.lower():
                    added_layer['layerDefinition']['elevationInfo']['unit'] = 'foot'
                elif 'meter' in global_info.object_units.lower():
                    added_layer['layerDefinition']['elevationInfo']['unit'] = 'meter'

                if label:
                    added_layer['layerDefinition']['elevationInfo']['offset'] = 3
            else:
                # TODO not used currently, we are using attribute mapping for 3D: remove eventually
                if lyr_properties:
                    lyr_properties_copy = lyr_properties
                    lyr_properties_copy.hasZ = True

                    # get 3D item
                    item_3D = A3D_poly.get_item_3D(global_info, layer_info, layer_item_info, lyr_properties_copy)

                    if item_3D:
                        useful_z_values = True
                        layer_info.item_id = item_3D.id
                        layer_info.url = item_3D.layers[0].url
                        layer_info.title = item_3D.name

                        added_layer['id'] = layer_info.title + "-layer-" + str(0)
                        added_layer['itemId'] = layer_info.item_id
                        added_layer['title'] = layer_info.title
                        added_layer['url'] = layer_info.url
        else:
            if geom_type == 'esriGeometryPolygon':
                added_layer['layerDefinition']['elevationInfo']['mode'] = 'onTheGround'
            else:
                added_layer['layerDefinition']['elevationInfo']['mode'] = 'relativeToScene'
                added_layer['layerDefinition']['elevationInfo']['offset'] = global_info.layer_offset
    else:
        added_layer['layerDefinition']['elevationInfo']['mode'] = 'absoluteHeight'

        if label:
            added_layer['layerDefinition']['elevationInfo']['offset'] = 3


def translate_lbl_info(label_info, label_placement):

    updated_label_info = get_default_labeling_info()['labelingInfo']
    updated_label_info[0]['labelExpressionInfo']['expression'] = label_info[0].labelExpressionInfo.expression
    updated_label_info[0]['labelPlacement'] = label_placement

    text_size = label_info[0]['symbol']['font']['size']
    updated_label_info[0]['symbol']['symbolLayers'][0]['size'] = text_size

    lbl_color = label_info[0]['symbol']['color']
    lbl_rgb_list = [lbl_color[0], lbl_color[1], lbl_color[2]]
    updated_label_info[0]['symbol']['symbolLayers'][0]['material']['color'] = lbl_rgb_list

    halo_size = label_info[0]['symbol']['haloSize']
    updated_label_info[0]['symbol']['symbolLayers'][0]['halo']['size'] = halo_size

    if halo_size > 0:
        try:
            halo_color = label_info[0]['symbol']['haloColor']
            halo_rgb_list = [halo_color[0], halo_color[1], halo_color[2]]
            updated_label_info[0]['symbol']['symbolLayers'][0]['halo']['color'] = halo_rgb_list
        except:
            pass

    return updated_label_info


def check_tag_in_ops_layer_title(layer_dict, unique_tag):
    found = False

    # for now only do PyPRT
    if "PyPRT" in layer_dict.get('title'):
        if unique_tag in layer_dict.get('title'):
            found = True

        # without underscore
        test_unique_tag = unique_tag.replace("_", " ")
        if test_unique_tag in layer_dict.get('title'):
            found = True

    return found


def map_item_type_to_web_scene(item, type_from_item, url):

    #   possibilities
    #   service type: Feature Service     | item title: Feature Layer Collection  -> ArcGISFeatureLayer
    #   service type: Scene Service:
    #   service type: Map Service         | item title: Map Image Layer           -> ArcGISTiledMapServiceLayer
    #   service type: Map Service / tiled
    #   service type: Vector Tile Service | item title: Vector Tile Layer -> VectorTileLayer
    #   service type: Image Service       | item title: Imagery Layer -> ArcGISImageServiceLayer

    # TODO: test all types
    type_dict = {"Building Scene Service": "BuildingSceneLayer",
                 "CSV": "CSV",
                 "Feature Service": "ArcGISFeatureLayer",
                 "Group Layer": "Group Layer",
                 "Image Service": "ArcGISImageServiceLayer",
                 "Mesh Service": "IntegratedMeshLayer",
                 "KML": "KML",
                 "Map Service": "ArcGISMapServiceLayer",
                 "Point Cloud Service": "PointCloudLayer",
                 "Raster Service": "RasterDataLayer",
                 "Scene Service": "ArcGISSceneServiceLayer",
                 "Tiled Image Service": "ArcGISTiledImageServiceLayer",
                 "Tiled Map Service":  "ArcGISTiledMapServiceLayer",
                 "Vector Tile Service": "VectorTileLayer",
                 "Web Tiled Service": "WebTiledLayer",
                 "WMS": "WMS"
                 }

    # TODO fix: massive hack
    if type_from_item == "Map Service" and "tiles" in url:
        return "ArcGISTiledMapServiceLayer"
    elif "type:Map Image Layer" in str(item):
        return "ArcGISMapServiceLayer"
    elif "type:Feature Layer" in str(item):
        return "ArcGISFeatureLayer"
    elif "type:Vector Tile Layer" in str(item):
        return "VectorTileLayer"
    elif "type:Imagery Layer" in str(item):
        return "ArcGISImageServiceLayer"
    elif type_from_item == "Scene Service":    # check if Building layer
        if A3D_common_lib.is_typeof_scene_service(item, 'Building'):
            return "BuildingSceneLayer"
        elif A3D_common_lib.is_typeof_scene_service(item, 'IntegratedMesh'):
            return "IntegratedMeshLayer"
        else:
            return type_dict[type_from_item]
    else:
        return type_dict[type_from_item]


def update_added_scene_layer(global_info, added_layer, layer_info, i):
    arcpy.AddMessage("Updating 3D rendering for layer: " + layer_info.title + ".")
    layer_item = global_info.gis.content.get(layer_info.item_id)

    try:
        item_folder = layer_item.ownerFolder
    except:
        item_folder = None

    # store in class
    layer_item_info = A3D_common_lib.ItemInfo(layer_item, item_folder)

    # check if there is any rendering info stored on the item, if so, we will use this.
    item_data_layers = A3D_common_lib.get_item_data(layer_item_info.item_id, global_info.org_content_items_url,
                                                    global_info.token)

    renderer = None
    if item_data_layers:
        for idl in item_data_layers:
            try:
                if layer_info.layer_no_id == idl.get('id'):
                    try:
                        ld = idl.get('layerDefinition')
                        di = ld.get('drawingInfo')
                        renderer = di.get('renderer')
                        break
                    except:
                        renderer = None
            except:
                renderer = None

    type_for_scene = map_item_type_to_web_scene(layer_item_info.item, layer_item_info.item_type,
                                                layer_item_info.item.url)

    if global_info.web_scene_layer_id == "create_layer_id":
        added_layer['id'] = layer_info.title + "-layer-" + str(i)
    else:
        added_layer['id'] = global_info.web_scene_layer_id

    added_layer['itemId'] = layer_info.item_id
    added_layer['title'] = layer_info.title
    added_layer['url'] = layer_info.url
    added_layer['layerType'] = type_for_scene

    # initially set to webmap / feature layer settings
    deleted_renderer = False
    if layer_info.rendering_info:
        # check if item data has rendering info or comes from unique_tag generation. If so delete the predefined
        if renderer:
            del added_layer['layerDefinition']['drawingInfo']['renderer']
            deleted_renderer = True
        else:
            added_layer['layerDefinition']['drawingInfo']['renderer'] = layer_info.rendering_info

    deleted_labeling = False
    if layer_info.labeling_info:
        added_layer['layerDefinition']['drawingInfo']['labelingInfo'] = layer_info.labeling_info
    else:
        del added_layer['layerDefinition']['drawingInfo']['labelingInfo']
        deleted_labeling = True

    if deleted_labeling and deleted_renderer:
        del added_layer['layerDefinition']['drawingInfo']

    if layer_info.popup_info:
        added_layer['popupInfo'] = layer_info.popup_info
    else:
        del added_layer['popupInfo']

    # set elevation mode
    # if rendering on the layer item , we assume web styles which need to be on the ground
    if not renderer:
        added_layer['layerDefinition']['elevationInfo']['mode'] = 'absoluteHeight'


def update_added_feature_layer(global_info, added_layer, layer_info, i):
    '''
        try and update the rendering of the feature layer so it looks good in 3D

        :param global_info: global_info object
        :param added_layer: the layer that will be added
        :param layer_info: layer_info for the layer that will be added
        :param i: number of the layer added

    '''
    arcpy.AddMessage("Updating 3D rendering for layer: " + layer_info.title + ".")
    layer_item = global_info.gis.content.get(layer_info.item_id)

    try:
        item_folder = layer_item.ownerFolder
    except:
        item_folder = None

    # store in class
    layer_item_info = A3D_common_lib.ItemInfo(layer_item, item_folder)
    type_for_scene = map_item_type_to_web_scene(layer_item_info.item, layer_item_info.item_type,
                                                layer_item_info.item.url)

    lyr_properties = layer_info.layer_properties
    geom_type = lyr_properties.geometryType

    added_layer['id'] = layer_info.title + "-layer-" + str(i)
    added_layer['itemId'] = layer_info.item_id
    added_layer['title'] = layer_info.title
    added_layer['url'] = layer_info.url
    added_layer['layerType'] = type_for_scene

    # initially set to incoming webmap / feature layer settings
    if layer_info.rendering_info:
        added_layer['layerDefinition']['drawingInfo']['renderer'] = layer_info.rendering_info

    if layer_info.labeling_info:
        added_layer['layerDefinition']['drawingInfo']['labelingInfo'] = layer_info.labeling_info
    else:
        del added_layer['layerDefinition']['drawingInfo']['labelingInfo']

    if layer_info.popup_info:
        added_layer['popupInfo'] = layer_info.popup_info
    else:
        del added_layer['popupInfo']

    # overwrite with 3D specific settings
    # attributes in settings_3dbasemaps.json are case sensitive!

    # check if the data has an extrusion attribute
    extrude_attr_list = bm_common_lib.get_info_from_json("settings_3dbasemaps.json", "web_scene_info",
                                                         "extrude_attributes")
    layer_info.extrude_attribute = A3D_common_lib.get_first_attribute(layer_info.url, extrude_attr_list)

    # check if the data has an elevation attribute
    elevation_attr_list = bm_common_lib.get_info_from_json("settings_3dbasemaps.json", "web_scene_info",
                                                           "elevation_attributes")
    layer_info.elevation_attribute = A3D_common_lib.get_first_attribute(layer_info.url, elevation_attr_list)

    if geom_type == 'esriGeometryPoint':
        # set 3D point rendering
        A3D_point.set_3D_point_layer_definition(added_layer, layer_info, geom_type, global_info)

    if geom_type == 'esriGeometryPolyline':
        A3D_line.set_3D_line_layer_definition(added_layer, layer_info, geom_type, global_info)

    if geom_type == 'esriGeometryPolygon':
        # check if we have a 'floor' attribute, if so create new feature service and link to original
        floor_attr_list = bm_common_lib.get_info_from_json("settings_3dbasemaps.json", "web_scene_info",
                                                           "floors_attributes")
        layer_info.floor_attribute = A3D_common_lib.get_first_attribute(layer_info.url, floor_attr_list)

        basement_attr_list = bm_common_lib.get_info_from_json("settings_3dbasemaps.json", "web_scene_info",
                                                              "basement_attributes")
        layer_info.basement_attribute = A3D_common_lib.get_first_attribute(layer_info.url, basement_attr_list)

        layer_info.floor_height = bm_common_lib.get_info_from_json("settings_3dbasemaps.json",
                                                                   "web_scene_info",
                                                                   "floor_height")
        layer_info.levelid_attribute = bm_common_lib.get_info_from_json("settings_3dbasemaps.json",
                                                                        "web_scene_info",
                                                                        "level_id_attribute")

        if layer_info.floor_attribute:
            item_3D = A3D_poly.create_polygonZ_feature_layer(layer_info, global_info, layer_item_info)

            if item_3D:
                layer_info.item_id = item_3D.id
                layer_info.url = item_3D.layers[0].url
                layer_info.title = item_3D.name

                added_layer['id'] = layer_info.title + "-layer-" + str(0)
                added_layer['itemId'] = layer_info.item_id
                added_layer['title'] = layer_info.title
                added_layer['url'] = layer_info.url

        A3D_poly.set_3D_poly_layer_definition(added_layer, layer_info, geom_type, global_info, layer_item_info)


def update_ops_layers_with_layer(global_info, the_list, layer_info):

    # check if we have existing layers (the_list)
    add = True
    update = False

    if len(the_list) > 0:
        # ops list check on similar titles
        for exist_layer in the_list:
            existing_item_url = exist_layer.get('url')
            existing_item_id = exist_layer.get('itemId')
            if layer_info.url == existing_item_url and layer_info.item_id == existing_item_id:
                add = False

                # if same url and fixed layer id, change layer_id (for tree solution)
                if not global_info.web_scene_layer_id == "create_layer_id":
                    exist_layer['id'] = global_info.web_scene_layer_id
                    update = True
                break

    # if the layer title is not in existing ops layers, add it
    if add:
        update = True

        # check for group layer
        if layer_info.group_layer:
            default_group_op_layer_list = get_group_operation_layers()['operationalLayers']
            the_list.append(copy.deepcopy(default_group_op_layer_list[0]))

            # set group info
            the_list[-1]['id'] = layer_info.title + "-group-layer"
            the_list[-1]['title'] = layer_info.title

            default_layer_list = get_multi_ops_layers()['layers']

            i = 0
            for sub_layer_info in layer_info.sub_layer_info_list:
                # layer_type = sub_layer_info.layer_properties.type

                the_list[-1]['layers'].append(copy.deepcopy(default_layer_list[0]))
                added_layer = the_list[-1]['layers'][-1]

                if 'FeatureServer' in sub_layer_info.url or 'MapServer' in layer_info.url:
                    #if 'Feature' in layer_type:
                    update_added_feature_layer(global_info, added_layer, sub_layer_info, i)
                    i += 1

                if 'SceneServer' in sub_layer_info.url:
                    #if 'Scene' in layer_type:
                    update_added_scene_layer(global_info, added_layer, sub_layer_info, i)
                    i += 1
        else:
            layer_type = layer_info.layer_type
            default_op_layer_list = get_single_ops_layers()['operationalLayers']

            the_list.append(copy.deepcopy(default_op_layer_list[0]))
            added_layer = the_list[-1]

            if 'FeatureServer' in layer_info.url or 'MapServer' in layer_info.url:
                # if 'Feature' in layer_type:
                update_added_feature_layer(global_info, added_layer, layer_info, 0)

            if 'SceneServer' in layer_info.url or '3DObject' in layer_type:
                # if 'Scene' in layer_type or '3DObject' in layer_type:
                update_added_scene_layer(global_info, added_layer, layer_info, 0)
    else:
        arcpy.AddMessage("Layer (" + layer_info.title + ") is already present in the input web scene...")
        arcpy.AddMessage("Add the layer manually to have multiple copies of the layer in the web scene.")

    return update


def add_scene_layers(global_info, web_scene_item, layer_info_list):
    '''
        add the layers found in the webmap or featire collection to an existing or new web scene
        :param global_info: global_info object
        :param web_scene_item: the web scene item
        :layer_info_list: list of all layer found plus info
    '''
    web_scene_obj = arcgis.mapping.WebScene(web_scene_item)
    existing_ops_layers = web_scene_obj['operationalLayers']
    update_web_scene = False

    # remove any entry with unique_tag in the existing ops list (because we are creating a new layer
    # with unique tag (street signs)
    if global_info.unique_tag:
        existing_ops_layers = [x for x in existing_ops_layers
                               if not check_tag_in_ops_layer_title(x, global_info.unique_tag)]

    if layer_info_list:
        # Step through layers in layer_info_list and create operational layers for web scene.
        for new_layer_info in layer_info_list:
            if new_layer_info.group_layer:
                for new_sub_layer_info in new_layer_info.sub_layer_info_list:
                    if new_sub_layer_info.process_layer:
                        if update_ops_layers_with_layer(global_info, existing_ops_layers, new_sub_layer_info):
                            update_web_scene = True
            else:
                if new_layer_info.process_layer:
                    if update_ops_layers_with_layer(global_info, existing_ops_layers, new_layer_info):
                        update_web_scene = True

        if update_web_scene:
            web_scene_obj['operationalLayers'] = existing_ops_layers
            web_scene_obj.update()

            try:
                scene_item_folder = web_scene_item.ownerFolder
            except:
                scene_item_folder = None

            if scene_item_folder:
                arcpy.AddMessage("Updated web scene with id: " + web_scene_item.id + " in folder: " +
                                 A3D_common_lib.get_foldername_user(global_info.gis.users.me,
                                                                    scene_item_folder) +
                                 " in your organization.")
            else:
                arcpy.AddMessage("Updated web scene with id: " + web_scene_item.id + " in your organization.")
        else:
            arcpy.AddMessage("Did not update web scene with id: " + web_scene_item.id)

    return web_scene_item.id


# get info from webmap
def get_layer_info_from_webmap(webmap_item):
    layer_info_list = list()

    web_map_obj = arcgis.mapping.WebMap(webmap_item)
    map_ops_layers = web_map_obj.layers

    for map_layer in map_ops_layers:
        layer_info = A3D_common_lib.LayerInfo()
        layer_info.layer_id = map_layer.id
        layer_info.layer_type = map_layer.layerType
        layer_info.title = map_layer.title

        if layer_info.layer_type == 'GroupLayer':
            layer_info.group_layer = True
            layer_info.sub_layer_info_list = A3D_common_lib.get_layers_info(map_layer.layers)

            if len(layer_info.sub_layer_info_list) > 0:
                layer_info_list.append(layer_info)
        else:
            try:
                item_id = map_layer.itemId
            except:
                item_id = None

            if item_id:
                if A3D_common_lib.get_layer_info(map_layer, layer_info, item_id):
                    layer_info_list.append(layer_info)
            else:
                arcpy.AddMessage("Could not find the item for " + map_layer.title + " in your organization."
                                                                                    " Items outside your organization"
                                                                                    " can not be processed"
                                                                                    " at the moment.")

                print("Could not find the item for " + map_layer.title + " in your organization. Items outside"
                                                                         " your organization can not be processed"
                                                                         " at the moment.")

    return layer_info_list


# create default web scene
def create_web_scene(gis, web_scene_dict, input_item_info, title, desc):
    '''
            creates a default web scene
            :param gis: gis object
            :param web_scene_dict: default (empty) web scene json
            :param input_item_info: input feature collection item info
            :param title: default web scene title
            :param desc: default web scene description
            :return: web scene id
    '''

    web_scene_item = None

    # get the folder name
    folder = A3D_common_lib.get_foldername_user(gis.users.me, input_item_info.item_folder)

    if web_scene_dict:
        web_scene_item_properties = {'title': title,
                                     'type': 'Web Scene',
                                     'snippet': desc,
                                     'tags': 'Auto3D',
                                     'text': json.dumps(web_scene_dict)}

        # Use the add() method to publish a new web scene
        if folder:
            web_scene_item = gis.content.add(web_scene_item_properties, folder=folder)
        else:
            web_scene_item = gis.content.add(web_scene_item_properties)

        web_scene_item.share(True)

    return web_scene_item


def get_web_scene_item(global_info):
    web_scene_item = None
    input_item_info = global_info.input_item_info

    new_web_scene_title = input_item_info.item_title + global_info.web_scene_title_postfix
    new_web_scene_description = global_info.web_scene_description_prefix + input_item_info.item_title

    # check if input web scene exists
    if global_info.input_web_scene_id:
        web_scene_item = global_info.gis.content.get(global_info.input_web_scene_id)

    if not web_scene_item:
        # create default web scene
        arcpy.AddMessage("Creating a new web scene...")
              
        web_scene_item = create_web_scene(global_info.gis, get_web_scene_dictionary(),
                                          input_item_info,
                                          new_web_scene_title,
                                          new_web_scene_description)

        arcpy.AddMessage("Created new web scene with id: " + web_scene_item.id)

    return web_scene_item


