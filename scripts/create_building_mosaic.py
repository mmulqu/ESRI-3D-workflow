# -------------------------------------------------------------------------------
# Name:        create_building_mosaic.py
# Purpose:     Process for creating a 8 bit unsigned mosaic raster from tiles
# Authors:     Dan Hedges | 3D Product Engineer | Esri (Updates for Solution integration)
#              Geoff Taylor | 3D Solutions Engineer | Esri (Framework)
#              Arthur Crawford | Content Product Engineer | Esri (Concept and improvement using raster functions)
#              Andrew Watson | 2017 Esri TWI Program 
# Created:     04/19/2017
# Copyright:   (c) Esri 2017
# Licence:
# -------------------------------------------------------------------------------

import arcpy
import os
import time
import sys
import csv
import re
import locale
locale.setlocale(locale.LC_ALL, '')

from scripts.bm_common_lib import msg, trace
from scripts import bm_common_lib

# constants
TOOLNAME = "create_building_mosaic"
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


def get_metric_from_linear_unit(linear_unit):
    unit_split = linear_unit.split(' ')
    value = float(unit_split[0])
    unit = unit_split[1]
    unit_dict = {
        "Kilometers": .001,
        "Meters": 1,
        "Decimeters": 10,
        "Centimeters": 100,
        "Millimeters": 1000,
        "Feet": 3.28084,
        "Inches": 39.3701,
        "Miles": 0.000621371,
        "Yards": 1.09361,
        "NauticalMiles": 0.000539957
    }
    metric_value = value / unit_dict[unit]
    return metric_value


def create_las_raster(in_file, out_folder, cell_size, spatial_ref):
    try:
        try:
            sr = arcpy.Describe(in_file).spatialReference
            if sr.name == "Unknown" or sr.type == "Geographic":
                sr = spatial_ref
        except:
            sr = spatial_ref

        if not os.path.exists(out_folder):
            os.mkdir(out_folder)

        # Obtain file name without extension
        lasd_layer = "lasd_layer"

        file_name_noext = "{0}".format(os.path.splitext(in_file)[0])
        file_basename = os.path.basename(file_name_noext)

        # Create Las Dataset Layers in scratch folder
        in_lasd = os.path.join(out_folder, "{0}.lasd".format(os.path.splitext(in_file)[0] + "_temp"))

        arcpy.CreateLasDataset_management(in_file, in_lasd, False, "", sr, "COMPUTE_STATS")

        arcpy.MakeLasDatasetLayer_management(in_lasd, lasd_layer, 6)

        bldg_pt_raster = os.path.join(out_folder, "{0}.tif".format(file_basename))
        arcpy.LasPointStatsAsRaster_management(lasd_layer, bldg_pt_raster, "PREDOMINANT_CLASS", "CELLSIZE",
                                               cell_size)
        # Delete Intermediate Data
        arcpy.Delete_management(lasd_layer)
        arcpy.Delete_management(in_lasd)
    except:
        errorMessage = "{0} failed @ {1} : Failed creating raster from las file".format(in_file,
                                                                                    time.strftime("%H:%M:%S"))
        arcpy.AddMessage(errorMessage)


def create_las_rasters(tileList, count, spatialRef, cellSize, scratchFolder):
    # Check to ensure that scratch folder exists:
    if not os.path.exists(scratchFolder):
        os.mkdir(scratchFolder)
    # Recursively process LiDAR Tiles
    iteration = 0
    arcpy.SetProgressor("step", "Percent Complete...", 0, count, iteration)

    for in_file in tileList:
        try:
            arcpy.SetProgressor("step", "{0} Percent Complete...".format(round((100/count)*iteration, 1)), 0, count,
                                iteration)

            create_las_raster(in_file, scratchFolder, cellSize, spatialRef)

            iteration += 1
            arcpy.SetProgressorPosition()

        except:
            iteration += 1
            arcpy.SetProgressorPosition()
            errorMessage = "{0} failed @ {1} : Check if building class-codes exist".format(in_file,
                                                                                           time.strftime("%H:%M:%S"))
            arcpy.AddMessage(errorMessage)
            in_lasd = os.path.join(scratchFolder, "{0}.lasd".format(os.path.splitext(in_file)[0]))
            if arcpy.Exists(in_lasd):
                arcpy.Delete_management(in_lasd)
            pass


