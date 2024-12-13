import arcpy
import os
import math
import sys
import time
import re
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
TOOLNAME = "extract_roof_form"

MinRoofSlope = 10
MaxRoofSlope = 60

BLDGHEIGHTfield = "BLDGHEIGHT"
EAVEHEIGHTfield = "EAVEHEIGHT"
ROOFFORMField = "ROOFFORM"
BASEELEVATIONfield = "BASEELEV"
ROOFDIRECTIONfield = "ROOFDIR"
BUILDINGIDfield = "BuildingFID"
numBUILDINGIDfield = "numBuildingFID"


def AddField(featureclass, field, fieldtype):
    if not bm_common_lib.field_exist(featureclass, field):
        arcpy.AddField_management(featureclass, field, fieldtype)


def joinOrigFields(newFC, newJoinField, origFC, origJoinField, avoid_fields):
    origFields = [f.name for f in arcpy.ListFields(origFC)]
    newFields = [f.name for f in arcpy.ListFields(newFC)]
    orig_oid = arcpy.Describe(origFC).OIDFieldName
    newFields.append(orig_oid)
    newFields.extend(avoid_fields)
    joinList = [item for item in origFields if item not in newFields]

    # Join fields to original feature class
    arcpy.JoinField_management(newFC, newJoinField, origFC, origJoinField, joinList)


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
        print((arcpy.GetMessages(1)))

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


# Create Roof-Form Domain
def AddRoofFormDomain(inFeatures):
    inGDB = bm_common_lib.get_work_space_from_feature_class(inFeatures, "yes")
    domName = "RoofFormTypes"
    inField = ROOFFORMField

    domDesc = arcpy.Describe(inGDB)
    domains = domDesc.domains

    if not domName in domains:
        arcpy.CreateDomain_management(inGDB, domName, "Valid Roof Form Types", "TEXT", "CODED")

        #create coded value dictionary
        domDict = {"Flat": "Flat", "Shed": "Shed", "Gable": "Gable", "Hip": "Hip", "Mansard": "Mansard", "Dome": "Dome", "Vault":"Vault", "Spherical": "Spherical"}

        # Add coded values to Domain
        for code in domDict:
            arcpy.AddCodedValueToDomain_management(inGDB, domName, code, domDict[code])

    # Assign domain to features
    arcpy.AssignDomainToField_management(inFeatures, inField, domName)

    return inFeatures


def DropAddRoofFormFields(featureclass):

    # Delete fields
    arcpy.DeleteField_management(featureclass, BLDGHEIGHTfield)
    arcpy.DeleteField_management(featureclass, EAVEHEIGHTfield)
    arcpy.DeleteField_management(featureclass, BASEELEVATIONfield)
    arcpy.DeleteField_management(featureclass, ROOFFORMField)
    arcpy.DeleteField_management(featureclass, ROOFDIRECTIONfield)
    arcpy.DeleteField_management(featureclass, BUILDINGIDfield)
    arcpy.DeleteField_management(featureclass, numBUILDINGIDfield)

    # Add all necessary fields
    arcpy.AddField_management(featureclass, BLDGHEIGHTfield, "FLOAT")
    arcpy.AddField_management(featureclass, EAVEHEIGHTfield, "FLOAT")
    arcpy.AddField_management(featureclass, ROOFFORMField, "TEXT")
    arcpy.AddField_management(featureclass, BUILDINGIDfield, "TEXT")
    arcpy.AddField_management(featureclass, numBUILDINGIDfield, "LONG")

    return featureclass


# Minimum Height Threshold DSM
def MinimumRoofHeightThresholdDSM (nDSM, DSM, MinHtThresholdDSM, RoofSlope, BuildingFootprint, MinRoofHeight,
                                   scratch_ws, verbose):
    arcpy.env.mask = BuildingFootprint
    # Calculate nDSM > 6ft
    minHeightnDSM = os.path.join(scratch_ws, "minHeightnDSM")
    if arcpy.Exists(minHeightnDSM):
        arcpy.Delete_management(minHeightnDSM)
    minHeightnDSMRaster = arcpy.sa.Con(nDSM, 1, 0, "VALUE >= " + str(MinRoofHeight))
    minHeightnDSMRaster.save(minHeightnDSM)

    # Set nDSM pixels < 6ft as Null
    nDSMNull = os.path.join(scratch_ws, "nDSMNull")
    if arcpy.Exists(nDSMNull):
        arcpy.Delete_management(nDSMNull)
    nDSMNullRaster = arcpy.sa.SetNull(minHeightnDSM, minHeightnDSM, "VALUE = 0")
    # Delete Intermediate minHeightnDSM Raster
    if verbose == 0:
        arcpy.Delete_management(minHeightnDSM)
    nDSMNullRaster.save(nDSMNull)

    # raster to elevation
    if arcpy.Exists(MinHtThresholdDSM):
        arcpy.Delete_management(MinHtThresholdDSM)
    minHeightDSMRaster = arcpy.sa.Con(nDSMNull, 0, DSM, "VALUE = 0")
    # Delete Intermediate nDSMNull Raster
    if verbose == 0:
        arcpy.Delete_management(nDSMNull)
    minHeightDSMRaster.save(MinHtThresholdDSM)

    # Create Roof Slope Raster
    if arcpy.Exists(RoofSlope):
        arcpy.Delete_management(RoofSlope)
    arcpy.Slope_3d(MinHtThresholdDSM, RoofSlope, "DEGREE", 1)

    return MinHtThresholdDSM, RoofSlope


# Create Roof Plane Polygons
def CreateRoofPlanePolygons(RoofSlope, MinHtThresholdDSM, MinRoofSlope, MaxRoofSlope, MinSlopeRoofArea, Buildings,
                            scratch_ws, verbose):
    # Extract Slope Raster by Building Area
    BuildingRoofSlope = os.path.join(scratch_ws, "BuildingRoofSlope")
    if arcpy.Exists(BuildingRoofSlope):
        arcpy.Delete_management(BuildingRoofSlope)
    BuildingSlopeExtract = arcpy.sa.ExtractByMask(RoofSlope, Buildings)
    if BuildingSlopeExtract.maximum is not None:
        BuildingSlopeExtract.save(BuildingRoofSlope)

        # Create Roof Slope Angle Raster
        RoofSlopeAngle = os.path.join(scratch_ws, "RoofSlopeAngle")
        if arcpy.Exists(RoofSlopeAngle):
            arcpy.Delete_management(RoofSlopeAngle)
        RoofSlopeAngleRaster = arcpy.sa.Con((arcpy.sa.Raster(BuildingRoofSlope) > MinRoofSlope) & (arcpy.sa.Raster(BuildingRoofSlope) < MaxRoofSlope), arcpy.sa.Raster(RoofSlope), 0)
        RoofSlopeAngleRaster.save(RoofSlopeAngle)
        if verbose == 0:
            arcpy.Delete_management(BuildingRoofSlope)

        # Set Nil RoofSlope Pixels classified as 0 to only enable sloped roof pixels
        RoofSlopeAngleNull = os.path.join(scratch_ws, "RoofSlopeAngleNull")
        if arcpy.Exists(RoofSlopeAngleNull):
            arcpy.Delete_management(RoofSlopeAngleNull)
        RoofSlopeAngleRaster = arcpy.sa.SetNull(RoofSlopeAngle, RoofSlopeAngle, "VALUE = 0")
        RoofSlopeAngleRaster.save(RoofSlopeAngleNull)

        arcpy.env.mask = RoofSlopeAngleNull
        Aspect = os.path.join(scratch_ws, "Aspect")
        if arcpy.Exists(Aspect):
            arcpy.Delete_management(Aspect)
        arcpy.Aspect_3d(MinHtThresholdDSM, Aspect)

        AspectReclassified = os.path.join(scratch_ws, "AspectReclass")
        if arcpy.Exists(AspectReclassified):
            arcpy.Delete_management(AspectReclassified)
        arcpy.Reclassify_3d(Aspect, "VALUE", "-1 22.500000 1;22.500000 67.500000 2;67.500000 112.500000 3;112.500000 157.500000 4;157.500000 202.500000 5;202.500000 247.500000 6;247.500000 292.500000 7;292.500000 337.500000 8;337.500000 360 1",
                            AspectReclassified, "false")

        AspectPolygons = os.path.join(scratch_ws, "AspectPolygons")
        if arcpy.Exists(AspectPolygons):
            arcpy.Delete_management(AspectPolygons)
        arcpy.RasterToPolygon_conversion(AspectReclassified, AspectPolygons, "false", "Value")

        AspectPolyClipped = os.path.join(scratch_ws, "AspectPolyClipped")
        if arcpy.Exists(AspectPolyClipped):
            arcpy.Delete_management(AspectPolyClipped)
        arcpy.Intersect_analysis([AspectPolygons, Buildings], AspectPolyClipped, "NO_FID")

        # Dan create the variable here and return it below
        RoofPlanePolygons = os.path.join(scratch_ws, "RoofPlanePolygons")
        if arcpy.Exists(RoofPlanePolygons):
            arcpy.Delete_management(RoofPlanePolygons)

        # Added for "in_memory" processing as in_memory does not except "Shape_Area" only "shape.area"
        arcpy.AddField_management(AspectPolyClipped, "GeomArea", "DOUBLE", None, None, None, None, "true", "false", None)
        arcpy.CalculateField_management(AspectPolyClipped, "GeomArea", "!shape.area!", "PYTHON_9.3", None)

        RoofPlaneEquation = "GeomArea >= " + str(MinSlopeRoofArea)
        arcpy.Select_analysis(AspectPolyClipped, RoofPlanePolygons, RoofPlaneEquation)

        # Delete Intermediate Aspect Polygons
        if verbose == 0:
            arcpy.Delete_management(AspectPolygons)
            arcpy.Delete_management(RoofSlopeAngleNull)
            arcpy.Delete_management(RoofSlopeAngle)
            arcpy.Delete_management(Aspect)
            arcpy.Delete_management(AspectReclassified)
            arcpy.Delete_management(AspectPolyClipped)

        return RoofPlanePolygons


# Create Aspect Polygons
def CreateAspectPlanes(SlopedPlaneBuilding, UniqueAspectPlanes):
    arcpy.AddField_management(SlopedPlaneBuilding, "FID_Aspect_Concat", "TEXT", None, None, None, None,
                              "true", "false", None)
    ConcatEquation = '!BuildingFID! + "_" + str(!GRIDCODE!)'
    arcpy.CalculateField_management(SlopedPlaneBuilding, "FID_Aspect_Concat", ConcatEquation, "PYTHON_9.3")

    if arcpy.Exists(UniqueAspectPlanes):
        arcpy.Delete_management(UniqueAspectPlanes)
    arcpy.Dissolve_management(SlopedPlaneBuilding, UniqueAspectPlanes, "FID_Aspect_Concat", None, "MULTI_PART", "DISSOLVE_LINES")
    return UniqueAspectPlanes


# Calculate BuildingMinElevation
def BuildingMinElevation(BuildingFootprint, DTM, BuildingPoint, IDField,
                         scratch_ws):
    arcpy.env.mask = BuildingFootprint
    DTMMin = os.path.join(scratch_ws, "DTMMin")
    if arcpy.Exists(DTMMin):
        arcpy.Delete_management(DTMMin)
    DTMMinRaster = arcpy.sa.ZonalStatistics(BuildingFootprint, IDField, DTM, "MINIMUM", "DATA")
    DTMMinRaster.save(DTMMin)
    arcpy.AddSurfaceInformation_3d(BuildingPoint, DTMMin, "Z", "BILINEAR", 1, 1, 0, None)
    arcpy.AddField_management(BuildingPoint, BASEELEVATIONfield, "FLOAT")
    arcpy.CalculateField_management(BuildingPoint, BASEELEVATIONfield, "!Z!", "PYTHON_9.3", None)
    if arcpy.Exists(DTMMin):
        arcpy.Delete_management(DTMMin)
    return BuildingPoint


