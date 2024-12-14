import json
import arcpy
import scripts.A3D_common_lib as A3D_common_lib
import scripts.A3D_wm2ws as A3D_wm2ws
import pandas as pd
import scripts.bm_common_lib as bm_common_lib


def get_default_extrude_polygon_symbol_3D():
    json_string = """{
        "symbol": {
            "type": "PolygonSymbol3D",
            "symbolLayers": [
                {
                  "type": "Extrude",
                  "size": 14,
                  "material": {
                      "color": [
                          255,
                          0,
                          0
                        ],
                        "transparency": 0
                  },
                  "edges": {
                      "type": "solid",
                      "color": [
                          0,
                          0,
                          0
                        ],
                        "transparency": 0,
                        "size": 1
                      }
                }
            ]
        }
    }"""

    default_extrude_polygon_symbol_3D_dict = json.loads(json_string)

    return default_extrude_polygon_symbol_3D_dict


def get_default_polygon_symbol_3D():
    json_string = """{
        "symbol": {
            "type": "PolygonSymbol3D",
            "symbolLayers": [
                {
                    "type": "Fill",
                    "material": {
                        "color": [
                            255,
                            0,
                            0
                          ],
                          "transparency": 0,
                          "colorMixMode": "replace"
                    },
                    "outline": {
                        "color": [0, 0, 0],
                        "size": 2
                    }
                }
            ]
        }
    }"""

    default_polygon_symbol_3D_dict = json.loads(json_string)

    return default_polygon_symbol_3D_dict


def update_polygon_symbol_3D(color, outline_color, outline_size):
    default_polygon_symbol_3D = get_default_polygon_symbol_3D()['symbol']
    default_polygon_symbol_3D['symbolLayers'][0]['material']['color'] = color

    if len(color) > 3:
        # convert transparency to opacity
        alpha_p = (color[3]/255)*100
        transparency = 100 - alpha_p

        default_polygon_symbol_3D['symbolLayers'][0]['material']['transparency'] = transparency

    default_polygon_symbol_3D['symbolLayers'][0]['outline']['color'] = outline_color
    default_polygon_symbol_3D['symbolLayers'][0]['outline']['size'] = outline_size

    return default_polygon_symbol_3D


def get_default_classbreak_3D():
    json_string = """{
        "classBreakInfos": [
            {
                "classMaxValue": 1.7976931348623157e+308,
                "symbol": {
                }
            }
        ]
    }"""

    default_polygon_symbol_3D_dict = json.loads(json_string)

    return default_polygon_symbol_3D_dict


def get_default_visualvariables_3D():
    json_string = """{
        "visualVariables": [
            {
                "type": "colorInfo",
                "field": "",
                "stops": [
                    {
                        "color": [
                          255,
                          255,
                          178,
                          255
                        ],
                        "value": 29
                    }
                ]
            },
            {
                "type": "sizeInfo",
                "field": "",
                "valueUnit": ""
            }
        ]
    }"""

    default_polygon_symbol_3D_dict = json.loads(json_string)

    return default_polygon_symbol_3D_dict


def get_default_authoringinfo_3D():
    json_string = """{
        "authoringInfo": {
              "lengthUnit": "meters",
               "visualVariables": [
                {
                    "field": "risklevel",
                    "maxSliderValue": 80,
                    "minSliderValue": 24,
                    "theme": "high-to-low",
                    "type": "colorInfo"
                }
            ]
        }
    }"""

    default_authoringinfo_3D_dict = json.loads(json_string)

    return default_authoringinfo_3D_dict


def default_classbreak_renderer_3D():

    # get default Polygon3DSymbol and update type and size
    default_polygon_symbol_3D = get_default_polygon_symbol_3D()['symbol']

    # set symbol on classbreak
    default_classbreak_3D = get_default_classbreak_3D()['classBreakInfos']
    default_classbreak_3D['classBreakInfos']['symbol'] = default_polygon_symbol_3D

    return default_classbreak_3D


