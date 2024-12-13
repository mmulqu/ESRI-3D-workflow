import arcpy
import scripts.A3D_common_lib as A3D_common_lib
import scripts.A3D_fl2sl as A3D_fl2sl
import numpy as np
from arcgis.geometry import Geometry
import os
from arcgis.features import FeatureLayer
from pprint import pprint

try:
    import pyprt
    pprint("PyPRT is already installed.")
except:
    pass
    # pprint("Installing PyPRT...")
    #!conda install -c esri pyprt --yes
    #import pyprt


# STREET SIGN SPECIFIC FUNCTIONS
def get_value_from_dataframe(df, search_field_name, search_field_value, value_field):
    value_series = df.loc[df[search_field_name] == search_field_value, value_field]
    value = value_series.iloc[0]
    return value


# functions for PyPRT
def add_dimension(array_coord_2d, z_value):
    array_coord_3d = np.insert(array_coord_2d, 1, z_value, axis=1)
    return np.reshape(array_coord_3d, (1, array_coord_3d.shape[0] * array_coord_3d.shape[1]))


def swap_yz_dimensions(array_coord):
    coord_swap_dim = array_coord.copy()
    temp = np.copy(array_coord[:, 1])
    coord_swap_dim[:, 1] = coord_swap_dim[:, 2]
    coord_swap_dim[:, 2] = temp
    return np.reshape(coord_swap_dim, (1, coord_swap_dim.shape[0] * coord_swap_dim.shape[1]))


def holes_conversion(holes_ind_list):
    holes_dict = {}
    holes_list = []
    if len(holes_ind_list) > 0:
        for h_idx in holes_ind_list:
            f_idx = h_idx
            while f_idx > 0:
                f_idx -= 1
                if not (f_idx in holes_ind_list):
                    if not (f_idx in holes_dict):
                        holes_dict[f_idx] = [h_idx]
                    else:
                        holes_dict[f_idx].append(h_idx)
                    break

        for key, value in holes_dict.items():
            face_holes = [key]
            face_holes.extend(value)
            holes_list.append(face_holes)
    return holes_list


def arcgis_to_pyprtDevelop(feature_set, z_list, unit_factor, object_units, layer_info, sdf):
    """arcgis_to_pyprt(feature_set) -> List[InitialShape]
    This function allows converting an ArcGIS FeatureSet into a list of PyPRT InitialShape instances.
    You then typically call the ModelGenerator constructor with the return value if this function as parameter.
    Parameters:
        feature_set: input polygon feature set
        z_list: list of z values: only used for 2D points
        unit_factor: elevation unit conversion factor
        object_units: units of the object parameters (typical inches or centimeters)
        layer_info: feature layer info
        sdf: associated pole spatial dataframe
    Returns:
        List[InitialShape], list[attributes]
    """
    initial_geometries = []
    attrs_list = []

    # get the domain for sign style
    fl_fields = layer_info.layer_properties.fields
    style_fields = get_field_from_fl_fields(fl_fields, 'style')

    if len(style_fields) > 0:
        name_domain_dict = dict()

        style_field = style_fields[0]  # we just grab the first one

        name_domain_dict['field_name'] = style_field.name
        name_domain_dict['domain'] = style_field.domain
    else:
        name_domain_dict = None

    num_features = len(feature_set.features)
    f = 0

    for feature in feature_set.features:
        try:
            geo = Geometry(feature.geometry)

            if geo.type == 'Polygon' and (not geo.is_empty):
                pts_cnt = 0
                vert_coord_list = []
                face_count_list = []
                holes_ind_list = []
                coord_list = geo.coordinates()

                for face_idx, coord_part in enumerate(coord_list):
                    if isinstance(coord_part, np.ndarray):
                        in_geo = Geometry({"rings": [coord_part.tolist()]})
                    else:
                        in_geo = Geometry({"rings": [coord_part]})
                    store_area = in_geo.area
                    coord_remove_last = coord_part[:-1]
                    coord_inverse = np.flip(coord_remove_last, axis=0)
                    coord_inverse[:, 1] *= -1

                    if len(coord_part[0]) == 2:
                        if len(z_list) > f:
                            z_value = z_list[f] * unit_factor
                        else:
                            z_value = 0

                        coord_fin = add_dimension(coord_inverse, z_value)

                    elif len(coord_part[0]) == 3:
                        coord_fin = swap_yz_dimensions(coord_inverse)
                    else:
                        arcpy.AddMessage("Only 2D or 3D points are supported.")

                    vert_coord_list.extend(coord_fin[0])
                    nb_pts = len(coord_fin[0]) / 3
                    pts_cnt += nb_pts
                    face_count_list.append(int(nb_pts))
                    if store_area > 0.0:  # interior ring / holes
                        holes_ind_list.append(face_idx)

                face_indices_list = list(range(0, sum(face_count_list)))
                holes_list = holes_conversion(holes_ind_list)

                # initial_geometry = pyprt.InitialShape(vert_coord_list, face_indices_list, face_count_list, holes_list)
                # initial_geometries.append(initial_geometry)

                feature_attrs = feature.attributes

                # get rid of None values
                for key, value in feature_attrs.items():
                    if not value:
                        feature_attrs[key] = 'None'

                # get Height attribute from pole feature layer
                if feature_attrs['attachid']:
                    if not 'None' in str(feature_attrs['attachid']):
                        pole_height = get_value_from_dataframe(sdf, 'assetid', feature_attrs['attachid'], 'height')

                        if A3D_common_lib.is_number(pole_height):
                            # rename and type setting to fit with CGA rule attributes
                            feature_attrs['Height'] = float(pole_height)
                        else:
                            feature_attrs['Height'] = 10
                    else:
                        feature_attrs['Height'] = 10
                else:
                    feature_attrs['Height'] = 10

                # rename and type setting to fit with CGA rule attributes
                feature_attrs['DirectionMethod'] = 'Degree'

                if feature_attrs['angle']:
                    if not 'None' in str(feature_attrs['angle']):
                        feature_attrs['DirectionDegrees'] = float(feature_attrs['angle'])
                    else:
                        feature_attrs['DirectionDegrees'] = float(0)
                else:
                    feature_attrs['DirectionDegrees'] = float(0)

                feature_attrs['SIGNSTYLE'] = str(feature_attrs['style'])
                feature_attrs['SIGNTEXT'] = str(feature_attrs['text'])
                feature_attrs['signUnits'] = object_units
                feature_attrs['DISTTOTOP'] = str(feature_attrs['disttotop'])
                feature_attrs['SIGNHEIGHT'] = str(feature_attrs['height'])
                feature_attrs['SIGNWIDTH'] = str(feature_attrs['width'])
                feature_attrs['ASSETID'] = str(feature_attrs['assetid'])
                feature_attrs['SHAPE'] = str(feature_attrs['SHAPE'])

                # the style atrribute has the domain code value, we need the domain name value,
                # if not found leave default value
                if name_domain_dict:
                    domain_name = get_domain_name(feature_attrs[name_domain_dict['field_name']],
                                                  name_domain_dict['domain'])

                    if domain_name:
                        feature_attrs['SIGNSTYLE'] = domain_name

                attrs_list.append(feature_attrs)
            else:
                arcpy.AddMessage("Only polygon features are supported.")

            f += 1

        except:
            arcpy.AddMessage("This feature is not valid: ")


            f += 1

    return initial_geometries, attrs_list