# Select largest feature with unique attribute
def DeleteAddField(featureclass, field, fieldtype):
    try:
        if bm_common_lib.field_exist(featureclass, field):
            arcpy.DeleteField_management(featureclass, field)

        result = arcpy.AddField_management(featureclass, field, fieldtype)

    except arcpy.ExecuteWarning:
        print ((arcpy.GetMessages(1)))
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


def unique_values(table, field):
        with arcpy.da.SearchCursor(table, [field]) as cursor:
            return sorted({row[0] for row in cursor})


# Calculate EaveHeight Elevation
def BuildingEaveHeight(LgSlopedPlane, DSM, LgSlopedPlaneBuildingPoint, IDField,
                       scratch_ws, verbose):
    arcpy.env.mask = LgSlopedPlane
    DSMMin = os.path.join(scratch_ws, "DSMMin")
    if arcpy.Exists(DSMMin):
        arcpy.Delete_management(DSMMin)
    DSMMinRaster = arcpy.sa.ZonalStatistics(LgSlopedPlane, IDField, DSM, "MINIMUM", "DATA")
    DSMMinRaster.save(DSMMin)

    arcpy.AddSurfaceInformation_3d(LgSlopedPlaneBuildingPoint, DSMMin, "Z", "BILINEAR", 1, 1, 0, None)

    # Delete Intermediate DSMMin Raster
    if verbose == 0:
        arcpy.Delete_management(DSMMin)

    arcpy.AddField_management(LgSlopedPlaneBuildingPoint, "Eave_Elev", "FLOAT", None, None, None, None, "true",
                              "false", None)
    arcpy.CalculateField_management(LgSlopedPlaneBuildingPoint, "Eave_Elev", "!Z!", "PYTHON_9.3", None)
    return LgSlopedPlaneBuildingPoint


# Create Flat Roof Polygon
def FlatRoofPolygons(BuildingFootprint, RoofSlope, FlatAreaPolygons,
                     scratch_ws, verbose):
    arcpy.env.mask = BuildingFootprint
    RoofSlopeLessThan10deg = os.path.join(scratch_ws, "RoofSlopeLessThan10deg")
    if arcpy.Exists(RoofSlopeLessThan10deg):
        arcpy.Delete_management(RoofSlopeLessThan10deg)
    RoofSlopeRast = arcpy.sa.Raster(RoofSlope)
    FlatRoofRaster = arcpy.sa.Con(RoofSlopeRast, 1, 0, "VALUE < 10")
    FlatRoofRaster.save(RoofSlopeLessThan10deg)
    # Set Nil RoofSlope Pixels classified as 0 to only enable sloped roof pixels
    SetNullFlatRoof = os.path.join(scratch_ws, "SetNullFlatRoof")
    if arcpy.Exists(SetNullFlatRoof):
        arcpy.Delete_management(SetNullFlatRoof)
    RoofSlopeAngleRaster = arcpy.sa.SetNull(RoofSlopeLessThan10deg, 1, "VALUE = 0")
    RoofSlopeAngleRaster.save(SetNullFlatRoof)
    # Delete Intermediate RoofSlopeLessThan10deg Raster
    if verbose == 0:
        arcpy.Delete_management(RoofSlopeLessThan10deg)

    FlatAreaPolyRaw = os.path.join(scratch_ws, "FlatAreaPolyRaw")
    if arcpy.Exists(FlatAreaPolyRaw):
        arcpy.Delete_management(FlatAreaPolyRaw)
    arcpy.RasterToPolygon_conversion(SetNullFlatRoof, FlatAreaPolyRaw, "false", "Value")

    if arcpy.Exists(FlatAreaPolygons):
        arcpy.Delete_management(FlatAreaPolygons)
    arcpy.Intersect_analysis([FlatAreaPolyRaw, BuildingFootprint], FlatAreaPolygons)
    # Delete Intermediate SetNullFlatRoof Raster
    if verbose == 0:
        arcpy.Delete_management(SetNullFlatRoof)
        arcpy.Delete_management(FlatAreaPolyRaw)

    return FlatAreaPolygons


def FlatRoofAreas(FlatAreaPolygons, RoofPlanesMergeOutput, MinFlatRoofArea):

    # Added for "in_memory" processing as in_memory does not except "Shape_Area" only "shape.area"
    arcpy.AddField_management(FlatAreaPolygons, "GeomArea", "DOUBLE", None, None, None, None, "true", "false", None)
    arcpy.CalculateField_management(FlatAreaPolygons, "GeomArea", "!shape.area!", "PYTHON_9.3", None)

    FlatRoofPlaneEquation = "GeomArea > " + str(MinFlatRoofArea)
    arcpy.Select_analysis(FlatAreaPolygons, RoofPlanesMergeOutput, FlatRoofPlaneEquation)
    return RoofPlanesMergeOutput


def FlatAreaCalculate(FlatAreaPolygons, BuildingFootprint, FlatAreaDissolved, scratch_ws, verbose):
    FlatAreaJoined = os.path.join(scratch_ws, "FlatAreaJoined")
    arcpy.SpatialJoin_analysis(FlatAreaPolygons, BuildingFootprint, FlatAreaJoined, "JOIN_ONE_TO_ONE", "KEEP_ALL",
                               "", "CONTAINS", None, None)
    arcpy.Dissolve_management(FlatAreaJoined, FlatAreaDissolved, BUILDINGIDfield, "", "MULTI_PART")
    # Delete Intermediate FlatAreaJoined Polygon
    if verbose == 0:
        arcpy.Delete_management(FlatAreaJoined)
    arcpy.AddField_management(FlatAreaDissolved, "FlatArea", "FLOAT", None, None, None, None, "true",
                              "false", None)

    # Added for "in_memory" processing as in_memory does not except "Shape_Area" only "shape.area"
    arcpy.AddField_management(FlatAreaDissolved, "GeomArea", "DOUBLE", None, None, None, None, "true", "false", None)
    arcpy.CalculateField_management(FlatAreaDissolved, "GeomArea", "!shape.area!", "PYTHON_9.3", None)

    arcpy.CalculateField_management(FlatAreaDissolved, "FlatArea", "!GeomArea!", "PYTHON_9.3", None)
    return FlatAreaDissolved


# Flat Plane Count
def FlatPlaneCount(FlatRoofPlanes, BuildingFootprint, SpatialJoinFlatPlaneCount):
    arcpy.SpatialJoin_analysis(BuildingFootprint, FlatRoofPlanes, SpatialJoinFlatPlaneCount, "JOIN_ONE_TO_ONE", "KEEP_ALL",
                               "", "CONTAINS", None, None)
    arcpy.AddField_management(SpatialJoinFlatPlaneCount, "FlatPlane_Count", "SHORT", None, None, None, None, "true",
                              "false", None)
    arcpy.CalculateField_management(SpatialJoinFlatPlaneCount, "FlatPlane_Count", "!Join_Count!", "PYTHON_9.3", None)
    return SpatialJoinFlatPlaneCount


# Calculate Maximum Roof Plane Height
def MaximumRoofPlaneHeights(RoofPlanesMergedDissolved, DSM, RoofPlanesMergedPointOutput,
                            RoofPlanesMerged,
                            scratch_ws, verbose):

    # Delete Intermediate RoofPlanesMerged Polygon
    if verbose == 0:
        arcpy.Delete_management(RoofPlanesMerged)

    DSMMax1 = os.path.join(scratch_ws, "DSMMax")
    if arcpy.Exists(DSMMax1):
        arcpy.Delete_management(DSMMax1)

    DSMOIDAttribute = arcpy.Describe(RoofPlanesMergedDissolved).OIDFieldName
    DSMMax1Raster = arcpy.sa.ZonalStatistics(RoofPlanesMergedDissolved, DSMOIDAttribute, DSM, "MAXIMUM", "DATA")
    DSMMax1Raster.save(DSMMax1)

    arcpy.FeatureToPoint_management(RoofPlanesMergedDissolved, RoofPlanesMergedPointOutput, "INSIDE")
    arcpy.AddSurfaceInformation_3d(RoofPlanesMergedPointOutput, DSMMax1, "Z", "BILINEAR", 1, 1, 0, None)
    arcpy.AddField_management(RoofPlanesMergedPointOutput, "Planar_Max", "FLOAT", None, None, None, None, "true",
                              "false", None)
    arcpy.CalculateField_management(RoofPlanesMergedPointOutput, "Planar_Max", "!Z!", "PYTHON_9.3", None)

    # Delete Intermediate DSMMax1 Raster & RoofPlanesMergedDissolved Polygon

    return RoofPlanesMergedPointOutput, RoofPlanesMergedDissolved


# Calculate MEAN lidar Height (not Max, as variables suggest)
def MaximumRoofHeight(BuildingFootprint, BuildingPoint, DSM, IDField,
                      scratch_ws, verbose):
    DSMMax = os.path.join(scratch_ws, "DSMMax")
    if arcpy.Exists(DSMMax):
        arcpy.Delete_management(DSMMax)
    DSMMaxRaster = arcpy.sa.ZonalStatistics(BuildingFootprint, IDField, DSM, "MEAN", "DATA")
    DSMMaxRaster.save(DSMMax)

    arcpy.AddSurfaceInformation_3d(BuildingPoint, DSMMax, "Z", "BILINEAR", 1, 1, 0, None)
    arcpy.AddField_management(BuildingPoint, "Building_Max", "FLOAT", None, None, None, None, "true",
                              "false", None)
    # Delete Intermediate DSMMax Raster
    if verbose == 0:
        arcpy.Delete_management(DSMMax)
    arcpy.CalculateField_management(BuildingPoint, "Building_Max", "!Z!", "PYTHON_9.3", None)

    return BuildingPoint


# RoofFormEquation
def RoofFormEquation(FlatRatio, AspectCount, FlatCount):
    if (FlatRatio > 0.45):
        return "Flat"
    elif (AspectCount == 0):
        return "Flat"
    elif (AspectCount > 0 and AspectCount < 3):
        return "Gable"
    elif (AspectCount > 2):
       return "Hip"


# TotalHeight Calc
def TotalHeightCalc(bldht, planarht):
    if (planarht is None):
        return bldht
    else:
        return planarht


##################
# Set First Edge #
##################

# check if vertcies are clockwise
def checkClockwise(vertex_list):
    sum = 0
    numberOfPoints = len(vertex_list)

    for i in range(0, numberOfPoints-1,1):
        x1 = vertex_list[i].X
        y1 = vertex_list[i].Y
        x2 = vertex_list[(i+1)].X
        y2 = vertex_list[(i+1)].Y
#        print(((x2-x1)*(y2+y1)))
        sum += (x2-x1)*(y2+y1)

    return sum > 0


# get feature vertex list
def featureGetVertices(row):
    vertex_list = []
    partnum = 0
    interiorRing = 0
    donut = 0

    # Step through each part of the feature
    #
    fail = False
    try:
        for part in row[1]:
            # Print the part number
            #
            #arcpy.AddMessage("Part {}:".format(partnum))

            # Step through each vertex in the feature
            #
            for pnt in part:
                if pnt:
                    # Get x,y,z coordinates of current point
                    #
                    #arcpy.AddMessage("{}, {}, {}:".format(pnt.X, pnt.Y, pnt.Z))
    #                print((pnt.X, pnt.Y, pnt.Z))
                    vertex_list.append(pnt)
                else:
                    # If pnt is None, this represents an interior ring
                    #
                    interiorRing = 1
                    #arcpy.AddMessage("Interior Ring:")
            partnum += 1
    except:
        fail = True


    if interiorRing == 1:
        donut = 1

    if not fail:
        return [vertex_list, donut]
    else:
        return None, None


# returns the orientation of every edge of the given shape
def getNormalOrientation(vertex_list):
    normalOrientation = []
    normalCorrection = 90
    if checkClockwise(vertex_list):
        normalCorrection = -90

    numberOfPoints = len(vertex_list)

    for i in range(0, numberOfPoints-1,1):
        x1 = vertex_list[i].X
        y1 = vertex_list[i].Y
        x2 = vertex_list[(i+1)].X
        y2 = vertex_list[(i+1)].Y

        azi = math.atan2(y2-y1, x2-x1)/math.pi*180
        normalOrientation.append((azi+normalCorrection)%360)
    return normalOrientation