def classbreak_to_visual_variable(added_layer, layer_info, extrude_attribute, extrusion_unit, renderer):
    try:
        color_attribute = layer_info.rendering_info.field
        classbreak_list = layer_info.rendering_info.classBreakInfos
        min_value = layer_info.rendering_info.minValue
        max_value = min_value

        cb_list = []
        # get dict of classbreaks
        for cb in classbreak_list:
            cb_dict = {'color': cb.symbol.color, 'value': cb.classMaxValue}
            if cb.classMaxValue > max_value:
                max_value = cb.classMaxValue

            cb_list.append(cb_dict)

        # set visualvariables on renderer
        default_visualvariables_3D = get_default_visualvariables_3D()['visualVariables']

        if renderer == 'visual_variables':
            authoring_info = layer_info.rendering_info.authoringInfo
            min_value = authoring_info.visualVariables[0].minSliderValue
            max_value = authoring_info.visualVariables[0].maxSliderValue
            visual_variables_info = layer_info.rendering_info.visualVariables
            default_visualvariables_3D[0] = visual_variables_info[0]
        else:
            default_visualvariables_3D[0]['field'] = color_attribute
            default_visualvariables_3D[0]['stops'] = cb_list

        default_visualvariables_3D[1]['field'] = extrude_attribute
        default_visualvariables_3D[1]['valueUnit'] = extrusion_unit.lower()
        added_layer['layerDefinition']['drawingInfo']['renderer'][
            'visualVariables'] = default_visualvariables_3D

        # set classbreak on renderer
        default_classbreak_3D = get_default_classbreak_3D()['classBreakInfos']
        default_polygon_symbol_3D = get_default_polygon_symbol_3D()['symbol']
        default_classbreak_3D[0]['symbol'] = default_polygon_symbol_3D

        if extrude_attribute:
            default_classbreak_3D[0]['symbol']['symbolLayers'][0]['size'] = 14
            default_classbreak_3D[0]['symbol']['symbolLayers'][0]['type'] = 'Extrude'

        added_layer['layerDefinition']['drawingInfo']['renderer']['classBreakInfos'] = default_classbreak_3D
        added_layer['layerDefinition']['drawingInfo']['renderer']['minValue'] = -1.7976931348623157e+308

        # set authoringInfo on renderer
        default_authoringinfo_3D = get_default_authoringinfo_3D()['authoringInfo']
        default_authoringinfo_3D['lengthUnit'] = extrusion_unit.lower()
        default_authoringinfo_3D['visualVariables'][0]['field'] = color_attribute
        default_authoringinfo_3D['visualVariables'][0]['maxSliderValue'] = max_value
        default_authoringinfo_3D['visualVariables'][0]['minSliderValue'] = min_value
        added_layer['layerDefinition']['drawingInfo']['renderer']['authoringInfo'] = default_authoringinfo_3D

        success = True
    except:
        success = False

    return success


def set_poly_classbreak_with_extrusion_renderer(added_layer, layer_info, extrude_attribute, extrusion_unit):
    try:
        renderer = 'no_renderer'

        try:
            renderer = layer_info.rendering_info.visualVariables
            renderer = 'visual_variables'
        except:
            pass

        try:
            renderer = layer_info.rendering_info.classificationMethod
            renderer = 'classification'
        except:
            pass

        # translate into visual variable renderer so we can extrude
        # TODO support other classbreak renderers
        if renderer != 'no_renderer':
            if not classbreak_to_visual_variable(added_layer, layer_info, extrude_attribute, extrusion_unit,
                                                 renderer):
                pass
                # del added_layer['layerDefinition']['drawingInfo']
        else:
            pass
            # del added_layer['layerDefinition']['drawingInfo']
    except:
        pass


