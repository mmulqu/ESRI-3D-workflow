# -------------------------------------------------------------------------------
# Name:        ModifyDTM.py
# Purpose:
#
# Author:      Gert
#
# Created:     07/04/2016
# Copyright:   (c) Esri 2016
# -------------------------------------------------------------------------------


import arcpy
import os
import sys
import re
import importlib
import time
from scripts.bm_common_lib import create_msg_body, msg, trace
from scripts import bm_common_lib
if 'bm_common_lib' in sys.modules:
    importlib.reload(bm_common_lib)  # force reload of the module

# constants
TOOLNAME = "modify_dtm"
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


# Get Workspace from Building feature class location
def getWorkSpaceFromFeatureClass(feature_class, get_gdb):
    dirname = os.path.dirname(arcpy.Describe(feature_class).catalogPath)
    desc = arcpy.Describe(dirname)

    if hasattr(desc, "datasetType") and desc.datasetType == 'FeatureDataset':
        dirname = os.path.dirname(dirname)

    if get_gdb == "yes":
        return dirname
    else:                   # directory where gdb lives
        return os.path.dirname(dirname)


# Create intermediate gdb workspace
def createIntGDB(path, name):
    intGDB = os.path.join(path, name)
    if not arcpy.Exists(intGDB):
        arcpy.CreateFileGDB_management(path, name, "CURRENT")
        return intGDB
    else:
        return intGDB


# Create building extent polygon fc
def CreateBuildingExtentFC(ws, name, Building, DTM):
    try:
        bldgLayer = "building_lyr"

        DTMExtent = os.path.join(ws, "DTM_extent")
        if arcpy.Exists(DTMExtent):
            result = arcpy.Delete_management(DTMExtent)

        bldgExtent = os.path.join(ws, name)
        if arcpy.Exists(bldgExtent):
            result = arcpy.Delete_management(bldgExtent)

#        extent = arcpy.Describe(DTM).extent.polygon
#        arcpy.management.CopyFeatures(extent, DTMExtent)

        outGeom = "POLYGON"  # output geometry type

        # Execute RasterDomain
        arcpy.RasterDomain_3d(DTM, DTMExtent, outGeom)

        arcpy.MakeFeatureLayer_management(Building, bldgLayer)
        arcpy.SelectLayerByLocation_management(bldgLayer, 'within', DTMExtent)
        arcpy.management.CopyFeatures(bldgLayer, bldgExtent)

        arcpy.Delete_management(DTMExtent)

        return(bldgExtent)

    # Return geoprocessing specific errors
    #
    except arcpy.ExecuteWarning:
        print(arcpy.GetMessages(1))

    except arcpy.ExecuteError:
        print((arcpy.GetMessages(2)))
        arcpy.AddError(arcpy.GetMessages(2))

    # Return any other type of error
    except:
        # By default any other errors will be caught here
        #
        e = sys.exc_info()[1]
        print((e.args[0]))
        arcpy.AddError(e.args[0])


