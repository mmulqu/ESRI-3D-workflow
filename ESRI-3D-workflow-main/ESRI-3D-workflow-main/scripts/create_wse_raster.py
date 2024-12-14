# -------------------------------------------------------------------------------
# Name:        create_wse_raster.py
# Purpose:
#
# Author:      Gert
#
# Created:     07/03/2022
# Copyright:   (c) Esri 2022
# -------------------------------------------------------------------------------


import arcpy
import os
import sys
import re
from scripts.bm_common_lib import create_msg_body, msg, trace
from scripts import bm_common_lib
import locale
locale.setlocale(locale.LC_ALL, '')

# constants
TOOLNAME = "create_modified_dtm"
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


# Create intermediate gdb workspace
def createIntGDB(path, name):
    intGDB = os.path.join(path, name)
    if not arcpy.Exists(intGDB):
        arcpy.CreateFileGDB_management(path, name, "CURRENT")
        return intGDB
    else:
        return intGDB


# Create building extent polygon fc
def CreateExtentFC(ws, name, Building, DTM):
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


def create_wse(project_ws, 
            lc_ws, 
            buffer_distance, 
            water_features,
            depth_attribute,
            dtm, 
            out_raster_ws,
            lc_debug,
            lc_memory_switch):
    try:
        # variables
        if buffer_distance:
            buffer_distance = re.sub("[,.]", ".", buffer_distance)
        else:
            buffer_distance = 0

        m_buffer_distance = bm_common_lib.get_metric_from_linear_unit(buffer_distance)
        m_buffer_distance = locale.atof(str(m_buffer_distance))

        water_extent_name = "water_extent"

        # out rasters
        outPrefix = os.path.basename(dtm)
        mod_dtm_out = os.path.join(out_raster_ws,f"{outPrefix}_wse_mod")
        wse_out = os.path.join(out_raster_ws,f"{outPrefix}_wse")
        
        # check if cs are the same
        feature_sr = arcpy.Describe(water_features).spatialReference.name
        raster_sr = arcpy.Describe(dtm).spatialReference.name

        if feature_sr == raster_sr:
            # create temporary building polygon feature class based on extent of DTM
            print("Selecting features that fall within the extent of the DTM")
            arcpy.AddMessage("Selecting features that fall within the extent of the DTM")
            water_extent_fc = CreateExtentFC(lc_ws, water_extent_name, water_features, dtm)

            if m_buffer_distance > 0:
                # buffer
                water_extent_fc_buffer = os.path.join(lc_ws, "water_buffer")

                if arcpy.Exists(water_extent_fc_buffer):
                    arcpy.Delete_management(water_extent_fc_buffer)

                # buffer water features
                arcpy.AddMessage("Buffering input features...")
                arcpy.Buffer_analysis(water_extent_fc, water_extent_fc_buffer, "-" + buffer_distance, "FULL")
            else:
                water_extent_fc_buffer = water_extent_fc

            arcpy.AddMessage("Creating depth raster...")
            depth_raster = os.path.join(lc_ws, "depth_raster")
            if arcpy.Exists(depth_raster):
                arcpy.Delete_management(depth_raster)

            # create depth raster
            desc = arcpy.Describe(dtm)
            cell_size = round(float(str(desc.meanCellWidth).replace("e-", "")), 2)

            arcpy.env.extent = dtm

            # if there is no depth attribute, create one
            if depth_attribute:
                if len(depth_attribute) != 0:
                    if not bm_common_lib.check_null_in_fields(water_features, [depth_attribute],
                                                              True, 0):
                        arcpy.conversion.PolygonToRaster(water_extent_fc_buffer, depth_attribute,
                                                         depth_raster,
                                                         "CELL_CENTER", "NONE", cell_size, "BUILD")

                        # create NUll mask
                        out_is_null = os.path.join(lc_ws, "outIsNull")
                        if arcpy.Exists(out_is_null):
                            arcpy.Delete_management(out_is_null)
                        out_is_null_raster = arcpy.sa.IsNull(depth_raster)
                        out_is_null_raster.save(out_is_null)

                        dtm_minus = os.path.join(lc_ws, "DTM_minus")
                        if arcpy.Exists(dtm_minus):
                            arcpy.Delete_management(dtm_minus)

                        arcpy.Minus_3d(dtm, depth_raster, dtm_minus)

                        # Create modified raster
                        arcpy.AddMessage(f"Creating modified ground elevation raster: {mod_dtm_out}")
                        
                        if arcpy.Exists(mod_dtm_out):
                            arcpy.Delete_management(mod_dtm_out)
                        out_con_raster = arcpy.sa.Con(out_is_null, dtm, dtm_minus)
                        out_con_raster.save(mod_dtm_out)

                        # Create wse raster
                        arcpy.AddMessage(f"Creating water elevation raster: {wse_out}")

                        if arcpy.Exists(wse_out):
                            arcpy.Delete_management(wse_out)

                        desc = arcpy.Describe(water_extent_fc)
                        extent = desc.extent
                        fp_envelope = f"{extent.XMin} {extent.YMin} {extent.XMax} {extent.YMax}"

                        arcpy.management.Clip(dtm,
                                              fp_envelope,
                                              wse_out,
                                              water_extent_fc, "3.4e+38",
                                              "ClippingGeometry", "NO_MAINTAIN_EXTENT")

                        arcpy.ResetEnvironments()

                        return wse_out, mod_dtm_out
                    else:
                        arcpy.AddError("Fix null values in the input data before running this tool.")
                        return None, None
                else:
                    arcpy.AddError("Can't use depth attribute: " + depth_attribute + ".")
                    return None, None
            else:
                arcpy.AddError("Can't find depth attribute.")
                return None, None
        else:
            arcpy.AddError("Spatial references of the input data are not the same: exiting...")
            return None, None

    # Return geoprocessing specific errors
    #
    except NoFeatures:
        # The input has no features
        #
        print('Error creating feature class')
        arcpy.AddError('Error creating feature class')
        return None, None

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
        return None, None


def run(home_directory, project_ws, water_features,
        depth_attribute,
        dtm,
        out_raster, buffer_distance, debug):
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

                    wse_raster, mod_dtm = create_wse(project_ws=project_ws,
                                                     lc_ws=scratch_ws,
                                                     buffer_distance=buffer_distance,
                                                     water_features=water_features,
                                                     depth_attribute=depth_attribute,
                                                     dtm=dtm,
                                                     out_raster_ws=out_raster,
                                                     lc_debug=verbose,
                                                     lc_memory_switch=in_memory_switch)

                    if arcpy.Exists(wse_raster) and arcpy.Exists(mod_dtm):
                        arcpy.AddMessage("Created water surface elevation raster: " +
                                         bm_common_lib.get_name_from_feature_class(wse_raster) +
                                         " and modified ground elevation raster: " +
                                         bm_common_lib.get_name_from_feature_class(mod_dtm) +
                                         " in " + project_ws + ".")
                                         
                        arcpy.ClearWorkspaceCache_management()

                        if delete_intermediate_data:
                            msg_prefix = "Deleting intermediate data..."
                            msg_body = bm_common_lib.create_msg_body(msg_prefix, 0, 0)
                            bm_common_lib.msg(msg_body)

                            fcs = bm_common_lib.listFcsInGDB(scratch_ws)
                            for fc in fcs:
                                arcpy.Delete_management(fc)
                        else:
                            arcpy.AddError("Input data is not valid. Check your data.")
                            arcpy.AddMessage("Only projected coordinate systems are supported.")
                        
                        arcpy.SetParameter(5,wse_raster)
                        arcpy.SetParameter(6,mod_dtm)
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