def set_poly_simple_with_extrusion_renderer(added_layer, layer_info, extrude_attribute, extrusion_unit):

    try:
        # set visualvariables on renderer
        default_visualvariables_3D = get_default_visualvariables_3D()['visualVariables']
        del default_visualvariables_3D[0]   # Delete the first field
        default_visualvariables_3D[0]['field'] = extrude_attribute
        default_visualvariables_3D[0]['valueUnit'] = extrusion_unit.lower()

        added_layer['layerDefinition']['drawingInfo']['renderer'][
            'visualVariables'] = default_visualvariables_3D

        default_polygon_symbol_3D = get_default_polygon_symbol_3D()['symbol']

        # get existing color
        existing_symbol_color = layer_info.rendering_info.symbol.color
        rgb_list = [existing_symbol_color[0], existing_symbol_color[1], existing_symbol_color[2]]
        default_polygon_symbol_3D['symbolLayers'][0]['material']['color'] = rgb_list

        if extrude_attribute:
            default_polygon_symbol_3D['symbolLayers'][0]['size'] = 14
            default_polygon_symbol_3D['symbolLayers'][0]['type'] = 'Extrude'

        added_layer['layerDefinition']['drawingInfo']['renderer']['symbol'] = default_polygon_symbol_3D

        # set authoringInfo on renderer
        default_authoringinfo_3D = get_default_authoringinfo_3D()['authoringInfo']
        default_authoringinfo_3D['lengthUnit'] = extrusion_unit.lower()
        added_layer['layerDefinition']['drawingInfo']['renderer']['authoringInfo'] = default_authoringinfo_3D
    except:
        pass
#        del added_layer['layerDefinition']['drawingInfo']


def add_level_fields(fields_list):

    add_fields_list = list()

    for f in fields_list:
        new_field = dict()
        new_field['alias'] = f.get('name')
        new_field['defaultValue'] = None
        new_field['domain'] = None
        new_field['editable'] = True
        new_field['name'] = f.get('name')
        new_field['nullable'] = True
        new_field['sqlType'] = 'sqlTypeOther'
        new_field['type'] = f.get('type')
        add_fields_list.append(new_field)

    return add_fields_list


def create_levels(spatial_info, layer_info, global_info, below_ground):
    # copy feature for each floor level

    if not below_ground:
        arcpy.AddMessage("Found floor attribute. Creating floor geometries...")
        print("Found floor attribute. Creating floor geometries...")
        num_level_attribute = layer_info.floor_attribute
    else:
        arcpy.AddMessage("Found basement attribute. Creating basement geometries...")
        print("Found basement attribute. Creating basement geometries...")
        num_level_attribute = layer_info.basement_attribute

    sdf = A3D_common_lib.create_feature_copies(spatial_info, num_level_attribute, below_ground)

    if sdf is not None:
        # calculate elevation_attribute based on original elevation and floor_height
        # conv_factor = A3D_common_lib.unit_conversion(spatial_info.linear_unit,
        #                                              global_info.object_units, 0)
        #
        # A3D_common_lib.set_level_elevation_attribute(sdf, layer_info.elevation_attribute,
        #                                              layer_info.floor_height,
        #                                              conv_factor, below_ground)

        sdf[layer_info.extrude_attribute] = layer_info.floor_height
        sdf['display_height'] = layer_info.floor_height * 0.9

        return sdf
    else:
        return None


