# -------------------------------------------------------------------------------
# Name:        Extract_Elevation_from_LAS.py
# Purpose:     wrapper for Elevation_from_LAS.py
#
# Author:      Gert van Maren
#
# Created:     04/10/12/2018
# Copyright:   (c) Esri 2018
# updated:
# updated:
# updated:

# Required:
#

# -------------------------------------------------------------------------------

import arcpy
import sys
import importlib
import os
import re
import time
from scripts.bm_common_lib import create_msg_body, msg, trace
from scripts import bm_common_lib

# constants
TOOLNAME = "extract_elevation_from_las"
WARNING = "warning"
ERROR = "error"


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


# ----------------------------Main Function---------------------------- #

def extract(lc_lasd, lc_ws, lc_cell_size, lc_ground_classcode,  lc_class_code, lc_output_elevation, lc_minimum_height,
            lc_maximum_height, lc_processing_extent, lc_noise, lc_log_dir, lc_debug, lc_memory_switch):
    try:
        dem = None
        dsm = None
        ndsm = None

        # create dem
        desc = arcpy.Describe(lc_lasd)
        l_unit = desc.spatialReference.linearUnitName
        #        if desc.spatialReference.linearUnitName in ['Foot_US', 'Foot']:
        if 'feet' in l_unit.lower() or 'foot' in l_unit.lower():
            unit = 'Feet'
        else:
            unit = 'Meters'

        if lc_class_code == 15:
            lc_cell_size = lc_cell_size*2

        # Classify overlap points
        # ptSpacing = desc.pointSpacing * 2.25
        # sampling = '{0} {1}'.format(ptSpacing, unit)
        # arcpy.ClassifyLasOverlap_3d(lc_lasd, sampling)

        # get lidar class code - TEMPORARY until Pro 2.3
        msg_body = create_msg_body("Looking for class codes: ", 0, 0)
        msg(msg_body)

        las_desc = arcpy.Describe(lc_lasd)
        class_codes = las_desc.classCodes
        arcpy.AddMessage("Class codes detected: " + str(class_codes))
        class_code_list = [int(code) for code in class_codes.split(';')]

        ground_code = 2

        if lc_ground_classcode and lc_class_code in class_code_list:
            class_code_list = list()
            class_code_list.append(int(ground_code))
            class_code_list.append(int(lc_class_code))

        # Generate DEM
        if ground_code in class_code_list:
            dem = lc_output_elevation + "_dtm"

            if arcpy.Exists(dem):
                arcpy.Delete_management(dem)

            msg_body = create_msg_body("Creating Ground Elevation using the following class codes: " +
                                       str(ground_code), 0, 0)
            msg(msg_body)

            ground_ld_layer = arcpy.CreateUniqueName('ground_ld_lyr')

            # Filter for ground points
            arcpy.management.MakeLasDatasetLayer(lc_lasd, ground_ld_layer, class_code=str(ground_code))

            arcpy.conversion.LasDatasetToRaster(ground_ld_layer, dem, 'ELEVATION',
                                                'BINNING MAXIMUM LINEAR',
                                                sampling_type='CELLSIZE',
                                                sampling_value=lc_cell_size)

            lc_max_neighbors = "#"
            lc_step_width = "#"
            lc_step_height = "#"

            if lc_noise:
                # Classify noise points
                msg_body = create_msg_body("Classifying points that are " + lc_minimum_height + " below ground and " +
                                           lc_maximum_height + " above ground as noise.", 0, 0)
                msg(msg_body)

                arcpy.ClassifyLasNoise_3d(lc_lasd, method='RELATIVE_HEIGHT', edit_las='CLASSIFY',
                                          withheld='WITHHELD', ground=dem,
                                          low_z=lc_minimum_height, high_z=lc_maximum_height,
                                          max_neighbors=lc_max_neighbors, step_width=lc_step_width,
                                          step_height=lc_step_height,
                                          extent=lc_processing_extent)
            else:
                # Classify noise points
                msg_body = create_msg_body("Noise will not be classified.", 0, 0)
                msg(msg_body)

            # check if we need to create dsm and ndsm based on lc_class_code != -1

            if lc_class_code != -1:
                # create dsm
                dsm = lc_output_elevation + "_dsm"

                if arcpy.Exists(dsm):
                    arcpy.Delete_management(dsm)

                msg_body = create_msg_body("Creating Surface Elevation using the following class codes: " +
                                           str(class_code_list), 0, 0)
                msg(msg_body)

                dsm_ld_layer = arcpy.CreateUniqueName('dsm_ld_lyr')

                return_usage = arcpy.Usage("MakeLasDatasetLayer_management").split(', ')[3].strip('{}').split(' | ')
                # last return = first entry
                last_return = return_usage[0]

                if lc_class_code == 15:
                    arcpy.management.MakeLasDatasetLayer(lc_lasd, dsm_ld_layer, class_code=class_code_list)
                else:
                    arcpy.management.MakeLasDatasetLayer(lc_lasd, dsm_ld_layer, class_code=class_code_list,
                                                         return_values=[last_return])

                arcpy.conversion.LasDatasetToRaster(in_las_dataset=dsm_ld_layer,
                                                    out_raster=dsm,
                                                    value_field='ELEVATION',
                                                    interpolation_type='BINNING MAXIMUM LINEAR',
                                                    sampling_type='CELLSIZE',
                                                    sampling_value=lc_cell_size)

                # create ndsm
                msg_body = create_msg_body("Creating normalized Surface Elevation using " +
                                           bm_common_lib.get_name_from_feature_class(dsm) + " and " +
                                           bm_common_lib.get_name_from_feature_class(dem), 0, 0)
                msg(msg_body)

                ndsm = lc_output_elevation + "_ndsm"

                if arcpy.Exists(ndsm):
                    arcpy.Delete_management(ndsm)

                arcpy.Minus_3d(dsm, dem, ndsm)
        else:
            msg_body = create_msg_body("Couldn't detect ground class code in las dataset. "
                                       "Use the -Classify LAS Ground- tool to classify ground. "
                                       "Exiting...", 0, 0)
            msg(msg_body, WARNING)

        return dem, dsm, ndsm

    except arcpy.ExecuteError:
        # Get the tool error messages
        msgs = arcpy.GetMessages(2)
        arcpy.AddError(msgs)
    except Exception:
        e = sys.exc_info()[1]
        arcpy.AddMessage("Unhandled exception: " + str(e.args[0]))


