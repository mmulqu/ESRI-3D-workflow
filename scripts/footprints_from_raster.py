import arcpy
from arcpy.sa import *
import os
import sys
import re
import locale
locale.setlocale(locale.LC_ALL, '')

from scripts.split_features import split
from scripts.bm_common_lib import msg, trace
from scripts import bm_common_lib


# constants
TOOLNAME = "footprints_from_raster"
WARNING = "warning"
ERROR = "error"


class FunctionError(Exception):

    """
    Raised when a function fails to run.
    """

    pass


class LicenseError3D(Exception):
    pass


class LicenseErrorSpatial(Exception):
    pass


class NoFeatures(Exception):
    pass


class StringHasSpace(Exception):
    pass


class HasSpace(Exception):
    pass


class NoLayerFile(Exception):
    pass


# Check if field exists in fc
def FieldExist(featureclass, fieldname):
    fieldList = arcpy.ListFields(featureclass, fieldname)
    fieldCount = len(fieldList)
    if fieldCount == 1:
        return True
    else:
        return False


def get_metric_from_areal_unit(areal_unit):
    unit_split = areal_unit.split(' ')
    value = float(unit_split[0])
    unit = unit_split[1]
    unit_dict = {
        "SquareKilometers": .000001,
        "Hectares": 0.0001,
        "SquareMeters": 1,
        "SquareDecimeters": 100,
        "SquareCentimeters": 10000,
        "SquareMillimeters": 1000000,
        "SquareFeet": 10.7639,
        "Inches": 1550,
        "Miles": 0.0000003861013863,
        "Yards": 1.19599,
        "Acres": 0.000247105
    }
    metric_value = value / unit_dict[unit]
    return metric_value


def get_area_field(fc):
    path = arcpy.Describe(fc).catalogPath
    path_name = os.path.dirname(path)
    if path_name == "in_memory":
        area_field = "geom_area"
        fields = arcpy.ListFields(fc)
        if area_field in [f.name for f in fields]:
            arcpy.DeleteField_management(fc, area_field)
        arcpy.AddField_management(fc, "geom_area", "FLOAT")
        arcpy.CalculateField_management(fc, "geom_area", "!shape.area!", "PYTHON_9.3")

    else:
        area_field = arcpy.Describe(fc).areaFieldName

    return area_field


def delete_existing(fc_list):
    for fc in fc_list:
        if arcpy.Exists(fc):
            arcpy.Delete_management(fc)


def simplify_and_buffer(workspace, non_reg_bldg, simplify_tolerance, buffer_distance, m_per_unit):
    try:
        simplify_tolerance_m = bm_common_lib.get_metric_from_linear_unit(simplify_tolerance)
        simplify_tolerance_map = simplify_tolerance_m / m_per_unit

        # Simplify Polygons
        arcpy.AddMessage("Simplifying polygons...")
        lg_bldg_sp = os.path.join(workspace, "lg_bldg_sp")
        arcpy.SimplifyPolygon_cartography(non_reg_bldg, lg_bldg_sp, "POINT_REMOVE", simplify_tolerance)

        # Buffer Neg
        if buffer_distance > 0:
            arcpy.AddMessage("Applying negative buffer...")
            simplify_tolerance_neg = (simplify_tolerance * -2)
            lg_bldg_sp_bufneg = os.path.join(workspace, "lg_bldg_sp_bufneg")
            arcpy.Buffer_analysis(lg_bldg_sp, lg_bldg_sp_bufneg, -buffer_distance)

            # Simplify Polygons
            arcpy.AddMessage("Simplifying polygons a second time...")
            lg_bldg_sp_bufneg_sp = os.path.join(workspace, "lg_bldg_sp_bufneg_sp")
            arcpy.SimplifyPolygon_cartography(lg_bldg_sp_bufneg, lg_bldg_sp_bufneg_sp, "POINT_REMOVE",
                                              simplify_tolerance)

            # Buffer Pos
            arcpy.AddMessage("Applying positive buffer... ")
            lg_bldg_sp_buf_pos = os.path.join(workspace, "lg_bldg_sp_buf_pos")
            arcpy.Buffer_analysis(lg_bldg_sp_bufneg_sp, lg_bldg_sp_buf_pos, buffer_distance)

            # Simplify Polygons
            arcpy.AddMessage("Simplifying polygons a third time...")
            lg_bldg_sp_bufpos_sp = os.path.join(workspace, "lg_bldg_sp_bufpos_sp")
            arcpy.SimplifyPolygon_cartography(lg_bldg_sp_buf_pos, lg_bldg_sp_bufpos_sp, "POINT_REMOVE",
                                              simplify_tolerance)
        else:
            lg_bldg_sp_bufpos_sp = lg_bldg_sp

        return lg_bldg_sp_bufpos_sp

    except arcpy.ExecuteWarning:
        print(arcpy.GetMessages(1))
        arcpy.AddWarning(arcpy.GetMessages(1))

    except arcpy.ExecuteError:
        print(arcpy.GetMessages(2))
        arcpy.AddError(arcpy.GetMessages(2))

    # Return any other type of error
    except:
        # By default any other errors will be caught here
        #
        e = sys.exc_info()[1]
        print((e.args[0]))
        arcpy.AddError(e.args[0])