def merge_related_sdfs(input_sdf, rel_list, levelid_attribute):

    do_continue = False
    merged = 0
    all_rel_fields = list()
    use_sdf = input_sdf

    remove_fields = [levelid_attribute, 'objectid', 'OBJECTID']
    all_field_names = list()
    origin_key_fields = list()

    # TODO support multiple relationships.
    if len(rel_list) != 1:
        do_continue = False
        arcpy.AddMessage("Found more than 1 relationship for layer. Only 1 relationship is supported currently.")
        print("Found more than 1 relationship for layer. Only 1 relationship is supported currently.")
    else:
        for rel in rel_list:
            if rel.foreign_key_field not in remove_fields:
                remove_fields.append(rel.foreign_key_field)

            spatial_info = A3D_common_lib.get_spatial_info_from_service_url(rel.foreign_url)

            if spatial_info:
                # check if related sdf has levelid_attribute
                rel_columns = list(spatial_info.fs_df.columns)

                if levelid_attribute in rel_columns:
                    # set unique_id on right sdf: related table
                    if A3D_common_lib.set_id_attribute(spatial_info.fs_df, 'unique_level_id',
                                                       rel.foreign_key_field, levelid_attribute):

                        sdf_columns = list(use_sdf.columns)

                        if 'unique_level_id' in sdf_columns:
                            use_sdf.fs_df.drop('unique_level_id', 1)

                        # set unique_id on left sdf
                        if A3D_common_lib.set_id_attribute(use_sdf, 'unique_level_id',
                                                           rel.origin_key_field, levelid_attribute):

                            rel_columns = list(spatial_info.fs_df.columns)

                            # remove levelid_attribute from right sdf
                            if levelid_attribute in rel_columns:
                                rel_columns.remove(levelid_attribute)

                            if rel.foreign_key_field in rel_columns:
                                rel_columns.remove(rel.foreign_key_field)

                            if 'OBJECTID' in rel_columns:
                                rel_columns.remove('OBJECTID')

                            # merge sdfs
                            merged_sdf = pd.merge(use_sdf, spatial_info.fs_df[rel_columns],
                                                  on='unique_level_id', how='left')

                            if merged_sdf is not None:
                                use_sdf = merged_sdf

                                # get list of columns names and types for relationship
                                rel_fields = spatial_info.fs_dict.get('fields')

                                # list of all fields as dictionary
                                all_rel_fields.extend(rel_fields)

                                # list of all field names / fill nan values
                                for f in rel_fields:
                                    if f.get('name') not in remove_fields:
                                        if 'integer' in f.get('type').lower() or 'double' in f.get('type').lower():
                                            use_sdf[f.get('name')] = use_sdf[f.get('name')].fillna(0)
                                        elif 'string' in f.get('type').lower():
                                            use_sdf[f.get('name')] = use_sdf[f.get('name')].fillna('unknown')
                                        else:
                                            use_sdf[f.get('name')] = use_sdf[f.get('name')].fillna(0)

                                    all_field_names.append(f.get('name'))

                                merged += 1

                                origin_key_fields.append(rel.origin_key_field)

                                do_continue = True
                        else:
                            arcpy.AddMessage("Failed to set unique level_id...")
                            print("Failed to set unique level_id...")
                    else:
                        arcpy.AddMessage("Failed to set unique level_id...")
                        print("Failed to set unique level_id...")
                else:
                    arcpy.AddMessage("Failed to find " + levelid_attribute + " in " +
                                     " related table. This attribute must be present to work with levels.")
                    print("Failed to set unique level_id...")

    if do_continue:
        # remove default fields from list of field dicts
        unique_field_names = list(set([item for item in all_field_names if item not in remove_fields]))

        # remove duplicates
        add_fields = [item for item in all_rel_fields if item['name'] in unique_field_names]

        if merged > 0:
            return use_sdf, add_fields, origin_key_fields
        else:
            return None, None, None
    else:
        return None, None, None


def check_for_levels(spatial_info, layer_info, global_info):

    sdf_above = None
    converted = False

    if layer_info.floor_attribute:
        sdf_above = create_levels(spatial_info, layer_info, global_info, False)

        if sdf_above is not None:
            A3D_common_lib.set_levelid_attribute(sdf_above, layer_info.levelid_attribute, False)

            arcpy.AddMessage("Floor creation successful...")
            print("Floor creation successful...")
        else:
            arcpy.AddMessage("Floor creation failed...")
            print("Floor creation failed...")