# checks for every segment, if its normal direction is
# within the tolerance equal to the reference orientation
def checkFaceOrientation (vertex_list, refOrientation, tolerance = 45):
    faceOrientation = []
    for i in getNormalOrientation(vertex_list):
        faceOrientation.append(abs((i-refOrientation+180) % 360-180) < tolerance)
    return faceOrientation


# get edge length
# returns the length of every edge of the given shape
def getEdgeLength(vertex_list):
    edgeLength = []

    numberOfPoints = len(vertex_list)

    for i in range(0, numberOfPoints-1,1):
        dx = vertex_list[i].X - vertex_list[(i+1)].X
        dy = vertex_list[i].Y - vertex_list[(i+1)].Y
        edgeLength.append(math.sqrt(dx*dx + dy*dy))
    return edgeLength


# returns the segment index of the longest edge that is
# facing the reference orientation
def getEdgeIndex(vertex_list, edgeLength, refOrientation, tolerance):
    orientation = checkFaceOrientation(vertex_list, refOrientation, tolerance)
    length = getEdgeLength(vertex_list)

    max = 0
    index = 0
    for i in range(0,len(length)):
        if length[i] > max and orientation[i]:
            max = length[i]
            index = i
    return index


def createDonutPolygon(row, spatial_reference, hasZcoords):
    # Step through each part of the feature
    #
    parts = arcpy.Array()
    rings = arcpy.Array()
    ring = arcpy.Array()
    partnum = 0

    for part in row[1]:
        for pnt in part:
            if pnt:
                pt = arcpy.Point()
                if hasZcoords:
                    ring.add(arcpy.Point(pnt.X, pnt.Y, pnt.Z))
                else:
                    ring.add(arcpy.Point(pnt.X, pnt.Y))
            else:
                # null point - we are at the start of a new ring
                rings.add(ring)
                ring.removeAll()

        # we have our last ring, add it
        rings.add(ring)
        ring.removeAll()

        # if we only have one ring: remove nesting
        if len(rings) == 1:
            rings = rings.getObject(0)
        parts.add(rings)
        rings.removeAll()

    # if single-part (only one part) remove nesting
    if len(parts) == 1:
        parts = parts.getObject(0)

    return (arcpy.Polygon(parts, spatial_reference,hasZcoords))


def featureWriteVertices(array, vertex_list, edge_index, spatial_reference, hasZcoords):

    # add vertices to array
    numberOfPoints = len(vertex_list)
    new_vertexlist = []

    #create new list without closing point
    for i in range(0, numberOfPoints-1, 1):
        new_vertexlist.append(vertex_list[i])

    numberOfPoints = len(new_vertexlist)

    # cycle through points, don't use last one because it is same as first
    for i in range(0, numberOfPoints, 1):

        if edge_index + i >= numberOfPoints:
            array.add(arcpy.Point(new_vertexlist[edge_index+i-numberOfPoints].X, new_vertexlist[edge_index+i-numberOfPoints].Y, new_vertexlist[edge_index+i-numberOfPoints].Z))
        else:
            array.add(arcpy.Point(new_vertexlist[edge_index+i].X, new_vertexlist[edge_index+i].Y, new_vertexlist[edge_index+i].Z))

        #add first point twice to close the polygon
        if i == numberOfPoints - 1:
            array.add(arcpy.Point(new_vertexlist[edge_index].X, new_vertexlist[edge_index].Y, new_vertexlist[edge_index].Z))

    return arcpy.Polygon(array, spatial_reference, hasZcoords)


def CreateBuildingFCWithDTMandDSMValues(ws, Building, DTM, DSM, output_buildings):
    try:
        outDTMPolygons = os.path.join(ws, "outDTMPolygons")
        if arcpy.Exists(outDTMPolygons):
            arcpy.Delete_management(outDTMPolygons)

        outDSMPolygons = os.path.join(ws, "outDSMPolygons")
        if arcpy.Exists(outDSMPolygons):
            arcpy.Delete_management(outDSMPolygons)

        # check number of input features
        input_layer = "input_lyr"
        arcpy.MakeFeatureLayer_management(Building, input_layer)
        result = arcpy.GetCount_management(input_layer)
        input_count = int(result.getOutput(0))

        # Create polygons of raster extents
        arcpy.RasterDomain_3d(DTM, outDTMPolygons, "POLYGON")
        arcpy.RasterDomain_3d(DSM, outDSMPolygons, "POLYGON")

        # Select all footprints that are within the DTM polygon
        arcpy.SelectLayerByLocation_management(input_layer, "within", outDTMPolygons)

        # Select all footprints that are within the DSM polygon
        arcpy.SelectLayerByLocation_management(input_layer, "within", outDSMPolygons, selection_type="SUBSET_SELECTION")

        result = arcpy.GetCount_management(input_layer)
        select_count = int(result.getOutput(0))
        if select_count > 0:
            # Write the selected features to a new featureclass
            arcpy.CopyFeatures_management(input_layer, output_buildings)

            arcpy.AddMessage(str(select_count)+" features of the "+str(input_count)+" will be processed based on the available DTM and DSM.")
        else:
            arcpy.AddError("No input footprints found within extent of both DTM and DSM")

        return output_buildings

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


def CutUpFeatureClassBySize(scratch_ws, featureClass, groupAttribute, size):
    try:
        featureclass_list = []
        numSelection = int(size)
        lessThan = numSelection
        greaterThan = 0
        featureLayer = "featureLayer"

        result = arcpy.GetCount_management(featureClass)
        numFeatures = int(result.getOutput(0))

        arcpy.MakeFeatureLayer_management(featureClass, featureLayer)

        while(greaterThan < numFeatures):
            expression = groupAttribute+" > "+str(greaterThan)+ " And "+groupAttribute+ " < "+str(lessThan)

            name = bm_common_lib.get_name_from_feature_class(featureClass)+"_"+str(greaterThan)+"_"+str(lessThan)
            outFeatureClass = os.path.join(scratch_ws, name)

            if arcpy.Exists(outFeatureClass):
                arcpy.Delete_management(outFeatureClass)

            arcpy.SelectLayerByAttribute_management(featureLayer,"NEW_SELECTION", expression)
            arcpy.management.CopyFeatures(featureLayer, outFeatureClass)

#            print(("Created temporary feature class: "+name))
#            arcpy.AddMessage("Created temporary feature class: "+name)

            featureclass_list.append(outFeatureClass)

            greaterThan = lessThan - 1
            lessThan = lessThan + numSelection

        return featureclass_list

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


def MarkLargestRoofPlane(ws, featureClass, groupAttribute, selectionSize, valueAttribute, markField, verbose):
    try:
        # cut up featureClass in blocks of selectionSize
        listOfFCs = CutUpFeatureClassBySize(ws,featureClass, groupAttribute, selectionSize)
        fcCount = len(listOfFCs)

        i = 1

        # process each cut
        for fc in listOfFCs:
            start_time = time.time()
            # create a list of unique "groupAttribute" values
            unique_field_values = unique_values(fc, groupAttribute)

            # step through unique value list
            for value in unique_field_values:
                whereclause = groupAttribute+" = "+str(value)
                # get sorted list of valueAttributes per unique feature
                with arcpy.da.SearchCursor(fc, [valueAttribute], whereclause) as cursor:
                    values_per_objectid = []
                    for row in cursor:
                        values_per_objectid.append(row[0])

                    values_per_objectid.sort(reverse=True)

                # write to markField
                whereclause2 = groupAttribute+" = "+str(value)+" AND "+valueAttribute+" = "+str(values_per_objectid[0])
                with arcpy.da.UpdateCursor(fc, [markField], whereclause2) as cursor:
                    for row in cursor:
                        row[0] = "mark"

                        # Update the cursor with the updated list
                        cursor.updateRow(row)

            # set time estiamtion
            end_time = time.time()
            time_diff = end_time-start_time

            percent = int((i / fcCount)*100)
            message = "Still working on it...  "+str(percent)+"% done."
            print((message))
            arcpy.AddMessage(message)
            i+=1

        # merge back together
        merged_fc = os.path.join(ws, "MarkedSlopedPlaneBuilding")
        if len(listOfFCs) == 0:
            arcpy.AddWarning("WARNING: no sloped roof planes detected")
        else:
            arcpy.Merge_management(listOfFCs, merged_fc)

        # Delete Intermediate data
        if verbose == 0:
            for fc in listOfFCs:
                arcpy.Delete_management(fc)

        return merged_fc

    # Return geoprocessing specific errors
    #
    except arcpy.ExecuteWarning:
        print (arcpy.GetMessages(1))

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


def CalculateUniqueID(TheFeatureClass, TheAttribute):
    try:
        cur = arcpy.UpdateCursor(TheFeatureClass)
        numID = 1
        success = 1

        for row in cur:
            row.setValue(TheAttribute, numID)
            cur.updateRow(row)
            numID += 1

        return success

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


def getFullPathFromLayer(in_layer):
    dirname = os.path.dirname(arcpy.Describe(in_layer).catalogPath)
    layername = arcpy.Describe(in_layer).name

    return os.path.join(dirname, layername)


def CreateBuildingExtentFC(ws, name, Building, DTM):
    try:
        bldgLayer = "building_lyr"

        DTMExtent = os.path.join(ws, "DTM_extent")
        if arcpy.Exists(DTMExtent):
            result = arcpy.Delete_management(DTMExtent)

        bldgExtent = os.path.join(ws, name)
        if arcpy.Exists(bldgExtent):
            result = arcpy.Delete_management(bldgExtent)

        extent = arcpy.Describe(DTM).extent.polygon
        arcpy.management.CopyFeatures(extent, DTMExtent)
        arcpy.MakeFeatureLayer_management(Building, bldgLayer)
        arcpy.SelectLayerByLocation_management(bldgLayer, 'within', DTMExtent)
        arcpy.management.CopyFeatures(bldgLayer, bldgExtent)

        arcpy.Delete_management(DTMExtent)

        return bldgExtent

    # Return geoprocessing specific errors
    #
    except arcpy.ExecuteWarning:
        print(arcpy.GetMessages(1))

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


def CreateBuildingPoints(ws, name, fc, field1, field2, field3, create_index):
    try:
        bldgPoint = os.path.join(ws, name)
        if arcpy.Exists(bldgPoint):
            result = arcpy.Delete_management(bldgPoint)
        arcpy.FeatureToPoint_management(fc, bldgPoint, "INSIDE")

        AddField(bldgPoint, field1, "DOUBLE")
        AddField(bldgPoint, field2, "DOUBLE")
        AddField(bldgPoint, field3, "DOUBLE")

        if (create_index == "true"):
            # Add index field for buffer
            AddField(bldgPoint, "BuffIndex", "DOUBLE")
            arcpy.CalculateField_management(bldgPoint, "BuffIndex", "!OBJECTID!", "PYTHON_9.3", None)

        return bldgPoint

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


# Calculate BASEELEV
def CalcBaseElevation(ws, DTM, building_fc, buildingPoint_fc, field1, field2):

    try:
        arcpy.env.mask = building_fc
        DTMMin = os.path.join(ws, "DTMMin")
        if arcpy.Exists(DTMMin):
            arcpy.Delete_management(DTMMin)

        oidFieldName = arcpy.Describe(building_fc).oidFieldName
        DTMMinRaster = arcpy.sa.ZonalStatistics(building_fc, oidFieldName, DTM, "MINIMUM", "true")
        DTMMinRaster.save(DTMMin)

        arcpy.AddSurfaceInformation_3d(buildingPoint_fc, DTMMin, "Z", "BILINEAR", 1, 1, 0, None)
        arcpy.CalculateField_management(buildingPoint_fc, field1, "!Z!", "PYTHON_9.3", None)
        arcpy.DeleteField_management(buildingPoint_fc, "Z")

        # calculate backup Z if case the DTMminraster fails
        arcpy.AddSurfaceInformation_3d(buildingPoint_fc, DTM, "Z", "BILINEAR", 1, 1, 0, None)
        arcpy.CalculateField_management(buildingPoint_fc, field2, "!Z!", "PYTHON_9.3", None)
        arcpy.DeleteField_management(buildingPoint_fc, "Z")

        # Apply backup Z if no DTMminrastr value
        with arcpy.da.UpdateCursor(buildingPoint_fc,(field1, field2)) as cursor:
            for row in cursor:
                if row[0] is None:
                    row[0] = row[1]

                cursor.updateRow(row)

        if arcpy.Exists(DTMMin):
            arcpy.Delete_management(DTMMin)
        return buildingPoint_fc

    # Return geoprocessing specific errors
    #
    except arcpy.ExecuteWarning:
        print ((arcpy.GetMessages(1)))

    except arcpy.ExecuteError:
        print ((arcpy.GetMessages(2)))
        arcpy.AddError(arcpy.GetMessages(2))

    # Return any other type of error
    except:
        # By default any other errors will be caught here
        #
        e = sys.exc_info()[1]
        print((e.args[0]))
        arcpy.AddError(e.args[0])