def get_files_from_lasd(las_dataset, outputdir, las_sr):
    try:
        # Check LAS Spatial Reference
        if las_sr.name == "Unknown":
            arcpy.AddError("LAS Dataset has an unknown coordinate system."
                           " Please use the Extract LAS tool to re-project and try again")
            return None
        if las_sr.type == "Geographic":
            arcpy.AddError("LAS Dataset is in a geographic coordinate system."
                           " Please re-create the LAS dataset, selecting the correct coordinate system and checking "
                           "'Create PRJ for LAS Files' and try again")
            return None

        # Get LiDAR file names
        las_files = []

        lasStats = os.path.join(outputdir, 'lasStats_stats.csv')

        if arcpy.Exists(lasStats):
            arcpy.Delete_management(lasStats)

        # work around because arcpy.LasDatasetStatistics_management fails in non us locale
        import locale
        orig_local = locale.getlocale()
        locale.setlocale(locale.LC_ALL, 'en_US.utf8')

        arcpy.LasDatasetStatistics_management(las_dataset, "OVERWRITE_EXISTING_STATS", lasStats, "LAS_FILES", "COMMA",
                                              "DECIMAL_POINT")

        locale.setlocale(locale.LC_ALL, orig_local)

        with open(lasStats, 'r') as f:
            reader = csv.reader(f)

            for row in reader:

                if len(row) > 1 and row[0] != 'File_Name' and row[0] not in las_files and row[1] == "6_Building":

                    las_files.append(row[0])

        arcpy.AddMessage('LAS Files with Building (6) class codes found: {}'.format(str(len(las_files))))

        # arcpy.Delete_management(lasStats)

        return las_files

    except arcpy.ExecuteError:
        # Get the tool error messages
        msgs = arcpy.GetMessages(2)
        arcpy.AddError(msgs)
    except Exception:
        e = sys.exc_info()[1]
        arcpy.AddMessage("Unhandled exception: " + str(e.args[0]))


def create_building_mosaic(in_lasd, out_folder, out_mosaic, spatial_ref, cell_size):
    try:
        las_desc = arcpy.Describe(in_lasd)
        las_sr = las_desc.spatialReference

        # Create LAS rasters
        lasd_path = arcpy.Describe(in_lasd).path

        # las_folder = os.path.dirname(lasd_path)
        las_list = get_files_from_lasd(in_lasd, lasd_path, las_sr)

        if las_list:
            las_count = len(las_list)
            metric_cell_size = get_metric_from_linear_unit(cell_size)
            las_m_per_unit = las_sr.metersPerUnit
            cell_size_conv = metric_cell_size / las_m_per_unit

            if las_count > 0:
                create_las_rasters(tileList=las_list, count=las_count, spatialRef=spatial_ref, cellSize=cell_size_conv,
                                   scratchFolder=out_folder)
            else:
                arcpy.AddError(
                    "No LAS files found containing Building (6) class codes. Classify building points and try again")
                return False

            # Create mosaic dataset
            if not arcpy.Exists(out_mosaic):
                out_gdb = os.path.dirname(out_mosaic)
                mosaic_name = os.path.basename(out_mosaic)

                arcpy.CreateMosaicDataset_management(out_gdb, mosaic_name, spatial_ref, None, "8_BIT_UNSIGNED",
                                                     "CUSTOM",
                                                     None)
                arcpy.AddMessage('Mosaic dataset {} created...'.format(out_mosaic))

            # Add rasters to mosaic and set cell size
            arcpy.AddMessage('Adding rasters to mosaic dataset...')
            arcpy.AddRastersToMosaicDataset_management(out_mosaic, "Raster Dataset", out_folder,
                                                       "UPDATE_CELL_SIZES", "UPDATE_BOUNDARY", "NO_OVERVIEWS", None, 0,
                                                       1500,
                                                       None, None, "SUBFOLDERS", "ALLOW_DUPLICATES", "NO_PYRAMIDS",
                                                       "NO_STATISTICS",
                                                       "NO_THUMBNAILS", None, "NO_FORCE_SPATIAL_REFERENCE",
                                                       "NO_STATISTICS",
                                                       None)

            # Update mosaic cell size
            arcpy.AddMessage('Updating mosaic cell size...')
            cellSize = arcpy.GetRasterProperties_management(out_mosaic, "CELLSIZEX")
            cellSize = re.sub("[,.]", ".", cellSize.getOutput(0))
            newSize = float(float(cellSize) / 2)
            arcpy.SetMosaicDatasetProperties_management(out_mosaic, cell_size=newSize)

            arcpy.AddMessage("Process complete")
        else:
            arcpy.AddError("Create Draft Footprint Raster failed.")

        return True

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


def run(home_directory, project_ws, in_lasd, out_folder,
        out_mosaic, spatial_ref, cell_size, debug):
    try:
        if debug == 1:
            delete_intermediate_data = False
        else:
            delete_intermediate_data = True

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
            cell_size = re.sub("[,.]", ".", cell_size)

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

                    success = create_building_mosaic(in_lasd=in_lasd,
                                                     out_folder=out_folder,
                                                     out_mosaic=out_mosaic,
                                                     spatial_ref=spatial_ref,
                                                     cell_size=cell_size)

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
                        arcpy.AddError("Error creating footprint raster.")
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