#    create floors if attribute has been detected
    sdf_below = None
    if layer_info.basement_attribute:
        sdf_below = create_levels(spatial_info, layer_info, global_info, True)

        if sdf_below is not None:
            A3D_common_lib.set_levelid_attribute(sdf_below, layer_info.levelid_attribute, True)

            arcpy.AddMessage("Basement creation successful...")
            print("Basement creation successful...")
        else:
            arcpy.AddMessage("Basement creation failed...")
            print("basement creation failed...")

    # merge if needed
    if sdf_above is not None and sdf_below is None:
        sdf = sdf_above
        sdf[layer_info.floor_attribute] = 1
    elif sdf_above is None and sdf_below is not None:
        sdf = sdf_below
        sdf[layer_info.basement_attribute] = 1
    elif sdf_above is not None and sdf_below is not None:
        sdf = sdf_above.append(sdf_below, ignore_index=True)
        sdf[layer_info.floor_attribute] = 1
        sdf[layer_info.basement_attribute] = 1
    else:
        sdf = None

    if sdf is not None:
        fields_list = list()
        origin_key_fields = None

        display_height_field = dict()
        display_height_field['name'] = 'display_height'
        display_height_field['type'] = 'esriFieldTypeDouble'
        fields_list.append(display_height_field)

        level_field = dict()
        level_field['name'] = layer_info.levelid_attribute
        level_field['type'] = 'esriFieldTypeInteger'
        fields_list.append(level_field)

        orig_id_field = dict()
        orig_id_field['name'] = 'orig_object_id'
        orig_id_field['type'] = 'esriFieldTypeInteger'
        fields_list.append(orig_id_field)

        add_fields_list = add_level_fields(fields_list)

        sdf[spatial_info.object_id_field_name] = sdf.index + 1

        # check for related tables
        # check relationship info for this layer
        rel_list = A3D_common_lib.get_relationship_info(global_info, layer_info,
                                                        spatial_info.service_url)

        if len(rel_list) > 0:
            # merge related tables
            sdf_merge, rel_fields, origin_key_fields = merge_related_sdfs(sdf, rel_list, layer_info.levelid_attribute)

            if sdf_merge is not None:
                floor_height_attr_list = bm_common_lib.get_info_from_json("settings_3dbasemaps.json", "web_scene_info",
                                                                          "floor_height_attributes")

                # check if floor height attribute is in sdf, if so set elevation attribute according
                floor_height_attribute = None
                sdf_columns = list(sdf_merge)

                for attr in floor_height_attr_list:
                    if attr in sdf_columns:
                        floor_height_attribute = attr
                        break

                if floor_height_attribute:
                    layer_info.extrude_attribute = floor_height_attribute

                    conv_factor = A3D_common_lib.unit_conversion(spatial_info.linear_unit,
                                                                 global_info.object_units, 0)

                    A3D_common_lib.set_level_elevation_attribute_level_id(sdf_merge, layer_info.elevation_attribute,
                                                                          layer_info.floor_height,
                                                                          floor_height_attribute,
                                                                          conv_factor,
                                                                          layer_info.levelid_attribute)
                    converted = True

                    if 'feet' in global_info.object_units:
                        offset = 0.6
                    else:
                        offset = 0.2

                    sdf_merge['display_height'] = sdf_merge[floor_height_attribute] - (offset * conv_factor)
                    sdf_merge[layer_info.extrude_attribute] = sdf_merge[floor_height_attribute]

                sdf = sdf_merge
                add_fields_list.extend(rel_fields)

        return sdf, add_fields_list, origin_key_fields, converted
    else:
        return None, None, None, None


