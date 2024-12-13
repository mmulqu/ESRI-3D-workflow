# -------------------------------------------------------------------------------
# Name:        ExtrudeByAtrribute
# Purpose:     Creates volumes from multipatch or polygon featuree. Requires numeri
#              attribute to be present in the input feature
#
# Author:      Gert van Maren
#
# Created:     16/11/12/2017
# Copyright:   (c) Esri 2017
# updated:
# updated:
# updated:

# Required:
#

# -------------------------------------------------------------------------------

import arcpy
import time
import os
import re
from scripts.bm_common_lib import create_msg_body, msg, trace
from scripts import bm_common_lib

# constants
ERROR = "error"
TOOLNAME = "CreateFloorVolumes"
CEextrusionheight = "extrusion_height"
CEunits = "extrusion_unit"
CEoffset = "offset"

WARNING = "warning"


# error classes
class StringHasSpace(Exception):
    pass


class HasSpace(Exception):
    pass


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


class FoundNullValues(Exception):
    pass


def do_extrude_by_attribute(ws, local_input_features, local_output_features, local_attribute, local_offset, local_rpk,
                            local_verbose):
    if local_verbose == 1:
        msg("--------------------------")
        msg("Executing extrude_by_attribute...")

    start_time = time.perf_counter()
    failed = False
    msg_prefix = ""

    try:
        msg_prefix = ""
        failed = True

        # your function code
        # split into edges
        msg_body = "Extruding features..."
        msg(msg_body)

        if bm_common_lib.get_z_unit(local_input_features, 0) == "Feet":
            bm_common_lib.delete_add_field(local_input_features, CEunits, "TEXT")
            arcpy.CalculateField_management(local_input_features, CEunits, "'Feet'", "PYTHON_9.3")

        # add extrusion attribute to feature class
        bm_common_lib.delete_add_field(local_input_features, CEextrusionheight, "DOUBLE")
        arcpy.CalculateField_management(local_input_features, CEextrusionheight, "!" + local_attribute + "!",
                                        "PYTHON_9.3")

        bm_common_lib.delete_add_field(local_input_features, CEoffset, "TEXT")
        arcpy.CalculateField_management(local_input_features, CEoffset, local_offset, "PYTHON_9.3")

        arcpy.FeaturesFromCityEngineRules_3d(local_input_features, local_rpk, local_output_features,
                                             "INCLUDE_EXISTING_FIELDS")

        msg_prefix = "extrude_by_attribute completed successfully."
        failed = False
        return local_output_features

    except:
        line, filename, synerror = trace()
        failed = True
        msg_prefix = ""
        raise FunctionError(
            {
                "function": "extrude_by_attribute",
                "line": line,
                "filename": filename,
                "synerror": synerror,
                "arc": str(arcpy.GetMessages(2))
            }
        )

    finally:
        end_time = time.perf_counter()
        msg_body = create_msg_body(msg_prefix, start_time, end_time)
        if failed:
            msg(msg_body, ERROR)
        else:
            if local_verbose == 1:
                msg(msg_body)
            pass


# ----------------------------Main Function---------------------------- #