# Define building height calculation with Inward Buffer on Buildings
def inBuffBuildings(ws, distance, building_fc, buildingPoint_fc, DSM, field1, field2, field3):
    try:
        # Apply buffer
        BuildingBuff = os.path.join(ws, "BuildingBuff")
        if arcpy.Exists(BuildingBuff):
            arcpy.Delete_management(BuildingBuff)

        arcpy.AddMessage("Working with buffer distance: "+str(distance))
        result = arcpy.Buffer_analysis(building_fc, BuildingBuff, float(distance))

        # Find features with null geometry
        bufferlist = [row[0]for row in arcpy.da.SearchCursor(BuildingBuff,(field3))]

        # Calculate max height raster within buffer areas
        DSMMaxBuffer = os.path.join(ws, "DSMMaxBuffer")
        if arcpy.Exists(DSMMaxBuffer):
            arcpy.Delete_management(DSMMaxBuffer)

        oidFieldName = arcpy.Describe(BuildingBuff).oidFieldName
        DSMMaxRaster = arcpy.sa.ZonalStatistics(BuildingBuff, oidFieldName, DSM, "MAXIMUM", "true")
        DSMMaxRaster.save(DSMMaxBuffer)

        # create a temporary point feature class to poll the buffered polygons -> buildingPoints might fall outside the buffer!
        bufferPoints = CreateBuildingPoints(ws, "bufferPoints", BuildingBuff, "bufferPointHeight","temp","temp2", "false")

        # Extract max height values to points within buffers
        arcpy.AddSurfaceInformation_3d(bufferPoints, DSMMaxBuffer, "Z", "BILINEAR", 1, 1, 0, None)
        arcpy.CalculateField_management(bufferPoints, "bufferPointHeight", "!Z!", "PYTHON_9.3", None)

        # Add temporary height fields
        result = arcpy.AddField_management(buildingPoint_fc, "BufferHeight", "DOUBLE")
        result = arcpy.AddField_management(buildingPoint_fc, "DSMHeight", "DOUBLE")

        # join back to the original building points based on BUFFER_INDEX
        arcpy.JoinField_management(buildingPoint_fc, field3, bufferPoints, field3, "bufferPointHeight")
        arcpy.Delete_management(bufferPoints)

        # set bufferHeight in original building points
        arcpy.CalculateField_management(buildingPoint_fc, "BufferHeight", "!bufferPointHeight! - !"+field1+"!", "PYTHON_9.3", None)
        arcpy.DeleteField_management(buildingPoint_fc, "bufferPointHeight")

        # Extract point height values to points
        arcpy.AddSurfaceInformation_3d(buildingPoint_fc, DSM, "Z", "BILINEAR", 1, 1, 0, None)
        arcpy.CalculateField_management(buildingPoint_fc, "DSMHeight", "!Z! - !"+field1+"!", "PYTHON_9.3", None)
        arcpy.DeleteField_management(buildingPoint_fc, "Z")

        # Apply DSMMax height to points if buffer feature is generated. If null, use DSM value at point location
        with arcpy.da.UpdateCursor(buildingPoint_fc,(field3, field2, "BufferHeight", "DSMHeight")) as cursor:
            for row in cursor:
                if row[0] in bufferlist:
                    if row[2] is None:
                        row[1] = row[3]
                    else:
                        row[1] = row[2]
                else:
                    row[1] = row[3]

                cursor.updateRow(row)

        if arcpy.Exists(DSMMaxBuffer):
            arcpy.Delete_management(DSMMaxBuffer)

        arcpy.Delete_management(BuildingBuff)

        return buildingPoint_fc

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


# Calculate BLDGHEIGHT based on full footprint
def CalcBldgHeight(ws, building_fc, buildingPoint_fc, DSM, field1, field2):
    try:
        arcpy.env.mask = building_fc
        DSMMax = os.path.join(ws, "DSMMax")
        if arcpy.Exists(DSMMax):
            arcpy.Delete_management(DSMMax)

        oidFieldName = arcpy.Describe(building_fc).oidFieldName
        DSMMaxRaster = arcpy.sa.ZonalStatistics(building_fc, oidFieldName, DSM, "MAXIMUM", "true")
        DSMMaxRaster.save(DSMMax)
        arcpy.AddSurfaceInformation_3d(buildingPoint_fc, DSMMax, "Z", "BILINEAR", 1, 1, 0, None)

        expression = "!Z! - !"+field1+"!"

        arcpy.CalculateField_management(buildingPoint_fc, field2, expression, "PYTHON_9.3", None)
        arcpy.DeleteField_management(buildingPoint_fc, "Z")
        if arcpy.Exists(DSMMax):
            arcpy.Delete_management(DSMMax)
        return buildingPoint_fc

    # Return geoprocessing specific errors
    #
    except arcpy.ExecuteWarning:
        print ((arcpy.GetMessages(1)))

    except arcpy.ExecuteError:
        arcpy.AddError(arcpy.GetMessages(2))

    # Return any other type of error
    except:
        # By default any other errors will be caught here
        #
        e = sys.exc_info()[1]
        print((e.args[0]))
        arcpy.AddError(e.args[0])


# Define buffer check to calculate building heights
def BufferCheck(ws, in_buffer, distance, building_fc, buildingPoint_fc, DSM, field1, field2, field3):

    if in_buffer and distance != 0:
        inBuffBuildings(ws, distance, building_fc, buildingPoint_fc, DSM, field1, field2, field3)
        arcpy.AddMessage("Working with Buffer.")
    else:
        CalcBldgHeight(ws, building_fc, buildingPoint_fc, DSM, field1, field2)


def extract_lod1_roof_form(home_directory, buildings_layer, dsm, dtm,
                           output_buildings, buffer_buildings, buffer_size,
                           verbose):

    try:
        # script variables
        layer_directory = home_directory + "\\layer_files"

        # for packaging
        if os.path.exists(layer_directory):
            bm_common_lib.rename_file_extension(layer_directory, ".txt", ".lyrx")

        if not bm_common_lib.check_valid_input(buildings_layer, True, ["Polygon"], False, True):
            raise InputDataNotValid

        arcpy.AddMessage("Creating buildings with flat roofs.")

        # Create and set workspace location in same directory as input feature class gdb
        scratch_ws = bm_common_lib.create_gdb(home_directory, "Analysis.gdb")
        arcpy.env.workspace = scratch_ws
        arcpy.env.overwriteOutput = True

        DTM = getFullPathFromLayer(dtm)
        DSM = getFullPathFromLayer(dsm)

        # fail safe for Europese's comma's
        if buffer_buildings:
            if buffer_size:
                Buff_Distance = float(re.sub("[,.]", ".", buffer_size))
            else:
                Buff_Distance = 0
        else:
            Buff_Distance = 0

        # variables
        tempBASEELEV = "tempBase"
        tempBASEELEVbackup = "tempBaseBackup"
        BASEELEVfield = "BASEELEV"
        tempBLDGHEIGHT = "tempHeight"
        tempBLDGHEIGHTbackup = "tempHeightBackup"
        BLDGHEIGHTfield = "BLDGHEIGHT"
        bufferIndex = "BuffIndex"
        building_extent_name = "building_extent"

        if bm_common_lib.check_valid_input(buildings_layer, True, ["Polygon"], False, True):
            # make a copy to grab the selection
            input_source_copy = os.path.join(scratch_ws,
                                             bm_common_lib.get_name_from_feature_class(buildings_layer) + "_copy")
            if arcpy.Exists(input_source_copy):
                arcpy.Delete_management(input_source_copy)

            arcpy.CopyFeatures_management(buildings_layer, input_source_copy)

            # create building polygon feature class based on extent of DTM
            arcpy.AddMessage("Selecting features that have valid DTM and DSM values.")
            arcpy.AddMessage("Only features that have valid DTM and DSM values will be processed and the output "
                             "will be a new polygon feature class called: " + output_buildings)

            Building = CreateBuildingFCWithDTMandDSMValues(scratch_ws, input_source_copy, dtm, dsm,
                                                           output_buildings)

            # run repair on it just to take care of possible errors
            arcpy.RepairGeometry_management(Building)
            print("Repairing geometries...")
            arcpy.AddMessage("Repairing geometries...")

            # delete any previous temporary fields just to be save
            result = arcpy.DeleteField_management(Building, [tempBASEELEV, tempBLDGHEIGHT, bufferIndex])

            # add required fields to input feature class
            arcpy.AddMessage("Adding BASEELEV and BLDGHEIGHT Fields")

            AddField(Building, BASEELEVfield, "DOUBLE")
            AddField(Building, BLDGHEIGHTfield, "DOUBLE")

            # Add index field for buffer
            AddField(Building, bufferIndex, "LONG")
            arcpy.CalculateField_management(Building, bufferIndex, "!OBJECTID!", "PYTHON_9.3", None)

            # create temporary building polygon feature class based on extent of DTM
            arcpy.AddMessage("Selecting features that fall within the extent of the DTM")
            building_extent_fc = CreateBuildingExtentFC(scratch_ws, building_extent_name, Building, DTM)

            # create building point that will hold the BASEELEV and BLDGHEIGHT
            arcpy.AddMessage("Creating Building Points")
            buildingPoint = CreateBuildingPoints(scratch_ws, "buildingPoint", building_extent_fc, tempBASEELEV,
                                                 tempBLDGHEIGHT, tempBASEELEVbackup, "false")

            num_footprints = arcpy.GetCount_management(building_extent_fc).getOutput(0)
            num_points = arcpy.GetCount_management(buildingPoint).getOutput(0)

            arcpy.AddMessage("Found: " + str(num_footprints) + " features")

            if (num_footprints == num_points) and int(num_footprints) != 0:
                arcpy.AddMessage("Calculating Base Elevation")
                CalcBaseElevation(scratch_ws, DTM, building_extent_fc, buildingPoint, tempBASEELEV,
                                  tempBASEELEVbackup)

                arcpy.AddMessage("Calculating Building Height")

                if buffer_buildings:
                    # we want a negative buffer always
                    if Buff_Distance > 0:
                        Buff_Distance = 0 - Buff_Distance
                else:
                    Buff_Distance = 0

                BufferCheck(scratch_ws, buffer_buildings, Buff_Distance, building_extent_fc,
                            buildingPoint, DSM, tempBASEELEV,
                            tempBLDGHEIGHT, bufferIndex)

                arcpy.AddMessage("Attributing Building Features")

                arcpy.JoinField_management(Building, "OBJECTID", buildingPoint, bufferIndex,
                                           [tempBASEELEV, tempBLDGHEIGHT])

                arcpy.AddMessage("Calculating BASEELEV")
                arcpy.CalculateField_management(Building, BASEELEVfield, "!" + tempBASEELEV + "!", "PYTHON_9.3")
                arcpy.AddMessage("Calculating BLDGHEIGHT")
                arcpy.CalculateField_management(Building, BLDGHEIGHTfield, "!" + tempBLDGHEIGHT + "!", "PYTHON_9.3")

                arcpy.AddMessage("Cleaning up...")
                arcpy.DeleteField_management(Building, [tempBASEELEV, tempBLDGHEIGHT, bufferIndex])
                arcpy.Delete_management(buildingPoint)
                arcpy.Delete_management(building_extent_fc)

                # apply rule to building footprints
                z_unit = bm_common_lib.get_z_unit(Building, 0)

                # if z_unit == "Feet":
                #     rule_file = rule_directory + "\\LOD1Building_Shells_feet.rpk"
                # else:
                #     rule_file = rule_directory + "\\LOD1Building_Shells_meters.rpk"

                # # export to temp fc
                # lod1_buildings = output_features
                # if arcpy.Exists(lod1_buildings):
                #     arcpy.Delete_management(lod1_buildings)
                #
                # arcpy.FeaturesFromCityEngineRules_3d(Building, rule_file, lod1_buildings,
                #                                      "INCLUDE_EXISTING_FIELDS")
                #
                # output_layer = bm_common_lib.get_name_from_feature_class(lod1_buildings)
                # arcpy.MakeFeatureLayer_management(lod1_buildings, output_layer)
                #
                # arcpy.SetParameter(11, output_layer)

                # add symbology and add layer to TOC
                output_layer = bm_common_lib.get_name_from_feature_class(Building)  # + "_LOD1"
                arcpy.MakeFeatureLayer_management(Building, output_layer)

                z_unit = bm_common_lib.get_z_unit(Building, verbose)

                if z_unit == "Feet":
                    SymbologyLayer = layer_directory + "\\LOD1BuildingShells_feet.lyrx"
                else:
                    SymbologyLayer = layer_directory + "\\LOD1BuildingShells_meters.lyrx"

                if arcpy.Exists(SymbologyLayer):
                    arcpy.ApplySymbologyFromLayer_management(output_layer, SymbologyLayer)
                else:
                    msg_body = create_msg_body("Can't find " + SymbologyLayer + " in " + layer_directory, 0, 0)
                    msg(msg_body, WARNING)

                arcpy.SetParameter(11, output_layer)
                arcpy.AddMessage("Processing Complete")

                return Building
            else:
                raise NoFeatures
        else:
            arcpy.AddError("Input data is not valid. Check your data.")

    except InputDataNotValid:
        arcpy.AddError("Input data is not valid. Check your data.")

    except NoFeatures:
        # The input has no features
        #
        print('Error creating feature class')
        arcpy.AddError('Error creating feature class')

    except NoRoofFeatures:
        arcpy.AddError("No roof areas found above the minimum height threshold. Please inspect your data and try again")

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