def create_building_mosaic(scratch_ws, in_raster, min_area, split_features, simplify_tolerance,
                           output_poly, reg_circles, circle_min_area, min_compactness,
                           circle_tolerance, lg_reg_method, lg_min_area,
                           lg_tolerance, med_reg_method, med_min_area, med_tolerance,
                           sm_reg_method, sm_tolerance, verbose, in_memory_switch):
    try:
        if in_memory_switch:
            workspace = "in_memory"
        else:
            workspace = scratch_ws

        # set regularize env settings
        arcpy.env.parallelProcessingFactor = "75%"

        ras_desc = arcpy.Describe(in_raster)
        ras_sr = ras_desc.spatialReference
        m_per_unit = ras_sr.metersPerUnit
        fc_delete_list = []
        precision = 0.15
        diagonal_penalty = 1.15

        # Get area inputs in map units
        m_min_area = get_metric_from_areal_unit(min_area)
        poly_min_area = m_min_area / (m_per_unit ** 2)
        if med_min_area is not None:
            min_area_med_m = get_metric_from_areal_unit(med_min_area)
            min_area_med = min_area_med_m / (m_per_unit ** 2)
        if lg_min_area is not None:
            min_area_lg_m = get_metric_from_areal_unit(lg_min_area)
            min_area_lg = min_area_lg_m / (m_per_unit ** 2)

        # Create output building feature class
        out_gdb = os.path.dirname(output_poly)
        out_name = os.path.basename(output_poly)
        arcpy.CreateFeatureclass_management(out_gdb, out_name, "POLYGON", spatial_reference=ras_sr)

        # Shrink grow
        arcpy.AddMessage("Shrinking and growing raster areas to remove slivers")
        bldg_shrink = Shrink(in_raster, 1, 6)
        bldg_grow = None
        if bldg_shrink.maximum > 0:
            bldg_grow = Expand(bldg_shrink, 1, 6)
        else:
            bldg_grow = in_raster

        # Raster to polygon
        arcpy.AddMessage("Converting raster to polygon")
        bldg_poly = os.path.join(scratch_ws, "bldg_poly")
        arcpy.RasterToPolygon_conversion(bldg_grow, bldg_poly, "NO_SIMPLIFY")

        # Delete non value features
        with arcpy.da.UpdateCursor(bldg_poly, "gridcode") as cursor:
            for row in cursor:
                if row[0] == 0:
                    cursor.deleteRow()

        # Select large buildings
        bldg_area = get_area_field(bldg_poly)
        bldg_lg = "bldg_lg"
        arcpy.MakeFeatureLayer_management(bldg_poly, bldg_lg, "{0} >= {1}".format(bldg_area, str(poly_min_area)))

        # Eliminate polygon part
        arcpy.AddMessage("Eliminating small holes")
        bldg_elim = os.path.join(scratch_ws, "bldg_elim")
        fc_delete_list.append(bldg_elim)
        arcpy.EliminatePolygonPart_management(bldg_lg, bldg_elim, "AREA", min_area)

        # Split using split features (identity) plus multipart to single part
        multi_single_part = os.path.join(scratch_ws, "bldg_mp_sp")
        split_bldg = os.path.join(scratch_ws, "split_bldg")
        fc_delete_list.append(split_bldg)
        non_reg_bldg = "non_reg_bldg"
        if arcpy.Exists(split_features):
            arcpy.AddMessage("Splitting polygons by reference features")

            arcpy.AddMessage(scratch_ws)

            arcpy.AddMessage("Copying split features...")
            copy_split = os.path.join(scratch_ws, "copy_split")
            arcpy.CopyFeatures_management(split_features, copy_split)

            arcpy.AddMessage("Removing identical shapes in split features")
            arcpy.management.DeleteIdentical(copy_split, "Shape", "4 Feet", 0)

            split_bldg = os.path.join(scratch_ws, "split_bldg")

            # custom split.
            # arcpy.Identity_analysis(bldg_elim, copy_split, split_bldg)
            split_bldg = split(scratch_ws, bldg_elim, copy_split, poly_min_area, split_bldg, 0, False)

    #        arcpy.MakeFeatureLayer_management(split_bldg, non_reg_bldg)
            arcpy.MultipartToSinglepart_management(split_bldg, multi_single_part)
        else:
            #   arcpy.MakeFeatureLayer_management(bldg_elim, non_reg_bldg)
            arcpy.MultipartToSinglepart_management(bldg_elim, multi_single_part)

        arcpy.AddMessage("Converting Multipart to singleparts")

        arcpy.MakeFeatureLayer_management(multi_single_part, non_reg_bldg)

        # add unique identifier
        non_reg_fc = arcpy.Describe(non_reg_bldg).catalogPath
        oid = arcpy.Describe(non_reg_fc).OIDFieldName
        unique_id = "unique_id"
        if not FieldExist(non_reg_fc, unique_id):
            arcpy.AddField_management(non_reg_fc, unique_id, "LONG")
        arcpy.CalculateField_management(non_reg_fc, unique_id, "!{}!".format(oid))

        area_field = get_area_field(non_reg_bldg)
        # Regularize circles
        if reg_circles:
            # Delete status field if it exists
            if FieldExist(non_reg_bldg, "STATUS"):
                arcpy.DeleteField_management(non_reg_bldg, "STATUS")

            # calculate compactness
            comp_field = "compactness"
            if not FieldExist(non_reg_bldg, comp_field):
                arcpy.AddField_management(non_reg_bldg, comp_field, "FLOAT")
            arcpy.CalculateField_management(non_reg_bldg, comp_field,
                                            "(4 * 3.14159 * !shape.area!) / (!shape.length! ** 2)", "PYTHON_9.3")
            # Select circle-like features
            arcpy.AddMessage("Selecting compact features")
            min_area_circle_m = get_metric_from_areal_unit(circle_min_area)
            min_area_circle = min_area_circle_m / (m_per_unit ** 2)

            expression = "{0} > {1} AND {2} > {3}".format(area_field, str(min_area_circle), comp_field,
                                                          str(min_compactness))
            arcpy.SelectLayerByAttribute_management(non_reg_bldg, "NEW_SELECTION", expression)

            num_features = int(arcpy.GetCount_management(non_reg_bldg).getOutput(0))

            if num_features > 0:
                # Get tolerance in map units
                circle_tolerance_m = bm_common_lib.get_metric_from_linear_unit(circle_tolerance)
                circle_tolerance_map = circle_tolerance_m / m_per_unit

                # Regularize
                arcpy.AddMessage("Regularizing circles")
                circle_reg = os.path.join(workspace, "circle_reg")
                fc_delete_list.append(circle_reg)

                arcpy.RegularizeBuildingFootprint_3d(in_features=non_reg_bldg, out_feature_class=circle_reg,
                                                     method="CIRCLE",
                                                     tolerance=circle_tolerance_map,
                                                     min_radius=1,
                                                     precision=precision,
                                                     max_radius=1000000000)

                # Select circles that successfully regularized
                my_status = "STATUS"
                circle_list = []
                with arcpy.da.UpdateCursor(circle_reg, [unique_id, my_status]) as cursor:
                    for row in cursor:
                        if row[1] == 0:
                            circle_list.append(row[0])
                        else:
                            cursor.deleteRow()

                # Delete circle features from draft polygons
                with arcpy.da.UpdateCursor(non_reg_bldg, unique_id) as cursor:
                    for row in cursor:
                        if row[0] in circle_list:
                            cursor.deleteRow()

                # Append circles to output fc
                arcpy.Append_management(circle_reg, output_poly, "NO_TEST")
            else:
                arcpy.AddMessage("Found no circular buildings.")

            arcpy.SelectLayerByAttribute_management(non_reg_bldg, "CLEAR_SELECTION")

        # Regularize large buildings
        if lg_reg_method != "NONE":
            # Select large buildings
            arcpy.AddMessage("Selecting large building areas")
            arcpy.SelectLayerByAttribute_management(non_reg_bldg,
                                                    "NEW_SELECTION", '{0} >= {1}'.format(area_field, str(min_area_lg)))

            num_features = int(arcpy.GetCount_management(non_reg_bldg).getOutput(0))

            if num_features > 0:
                # Get tolerance in map units
                lg_tolerance_m = bm_common_lib.get_metric_from_linear_unit(lg_tolerance)
                lg_tolerance_map = lg_tolerance_m / m_per_unit

                # Regularize
                arcpy.AddMessage("Regularizing large buildings")

                #  Arthur's method  #
                processed_polygons = simplify_and_buffer(workspace, non_reg_bldg, simplify_tolerance, 3, m_per_unit)

                # Regularize
                arcpy.AddMessage("Regularizing large buildings...")
                lg_bldg_simpa = os.path.join(workspace, "lg_bldg_simpa")
                arcpy.RegularizeBuildingFootprint_3d(in_features=processed_polygons,
                                                     out_feature_class=lg_bldg_simpa,
                                                     method=lg_reg_method,
                                                     tolerance=lg_tolerance_map,
                                                     precision=precision,
                                                     diagonal_penalty=diagonal_penalty)

                # Regularize2
                arcpy.AddMessage("Regularizing large buildings a second time...")
                lg_tolerance_mapa = (lg_tolerance_map * 2)
                lg_bldg_simp = os.path.join(workspace, "lg_bldg_simp")
                arcpy.RegularizeBuildingFootprint_3d(in_features=lg_bldg_simpa,
                                                     out_feature_class=lg_bldg_simp,
                                                     method=lg_reg_method,
                                                     tolerance=lg_tolerance_mapa,
                                                     precision=precision,
                                                     diagonal_penalty=diagonal_penalty)

                #  Dan's method  #
                # arcpy.RegularizeBuildingFootprint_3d(in_features=non_reg_bldg, out_feature_class=lg_bldg_reg,
                #                                      precision=precision,
                #                                      method=lg_reg_method,
                #                                      tolerance=lg_tolerance_map)
                #
                # # Simplify buildings
                # lg_bldg_simp = os.path.join(workspace, "lg_bldg_simp")
                # arcpy.SimplifyBuilding_cartography(lg_bldg_reg, lg_bldg_simp, lg_tolerance)

                # Append to output
                arcpy.Append_management(lg_bldg_simp, output_poly, "NO_TEST")
            else:
                arcpy.AddMessage("Found no large buildings.")

            arcpy.SelectLayerByAttribute_management(non_reg_bldg, "SWITCH_SELECTION")

        # Regularize medium buildings
        if med_reg_method != "NONE":
            # Select medium buildings
            arcpy.AddMessage("Selecting medium building areas")
            if lg_reg_method != "NONE":
                selection = "SUBSET_SELECTION"
            else:
                selection = "NEW_SELECTION"
            arcpy.SelectLayerByAttribute_management(non_reg_bldg, selection, '{0} >= {1}'.format(area_field,
                                                                                                 str(min_area_med)))

            num_features = int(arcpy.GetCount_management(non_reg_bldg).getOutput(0))

            if num_features > 0:
                # Get tolerance in map units
                med_tolerance_m = bm_common_lib.get_metric_from_linear_unit(med_tolerance)
                med_tolerance_map = med_tolerance_m / m_per_unit

                #  Arthur's method  #
                processed_polygons = simplify_and_buffer(workspace, non_reg_bldg, simplify_tolerance, 1, m_per_unit)

                # Regularize
                arcpy.AddMessage("Regularizing medium buildings...")
                med_bldg_simpa = os.path.join(workspace, "med_bldg_simpa")
                arcpy.RegularizeBuildingFootprint_3d(in_features=processed_polygons,
                                                     out_feature_class=med_bldg_simpa,
                                                     method=med_reg_method,
                                                     tolerance=med_tolerance_map,
                                                     precision=precision,
                                                     diagonal_penalty=diagonal_penalty)

                # Regularize2
                arcpy.AddMessage("Regularizing medium buildings a second time...")
                med_tolerance_mapa = (med_tolerance_map * 2)
                med_bldg_simp = os.path.join(workspace, "med_bldg_simp")
                arcpy.RegularizeBuildingFootprint_3d(in_features=med_bldg_simpa,
                                                     out_feature_class=med_bldg_simp,
                                                     method=med_reg_method,
                                                     tolerance=med_tolerance_mapa,
                                                     precision=precision,
                                                     diagonal_penalty=diagonal_penalty)

                #  Dan's method  #
                # Regularize
                # arcpy.AddMessage("Regularizing medium buildings")
                # med_bldg_reg = os.path.join(workspace, "med_bldg_reg")
                # arcpy.RegularizeBuildingFootprint_3d(in_features=non_reg_bldg,
                #                                      out_feature_class=med_bldg_reg,
                #                                      method=med_reg_method,
                #                                      precision=precision,
                #                                      tolerance=med_tolerance_map)
                #
                # # Simplify buildings
                # med_bldg_simp = os.path.join(workspace, "med_bldg_simp")
                # arcpy.SimplifyBuilding_cartography(med_bldg_reg, med_bldg_simp, med_tolerance, min_area)

                # Append to output
                arcpy.Append_management(med_bldg_simp, output_poly, "NO_TEST")
            else:
                arcpy.AddMessage("Found no medium buildings.")

            arcpy.SelectLayerByAttribute_management(non_reg_bldg, "CLEAR_SELECTION")

        # Regularize small buildings
        if sm_reg_method != "NONE":
            # Select small buildings
            arcpy.AddMessage("Selecting small building areas")
            if med_reg_method != "NONE":
                arcpy.SelectLayerByAttribute_management(non_reg_bldg, "NEW_SELECTION", '{0} < {1}'
                                                        .format(area_field, str(min_area_med)))
            else:
                if lg_reg_method != "NONE":
                    arcpy.SelectLayerByAttribute_management(non_reg_bldg, "NEW_SELECTION", '{0} < {1}'
                                                            .format(area_field, str(min_area_lg)))

            num_features = int(arcpy.GetCount_management(non_reg_bldg).getOutput(0))

            if num_features > 0:
                # Get tolerance in map units
                sm_tolerance_m = bm_common_lib.get_metric_from_linear_unit(sm_tolerance)
                sm_tolerance_map = sm_tolerance_m / m_per_unit

                #  Arthur's method  #
                processed_polygons = simplify_and_buffer(workspace, non_reg_bldg, simplify_tolerance, 0, m_per_unit)

                # Regularize
                arcpy.AddMessage("Regularizing small buildings...")
                sm_bldg_simpa = os.path.join(workspace, "sm_bldg_simpa")
                arcpy.RegularizeBuildingFootprint_3d(in_features=processed_polygons,
                                                     out_feature_class=sm_bldg_simpa,
                                                     method=sm_reg_method,
                                                     tolerance=sm_tolerance_map,
                                                     precision=precision,
                                                     diagonal_penalty=diagonal_penalty)

                # Regularize2
                # arcpy.AddMessage("Regularizing small buildings a second time...")
                # sm_tolerance_mapa = (sm_tolerance_map * 2)
                # sm_bldg_simp = os.path.join(workspace, "sm_bldg_simp")
                # arcpy.RegularizeBuildingFootprint_3d(in_features=sm_bldg_simpa,
                #                                      out_feature_class=sm_bldg_simp,
                #                                      method=sm_reg_method,
                #                                      tolerance=sm_tolerance_mapa,
                #                                      precision=precision,
                #                                      diagonal_penalty=diagonal_penalty)

                #  Dan's method  #
                # Regularize
                # arcpy.AddMessage("Regularizing small buildings")
                # sm_bldg_reg = os.path.join(workspace, "sm_bldg_reg")
                # arcpy.RegularizeBuildingFootprint_3d(in_features=non_reg_bldg,
                #                                      out_feature_class=sm_bldg_reg,
                #                                      method=sm_reg_method,
                #                                      precision=precision,
                #                                      tolerance=sm_tolerance_map)
                #
                # # Simplify buildings
                # sm_bldg_simp = os.path.join(workspace, "sm_bldg_simp")
                # arcpy.SimplifyBuilding_cartography(sm_bldg_reg, sm_bldg_simp, sm_tolerance, min_area)

                # Append to output
                arcpy.Append_management(sm_bldg_simpa, output_poly, "NO_TEST")
            else:
                arcpy.AddMessage("Found no small buildings.")

        arcpy.ClearEnvironment("parallelProcessingFactor")
        return True

    except arcpy.ExecuteWarning:
        print(arcpy.GetMessages(1))
        arcpy.AddWarning(arcpy.GetMessages(1))

    except arcpy.ExecuteError:
        print(arcpy.GetMessages(2))
        arcpy.AddError(arcpy.GetMessages(2))

    # Return any other type of error
    except:
        # By default any other errors will be caught here
        #
        e = sys.exc_info()[1]
        print((e.args[0]))
        arcpy.AddError(e.args[0])


