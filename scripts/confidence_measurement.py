import arcpy
import os
import sys
from scripts import bm_common_lib
from scripts.bm_common_lib import create_msg_body, msg, trace


class FunctionError(Exception):
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


class NoFlat(Exception):
    pass


class NoSegmentOutput(Exception):
    pass


class ProVersionRequired(Exception):
    pass


class InputDataNotValid(Exception):
    pass


class NoRoofFeatures(Exception):
    pass


ERROR = "error"
WARNING = "warning"
TOOLNAME = "confidence_measurement"


def CreateBackupFeatureClass(ws, featureClass):
    try:
        myResult = 0

        backUPfeatureClassName = ws+"\\"+arcpy.Describe(featureClass).name+"_BackUp"

        if not arcpy.Exists(backUPfeatureClassName):
            result = arcpy.CopyFeatures_management(featureClass, backUPfeatureClassName)
            myResult = 1

        return(myResult)

    # Return geoprocessing specific errors
    #
    except arcpy.ExecuteWarning:
        print ((arcpy.GetMessages(1)))

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


# Flag buildings with potential missed planes
def CalcMissedPlanes(BuildingRoofPlanes, buildings):
    try:
        # Calculate PlaneArea field on dissolved roof planes
        arcpy.AddField_management(BuildingRoofPlanes, "PlaneArea","FLOAT", None, None, None, None, "true", "false", None)
        arcpy.CalculateField_management(BuildingRoofPlanes, "PlaneArea", "!shape.area!", "PYTHON_9.3", None)

        # Calculate Plane Area Ratio on buildings
        arcpy.JoinField_management(buildings, "BuildingFID", BuildingRoofPlanes, "BuildingFID", "PlaneArea")
        arcpy.AddField_management(buildings, "PlaneAreaRatio", "FLOAT", None, None, None, None, "true", "false", None)
        arcpy.CalculateField_management(buildings, "PlaneAreaRatio", "!PlaneArea! / !shape.area!", "PYTHON_9.3", None)

        # Calculate "Planes Missed" indicator
        arcpy.AddField_management(buildings, "PlanesMissed", "TEXT", None, None, None, None, "true", "false", None)
        missedPlaneCode = """def MissedPlanes(PlaneAreaRatio):
        if (PlaneAreaRatio >= 0.5):
            return "Low"
        elif (PlaneAreaRatio < 0.5 and PlaneAreaRatio > 0.25):
            return "Medium"
        elif (PlaneAreaRatio < 0.25 and PlaneAreaRatio != 0):
            return "High"
        elif (PlaneAreaRatio is None):
            return "All"
            """
        arcpy.CalculateField_management(buildings, "PlanesMissed", "MissedPlanes(!PlaneAreaRatio!)", "PYTHON_9.3", missedPlaneCode)
        arcpy.DeleteField_management(buildings, ["PlaneArea", "PlaneAreaRatio"])
        return buildings

    except arcpy.ExecuteWarning:
        print((arcpy.GetMessages(1)))
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


# Flag buildings with potential eave height underestimation
def CalcLowEaveError(buildings):
    try:
        # Calculate Roof Height Ratio
        arcpy.AddField_management(buildings, "RoofHeightRatio", "FLOAT", None, None, None, None, "true", "false", None)
        arcpy.CalculateField_management(buildings, "RoofHeightRatio", "(!BLDGHEIGHT! - !EAVEHEIGHT!) / !BLDGHEIGHT!", "PYTHON_9.3", None)

        # Calculate "Low Eave Error" indicator
        arcpy.AddField_management(buildings, "LowEaveError", "TEXT", None, None, None, None, "true", "false", None)
        eaveFlagCode = """def EaveFlag(RHRatio):
        if (RHRatio > 0.75):
            return "High"
        elif (RHRatio > 0.65):
            return "Medium"
        elif (RHRatio <= 0.65):
            return "Low"
            """
        arcpy.CalculateField_management(buildings, "LowEaveError", "EaveFlag(!RoofHeightRatio!)", "PYTHON_9.3", eaveFlagCode)
        arcpy.DeleteField_management(buildings, "RoofHeightRatio")
        return buildings

    except arcpy.ExecuteWarning:
        print((arcpy.GetMessages(1)))
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