def clip_rasters_by_building_extent(scratch_ws, dtm, dsm, ndsm, buildings):
    try:
        # Extract DSM by Buildings
        DTMClip = os.path.join(scratch_ws, "DTMClip")
        if arcpy.Exists(DTMClip):
            arcpy.Delete_management(DTMClip)

        arcpy.Clip_management(dtm, "#", DTMClip, buildings, "#", "#", "NO_MAINTAIN_EXTENT")

        DSMClip = os.path.join(scratch_ws, "DSMClip")
        if arcpy.Exists(DSMClip):
            arcpy.Delete_management(DSMClip)

        arcpy.Clip_management(dsm, "#", DSMClip, buildings, "#", "#", "NO_MAINTAIN_EXTENT")

        nDSMClip = os.path.join(scratch_ws, "nDSMClip")
        if arcpy.Exists(nDSMClip):
            arcpy.Delete_management(nDSMClip)

        arcpy.Clip_management(ndsm, "#", nDSMClip, buildings, "#", "#", "NO_MAINTAIN_EXTENT")

        return DTMClip, DSMClip, nDSMClip

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


def extract_lod2_roof_form(home_directory, buildings_layer, dsm, dtm, ndsm,
                           min_flat_roof_area, min_slope_roof_area, min_roof_height,
                           output_buildings, simplify_buildings, simplify_tolerance,
                           verbose):

    try:
        start_time_lod2 = time.time()

        if verbose:
            end_time_copy = 0
            start_time_copy = 0
            end_time_CreateBuildingFCWithDTMandDSMValues = 0
            start_time_CreateBuildingFCWithDTMandDSMValues = 0
            end_time_MinimumRoofHeightThresholdDSM = 0
            start_time_MinimumRoofHeightThresholdDSM = 0
            end_time_CreateRoofPlanePolygons = 0
            start_time_CreateRoofPlanePolygons = 0
            end_time_CreateAspectPlanes = 0
            start_time_CreateAspectPlanes = 0
            end_time_BuildingMinElevation = 0
            start_time_BuildingMinElevation = 0
            end_time_MarkedSlopedPlaneBuilding = 0
            start_time_MarkedSlopedPlaneBuilding = 0
            end_time_BuildingEaveHeight = 0
            start_time_BuildingEaveHeight = 0
            end_time_FlatRoofPolygons = 0
            start_time_FlatRoofPolygons = 0
            end_time_FlatAreaCalculate = 0
            start_time_FlatAreaCalculate = 0
            end_time_MaximumRoofPlaneHeights = 0
            start_time_MaximumRoofPlaneHeights = 0
            end_time_lotsofjoining = 0
            start_time_lotsofjoining = 0
            end_time_firstedgestart_time_firstedge = 0

        # script variables
        layer_directory = home_directory + "\\layer_files"

        # for packaging
        if os.path.exists(layer_directory):
            bm_common_lib.rename_file_extension(layer_directory, ".txt", ".lyrx")

        if not bm_common_lib.check_valid_input(buildings_layer, True, ["Polygon"], False, True):
            raise InputDataNotValid

        arcpy.AddMessage("Creating buildings with roof forms.")

        # Create and set workspace location in same directory as input feature class gdb
        scratch_ws = bm_common_lib.create_gdb(home_directory, "Analysis.gdb")
        arcpy.env.workspace = scratch_ws
        arcpy.env.overwriteOutput = True

        # empty the scratch GDB
        featureclasses = arcpy.ListFeatureClasses()
        for fc in featureclasses:
            arcpy.Delete_management(fc)

        # make new feature class to capture possible selection
        BuildingPolygonsOriginal = os.path.join(scratch_ws, "BuildingPolygonsOriginal")
        if arcpy.Exists(BuildingPolygonsOriginal):
           arcpy.Delete_management(BuildingPolygonsOriginal)

        start_time_copy = time.time()
        arcpy.management.CopyFeatures(buildings_layer, BuildingPolygonsOriginal)
        end_time_copy = time.time()

        # create building polygon feature class based on extent of DTM
        arcpy.AddMessage("Selecting features that have valid DTM and DSM values.")
        arcpy.AddMessage("Only features that have valid DTM and DSM values will be processed and the output "
                         "will be a new polygon feature class called: " + output_buildings + ".")

        DSMBuildings = os.path.join(scratch_ws, "DSMBuildings")
        if arcpy.Exists(DSMBuildings):
            arcpy.Delete_management(DSMBuildings)

        start_time_CreateBuildingFCWithDTMandDSMValues = time.time()
        BuildingPolygons = CreateBuildingFCWithDTMandDSMValues(scratch_ws, BuildingPolygonsOriginal, dtm, dsm,
                                                               DSMBuildings)
        end_time_CreateBuildingFCWithDTMandDSMValues = time.time()


        # clip rasters to building extent
        # dtm, dsm, ndsm = clip_rasters_by_building_extent(scratch_ws, dtm, dsm, ndsm, BuildingPolygons)

        # Run multi-part to single-part
        buildings_sp = os.path.join(scratch_ws, "buildings_sp")
        arcpy.MultipartToSinglepart_management(BuildingPolygons, buildings_sp)
        BuildingPolygons = buildings_sp

        # run repair on it just to take care of possible errors
        arcpy.RepairGeometry_management(BuildingPolygons)
        print("Repairing geometries...")
        arcpy.AddMessage("Repairing geometries...")

        # Densify vertices by angle in case there are arc segments
        arcpy.Densify_edit(BuildingPolygons, "ANGLE", max_angle=10)

        # delete any previous temporary fields just to be save
        DropAddRoofFormFields(BuildingPolygons)

        print("Calculating unique object ID...")
        arcpy.AddMessage("Calculating unique object ID...")
        uniqueFID = arcpy.Describe(BuildingPolygons).OIDFieldName
        arcpy.CalculateField_management(BuildingPolygons, BUILDINGIDfield, "'Building_' + str(!" + uniqueFID + "!)",
                                        "PYTHON_9.3")

        # only needed for marking speedup
        CalculateUniqueID(BuildingPolygons, numBUILDINGIDfield)
        # arcpy.CalculateField_management(BuildingPolygons, numBUILDINGIDfield, '!OBJECTID!', "PYTHON_9.3")

        print("Calculating Minimum Height Threshold DSM...")
        arcpy.AddMessage("Calculating Minimum Height Threshold DSM...")

        # Calculate Minimum Height Threshold DSM
        RoofSlope = os.path.join(scratch_ws, "RoofSlope")
        MinHtThresholdDSM = os.path.join(scratch_ws, "MinHtThresholdDSM")

        start_time_MinimumRoofHeightThresholdDSM = time.time()
        MinimumRoofHeightThresholdDSM(nDSM=ndsm, DSM=dsm, MinHtThresholdDSM=MinHtThresholdDSM,
                                      RoofSlope=RoofSlope, BuildingFootprint=BuildingPolygons,
                                      MinRoofHeight=min_roof_height,
                                      scratch_ws=scratch_ws,
                                      verbose=verbose)
        end_time_MinimumRoofHeightThresholdDSM = time.time()

        min_height_raster = arcpy.sa.Raster(MinHtThresholdDSM)
        if min_height_raster.maximum is None:
            raise NoRoofFeatures

        print("Creating Roof Plane Polygons...")
        arcpy.AddMessage("Creating Roof Plane Polygons...")

        # Create Roof Plane Polygons
        start_time_CreateRoofPlanePolygons = time.time()
        RoofPlanePolygons = CreateRoofPlanePolygons(RoofSlope, MinHtThresholdDSM, MinRoofSlope, MaxRoofSlope,
                                                    min_slope_roof_area, BuildingPolygons,
                                                    scratch_ws, verbose)
        end_time_CreateRoofPlanePolygons = time.time()

        # Delete Intermediate MinHtThresholdDSM Raster
        if verbose == 0:
            arcpy.Delete_management(MinHtThresholdDSM)

        # ADD FlatAreaRatio Attribute
        arcpy.AddField_management(BuildingPolygons, "FlatAreaRatio", "FLOAT", None, None, None, None, "true",
                                  "false", None)

        # Join Building Information to Slope Planes.
        start_time_CreateAspectPlanes = time.time()
        UniqueAspectPlanes = os.path.join(scratch_ws, "UniqueAspectPlanes")
        if arcpy.Exists(RoofPlanePolygons):
            SlopedPlaneBuilding = os.path.join(scratch_ws, "SlopedPlaneBuildingJoin")
            if arcpy.Exists(SlopedPlaneBuilding):
                arcpy.Delete_management(SlopedPlaneBuilding)
            arcpy.SpatialJoin_analysis(RoofPlanePolygons, BuildingPolygons, SlopedPlaneBuilding)

            print("Creating Aspect Planes...")
            arcpy.AddMessage("Creating Aspect Planes...")

            # Create Aspect Planes

            CreateAspectPlanes(SlopedPlaneBuilding, UniqueAspectPlanes)
        end_time_CreateAspectPlanes = time.time()

        # Building Footprint To Point
        BuildingPoint = os.path.join(scratch_ws, "BuildingPoint")
        if arcpy.Exists(BuildingPoint):
            arcpy.Delete_management(BuildingPoint)
        arcpy.FeatureToPoint_management(BuildingPolygons, BuildingPoint, "INSIDE")

        print("Determining Minimum Building Elevation...")
        arcpy.AddMessage("Determining Minimum Building Elevation...")

        # Determine Minimum Building Elevation
        start_time_BuildingMinElevation = time.time()
        BuildingMinElevation(BuildingFootprint=BuildingPolygons, DTM=dtm,
                             BuildingPoint=BuildingPoint, IDField=uniqueFID,
                             scratch_ws=scratch_ws)
        end_time_BuildingMinElevation = time.time()

        ######################
        #Select Largest Plane#
        ######################
        if not arcpy.Exists(UniqueAspectPlanes):
            arcpy.AddWarning("Sloped plane feature class not created")
            slopedPlanesExist = 0
            print("Sloped plane feature class not created")
        else:
            countAspects = arcpy.GetCount_management(UniqueAspectPlanes)
            aspectResult = int(countAspects.getOutput(0))
            if aspectResult == 0:
                arcpy.AddWarning("No sloped plane features detected:")
                print("No sloped plane features detected:")
                slopedPlanesExist = 0

            else:
                slopedPlanesExist = 1
                print("Determining Largest Roof Plane...")
                arcpy.AddMessage("Determining Largest Roof Plane...")

                #Identify largest sloped plane with unique BuildingFID
                featureClass = SlopedPlaneBuilding
                groupAttribute = BUILDINGIDfield
                valueAttribute = "Shape_Area"
                selectionSize = 5000

                arcpy.AddMessage("Marking feature class... NOTE: takes time for large feature classes.")

                markField = "mark"

                # delete marking field
                DeleteAddField(featureClass, markField, "TEXT")

                if verbose == 0:
                    # cut the fc up into x feature parts, the process. This speeds up the cursor actions
                    start_time_MarkedSlopedPlaneBuilding = time.time()
                    MarkedSlopedPlaneBuilding = MarkLargestRoofPlane(scratch_ws, featureClass,
                                                                     numBUILDINGIDfield, selectionSize, valueAttribute,
                                                                     markField, verbose)
                    end_time_MarkedSlopedPlaneBuilding = time.time()

                    # Select and Export Largest Planes
                    LargeSlopedPlanes = os.path.join(scratch_ws, "LargeSlopedPlanes")

                    if arcpy.Exists(MarkedSlopedPlaneBuilding):
                        arcpy.Select_analysis(MarkedSlopedPlaneBuilding, LargeSlopedPlanes, "mark = 'mark'")

                    arcpy.Delete_management(SlopedPlaneBuilding)
                    arcpy.Delete_management(MarkedSlopedPlaneBuilding)
                else:
                    # create a list of unique "groupAttribute" values
                    unique_field_values = unique_values(featureClass, groupAttribute)

                    i = 1
                    dec = 25
                    timecheck = 5
                    start_time = time.time()

                    # step through unique value list
                    for value in unique_field_values:
                        percent = int((i / float(len(unique_field_values)))*100)

                        if percent == timecheck:
                            end_time = time.time()
                            time_diff = end_time-start_time
                            message = "Estimated time required to finish marking the feature class... {:.2f} minutes.".format(((time_diff/60)*(100-percent))/percent)
                            arcpy.AddMessage(message)
                            timecheck = 0

                        if percent >= dec:
                            end_time = time.time()
                            time_diff = end_time-start_time
                            message = "Still working on it...  "+str(percent)+"% done. Approx: {:.2f} minutes left to go.".format(((time_diff/60)*(100-percent))/percent)
                            arcpy.AddMessage(message)

                            dec = dec + 25

                        whereclause = groupAttribute+" = "+ "'"+str(value)+"'"
                        # get sorted list of valueAttributes per unique feature
                        with arcpy.da.SearchCursor(featureClass, [valueAttribute], whereclause) as cursor:
                            values_per_objectid = []
                            for row in cursor:
                                values_per_objectid.append(row[0])

                            values_per_objectid.sort(reverse=True)

                        # write to markField
                        whereclause2 = groupAttribute+" = "+ "'"+str(value)+"' AND "+valueAttribute+" = "+str(values_per_objectid[0])
                        with arcpy.da.UpdateCursor(featureClass, [markField], whereclause2) as cursor:
                            for row in cursor:
                                row[0] = "mark"

                                # Update the cursor with the updated list
                                cursor.updateRow(row)

                        i+=1

                    # Select and Export Largest Planes
                    LargeSlopedPlanes = os.path.join(scratch_ws, "LargeSlopedPlanes")
                    arcpy.Select_analysis(SlopedPlaneBuilding, LargeSlopedPlanes, "mark = 'mark'")

                    if verbose == 0:
                        arcpy.Delete_management(SlopedPlaneBuilding)

                # Sloped Plane Building to Point
                SlopedPlaneBuildingPoint = os.path.join(scratch_ws, "SlopedPlaneBuildingPoint")
                arcpy.FeatureToPoint_management(LargeSlopedPlanes, SlopedPlaneBuildingPoint, "INSIDE")

                print("Calculating Eave Elevation...")
                arcpy.AddMessage("Calculating Eave Elevation...")

                # Calculate Eave Elevation
                SlopedUID = arcpy.Describe(LargeSlopedPlanes).OIDFieldName

                start_time_BuildingEaveHeight = time.time()
                BuildingEaveHeight(LgSlopedPlane=LargeSlopedPlanes, DSM=dsm,
                                   LgSlopedPlaneBuildingPoint=SlopedPlaneBuildingPoint, IDField=SlopedUID,
                                   scratch_ws=scratch_ws, verbose=verbose)
                end_time_BuildingEaveHeight = time.time()

                # Delete Intermediate SlopedPlaneBuildingDissolve Raster
                if verbose == 0:
                    arcpy.Delete_management(LargeSlopedPlanes)

        print("Creating Flat Roof Slope Polygons...")
        arcpy.AddMessage("Creating Flat Roof Slope Polygons...")

        # Flat Roof Slope Polygons
        FlatAreaPolygons = os.path.join(scratch_ws, "FlatAreaPolygons")

        start_time_FlatRoofPolygons = time.time()
        FlatRoofPolygons(BuildingFootprint=BuildingPolygons, RoofSlope=RoofSlope, FlatAreaPolygons=FlatAreaPolygons,
                         scratch_ws=scratch_ws, verbose=verbose)


        # Delete Intermediate RoofSlope
        if verbose == 0:
            arcpy.Delete_management(RoofSlope)

        # Merge Flat Roof Slope Polygons & Building Footprint
        RoofPlanesMergeOutput = os.path.join(scratch_ws, "RoofPlanesMerge")
        FlatRoofAreas(FlatAreaPolygons=FlatAreaPolygons, RoofPlanesMergeOutput=RoofPlanesMergeOutput,
                      MinFlatRoofArea=min_flat_roof_area)

        # Delete Intermediate RoofPlanesMergeOutput Polygon
        if verbose == 0:
            arcpy.Delete_management(RoofPlanesMergeOutput)

        end_time_FlatRoofPolygons = time.time()

        print("Calculating Flat Roof Area...")
        arcpy.AddMessage("Calculating Flat Roof Area...")

        # Calculate Flat Roof Area
        start_time_FlatAreaCalculate = time.time()

        FlatAreaDissolved = os.path.join(scratch_ws, "FlatAreaDissolved")
        FlatAreaCalculate(FlatAreaPolygons=FlatAreaPolygons, BuildingFootprint=BuildingPolygons,
                          FlatAreaDissolved=FlatAreaDissolved,
                          scratch_ws=scratch_ws, verbose=verbose)

        # Select Flat Planes by Area
        FlatRoofPlanes = os.path.join(scratch_ws, "FlatRoofPlanes")  # Input for "Flat Plane Count & Max Plane Ht
        FlatRoofPlaneEquation = "GeomArea > " + str(min_flat_roof_area)
        arcpy.Select_analysis(FlatAreaPolygons, FlatRoofPlanes, FlatRoofPlaneEquation)

        # Delete Intermediate FlatAreaPolygons Polygon
        if verbose == 0:
            arcpy.Delete_management(FlatAreaPolygons)

        # Flat Plane Count
        SpatialJoinFlatPlaneCount = os.path.join(scratch_ws, "SpatialJoinFlatPlaneCount")
        FlatPlaneCount(FlatRoofPlanes=FlatRoofPlanes, BuildingFootprint=BuildingPolygons,
                       SpatialJoinFlatPlaneCount=SpatialJoinFlatPlaneCount)

        # Merge and Dissolve all roof planes
        RoofPlanesMerged = os.path.join(scratch_ws, "RoofPlanesMerged")
        RoofPlanesMergeInput = [RoofPlanePolygons, FlatRoofPlanes]
        fieldMappings = arcpy.FieldMappings()
        fieldMappings.addTable(RoofPlanePolygons)
        fieldMappings.addTable(FlatRoofPlanes)
        arcpy.Merge_management(RoofPlanesMergeInput, RoofPlanesMerged, fieldMappings)
        RoofPlanesMergedDissolved = os.path.join(scratch_ws, "BuildingRoofPlanes")
        if arcpy.Exists(RoofPlanesMergedDissolved):
            arcpy.Delete_management(RoofPlanesMergedDissolved)
        arcpy.Dissolve_management(RoofPlanesMerged, RoofPlanesMergedDissolved, BUILDINGIDfield, None, "MULTI_PART", "DISSOLVE_LINES")
        if verbose == 0:
            arcpy.Delete_management(RoofPlanesMerged)
            arcpy.Delete_management(FlatRoofPlanes)

        end_time_FlatAreaCalculate = time.time()

        print("Calculating Maximum Roof Plane Heights...")
        arcpy.AddMessage("Calculating Maximum Roof Plane Heights...")

        start_time_MaximumRoofPlaneHeights = time.time()

        # Calculate Maximum Roof Plane Heights
        RoofPlanesMergedPoint = os.path.join(scratch_ws, "RoofPlanesMergedPoint")
        MaximumRoofPlaneHeights(RoofPlanesMergedDissolved=RoofPlanesMergedDissolved, DSM=dsm,
                                RoofPlanesMergedPointOutput=RoofPlanesMergedPoint,
                                RoofPlanesMerged=RoofPlanesMerged,
                                scratch_ws=scratch_ws,
                                verbose=verbose)

        # Delete Intermediate FlatRoofPlanes Polygon
        if verbose == 0:
            arcpy.Delete_management(FlatRoofPlanes)

        # Calculate Maximum Roof Height
        MaximumRoofHeight(BuildingFootprint=BuildingPolygons, BuildingPoint=BuildingPoint, DSM=dsm, IDField=uniqueFID,
                          scratch_ws=scratch_ws, verbose=verbose)

        end_time_MaximumRoofPlaneHeights = time.time()

        ###################################
        # Join and Calculate Fields #
        ###################################

    #    arcpy.AddMessage("Begin Calculating roof-form attributes")

        start_time_lotsofjoining = time.time()

        # Spatial Join Unique Aspect Planes to Buildings
        BuildingAspectJoin = os.path.join(scratch_ws, "BuildingAspectJoin")
        arcpy.SpatialJoin_analysis(BuildingPolygons, UniqueAspectPlanes, BuildingAspectJoin, "#", "#", "#", "CONTAINS")

        #Delete Intermediate UniqueAspectPlanes
        if verbose == 0:
            arcpy.Delete_management(UniqueAspectPlanes)
        arcpy.AddField_management(BuildingAspectJoin, "Aspect_Count", "SHORT", None, None, None, None, "true", "false", None)
        arcpy.CalculateField_management(BuildingAspectJoin, "Aspect_Count", "!Join_Count!", "PYTHON_9.3")

        # Delete Joined Fields
        arcpy.DeleteField_management(BuildingPolygons, ["Aspect_Count", "Eave_Elev", "FlatArea", "FlatPlane_Count", "Planar_Max", "Building_Max"])

        # Join Aspect Count Field
        arcpy.JoinField_management(BuildingPolygons, BUILDINGIDfield, BuildingAspectJoin, BUILDINGIDfield, "Aspect_Count")
        if verbose == 0:
            arcpy.Delete_management(BuildingAspectJoin)

        # Join Base Elevation
        arcpy.JoinField_management(BuildingPolygons, BUILDINGIDfield, BuildingPoint, BUILDINGIDfield, BASEELEVATIONfield)

        # Join Flat Area
        arcpy.JoinField_management(BuildingPolygons, BUILDINGIDfield, FlatAreaDissolved, BUILDINGIDfield, "FlatArea")

        # Delete Intermediate FlatAreaDissolved Polygon
        if verbose == 0:
            arcpy.Delete_management(FlatAreaDissolved)

        # Added for "in_memory" processing as in_memory does not except "Shape_Area" only "shape.area"
        arcpy.AddField_management(BuildingPolygons, "GeomArea", "DOUBLE", None, None, None, None, "true", "false", None)
        arcpy.CalculateField_management(BuildingPolygons, "GeomArea", "!shape.area!", "PYTHON_9.3", None)

        # Join Flat Plane Count
        arcpy.JoinField_management(BuildingPolygons, BUILDINGIDfield, SpatialJoinFlatPlaneCount, BUILDINGIDfield, "FlatPlane_Count")
        # Delete Intermediate SpatialJoinFlatPlaneCount
        if verbose == 0:
            arcpy.Delete_management(SpatialJoinFlatPlaneCount)

        # Calculate Flat Area Ratio
        flatAreaCodeblock = """   
def flatAreaCode(flatArea, shapeArea):
    if flatArea is None:
        return 0
    else:
        return (flatArea/shapeArea)"""

        arcpy.CalculateField_management(BuildingPolygons, "FlatAreaRatio", "flatAreaCode(!FlatArea!, !GeomArea!)",
                                        "PYTHON_9.3", flatAreaCodeblock)

        # Calculate Roof Form
        RoofFormEquationInput = """
def RoofFormEquation(FlatRatio, AspectCount, FlatCount):
    if (FlatRatio > 0.45):
        return "Flat"
    elif (AspectCount == 0):
        return "Flat"
    elif (AspectCount > 0 and AspectCount < 3):
        return "Gable"
    elif (AspectCount > 2):
       return "Hip"
       """
        arcpy.CalculateField_management(BuildingPolygons, ROOFFORMField,
                                        "RoofFormEquation(!FlatAreaRatio!, !Aspect_Count!, !FlatPlane_Count!)",
                                        "PYTHON_9.3", RoofFormEquationInput)
        if slopedPlanesExist == 1:
            # Join Sloped Plane Eave Elevation and Calculate local Eave-Elevation HEIGHT
            arcpy.JoinField_management(BuildingPolygons, BUILDINGIDfield, SlopedPlaneBuildingPoint, BUILDINGIDfield, "Eave_Elev")
            eaveHeightCodeblock = """
def EaveHeight(eaveElev, baseElev, roofForm):
    if roofForm != 'Flat':
        return (eaveElev - baseElev)"""
            arcpy.CalculateField_management(BuildingPolygons, EAVEHEIGHTfield, "EaveHeight(!Eave_Elev!, !BASEELEV!, !ROOFFORM!)", "PYTHON_9.3", eaveHeightCodeblock)
            # Delete Intermediate SlopedPlaneBuildingPoint
            if verbose == 0:
                arcpy.Delete_management(SlopedPlaneBuildingPoint)

        # Add Building Max World Elevation
        arcpy.JoinField_management(BuildingPolygons, BUILDINGIDfield, RoofPlanesMergedPoint, BUILDINGIDfield, "Planar_Max")

        # Delete Intermediate RoofPlanesMergedPoint Point
        if verbose == 0:
            arcpy.Delete_management(RoofPlanesMergedPoint)

        # Add Building Max World Elevation
        arcpy.JoinField_management(BuildingPolygons, BUILDINGIDfield, BuildingPoint, BUILDINGIDfield, "Building_Max")

        # Calculate Building Max Local Elevation
        arcpy.CalculateField_management(BuildingPolygons, "Building_Max", "!Building_Max!-!BASEELEV!", "PYTHON_9.3", None)

        # Calculate Building Planar Max Local Elevation
        arcpy.CalculateField_management(BuildingPolygons, "Planar_Max", "!Planar_Max!-!BASEELEV!", "PYTHON_9.3", None)

        # Calculate Total Height
        TotalHeightCalcInput = """
def TotalHeightCalc(bldht, planarht):
    if (planarht is None):
        return bldht
    else:
        return planarht
        """
        arcpy.CalculateField_management(BuildingPolygons, BLDGHEIGHTfield, "TotalHeightCalc(!Building_Max!,!Planar_Max!)",
                                        "PYTHON_9.3", TotalHeightCalcInput)


        if verbose == 0:
            arcpy.Delete_management(BuildingPoint)

        # Calculate Roof Direction
        BuildingPlaneDir = os.path.join(scratch_ws, "BuildingPlaneDir")
        # PlaneDirSelect = os.path.join(scratch_ws, "PlaneDirSelect")
        if arcpy.Exists(BuildingPlaneDir):
            arcpy.Delete_management(BuildingPlaneDir)
        # if arcpy.Exists(PlaneDirSelect):
        #     arcpy.Delete_management(PlaneDirSelect)
        arcpy.SpatialJoin_analysis(BuildingPolygons, RoofPlanePolygons, BuildingPlaneDir)
        arcpy.AddField_management(BuildingPlaneDir, ROOFDIRECTIONfield, "SHORT", None, None, None, None, "true", "false", None)
        # arcpy.Select_analysis(BuildingPlaneDir, PlaneDirSelect, "ROOFFORM = 'Shed' OR ROOFFORM = 'Gable'")
        # Roof Direction Codeblock
        roofDirCode = """
def aspectDir(roofForm, aspect):
    if roofForm == 'Shed' and aspect == 1:
        return 0
    elif roofForm == 'Shed' and aspect == 2:
        return 45
    elif roofForm == 'Shed' and aspect == 3:
        return 90
    elif roofForm == 'Shed' and aspect == 4:
        return 135
    elif roofForm == 'Shed' and aspect == 5:
        return 180
    elif roofForm == 'Shed' and aspect == 6:
        return 225
    elif roofForm == 'Shed' and aspect == 7:
        return 270
    elif roofForm == 'Shed' and aspect == 8:
        return 315
    elif roofForm == 'Gable' and aspect == 1:
        return 90
    elif roofForm == 'Gable' and aspect == 2:
        return 135
    elif roofForm == 'Gable' and aspect == 3:
        return 180
    elif roofForm == 'Gable' and aspect == 4:
        return 225
    elif roofForm == 'Gable' and aspect == 5:
        return 270
    elif roofForm == 'Gable' and aspect == 6:
        return 315
    elif roofForm == 'Gable' and aspect == 7:
        return 0
    elif roofForm == 'Gable' and aspect == 8:
        return 45
        """
        arcpy.CalculateField_management(BuildingPlaneDir, ROOFDIRECTIONfield, "aspectDir(!ROOFFORM!, !gridcode!)", "PYTHON_9.3", roofDirCode)
        #Join ROOFDIRECTION to Building Polygons
        arcpy.JoinField_management(BuildingPolygons, BUILDINGIDfield, BuildingPlaneDir, BUILDINGIDfield, ROOFDIRECTIONfield)
        #Delete intermediate data
        if verbose == 0:
            arcpy.Delete_management(BuildingPlaneDir)
            # arcpy.Delete_management(PlaneDirSelect)
            arcpy.Delete_management(RoofPlanePolygons)
        # Delete Joined Fields
        #arcpy.DeleteField_management(BuildingPolygons, ["Aspect_Count", "Eave_Elev", "FlatArea", "FlatPlane_Count", "Planar_Max", "Building_Max"])

        # # Set base Z
        # BuildingPolys3D = os.path.join(scratch_ws, "BuildingPolys3D")
        # if arcpy.Exists(BuildingPolys3D):
        #     arcpy.Delete_management(BuildingPolys3D)
        # arcpy.FeatureTo3DByAttribute_3d(BuildingPolygons, BuildingPolys3D, BASEELEVATIONfield)

        end_time_lotsofjoining = time.time()

        # Simplify Polygons
        if simplify_buildings == "true":
            print("Simplifying Polygons...")
            arcpy.AddMessage("Simplifying Polygons...")

            BuildingsSimplify = os.path.join(scratch_ws, "BuildingsSimplify")
            arcpy.SimplifyPolygon_cartography(BuildingPolygons, BuildingsSimplify, "POINT_REMOVE", simplify_tolerance)
        else:
            BuildingsSimplify = BuildingPolygons


        ##################
        # Set First Edge #
        ##################
        input_features = BuildingsSimplify
        roofDirectionField = ROOFDIRECTIONfield
        roofDirAttribute = 1

        # define reference orientation in degrees measured from x to y
        # (e.g. 0 = east, 90 = south, 180 = west, 270 = north)
        refOrientation = 270    # [deg]
        tolerance = 45          # (+-) [deg] (optional)
        edgeLength = "longest"

        workspace = bm_common_lib.get_work_space_from_feature_class(input_features, "yes")
        arcpy.env.workspace = workspace
        arcpy.env.overwriteOutput = True

        # Use Describe to get a SpatialReference object
        dsc = arcpy.Describe(input_features)
        spatial_reference = dsc.spatialReference
        fields = dsc.fields
        fieldnames = [field.name for field in fields]

        # create output polygon feature class
        geometry_type = dsc.shapeType
        has_m = "SAME_AS_TEMPLATE"
        has_z = "DISABLED"

        # if dsc.hasZ:
        #     has_z = "ENABLED"

        if dsc.hasM:
            has_m = "ENABLED"

        if arcpy.Exists(output_buildings):
            arcpy.Delete_management(output_buildings)
        result = arcpy.CreateFeatureclass_management(os.path.dirname(output_buildings),
                                                     os.path.basename(output_buildings), geometry_type, "",
                                                     has_m, has_z, spatial_reference)

        # add BUILDINGfid for joining
        arcpy.AddField_management(output_buildings, BUILDINGIDfield, "TEXT")

        if result.status == 4:

            start_time_firstedge = time.time()
            print("Calculating the first edge...")
            arcpy.AddMessage("Calculating the first edge...")

            # Open an insert cursor for the new feature class
            cur = arcpy.da.InsertCursor(output_buildings, ["OID@", "SHAPE@", BUILDINGIDfield])

            # Create an array object needed to create features
            array = arcpy.Array()

            # get number of features for time estimate
            input_layer = "input_lyr"
            arcpy.MakeFeatureLayer_management(input_features, input_layer)
            result = arcpy.GetCount_management(input_layer)
            count = int(result.getOutput(0))
            i = 1
            dec = 25
            timecheck = 5
            start_time = time.time()

            # Enter for loop for each feature
            #
            r = 0
            for row in arcpy.da.SearchCursor(input_features, ["OID@", "SHAPE@",
                                                              ROOFDIRECTIONfield,
                                                              BUILDINGIDfield]): 	###@DAN: enable this line
                if row:
                    if row[0] and row[1] and row[3]:
                        # Print the current multipoint's ID
                        #
                        donut = 0
                        edge_index = 0
                        percent = int((i / count)*100)

                        if percent == timecheck:
                            end_time = time.time()
                            time_diff = end_time-start_time
                            message = "Estimated time required to finish setting the first edge... {:.2f} " \
                                      "minutes.".format(((time_diff/60)*(100-percent))/percent)
                            arcpy.AddMessage(message)
                            timecheck = 0

                        if percent >= dec:
                            end_time = time.time()
                            time_diff = end_time-start_time
                            message = "Still working on " \
                                      "it...  "+str(percent)+"% done. Approx: {:.2f} minutes left to " \
                                      "go.".format(((time_diff/60)*(100-percent))/percent)
                            arcpy.AddMessage(message)

                            dec = dec + 25

                        # generate a vertex list
                        return_list = featureGetVertices(row)
                        if return_list:
                            vertex_list = return_list[0]
                            donut = return_list[1]

                            # SET THE REF_ORIENTATION VALUE
                            direction_values = {0: 270, 45: 225, 90: 180, 135: 135, 180: 90, 225: 45, 270: 0,
                                                315: 315, None: 270}

                            if roofDirAttribute == 1:
                                refOrientation = direction_values[row[2]]

                            # check if clockwise
                            clockwise = checkClockwise(vertex_list)

                            #  set longest edge with selected orientation as first edge
                            if donut == 1:
                                # create the donut polygon // do not reset edge
                                cur.insertRow([row[0], row[1], row[3]])
                            else:
                                edge_index = getEdgeIndex(vertex_list, edgeLength, refOrientation, tolerance)
                                newFeature = featureWriteVertices(array, vertex_list, edge_index, spatial_reference,
                                                                  arcpy.Describe(input_features).hasZ)
                                cur.insertRow([row[0], newFeature, row[3]])

                            array.removeAll()

                            i += 1
                        else:
                            arcpy.AddWarning("Error reading feature: " + str(r) +
                                             " from: " + input_features + ".")
                    else:
                        arcpy.AddWarning("Error reading feature: " + str(r) +
                                         " from: " + input_features + ".")
                else:
                    arcpy.AddWarning("Error reading feature: " + str(r) +
                                     " from: " + input_features + ".")

                r += 1

            end_time_firstedge = time.time()

        # Join Necessary attributes back to output building polygons
        no_join_list = ["Shape", "shape", "numBuildingFID", "FlatAreaRatio", "Aspect_Count", "FlatArea",
                        "GeomArea", "FlatPlane_Count", "Eave_Elev", "Planar_Max", "Building_Max",
                        "SHAPE_Length", "SHAPE_Area", "SHAPE"]
        out_oid = arcpy.Describe(output_buildings).OIDFieldName

        # join on Building fid
