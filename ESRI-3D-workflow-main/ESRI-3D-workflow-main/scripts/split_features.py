# -------------------------------------------------------------------------------
# Name:         elevation_from_las
# Purpose:      Creates 3 elevation surface from a input las dataset

# Author:      Gert van Maren
#
# Created:     27/10/18
# Copyright:   (c) Esri 2018
# updated:
# updated:
# updated:

# Required:
#

# -------------------------------------------------------------------------------

import arcpy
import sys
import os
import re
import time
from scripts import bm_common_lib
from scripts.bm_common_lib import create_msg_body, msg, trace

# constants
TOOLNAME = "split_features"
WARNING = "warning"
ERROR = "error"


# error classes
class MoreThan1Selected(Exception):
    pass


class NoLayerFile(Exception):
    pass


class NoPointLayer(Exception):
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


def split(scratch_ws, lc_input_features, lc_split_features, lc_minimum_area, lc_output_name, lc_debug,
          lc_memory_switch):

    try:
        # split features
        if lc_input_features and lc_split_features:

            SHAPEAREAFIELD = "Shape_Area"
            PRESPLITFIELD = "PRESPLIT_FID"

            # Keep original input feature OBJECTID as TEXT. copy to PRESPLITFIELD.
            bm_common_lib.delete_add_field(lc_input_features, PRESPLITFIELD, "LONG")
            arcpy.CalculateField_management(lc_input_features, PRESPLITFIELD, "!OBJECTID!", "PYTHON_9.3", None)

            # use Identity to split the input features
            # copy feature class to capture selection
            identity_fc = os.path.join(scratch_ws, "identity_split")
            if arcpy.Exists(identity_fc):
                arcpy.Delete_management(identity_fc)

            arcpy.AddMessage("Splitting features, this may take some time...")

            # Process: Use the Identity function
            arcpy.Identity_analysis(lc_input_features, lc_split_features, identity_fc, "ONLY_FID")

            # check for area attribute
            if not bm_common_lib.check_fields(identity_fc, [SHAPEAREAFIELD], True, lc_debug) == 0:
                arcpy.AddField_management(identity_fc, "Shape_Area", "DOUBLE")
                exp = "!shape.area!"
                arcpy.CalculateField_management(identity_fc, "Shape_Area", exp, "PYTHON_9.3")

            # select / delete  all features with area < lc_minimum_area
            arcpy.AddMessage("Selecting features with an area < " + str(lc_minimum_area) + "...")
            expression = """{} < {}""".format(arcpy.AddFieldDelimiters(identity_fc, SHAPEAREAFIELD), lc_minimum_area)

            local_layer = bm_common_lib.get_name_from_feature_class(identity_fc) + "_lyr"
            arcpy.MakeFeatureLayer_management(identity_fc, local_layer)
            arcpy.SelectLayerByAttribute_management(local_layer, "NEW_SELECTION", expression)

            num_selected = int(arcpy.GetCount_management(local_layer).getOutput(0))

            if num_selected > 0:
                arcpy.DeleteFeatures_management(local_layer)
                arcpy.AddMessage("Removed " + str(num_selected) + " features with an area < " +
                                 str(lc_minimum_area) + " from the input feature class.")

            arcpy.SelectLayerByAttribute_management(local_layer, "CLEAR_SELECTION")

            # select / delete  all features that have no intersection to get rid of slivers
            arcpy.AddMessage("Selecting features with no intersection...")
            split_FID_field = "FID_" + bm_common_lib.get_name_from_feature_class(lc_split_features)
            expression = """{} = {}""".format(arcpy.AddFieldDelimiters(local_layer, split_FID_field), -1)

            arcpy.SelectLayerByAttribute_management(local_layer, "NEW_SELECTION", expression)

            num_selected = int(arcpy.GetCount_management(local_layer).getOutput(0))

            if num_selected > 0:
                arcpy.DeleteFeatures_management(local_layer)
                arcpy.AddMessage("Removing slivers...")

            arcpy.SelectLayerByAttribute_management(local_layer, "CLEAR_SELECTION")

            num_selected = int(arcpy.GetCount_management(lc_input_features).getOutput(0))

            # add features from input that don't intersect with the resulting fc
            if bm_common_lib.is_layer(lc_input_features) == 0:
                input_layer = bm_common_lib.get_name_from_feature_class(lc_input_features) + "_lyr"
                arcpy.MakeFeatureLayer_management(lc_input_features, input_layer)
                arcpy.SelectLayerByLocation_management(input_layer, "INTERSECT", local_layer,
                                                       invert_spatial_relationship="INVERT")
            else:
                input_layer = lc_input_features

                if bm_common_lib.get_num_selected(input_layer) > 0:
                    arcpy.SelectLayerByLocation_management(input_layer, "INTERSECT", local_layer,
                                                           selection_type="REMOVE_FROM_SELECTION")
                else:
                    arcpy.SelectLayerByLocation_management(input_layer, "INTERSECT", local_layer,
                                                           invert_spatial_relationship="INVERT")

            arcpy.AddMessage("Adding original features with no intersection...")

            # copy layer to preserve selection
            copy_fc = os.path.join(scratch_ws, "copy_selection")
            if arcpy.Exists(copy_fc):
                arcpy.Delete_management(copy_fc)

            # Copy selection to output
            arcpy.CopyFeatures_management(input_layer, copy_fc)

            # merge
            merged_fc = lc_output_name + "_split"
            if arcpy.Exists(merged_fc):
                arcpy.Delete_management(merged_fc)

            arcpy.Merge_management([copy_fc, local_layer], merged_fc)

            # delete PRESPLITFIELD from input features