# end of functions for PyPRT


def get_domain_name(look_up_value, domain):
    domain_name = None
    coded_values = domain.codedValues

    for nc in coded_values:
        if nc.code == look_up_value:
            domain_name = nc.name
            break

    return domain_name


def get_field_from_fl_fields(fields, field_name):
    found_fields = list()

    for f in fields:
        if field_name in f.name.lower():
            found_fields.append(f)

    return found_fields


def get_pole_sdf(layer_info):
    sdf = None

    associated_layers = layer_info.associated_layers

    for url in associated_layers:
        fl = FeatureLayer(url)

        if 'pole' in fl.properties.name.lower():
            # spatial data frame
            expression = '1=1'
            fs = fl.query(where=expression, return_z=True)

            sdf = fs.sdf
            break

    return sdf


# create scene layer package from input item
def create_sign_slpk(global_info, layer_info, sign_attrs):
    slpk_filepath = None
    z_list = list()

    spatial_info = A3D_common_lib.get_spatial_info_from_service_url(layer_info.url)
    geom_type = layer_info.layer_properties.geometryType
    elevation_unit = spatial_info.linear_unit

    # check if we need to create elevation values from the elevation service
    if not spatial_info.has_z:
        if not spatial_info.fs_df.empty:
            # get xy point list
            arcpy.AddMessage("Retrieving vertex information for input points.")
            vertex_list = A3D_common_lib.get_vertex_list_from_feature_sdf(spatial_info.fs_df,
                                                                          geom_type, spatial_info.has_z)
            if vertex_list:
                if len(vertex_list) > 0:
                    geometry_dict = dict()

                    geometry_dict['points'] = vertex_list
                    geometry_dict['spatialReference'] = dict()
                    geometry_dict['spatialReference']['wkid'] = spatial_info.wkid

                    # use Esri elevation service for now
                    url = "https://elevation.arcgis.com/arcgis/rest/ser" \
                          "vices/WorldElevation/Terrain/ImageServer/getSamples"
                    elevation_unit = 'meter'
                    arcpy.AddMessage("Retrieving elevation for input points.")
                    new_vertex_list, z_list = A3D_common_lib.z_values_from_elevation_service(global_info.token,
                                                                                             url, geometry_dict)

                    # buffer features
                    arcpy.AddMessage("Buffering features...")
                    buffered_fs = A3D_common_lib.buffer_point_features_z(spatial_info, z_list)
                else:
                    buffered_fs = A3D_common_lib.buffer_point_features(spatial_info)
            else:
                buffered_fs = A3D_common_lib.buffer_point_features(spatial_info)
        else:
            buffered_fs = A3D_common_lib.buffer_point_features(spatial_info)
    else:
        buffered_fs = A3D_common_lib.buffer_point_features(spatial_info)

    # set conversion factor based on data units and elevation units
    if elevation_unit == 'meter' and spatial_info.linear_unit == 'feet':
        conv_factor = 3.28084
    elif elevation_unit == 'feet' and spatial_info.linear_unit == 'meter':
        conv_factor = 0.3048000097536
    else:
        conv_factor = 1

    # get pole spatial dataframe
    arcpy.AddMessage("Looking for associated pole layer...")
    pole_sdf = get_pole_sdf(layer_info)

    # create PyPRT initial shapes
    # initialize prt
    pyprt.initialize_prt()

    if (not pyprt.is_prt_initialized()):
        raise Exception("PRT is not initialized")

    initial_geometries_from_set, attrs_list_from_set = arcgis_to_pyprtDevelop(buffered_fs, z_list,
                                                                              conv_factor,
                                                                              global_info.object_units,
                                                                              layer_info, pole_sdf)

    arcpy.AddMessage("Created " + str(len(initial_geometries_from_set)) + " initial geometries...")
    arcpy.AddMessage("Created " + str(len(attrs_list_from_set)) + " attributes dictionaries...")

    # generate model and slpk
    rpk = global_info.gis.content.get(global_info.rpk_id)
    scene_service_item_name = layer_info.title + "_" + global_info.unique_tag + "_" + global_info.start_time

    if rpk:
        export_file_name = scene_service_item_name
        enc_optionsSLPK = {
            'sceneType': 'Local',
            'baseName': export_file_name,
            'sceneWkid': '3857',
            'layerTextureEncoding': ['2'],
            'layerEnabled': [True],
            'layerUID': ['1'],
            'layerName': ['1'],
            'layerTextureQuality': [1.0],
            'layerTextureCompression': [9],
            'layerTextureScaling': [1.0],
            'layerTextureMaxDimension': [2048],
            'layerFeatureGranularity': ['0'],
            'layerBackfaceCulling': [False],
            'outputPath': os.path.join(os.getcwd(), 'home', 'PyPRT_output1')}

        # delete any existing output and create new directory to output
        import shutil
        if os.path.exists(enc_optionsSLPK['outputPath']):
            shutil.rmtree(enc_optionsSLPK['outputPath'])

        os.makedirs(enc_optionsSLPK['outputPath'])
        arcpy.AddMessage("SLPK output location: " + enc_optionsSLPK['outputPath'])

        mod_parcel = pyprt.ModelGenerator(initial_geometries_from_set)
        generated_parks = mod_parcel.generate_model(
            attrs_list_from_set, rpk.download(), 'com.esri.prt.codecs.I3SEncoder', enc_optionsSLPK)

        slpk_filepath = os.path.join(enc_optionsSLPK['outputPath'], export_file_name + '.slpk')
        arcpy.AddMessage("SLPK output: " + slpk_filepath)
    else:
        arcpy.AddMessage("Could not find rpk: " + global_info.rpk_id + " No geometries created.")

    return slpk_filepath