#        joinOrigFields(output_buildings, out_oid, BuildingPolygons, numBUILDINGIDfield, no_join_list)
        joinOrigFields(output_buildings, BUILDINGIDfield, BuildingPolygons, BUILDINGIDfield, no_join_list)
        print("Adding roof form field domain...")
        arcpy.AddMessage("Adding roof form field domain...")

        # Add roof form field domain
        AddRoofFormDomain(output_buildings)

        #Add Ridge Adjust field
        arcpy.AddField_management(output_buildings, "RoofDirAdjust", "SHORT")
        arcpy.CalculateField_management(output_buildings, "RoofDirAdjust", "0", "PYTHON_9.3", None)

        SimplifyPoints = os.path.join(scratch_ws, "BuildingsSimplify_Pnt")

        # add symbology and add layer to TOC
        output_layer = bm_common_lib.get_name_from_feature_class(output_buildings) # + "_LOD2"
        arcpy.MakeFeatureLayer_management(output_buildings, output_layer)

        z_unit = bm_common_lib.get_z_unit(output_buildings, verbose)

        if z_unit == "Feet":
            SymbologyLayer = layer_directory + "\\LOD2BuildingShells_feet.lyrx"
        else:
            SymbologyLayer = layer_directory + "\\LOD2BuildingShells_meters.lyrx"

        if arcpy.Exists(SymbologyLayer):
            arcpy.ApplySymbologyFromLayer_management(output_layer, SymbologyLayer)
        else:
            msg_body = create_msg_body("Can't find " + SymbologyLayer + " in " + layer_directory, 0, 0)
            msg(msg_body, WARNING)

        # add the layer to the scene
        arcpy.SetParameter(11, output_layer)

        if verbose == 0:
            fcs = bm_common_lib.listFcsInGDB(scratch_ws)

            msg_prefix = "Deleting intermediate data..."

            msg_body = bm_common_lib.create_msg_body(msg_prefix, 0, 0)
            bm_common_lib.msg(msg_body)

            for fc in fcs:
                arcpy.Delete_management(BuildingPolygons)

        print("All done :)")
        arcpy.AddMessage("All done :)")

        end_time_lod2 = time.time()

        if verbose == 1:
            copy_time_diff = end_time_copy - start_time_copy
            DTMDSMValues_td = end_time_CreateBuildingFCWithDTMandDSMValues - start_time_CreateBuildingFCWithDTMandDSMValues
            MinRoofHeight_time_diff = end_time_MinimumRoofHeightThresholdDSM - start_time_MinimumRoofHeightThresholdDSM
            CreateRoofPlanePolygons_time_diff = end_time_CreateRoofPlanePolygons - start_time_CreateRoofPlanePolygons
            CreateAspectPlanes_time_diff = end_time_CreateAspectPlanes - start_time_CreateAspectPlanes
            BuildingMinElevation_time_diff = end_time_BuildingMinElevation - start_time_BuildingMinElevation
            MarkedSlopedPlaneBuilding_time_diff = end_time_MarkedSlopedPlaneBuilding - start_time_MarkedSlopedPlaneBuilding
            BuildingEaveHeight_time_diff = end_time_BuildingEaveHeight - start_time_BuildingEaveHeight
            FlatRoofPolygons_time_diff = end_time_FlatRoofPolygons - start_time_FlatRoofPolygons
            FlatAreaCalculate_time_diff = end_time_FlatAreaCalculate - start_time_FlatAreaCalculate
            MaximumRoofPlaneHeights_time_diff = end_time_MaximumRoofPlaneHeights - start_time_MaximumRoofPlaneHeights
            lotsofjoining_time_diff = end_time_lotsofjoining - start_time_lotsofjoining
            firstedge_time_diff = end_time_firstedge - start_time_firstedge

            lod2_time_diff = end_time_lod2 - start_time_lod2

            arcpy.AddMessage("Time to do copy feature class: " +
                             str(int(((copy_time_diff / lod2_time_diff) * 100))) + "%")
            arcpy.AddMessage("Time to do CreateBuildingFCWithDTMandDSMValues: "
                             + str(int(((DTMDSMValues_td / lod2_time_diff) * 100))) + "%")
            arcpy.AddMessage("Time to do MinimumRoofHeightThresholdDSM: " +
                             str(int(((MinRoofHeight_time_diff / lod2_time_diff) * 100))) + "%")
            arcpy.AddMessage("Time to do CreateRoofPlanePolygons: " +
                             str(int(((CreateRoofPlanePolygons_time_diff / lod2_time_diff) * 100))) + "%")
            arcpy.AddMessage("Time to do CreateAspectPlanes: " +
                             str(int(((CreateAspectPlanes_time_diff / lod2_time_diff) * 100))) + "%")
            arcpy.AddMessage("Time to do BuildingMinElevation: " +
                             str(int(((BuildingMinElevation_time_diff / lod2_time_diff) * 100))) + "%")
            arcpy.AddMessage("Time to do MarkedSlopedPlaneBuilding: " +
                             str(int(((MarkedSlopedPlaneBuilding_time_diff / lod2_time_diff) * 100))) + "%")
            arcpy.AddMessage("Time to do BuildingEaveHeight: " +
                             str(int(((BuildingEaveHeight_time_diff / lod2_time_diff) * 100))) + "%")
            arcpy.AddMessage("Time to do FlatRoofPolygons: " +
                             str(int(((FlatRoofPolygons_time_diff / lod2_time_diff) * 100))) + "%")
            arcpy.AddMessage("Time to do FlatAreaCalculate: " +
                             str(int(((FlatAreaCalculate_time_diff / lod2_time_diff) * 100))) + "%")
            arcpy.AddMessage("Time to do MaximumRoofPlaneHeights: " +
                             str(int(((MaximumRoofPlaneHeights_time_diff / lod2_time_diff) * 100))) + "%")
            arcpy.AddMessage("Time to do lotsofjoining: " +
                             str(int(((lotsofjoining_time_diff / lod2_time_diff) * 100))) + "%")
            arcpy.AddMessage("Time to do firstedge: " +
                             str(int(((firstedge_time_diff / lod2_time_diff) * 100))) + "%")

        return output_buildings

    except InputDataNotValid:
        arcpy.AddError("Input data is not valid. Check your data.")

    except NoFeatures:
        # The input has no features
        #
        print('Error creating feature class')
        arcpy.AddError('Error creating feature class')

    except NoRoofFeatures:
        arcpy.AddError("No roof areas found above the minimum height threshold. Please inspect your data and try again")

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

