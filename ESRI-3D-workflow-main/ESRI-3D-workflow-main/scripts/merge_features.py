# -------------------------------------------------------------------------------
# Name:         merge_features
# Purpose:      merges 1 feature class into another based on intersection

# Author:      Gert van Maren
#
# Created:     08/05/19
# Copyright:   (c) Esri 2019
# updated:
# updated:
# updated:

# Required:
#

# -------------------------------------------------------------------------------

import arcpy
import os
import sys
import time
from scripts import bm_common_lib
from scripts.bm_common_lib import create_msg_body, msg, trace

# constants
TOOLNAME = "merge_features"
WARNING = "warning"
ERROR = "error"
UPDATE_STATUS_FIELD = "Update_Status"


class StringHasSpace(Exception):
    pass


class HasSpace(Exception):
    pass


class NoLayerFile(Exception):
    pass


class NoFlat(Exception):
    pass


class NoSegmentOutput(Exception):
    pass


class ProVersionRequired(Exception):
    pass


class LicenseError3D(Exception):
    pass


class LicenseErrorSpatial(Exception):
    pass


class SchemaLock(Exception):
    pass


class NotSupported(Exception):
    pass


class FunctionError(Exception):

    """
    Raised when a function fails to run.
    """

    pass


def merge_features(scratch_ws, lc_input_features, lc_merge_features, select_field, lc_output_name):

    try:
        merged_fc = None
        point_fc_3d = None

        # merge features
        if lc_input_features and lc_merge_features:
            arcpy.AddMessage("Setting merge date on merge features...")
            date_field = "merge_date"
            bm_common_lib.delete_add_field(lc_merge_features, date_field, "DATE")
            arcpy.CalculateField_management(lc_merge_features, date_field,
                                            "time.strftime('%d/%m/%Y')", "PYTHON_9.3", "")

            # create point feature class showing
            point_fc = os.path.join(scratch_ws, "temp_point")
            if arcpy.Exists(point_fc):
                arcpy.Delete_management(point_fc)

            # create 3D point feature class showing
            point_fc_3d = lc_output_name + "_points"
            if arcpy.Exists(point_fc):
                arcpy.Delete_management(point_fc)

            arcpy.AddZInformation_3d(lc_merge_features, "Z_MIN;Z_MAX", None)
            arcpy.FeatureToPoint_management(lc_merge_features, point_fc, "INSIDE")

            point_field = "point_elevation"
            bm_common_lib.delete_add_field(point_fc, point_field, "DOUBLE")

            z_unit = bm_common_lib.get_z_unit(point_fc, 0)

            if z_unit == "Feet":
                offset = 30
            else:
                offset = 10

            expression = "round(float(!Z_Max!), 2) + " + str(offset)
            arcpy.CalculateField_management(point_fc, point_field, expression, "PYTHON_9.3", None)

            arcpy.FeatureTo3DByAttribute_3d(point_fc, point_fc_3d, point_field, None)

            # select in the base layer the features that don't intersect
            arcpy.AddMessage("Finding all features that don't intersect, this may take some time...")
            non_intersect_lyr = arcpy.SelectLayerByLocation_management(lc_input_features, "INTERSECT",
                                                                       lc_merge_features,
                                                                       None, "NEW_SELECTION", "INVERT")

            input_selectbyloc_layer = os.path.join(scratch_ws, "input_selectbyloc_layer")
            if arcpy.Exists(input_selectbyloc_layer):
                arcpy.Delete_management(input_selectbyloc_layer)

            arcpy.CopyFeatures_management(non_intersect_lyr, input_selectbyloc_layer)
            bm_common_lib.delete_add_field(input_selectbyloc_layer, select_field, "TEXT")
            arcpy.CalculateField_management(input_selectbyloc_layer, select_field, "'Unchanged'", "PYTHON_9.3", "")

            # select features that are not "Demolished in merge layer and only merge those"
            no_demol_lyr = "no_demol_lyr"
            arcpy.MakeFeatureLayer_management(lc_merge_features, no_demol_lyr)
            expression = """{} <> 'Demolished'""".format(arcpy.AddFieldDelimiters(no_demol_lyr, select_field))
            arcpy.SelectLayerByAttribute_management(no_demol_lyr, "NEW_SELECTION", expression, None)

            # merge
            merged_fc = lc_output_name + "_merged"
            if arcpy.Exists(merged_fc):
                arcpy.Delete_management(merged_fc)

            arcpy.Merge_management([input_selectbyloc_layer, no_demol_lyr], merged_fc)

        else:
            msg_body = create_msg_body("No output name detected. Exiting...", 0, 0)
            msg(msg_body, WARNING)

        return merged_fc, point_fc_3d

    except arcpy.ExecuteError:
        # Get the tool error messages
        msgs = arcpy.GetMessages(2)
        arcpy.AddError(msgs)
    except Exception:
        e = sys.exc_info()[1]
        arcpy.AddMessage("Unhandled exception: " + str(e.args[0]))