def get_item_3D(global_info, layer_info, layer_item_info, lyr_properties):
    try:
        target_tkw = None
        item_3D = None
        type_key_word_list = layer_item_info.item.typeKeywords

        arcpy.AddMessage("Checking if " + layer_info.title + " has an associated 3D feature layer...")
        print("Checking if " + layer_info.title + " has an associated 3D feature layer...")

        for tkw in type_key_word_list:
            if "target_fs:" in tkw:
                target_tkw = tkw
                break

        if target_tkw:
            target_id = target_tkw.replace('target_fs:', '')
            item_3D = global_info.gis.content.get(str(target_id))

            if item_3D:
                arcpy.AddMessage("Found associated 3D feature layer " + item_3D.title + " for "
                                 + layer_info.title + ".")
                print("Found associated 3D feature layer " + item_3D.title + " for " + layer_info.title + ".")
                return item_3D
            else:
                # remove typeKeyword
                type_key_word_list.remove(target_tkw)
                layer_item_info.item.update(item_properties={'typeKeywords': type_key_word_list})

        if not item_3D:
            # create new feature service
            service_item_name = layer_info.title + "_3D"
            org_title = layer_info.title

            portal_id = A3D_common_lib.get_portal_id(global_info.token, global_info.org_portal_url)
            portal_url = global_info.org_portal_url + "/" + portal_id

            # check if item name is available
            name_available = A3D_common_lib.check_service_name(global_info.token,
                                                               portal_url, service_item_name,
                                                               "featureService")

            if not name_available:
                service_item_name = layer_info.title + "_3D " + \
                                    global_info.start_time

                name_available = A3D_common_lib.check_service_name(global_info.token,
                                                                   portal_url, service_item_name,
                                                                   "featureService")

            if name_available:
                arcpy.AddMessage("Creating 3D feature layer " + service_item_name + " from " +
                                 layer_info.title + ".")
                print("Creating new 3D feature layer " + service_item_name + " from " +
                      layer_info.title + ".")

                service_info = A3D_common_lib.get_item_info(global_info.token, layer_item_info.item.url)

                # remove layers and tables entries from response
                if 'layers' in service_info:
                    del service_info['layers']

                if 'tables' in service_info:
                    del service_info['tables']

                service_info['serviceDescription'] = service_item_name
                service_info['_ssl'] = True
                service_info['name'] = service_item_name

                # use input layer item folder, otherwise try input_item folder
                try:
                    layer_item_folder = layer_item_info.item.ownerFolder
                except:
                    layer_item_folder = global_info.input_item_info.item_folder

                # create service
                item_3D_response = A3D_common_lib.create_service(global_info.token,
                                                                 global_info.org_content_users_url,
                                                                 global_info.my_username,
                                                                 layer_item_info.item,
                                                                 layer_item_folder,
                                                                 service_info,
                                                                 "featureService")

                arcpy.AddMessage(service_item_name + " created...")
                print(service_item_name + " created...")

                if item_3D_response:
                    item_id = item_3D_response.get('itemId')
                    url = item_3D_response.get('serviceurl')
                    item_3D = global_info.gis.content.get(str(item_id))

                    try:
                        item_folder = item_3D.ownerFolder
                    except:
                        item_folder = None

                    # update the new item with source layer id
                    type_key_word = "source_fs:" + layer_item_info.item_id
                    input_item_snippet = layer_item_info.item.snippet
                    input_item_desc = layer_item_info.item.description
                    input_item_tags = layer_item_info.item.tags

                    snippet = input_item_snippet + " (converted to 3D using attribute values from " + item_3D.title + ")"
                    description = input_item_desc + \
                                  " (converted to 3D using attribute values from " + item_3D.title + ")"
                    tags = input_item_tags.copy()
                    tags.append("2Dto3D")

                    input_item_tags_astext = ','.join(map(str, input_item_tags))
                    tags_astext = ','.join(map(str, tags))

                    arcpy.AddMessage("Updating " + service_item_name + " item info and adding service definition...")
                    print("Updating " + service_item_name + " item info and adding service definition...")

                    success = A3D_common_lib.update_item(global_info.token,
                                                         global_info.org_content_users_url,
                                                         global_info.my_username,
                                                         item_3D,
                                                         item_folder,
                                                         snippet,
                                                         description,
                                                         tags_astext,
                                                         type_key_word)

                    # add geometries
                    if success:
                        arcpy.AddMessage("Creating geometries...")
                        print("Creating geometries...")

                        spatial_info = A3D_common_lib.get_spatial_info_from_service_url(layer_info.url)
                        spatial_info.service_url = layer_item_info.item.url
                        source_fields = spatial_info.fs_dict.get('fields')
                        remove_fields_list = list()

                        # check if we can make levels
                        sdf, add_fields_list, origin_key_fields, converted = \
                            check_for_levels(spatial_info, layer_info, global_info)

                        if sdf is not None:
                            # get list of source field names we want to drop
                            keep_list = [spatial_info.object_id_field_name,
                                         layer_info.extrude_attribute,
                                         layer_info.elevation_attribute,
                                         'GlobalID',
                                         'Shape__Area',
                                         'Shape__Length']

                            if origin_key_fields:
                                keep_list.extend(origin_key_fields)

                            for f in source_fields:
                                name = f.get('name')
                                if name not in keep_list:
                                    remove_fields_list.append(name)

                            floors_fs = sdf.spatial.to_featureset()

                            # replace feature dictionary in spatial_info
                            fs_dict = floors_fs.to_dict()

                            # dumps to json to lock in row repeats
                            json_dict = json.dumps(fs_dict)
                            spatial_info.fs_dict = json.loads(json_dict)

                        # add z values to features
                        arcpy.AddMessage("Adding z values to " + service_item_name + ".")
                        print("Adding z values to " + service_item_name + ".")

                        success = A3D_common_lib.polygons_add_z(spatial_info, layer_info.elevation_attribute,
                                                                global_info.object_units, converted)

                        if success:
                            # add service definition
                            lyr_properties.id = 0
                            lyr_properties.name = service_item_name
                            lyr_properties['tables'] = list()
                            lyr_properties['relationships'] = list()
                            lyr_properties['indexes'] = list()

                            arcpy.AddMessage("Adding service definition to " + service_item_name + ".")
                            print("Adding service definition to " + service_item_name + ".")

                            success = A3D_common_lib.add_definition(global_info.token,
                                                                    global_info.org_content_users_url,
                                                                    global_info.my_username,
                                                                    item_3D,
                                                                    item_folder,
                                                                    lyr_properties,
                                                                    add_fields_list,
                                                                    remove_fields_list)

                            # append features to new service
                            if success:
                                success = A3D_common_lib.add_records_hosted_layer_via_rest(global_info.token,
                                                                                           item_3D,
                                                                                           spatial_info)
                                if success:
                                    # update the source item with target id
                                    type_key_word = "target_fs:" + item_3D.id

                                    success = A3D_common_lib.update_item(global_info.token,
                                                                         global_info.org_content_users_url,
                                                                         global_info.my_username,
                                                                         layer_item_info.item,
                                                                         layer_item_folder,
                                                                         input_item_snippet,
                                                                         input_item_desc,
                                                                         input_item_tags_astext,
                                                                         type_key_word,
                                                                         )
                                    if success:
                                        arcpy.AddMessage(
                                            "Successfully created " + service_item_name + "...")
                                        print("Successfully created " + service_item_name + "...")

                                        return item_3D
                                    else:
                                        item_3D.delete()
                                        arcpy.AddMessage(
                                            "Error creating " + service_item_name + "...")
                                        print("Error creating " + service_item_name + "...")
                                        return None
                                else:
                                    item_3D.delete()
                                    arcpy.AddMessage(
                                        "Error creating " + service_item_name + "...")
                                    print("Error creating " + service_item_name + "...")
                                    return None
                            else:
                                item_3D.delete()
                                arcpy.AddMessage(
                                    "Error creating " + service_item_name + "...")
                                print("Error creating " + service_item_name + "...")
                                return None
                        else:
                            item_3D.delete()
                            arcpy.AddMessage(
                                "Error creating " + service_item_name + "...")
                            print("Error creating " + service_item_name + "...")
                            return None
                    else:
                        item_3D.delete()
                        arcpy.AddMessage(
                            "Error creating " + service_item_name + "...")
                        print("Error creating " + service_item_name + "...")
                        return None
                else:
                    return None
            else:
                arcpy.AddMessage("Error when creating new feature layer. Name " + service_item_name + " not available.")
                print("Error when creating new feature layer. Name " + service_item_name + " not available.")
                return None

    except:
        return None