def run(home_directory, project_ws, in_raster,
        min_area, split_features, simplify_tolerance, output_poly,
        reg_circles, circle_min_area, min_compactness,
        circle_tolerance, lg_reg_method, lg_min_area,
        lg_tolerance, med_reg_method, med_min_area,
        med_tolerance, sm_reg_method, sm_tolerance,
        debug=0):
    try:
        if debug == 1:
            delete_intermediate_data = False
            verbose = 1
            in_memory_switch = False
        else:
            delete_intermediate_data = True
            verbose = 0
            in_memory_switch = False

        if os.path.exists(os.path.join(home_directory, "p20")):      # it is a package
            home_directory = os.path.join(home_directory, "p20")

        arcpy.AddMessage("Project Home Directory is: " + home_directory)

        for a in home_directory:
            if a.isspace():
                raise HasSpace

        if bm_common_lib.check_directory(home_directory):
            # set directories
            layer_directory = os.path.join(home_directory, "layer_files")
            log_directory = os.path.join(home_directory, "Logs")
            if not os.path.exists(log_directory):
                os.makedirs(log_directory)

            bm_common_lib.set_up_logging(log_directory, TOOLNAME)

            #  ensure numerical input is correct
            # fail safe for Europe's comma's
            # variables
            min_area = re.sub("[,.]", ".", min_area)
            simplify_tolerance = re.sub("[,.]", ".", simplify_tolerance)
            circle_min_area = re.sub("[,.]", ".", circle_min_area)
            min_compactness = float(re.sub("[,.]", ".", str(min_compactness)))
            circle_tolerance = re.sub("[,.]", ".", circle_tolerance)
            lg_min_area = re.sub("[,.]", ".", lg_min_area)
            lg_tolerance = re.sub("[,.]", ".", lg_tolerance)
            med_min_area = re.sub("[,.]", ".", med_min_area)
            med_tolerance = re.sub("[,.]", ".", med_tolerance)
            sm_tolerance = re.sub("[,.]", ".", sm_tolerance)

            # rename layer files (for packaging)
            if os.path.exists(layer_directory):
                bm_common_lib.rename_file_extension(layer_directory, ".txt", ".lyrx")

            scratch_ws = bm_common_lib.create_gdb(home_directory, "Intermediate.gdb")
            arcpy.env.workspace = scratch_ws
            arcpy.env.overwriteOutput = True

            if arcpy.CheckExtension("3D") == "Available":
                arcpy.CheckOutExtension("3D")

                if arcpy.CheckExtension("Spatial") == "Available":
                    arcpy.CheckOutExtension("Spatial")

                    success = create_building_mosaic(scratch_ws=scratch_ws,
                                                     in_raster=in_raster,
                                                     min_area=min_area,
                                                     split_features=split_features,
                                                     simplify_tolerance=simplify_tolerance,
                                                     output_poly=output_poly,
                                                     reg_circles=reg_circles,
                                                     circle_min_area=circle_min_area,
                                                     min_compactness=min_compactness,
                                                     circle_tolerance=circle_tolerance,
                                                     lg_reg_method=lg_reg_method,
                                                     lg_min_area=lg_min_area,
                                                     lg_tolerance=lg_tolerance,
                                                     med_reg_method=med_reg_method,
                                                     med_min_area=med_min_area,
                                                     med_tolerance=med_tolerance,
                                                     sm_reg_method=sm_reg_method,
                                                     sm_tolerance=sm_tolerance,
                                                     verbose=verbose,
                                                     in_memory_switch=in_memory_switch)

                    if success:
                        arcpy.ClearWorkspaceCache_management()

                        if delete_intermediate_data:
                            fcs = bm_common_lib.listFcsInGDB(scratch_ws)

                            msg_prefix = "Deleting intermediate data..."

                            msg_body = bm_common_lib.create_msg_body(msg_prefix, 0, 0)
                            bm_common_lib.msg(msg_body)

                            for fc in fcs:
                                arcpy.Delete_management(fc)
                    else:
                        arcpy.AddError("Error creating footprints form raster.")
                    # end main code
                else:
                    raise LicenseErrorSpatial
            else:
                raise LicenseError3D

            arcpy.ClearWorkspaceCache_management()

    except StringHasSpace:
        print("One or more parameters has spaces in path. Exiting...")
        arcpy.AddError("One or more parameters has spaces in path. Exiting...")

    except HasSpace:
        print("Home directory has spaces in path. Exiting...")
        arcpy.AddError("Home directory has spaces in path. Exiting...")

    except NoLayerFile:
        print("Can't find Layer file. Exiting...")
        arcpy.AddError("Can't find Layer file. Exiting...")

    except LicenseError3D:
        print("3D Analyst license is unavailable")
        arcpy.AddError("3D Analyst license is unavailable")

    except LicenseErrorSpatial:
        print("Spatial Analyst license is unavailable")
        arcpy.AddError("Spatial Analyst license is unavailable")

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

    finally:
        arcpy.CheckInExtension("3D")
        arcpy.CheckInExtension("Spatial")