def run(home_directory, project_ws, input_layer, merge_layer,
        output_name, debug):
    try:
        if debug == 1:
            delete_intermediate_data = False
            verbose = 1
            in_memory_switch = False
        else:
            delete_intermediate_data = True
            verbose = 0
            in_memory_switch = True

        pro_version = arcpy.GetInstallInfo()['Version']
        if int(pro_version[0]) >= 2 and int(pro_version[2]) >= 2 or int(pro_version[0]) >= 3:
            arcpy.AddMessage("ArcGIS Pro version: " + pro_version)
        else:
            raise ProVersionRequired

        if os.path.exists(os.path.join(home_directory, "p20")):  # it is a package
            home_directory = os.path.join(home_directory, "p20")

        arcpy.AddMessage("Project Home Directory is: " + home_directory)

        for a in home_directory:
            if a.isspace():
                raise HasSpace

        if bm_common_lib.check_directory(home_directory):
            # set directories
            layer_directory = home_directory + "\\layer_files"
            log_directory = home_directory + "\\Logs"
            if not os.path.exists(log_directory):
                os.makedirs(log_directory)

            # rename layer files (for packaging)
            if os.path.exists(layer_directory):
                bm_common_lib.rename_file_extension(layer_directory, ".txt", ".lyrx")

            scratch_ws = bm_common_lib.create_gdb(home_directory, "Intermediate.gdb")
            arcpy.env.workspace = scratch_ws
            arcpy.env.overwriteOutput = True
            start_time = time.perf_counter()

            if arcpy.CheckExtension("3D") == "Available":
                arcpy.CheckOutExtension("3D")

                if arcpy.CheckExtension("Spatial") == "Available":
                    arcpy.CheckOutExtension("Spatial")

                    # check if input exists
                    if arcpy.Exists(input_layer) and arcpy.Exists(merge_layer):
                        # check update attribute in merge layer
                        if bm_common_lib.check_fields(merge_layer, [UPDATE_STATUS_FIELD], True, verbose) == 1:
                            msg_body = create_msg_body("Merging all features.", 0, 0)
                            msg(msg_body, WARNING)
                        else:
                            msg_body = create_msg_body("Merging new and modified features.", 0, 0)
                            msg(msg_body)

                        # copy in case layers because layers always fail later on.
                        copy_input_layer = os.path.join(scratch_ws, "copy_input_layer")
                        if arcpy.Exists(copy_input_layer):
                            arcpy.Delete_management(copy_input_layer)

                        arcpy.CopyFeatures_management(input_layer, copy_input_layer)

                        copy_merge_layer = os.path.join(scratch_ws, "copy_merge_layer")
                        if arcpy.Exists(copy_merge_layer):
                            arcpy.Delete_management(copy_merge_layer)

                        arcpy.CopyFeatures_management(merge_layer, copy_merge_layer)

                        # go to main function
                        out_put_features, points = merge_features(scratch_ws=scratch_ws,
                                                                  lc_input_features=copy_input_layer,
                                                                  lc_merge_features=copy_merge_layer,
                                                                  select_field=UPDATE_STATUS_FIELD,
                                                                  lc_output_name=output_name)

                        if out_put_features and points:
                            if arcpy.Exists(out_put_features):
                                # create layer, set layer file
                                # apply transparency here // checking if symbology layer is present
                                z_unit = bm_common_lib.get_z_unit(out_put_features, verbose)

                                if z_unit == "Feet":
                                    change_point_SymbologyLayer = layer_directory + "\\change_point_color_feet.lyrx"
                                    change_mp_SymbologyLayer = layer_directory + "\\change_mp_color_feet.lyrx"
                                else:
                                    change_point_SymbologyLayer = layer_directory + "\\change_point_color_meters.lyrx"
                                    change_mp_SymbologyLayer = layer_directory + "\\change_mp_color_meters.lyrx"

                                output_layer1 = bm_common_lib.get_name_from_feature_class(out_put_features)
                                arcpy.MakeFeatureLayer_management(out_put_features, output_layer1)
                                output_layer2 = bm_common_lib.get_name_from_feature_class(points)
                                arcpy.MakeFeatureLayer_management(points, output_layer2)

                                if arcpy.Exists(change_mp_SymbologyLayer):
                                    arcpy.ApplySymbologyFromLayer_management(output_layer1, change_mp_SymbologyLayer)
                                else:
                                    msg_body = create_msg_body("Can't find" + change_mp_SymbologyLayer +
                                                               " in " + layer_directory, 0, 0)
                                    msg(msg_body, WARNING)

                                if arcpy.Exists(change_point_SymbologyLayer):
                                    arcpy.ApplySymbologyFromLayer_management(output_layer2, change_point_SymbologyLayer)
                                else:
                                    msg_body = create_msg_body(
                                        "Can't find" + change_point_SymbologyLayer + " in " + layer_directory, 0, 0)
                                    msg(msg_body, WARNING)

                                arcpy.SetParameter(3, output_layer1)
                                arcpy.SetParameter(4, output_layer2)

                                end_time = time.perf_counter()
                                msg_body = create_msg_body("merge_features completed successfully.", start_time,
                                                           end_time)
                                msg(msg_body)
                            else:
                                end_time = time.perf_counter()
                                msg_body = create_msg_body("No merge features created. Exiting...", start_time,
                                                           end_time)
                                msg(msg_body, WARNING)

                        arcpy.ClearWorkspaceCache_management()

                        if delete_intermediate_data:
                            fcs = bm_common_lib.listFcsInGDB(scratch_ws)

                            msg_prefix = "Deleting intermediate data..."

                            msg_body = bm_common_lib.create_msg_body(msg_prefix, 0, 0)
                            bm_common_lib.msg(msg_body)

                            for fc in fcs:
                                arcpy.Delete_management(fc)
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