def modify(lc_ws, buffer_distance, building_footprints, dtm, mod_type, offset, mod_dtm,
           lc_debug,
           lc_memory_switch):
    try:
        # variables
        if buffer_distance:
            buffer_distance = re.sub("[,.]", ".", buffer_distance)
        else:
            buffer_distance = 0

        if offset:
            offset = re.sub("[,.]", ".", offset)
        else:
            offset = 0

        building_extent_name = "building_extent"

        # check if cs are the same
        feature_sr = arcpy.Describe(building_footprints).spatialReference.name
        raster_sr = arcpy.Describe(dtm).spatialReference.name

        if feature_sr == raster_sr:
            # create temporary building polygon feature class based on extent of DTM
            print("Selecting features that fall within the extent of the DTM")
            arcpy.AddMessage("Selecting features that fall within the extent of the DTM")
            building_extent_fc = CreateBuildingExtentFC(lc_ws, building_extent_name, building_footprints, dtm)

            # construct sightlines
            building_extent_fc_buffer = os.path.join(lc_ws, "building_buffer")

            if arcpy.Exists(building_extent_fc_buffer):
                arcpy.Delete_management(building_extent_fc_buffer)

            if buffer_distance != 0:
                # buffer building footprints so we get a flat area around the buildings
                arcpy.AddMessage("Buffering input features...")
                arcpy.Buffer_analysis(building_extent_fc, building_extent_fc_buffer, float(buffer_distance), "FULL")
            else:
                building_extent_fc_buffer = building_extent_fc

            # create zonal stat raster with mean value for the building buffers
            dtm_mean = os.path.join(lc_ws, "DTMMean")
            if arcpy.Exists(dtm_mean):
                arcpy.Delete_management(dtm_mean)

            arcpy.env.extent = dtm

            oid_field_name = arcpy.Describe(building_extent_fc_buffer).oidFieldName
            dtm_mean_raster = arcpy.sa.ZonalStatistics(building_extent_fc_buffer, oid_field_name, dtm,
                                                       mod_type.upper(), "true")
            dtm_mean_raster.save(dtm_mean)

            # create NUll mask
            out_is_null = os.path.join(lc_ws, "outIsNull")
            if arcpy.Exists(out_is_null):
                arcpy.Delete_management(out_is_null)
            out_is_null_raster = arcpy.sa.IsNull(dtm_mean_raster)
            out_is_null_raster.save(out_is_null)

            # deal offset
            if offset != 0:
                offset_raster = os.path.join(lc_ws, "offset_raster")

                if arcpy.Exists(offset_raster):
                    arcpy.Delete_management(offset_raster)

                arcpy.Minus_3d(dtm_mean, offset, offset_raster)
                arcpy.Delete_management(dtm_mean)

                dtm_mean = offset_raster

            # Create modified raster
            if arcpy.Exists(mod_dtm):
                arcpy.Delete_management(mod_dtm)
            out_con_raster = arcpy.sa.Con(out_is_null, dtm, dtm_mean)
            out_con_raster.save(mod_dtm)

            arcpy.ResetEnvironments()

            return True
        else:
            arcpy.AddError("Spatial references of the input data are not the same: exiting...")
            return False

    # Return geoprocessing specific errors
    #
    except NoFeatures:
        # The input has no features
        #
        print('Error creating feature class')
        arcpy.AddError('Error creating feature class')

    except arcpy.ExecuteWarning:
        print(arcpy.GetMessages(1))
        arcpy.AddWarning(arcpy.GetMessages(1))

    except arcpy.ExecuteError:
        print((arcpy.GetMessages(2)))
        arcpy.AddError(arcpy.GetMessages(2))

    # Return any other type of error
    except:
        # By default any other errors will be caught here
        #
        e = sys.exc_info()[1]
        print((e.args[0]))
        arcpy.AddError(e.args[0])


def run(home_directory, project_ws, building_footprints, dtm,
        mod_dtm, mod_type, offset, buffer_distance, debug):
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
            if buffer_distance:
                buffer_distance = re.sub("[,.]", ".", buffer_distance)
            else:
                buffer_distance = 0

            if offset:
                offset = re.sub("[,.]", ".", offset)
            else:
                offset = 0

            # rename layer files (for packaging)
            if os.path.exists(layer_directory):
                bm_common_lib.rename_file_extension(layer_directory, ".txt", ".lyrx")

            # Create and set workspace location in same directory as input feature class gdb
            workspace_path = getWorkSpaceFromFeatureClass(building_footprints, "no")
            scratch_ws = createIntGDB(workspace_path, "Intermediate.gdb")
            arcpy.env.workspace = scratch_ws
            arcpy.env.overwriteOutput = True

            if arcpy.CheckExtension("3D") == "Available":
                arcpy.CheckOutExtension("3D")

                if arcpy.CheckExtension("Spatial") == "Available":
                    arcpy.CheckOutExtension("Spatial")

                    success = modify(lc_ws=scratch_ws,
                                     buffer_distance=buffer_distance,
                                     building_footprints=building_footprints,
                                     dtm=dtm,
                                     mod_type=mod_type,
                                     offset=offset,
                                     mod_dtm=mod_dtm,
                                     lc_debug=verbose,
                                     lc_memory_switch=in_memory_switch)

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