def RMSE(buildings, dsm, buildingpoints, buildingshell, uniqueID, scratch_ws, verbose):

    # Extract DSM by Buildings
    DSMClip = os.path.join(scratch_ws, "DSMClip")
    if arcpy.Exists(DSMClip):
        arcpy.Delete_management(DSMClip)

    DSM_Extract = arcpy.sa.ExtractByMask(dsm, buildings)
    DSM_Extract.save(DSMClip)

    # Rasterize Building Shells
    BuildingShellRaster = os.path.join(scratch_ws, "BuildingShellRaster")
    description = arcpy.Describe(DSMClip)
    cellsize = description.children[0].meanCellHeight
    if arcpy.Exists(BuildingShellRaster):
        arcpy.Delete_management(BuildingShellRaster)

    if cellsize == 2:
        cellsize = 3

    arcpy.MultipatchToRaster_conversion(buildingshell, BuildingShellRaster, cellsize)

    # Compare Rasters
    SqDiffRasterPath = os.path.join(scratch_ws, "SqDiffRaster")
    if arcpy.Exists(SqDiffRasterPath):
        arcpy.Delete_management(SqDiffRasterPath)
    SqDiffRaster = (arcpy.sa.Raster(DSMClip) - arcpy.sa.Raster(BuildingShellRaster)) * (arcpy.sa.Raster(DSMClip) - arcpy.sa.Raster(BuildingShellRaster))
    SqDiffRaster.save(os.path.join(scratch_ws, "SqDiffRaster"))

    # Convert buildings to zone raster
    bldgzones = os.path.join(scratch_ws, "bldgzones")
    arcpy.FeatureToRaster_conversion(buildings, uniqueID, bldgzones, cellsize)

    # Calculate Mean Square Error Zonal Raster
    MSE = os.path.join(scratch_ws, "MSE_Raster")
    if arcpy.Exists(MSE):
        arcpy.Delete_management(MSE)
    MSE_Raster = arcpy.sa.ZonalStatistics(bldgzones, "VALUE", SqDiffRaster, "MEAN")
    MSE_Raster.save(MSE)

    # Extract RMSE to building points
    RMSEpoints = os.path.join(scratch_ws, "RMSEpoints")
    if arcpy.Exists(RMSEpoints):
        arcpy.Delete_management(RMSEpoints)
    arcpy.sa.ExtractValuesToPoints(buildingpoints, MSE, RMSEpoints, "NONE", "VALUE_ONLY")

    bm_common_lib.delete_add_field(RMSEpoints, "RMSE", "FLOAT")
    arcpy.CalculateField_management(RMSEpoints, "RMSE", "math.sqrt(!RASTERVALU!)", "PYTHON_9.3", None)

    if bm_common_lib.field_exist(buildings, "RMSE"):
        arcpy.DeleteField_management(buildings, "RMSE")

    # Join RMSE to Buildings
    arcpy.JoinField_management(buildings, uniqueID, RMSEpoints, uniqueID, "RMSE")
    if verbose == 0:
        arcpy.Delete_management(DSMClip)
        arcpy.Delete_management(BuildingShellRaster)
        arcpy.Delete_management(SqDiffRaster)
        arcpy.Delete_management(RMSEpoints)

    return buildings, buildingshell