# convert point feature layer into sign scene layer
def convert_point_layer_to_sign_layer(global_info, layer_info, sign_attrs):
    arcpy.AddMessage("Found: " + layer_info.title + " layer. Assuming this is a sign layer.")
    arcpy.AddMessage("Converting " + layer_info.title + " to scene layer for 3D sign display.")

    global_info.unique_tag = "PyPRT_street_signs"

    arcpy.AddMessage("Deleting associated layers...")
    # success = delete_associated_scene_items(global_info, layer_info)

    arcpy.AddMessage("Creating street sign slpk...")
    # slpk = create_sign_slpk(global_info, layer_info, sign_attrs)

    arcpy.AddMessage("Publishing street sign slpk...")
    # published_item = publish_slpk(global_info, slpk, global_info.input_item_info.item_folder)

    gis_org = global_info.gis
    global_info.input_item_id = '91295fdc7ce746c2b17a2fb9415ecf0f'
    published_item = gis_org.content.get(global_info.input_item_id)

    # update layer_info
    if published_item:
        layer_info_list = A3D_fl2sl.get_layer_info_from_item(published_item)

        if len(layer_info_list) > 0:
            return layer_info_list
        else:
            return None
    else:
        return None

# END STREET SIGN SPECIFIC FUNCTIONS