def generate_unique_field_name(fieldList, candidateName):
    if candidateName not in fieldList:
        return candidateName
    else:
        for x in range(1,1000):
            newname = f"{candidateName}_{x}"
            if newname not in fieldList:
                return newname

def check_field_conflicts(lyr):
    field_dict = {field.name: field for field in arcpy.ListFields(lyr)}
    if "Join_Count" in field_dict:
        fms = arcpy.FieldMappings()
        for name, field in field_dict.items():
            if field.type not in ['OID', 'Geometry']:
                fm = arcpy.FieldMap()
                fm.addInputField(lyr,name)
                if name == "Join_Count":
                    out_field = fm.outputField
                    out_field.name = generate_unique_field_name(list(field_dict.keys()),"Join_Count")
                    fm.outputField = out_field
                fms.addFieldMap(fm)

        out_fc = f"{arcpy.env.scratchGDB}{os.sep}clean_buildings" 
        arcpy.conversion.ExportFeatures(lyr, out_fc,field_mapping=fms)
        return out_fc
    else:
        return lyr

def run(home_directory, project_ws, buildings_layer, dsm, dtm, ndsm,
        flat_roofs, min_flat_roof_area, min_slope_roof_area, min_roof_height,
        output_buildings, simplify_buildings, simplify_tolerance, debug):
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

        output_building_polys = output_buildings + "_roofform"

        if not min_flat_roof_area or not min_slope_roof_area or not min_roof_height or not simplify_tolerance:
            arcpy.AddError("Found empty numeric input. Please make sure all numeric input is valid.")
            quit()
            sys.exit

        if min_flat_roof_area == "" or min_slope_roof_area == "" or min_roof_height == "" or simplify_tolerance == "":
            arcpy.AddError("Found empty numeric input. Please make sure all numeric input is valid.")
            quit()
            sys.exit

        if min_flat_roof_area == "0" or min_slope_roof_area == "0" or min_roof_height == "0" \
                or simplify_tolerance == "0":
            arcpy.AddError("Found zero in numeric input. Please make sure all numeric input is valid.")
            quit()
            sys.exit

        # fail safe for European comma's
        min_flat_roof_area = float(re.sub("[,.]", ".", min_flat_roof_area))
        min_slope_roof_area = float(re.sub("[,.]", ".", min_slope_roof_area))
        min_roof_height = float(re.sub("[,.]", ".", min_roof_height))
        simplify_tolerance = float(re.sub("[,.]", ".", simplify_tolerance))

        if os.path.exists(os.path.join(home_directory, "p20")):      # it is a package
            home_directory = os.path.join(home_directory, "p20")

        arcpy.AddMessage("Project Home Directory is: " + home_directory)

        for a in home_directory:
            if a.isspace():
                raise HasSpace

        if bm_common_lib.check_directory(home_directory):
            scratch_ws = bm_common_lib.create_gdb(home_directory, "Intermediate.gdb")
            analysis_ws = bm_common_lib.create_gdb(home_directory, "Analysis.gdb")
            arcpy.env.workspace = scratch_ws
            arcpy.env.overwriteOutput = True

            if arcpy.CheckExtension("3D") == "Available":
                arcpy.CheckOutExtension("3D")

                if arcpy.CheckExtension("Spatial") == "Available":
                    arcpy.CheckOutExtension("Spatial")

                    buildings_layer = check_field_conflicts(buildings_layer)

                    if not flat_roofs:
                        output_fc = extract_lod2_roof_form(home_directory=home_directory,
                                                           buildings_layer=buildings_layer,
                                                           dsm=dsm,
                                                           dtm=dtm,
                                                           ndsm=ndsm,
                                                           min_flat_roof_area=min_flat_roof_area,
                                                           min_slope_roof_area=min_slope_roof_area,
                                                           min_roof_height=min_roof_height,
                                                           output_buildings=output_building_polys,
                                                           simplify_buildings=simplify_buildings,
                                                           simplify_tolerance=simplify_tolerance,
                                                           verbose=verbose)
                    else:
                        output_fc = extract_lod1_roof_form(home_directory=home_directory,
                                                           buildings_layer=buildings_layer,
                                                           dsm=dsm,
                                                           dtm=dtm,
                                                           output_buildings=output_building_polys,
                                                           buffer_buildings=True,
                                                           buffer_size=str(1),
                                                           verbose=verbose)

                    if arcpy.Exists(output_fc):
                        arcpy.ClearWorkspaceCache_management()

                        if delete_intermediate_data:
                            bm_common_lib.clean_gdb(scratch_ws, debug)
                            bm_common_lib.clean_gdb(analysis_ws, debug)

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