# Run process
def confidence_measure(home_directory, scratch_ws, buildings_layer, dsm,
                       verbose):
    try:
        BuildingPolygons = bm_common_lib.get_full_path_from_layer(buildings_layer)

        layerDirectory = home_directory + "\\layer_files"

        if os.path.exists(layerDirectory):
            bm_common_lib.rename_file_extension(layerDirectory, ".txt", ".lyrx")

        # Create and set workspace location in same directory as input feature class gdb
        workspacePath = bm_common_lib.get_work_space_from_feature_class(BuildingPolygons, "no")
        scratch_ws = bm_common_lib.create_gdb(home_directory, "Analysis.gdb")
        arcpy.env.workspace = scratch_ws
        arcpy.env.overwriteOutput = True

        # Create unique ID Field
        uniqueID = "confidenceID"
        oid = arcpy.Describe(BuildingPolygons).OIDFieldName
        field_names = [f.name for f in arcpy.ListFields(BuildingPolygons)]
        if uniqueID not in field_names:
            arcpy.AddField_management(BuildingPolygons, uniqueID, "LONG")

        arcpy.CalculateField_management(BuildingPolygons, uniqueID, "!{0}!".format(oid), "PYTHON_9.3")

        BuildingPoint = os.path.join(scratch_ws, "BuildingPoint")
        if arcpy.Exists(BuildingPoint):
            arcpy.Delete_management(BuildingPoint)
        arcpy.FeatureToPoint_management(BuildingPolygons, BuildingPoint, "INSIDE")

        # create Multipatch features from procedural layer
        arcpy.AddMessage("Creating building shells...")
        BuildingShells = os.path.join(scratch_ws, "BuildingShells")
        result = arcpy.Layer3DToFeatureClass_3d(buildings_layer, BuildingShells)
        message = result.getMessages()
        num_features = int(arcpy.GetCount_management(BuildingShells).getOutput(0))

        if num_features > 0:
            arcpy.AddMessage("Calculating RMSE of Output Building Shells: ...")

            # Calculate RMSE
            RMSE(BuildingPolygons, dsm, BuildingPoint, BuildingShells, uniqueID, scratch_ws, verbose)

            arcpy.DeleteField_management(BuildingPolygons, uniqueID)

            arcpy.AddMessage("Calculating RMSE of Output Building Shells: DONE!")

            # Delete Intermediate Building Point
            if verbose == 0:
                arcpy.Delete_management(BuildingPoint)
                arcpy.Delete_management(BuildingShells)

            # copy the layer to the Map
            aprx = arcpy.mp.ArcGISProject("CURRENT")

            for m in aprx.listMaps():
                if m.mapType == "MAP":
                    m.addDataFromPath(bm_common_lib.get_full_path_from_layer(dsm))
                    m.addDataFromPath(BuildingPolygons)
        #            m.addLayer(output_layer)
        #            m.addLayer(newLayer2)
                    break
        else:
            arcpy.AddError("Can not convert building layer to multipatch format. Please check input layer for errors.")

    except NoFeatures:
        # The input has no features
        #
        print('Error creating feature class')
        arcpy.AddError('Error creating feature class')

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


def run(home_directory, project_ws, buildings_layer, dsm, debug):
    try:
        if debug == 1:
            delete_intermediate_data = False
            verbose = 1
        else:
            delete_intermediate_data = True
            verbose = 0

        pro_version = arcpy.GetInstallInfo()['Version']
        if int(pro_version[0]) >= 2 and int(pro_version[2]) >= 2 or int(pro_version[0]) >= 3:
            arcpy.AddMessage("ArcGIS Pro version: " + pro_version)
        else:
            raise ProVersionRequired

        if os.path.exists(os.path.join(home_directory, "p20")):      # it is a package
            home_directory = os.path.join(home_directory, "p20")

        arcpy.AddMessage("Project Home Directory is: " + home_directory)

        for a in home_directory:
            if a.isspace():
                raise HasSpace

        if bm_common_lib.check_directory(home_directory):
            scratch_ws = bm_common_lib.create_gdb(home_directory, "Intermediate.gdb")
            arcpy.env.workspace = scratch_ws
            arcpy.env.overwriteOutput = True

            if arcpy.CheckExtension("3D") == "Available":
                arcpy.CheckOutExtension("3D")

                if arcpy.CheckExtension("Spatial") == "Available":
                    arcpy.CheckOutExtension("Spatial")

                    confidence_measure(home_directory=home_directory,
                                       scratch_ws=scratch_ws,
                                       buildings_layer=buildings_layer,
                                       dsm=dsm,
                                       verbose=verbose)

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