def set_3D_poly_layer_definition(added_layer, layer_info, geom_type, global_info, layer_item_info):
    try:
        existing_renderer = layer_info.rendering_info.type

        # set visual variable rendering if extrude attribute
        if layer_info.extrude_attribute:
            arcpy.AddMessage("Extruding layer: " + layer_info.title + " with " + layer_info.extrude_attribute +
                             " attribute values.")
            print("Extruding layer: " + layer_info.title + " with " + layer_info.extrude_attribute +
                  " attribute values.")

            # set classBreaks with extrusion
            if existing_renderer == 'classBreaks':
                set_poly_classbreak_with_extrusion_renderer(added_layer, layer_info, layer_info.extrude_attribute,
                                                            global_info.object_units)

            # set simple fill with extrusion
            if existing_renderer == 'simple':
                set_poly_simple_with_extrusion_renderer(added_layer, layer_info, layer_info.extrude_attribute,
                                                        global_info.object_units)
        # TODO other renderers
        else:
            # if not tree attrs -> only simple and uniqueValue is supported at the moment
            if existing_renderer == 'simple':
                # get symbol point color and size from layer_info
                if layer_info.rendering_info.symbol.type == 'esriSFS':
                    try:
                        existing_symbol_color = layer_info.rendering_info.symbol.color
                        existing_symbol_outline_color = layer_info.rendering_info.symbol.outline.color
                        existing_symbol_outline_size = layer_info.rendering_info.symbol.outline.width
                    except:
                        existing_symbol_color = [0, 0, 255, 255]
                        existing_symbol_outline_color = [0, 0, 0, 255]
                        existing_symbol_outline_size = 2

                    rgb_list = [existing_symbol_color[0], existing_symbol_color[1], existing_symbol_color[2]]
                    # replace symbol with PointSymbol3D
                    layer_info.rendering_info.symbol = update_polygon_symbol_3D(existing_symbol_color,
                                                                                existing_symbol_outline_color,
                                                                                existing_symbol_outline_size)
                else:
                    del added_layer['layerDefinition']['drawingInfo']

            else:
               del added_layer['layerDefinition']['drawingInfo']

        # set 3D poly labeling
        do_label = False
        try:
            lbl_info = layer_info.labeling_info

            # if label info then translate to web scene specs
            if lbl_info:
                updated_lbl_info = A3D_wm2ws.translate_lbl_info(lbl_info, 'esriServerPolygonPlacementAlwaysHorizontal')
                added_layer['layerDefinition']['drawingInfo']['labelingInfo'] = updated_lbl_info
                do_label = True
            else:
                # if no labeling info in the layer, try and overwrite it with default name label
                has_attrs, num_fs = A3D_common_lib.check_attributes(layer_info.url, ['name'])
                if has_attrs:
                    lbl_info = A3D_wm2ws.get_default_labeling_info()['labelingInfo']
                    lbl_info[0]['labelExpression'] = "[name]"
                    lbl_info[0]['labelPlacement'] = 'esriServerPolygonPlacementAlwaysHorizontal'
                    added_layer['layerDefinition']['drawingInfo']['labelingInfo'] = lbl_info
                    do_label = True
        except:
            pass

        # set elevation
        A3D_wm2ws.set_elevation_info(added_layer, layer_info, geom_type, global_info, False, layer_item_info)

    except:
        pass


def create_polygonZ_feature_layer(layer_info, global_info, layer_item_info):
    lyr_properties = layer_info.layer_properties

    if lyr_properties:
        lyr_properties_copy = lyr_properties
        lyr_properties_copy.hasZ = True

        if layer_info.elevation_attribute:
            # get 3D item
            return get_item_3D(global_info, layer_info, layer_item_info, lyr_properties_copy)
    else:
        return None