def run(home_directory, project_ws, input_las_dataset, cell_size, only_ground_plus_class_code,
        class_code, output_elevation_raster, classify_noise, minimum_height, maximum_height,
        processing_extent, debug):
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
            start_time = time.perf_counter()

            #  ensure numerical input is correct
            # fail safe for Europe's comma's
            cell_size = float(re.sub("[,.]", ".", cell_size))

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
                    if arcpy.Exists(input_las_dataset):
                        # check if projected coordinates
                        cs_name, cs_vcs_name, is_projected = bm_common_lib.get_cs_info(input_las_dataset, 0)

                        if is_projected:
                            # extract the elevation layers
                            dem, dsm, ndsm = extract(lc_lasd=input_las_dataset,
                                                     lc_ws=project_ws,
                                                     lc_cell_size=float(cell_size),
                                                     lc_ground_classcode=only_ground_plus_class_code,
                                                     lc_class_code=class_code,
                                                     lc_output_elevation=output_elevation_raster,
                                                     lc_minimum_height=minimum_height,
                                                     lc_maximum_height=maximum_height,
                                                     lc_processing_extent=processing_extent,
                                                     lc_noise=classify_noise,
                                                     lc_log_dir=log_directory,
                                                     lc_debug=verbose,
                                                     lc_memory_switch=in_memory_switch)

                            if dem and dsm and ndsm:
                                if arcpy.Exists(dem) and arcpy.Exists(dsm) and arcpy.Exists(ndsm):
                                    arcpy.AddMessage("Adding Surfaces")

                                    output_layer1 = bm_common_lib.get_name_from_feature_class(dem) + "_surface"
                                    arcpy.MakeRasterLayer_management(dem, output_layer1)

                                    output_layer2 = bm_common_lib.get_name_from_feature_class(dsm) + "_surface"
                                    arcpy.MakeRasterLayer_management(dsm, output_layer2)

                                    output_layer3 = bm_common_lib.get_name_from_feature_class(ndsm) + "_surface"
                                    arcpy.MakeRasterLayer_management(ndsm, output_layer3)

                                    arcpy.SetParameter(10, output_layer1)
                                    arcpy.SetParameter(11, output_layer2)
                                    arcpy.SetParameter(12, output_layer3)

                                    end_time = time.perf_counter()
                                    msg_body = create_msg_body("Extract_elevation_from_las completed successfully.",
                                                               start_time, end_time)
                                    msg(msg_body)
                                else:
                                    end_time = time.perf_counter()
                                    msg_body = create_msg_body("No elevation surfaces created. Exiting...", start_time,
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