#            common_lib.delete_fields(lc_input_features, [PRESPLITFIELD])

            arcpy.SelectLayerByAttribute_management(input_layer, "CLEAR_SELECTION")

            return merged_fc

        else:
            msg_body = create_msg_body("No output name detected. Exiting...", 0, 0)
            msg(msg_body, WARNING)

    except arcpy.ExecuteError:
        # Get the tool error messages
        msgs = arcpy.GetMessages(2)
        arcpy.AddError(msgs)
    except Exception:
        e = sys.exc_info()[1]
        arcpy.AddMessage("Unhandled exception: " + str(e.args[0]))


def run(home_directory, project_ws, input_layer, split_layer,
        minimum_area, output_name, debug=0):
    try:
        if debug == 1:
            delete_intermediate_data = False
            verbose = 1
            in_memory_switch = False
        else:
            delete_intermediate_data = True
            verbose = 0
            in_memory_switch = False

        if os.path.exists(home_directory + "\\p20"):  # it is a package
            home_directory = home_directory + "\\p20"

        arcpy.AddMessage("Project Home Directory is: " + home_directory)

        # set directories
        layer_directory = home_directory + "\\layer_files"
        log_directory = home_directory + "\\Logs"
        if not os.path.exists(log_directory):
            os.makedirs(log_directory)

        #  ensure numerical input is correct
        #  fail safe for Europe's comma's
        minimum_area = float(re.sub("[,.]", ".", minimum_area))

        # rename layer files (for packaging)
        if os.path.exists(layer_directory):
            bm_common_lib.rename_file_extension(layer_directory, ".txt", ".lyrx")

        #  Create folders and intermediate gdb, if needed
        scratch_ws = bm_common_lib.create_gdb(home_directory, "Intermediate.gdb")
        arcpy.env.workspace = scratch_ws
        arcpy.env.overwriteOutput = True

        start_time = time.perf_counter()

        # check if input exists
        if arcpy.Exists(input_layer) and arcpy.Exists(split_layer):
            if bm_common_lib.check_valid_input(input_layer, True, ["Polygon"], False, True):
                if bm_common_lib.check_valid_input(split_layer, True, ["Polygon"], False, True):

                    # go to main function
                    out_put_features = split(scratch_ws=scratch_ws,
                                             lc_input_features=input_layer,
                                             lc_split_features=split_layer,
                                             lc_minimum_area=minimum_area,
                                             lc_output_name=output_name,
                                             lc_debug=verbose,
                                             lc_memory_switch=in_memory_switch)

                    if out_put_features:
                        if arcpy.Exists(out_put_features):

                            output_layer1 = bm_common_lib.get_name_from_feature_class(out_put_features)
                            arcpy.MakeFeatureLayer_management(out_put_features, output_layer1)

                            arcpy.SetParameter(4, output_layer1)

                            end_time = time.perf_counter()
                            msg_body = create_msg_body("split_features completed successfully.", start_time, end_time)
                            msg(msg_body)
                        else:
                            end_time = time.perf_counter()
                            msg_body = create_msg_body("No split features created. Exiting...", start_time, end_time)
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
                    arcpy.AddError("Input data is not valid. Check your data.")
            else:
                arcpy.AddError("Input data is not valid. Check your data.")

    except LicenseError3D:
        print("3D Analyst license is unavailable")
        arcpy.AddError("3D Analyst license is unavailable")

    except NoPointLayer:
        print("Can't find attachment points layer. Exiting...")
        arcpy.AddError("Can't find attachment points layer. Exiting...")

    except MoreThan1Selected:
        print("More than 1 line selected. Please select 1 guide line only. Exiting...")
        arcpy.AddError("More than 1 line selected. Please select 1 guide line only. Exiting...")

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