def extrude_by_attribute(home_directory, project_ws, scratch_ws, input_features,
                         extrude_attribute, offset, output_features,
                         verbose, in_memory_switch):
    try:
        rule_directory = home_directory + "\\rule_packages"
        layer_directory = home_directory + "\\layer_files"

        start_time = time.perf_counter()

        output_name = str(os.path.basename(output_features))
        output_dir = str(os.path.dirname(output_features))
        output_features_path = os.path.join(output_dir, output_name) + "_volumes"
        if arcpy.Exists(output_features_path):
            arcpy.Delete_management(output_features_path)

        # check input exists
        if arcpy.Exists(input_features):
            input_type = arcpy.Describe(input_features).shapetype

            if input_type == "MultiPatch" or input_type == "Polygon":
                if bm_common_lib.check_fields(input_features, [extrude_attribute], False, verbose) == 0:
                    if bm_common_lib.check_null_in_fields(input_features, [extrude_attribute], True, verbose):
                        msg_body = "Detected NULL values in extusion attribute, Exitting..."
                        msg(msg_body)

                        raise FoundNullValues

                    if input_type == "MultiPatch":
                        extrude_rpk = rule_directory + "\\ExtrudeMultipatch.rpk"
                    elif input_type == "Polygon":
                        extrude_rpk = rule_directory + "\\ExtrudePolygon.rpk"
                    else:
                        extrude_rpk = ""

                    # else continue
                    output_volumes = do_extrude_by_attribute(project_ws, input_features, output_features_path,
                                                             extrude_attribute, offset, extrude_rpk, verbose)

                    end_time = time.perf_counter()
                    msg_body = create_msg_body("extrude_by_volume completed successfully.", start_time, end_time)
                    msg(msg_body)

                    return output_volumes
            else:
                end_time = time.perf_counter()
                msg_body = create_msg_body("Input " + input_features +
                                           " must be multipatch or polygon type. Exiting...!", start_time, end_time)
                msg(msg_body, ERROR)
                return None
        else:
            end_time = time.perf_counter()
            msg_body = create_msg_body("Can't find: " + input_features + "!", start_time, end_time)
            msg(msg_body, WARNING)
            return None

    except FoundNullValues:
        print("Found NULL values in UID field. Remove field and rerun...")
        arcpy.AddError("Found NULL values in UID field. Remove field and rerun...")

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


def run(home_directory, project_ws, input_features, extrude_attribute,
        offset, output_features, debug):
    try:
        if debug == 1:
            delete_intermediate_data = False
            verbose = 1
            in_memory_switch = False
        else:
            delete_intermediate_data = True
            verbose = 0
            in_memory_switch = True

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
            offset = re.sub("[,.]", ".", offset)

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

                    # check if input exists
                    if arcpy.Exists(input_features):
                        # check if projected coordinates
                        cs_name, cs_vcs_name, is_projected = bm_common_lib.get_cs_info(input_features, 0)

                        if is_projected:
                            output_fc = extrude_by_attribute(home_directory,
                                                             project_ws,
                                                             scratch_ws,
                                                             input_features,
                                                             extrude_attribute,
                                                             offset, output_features,
                                                             verbose,
                                                             in_memory_switch)

                            if arcpy.Exists(output_fc):
                                output_layer = bm_common_lib.get_name_from_feature_class(output_fc)
                                arcpy.MakeFeatureLayer_management(output_fc, output_layer)

                                if bm_common_lib.get_z_unit(output_fc, 0) == "Feet":
                                    colorSymbologyLayer = layer_directory + "\\colorVolumes_feet.lyrx"
                                else:
                                    colorSymbologyLayer = layer_directory + "\\colorVolumes_meters.lyrx"

                                if arcpy.Exists(colorSymbologyLayer):
                                    arcpy.ApplySymbologyFromLayer_management(output_layer, colorSymbologyLayer)
                                else:
                                    msg_body = create_msg_body(
                                        "Can't find" + colorSymbologyLayer + " in " + layer_directory, 0, 0)
                                    msg(msg_body, WARNING)

                                arcpy.SetParameter(4, output_layer)

                            if delete_intermediate_data:
                                fcs = bm_common_lib.listFcsInGDB(scratch_ws)

                                msg_prefix = "Deleting intermediate data..."

                                msg_body = bm_common_lib.create_msg_body(msg_prefix, 0, 0)
                                bm_common_lib.msg(msg_body)

                                for fc in fcs:
                                    arcpy.Delete_management(fc)
                        else:
                            arcpy.AddError("Input data is not valid. Check your data.")
                            arcpy.AddMessage("Only projected coordinate systems are supported.")
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
