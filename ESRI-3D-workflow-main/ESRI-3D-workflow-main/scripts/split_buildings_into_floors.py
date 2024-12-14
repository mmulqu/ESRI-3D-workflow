# -------------------------------------------------------------------------------
# Name:         SplitBuildingsIntoFloors
# Purpose:      Split Buildings into floor based on Tier1FloorHeightGround and Tier1FloorHeightUpper
#               -> read from SpaceSUe table.
#               If no SpaceUseTable or no SpaceUseCode available, the user can input values for
#               Tier1FloorHeightGround and Tier1FloorHeightUpper
#           `   Alternatively the user can split by number of floors, groundfloor height and upper floor height
#               Currently we use BuildingType table and BuildingTypeName as table and join field

#               left to do:
#               - split vertically along parcel boundaries
#               - auto calculate building height (scope.sy)
#               - use building height and floor heights to guess number of floors, check with
#               split floors and fail or not.
#               - deal with multiple ground floors and different elevations
#               - deal with colors from spliterator edges
#               - deal with roofHeight is BLDGHEIGHT
#               - add Tier#SpaceUse and Tier#GFA in the building output
#               - fail gracefully when no layer files / rule packages

# Author:      Gert van Maren
#
# Created:     27/04/12/2017
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
TOOLNAME = "SplitFloors"
SPACEUSETABLE = "BuildingType"
ERROR = "error"
WARNING = "warning"
SPACEUSEJOINFIELD = "BuildingTypeName"
BUILDINGID = "BuildingID"
GROUNDFLOORHEIGHT = "GroundFloorHeight"
UPPERLOORHEIGHT = "UpperFloorHeight"
NUMFLOORSFIELD = "NumFloors"
EVENFLOORS = "EvenLevel"
UNITS = "Units"
MYSHAPEAREAFIELD = "MyShapeArea"
SHAPEAREAFIELD = "Shape_Area"
GFATOTALFIELD = "GFATotal"
ROOFHEIGHTFIELD = "RoofHeight"
MINIMUMFLOORAREA = "MinimumFloorArea"
BLDGHEIGHTfield = "BLDGHEIGHT"
EAVEHEIGHTfield = "EAVEHEIGHT"

CEREPORTfloorcolor = "FloorColor"
CEREPORTfloorheight = "FloorHeight"
CEREPORTelevation = "Elevation"
CEREPORTtier = "TierNumber"
CEREPORTunique_OID_field = "UID"
CEREPORTlevel = "Level"
CEREPORTusage = "SpaceUse"


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


class NoObjects(Exception):
    pass


class NoTable(Exception):
    pass


class NoID(Exception):
    pass


def get_failed_buildings(ws, org_buildings, split_buildings, local_sensitivity, debug):

    if debug == 1:
        msg("--------------------------")
        msg("Executing get_failed_buildings...")

    start_time = time.perf_counter()

    try:
        # get unique level values from split buildings table

        out_stats_table = os.path.join(ws, "building_floorStats")
        if arcpy.Exists(out_stats_table):
            arcpy.Delete_management(out_stats_table)

        stats_fields = [[CEREPORTlevel, "MAX"], [CEREPORTlevel, "RANGE"]]
        case_fields = [CEREPORTunique_OID_field]

        # get frequency of levels per buildingID
        arcpy.Statistics_analysis(split_buildings, out_stats_table, stats_fields, case_fields)

        # step through each build uid
        uid_values = bm_common_lib.unique_values(split_buildings, CEREPORTunique_OID_field)

        fields = [CEREPORTlevel, GFATOTALFIELD]

        failed_building_ids = []

        msg_body = ("Finding buildings where the split failed...")
        msg(msg_body)

        for id in uid_values:
            GFAtotal = 0
            level_list = []
            expression = """{} = {}""".format(arcpy.AddFieldDelimiters(split_buildings, CEREPORTunique_OID_field),
                                              str(id))
            with arcpy.da.SearchCursor(split_buildings, fields, expression) as s_cursor:
                count = 0
                for s_row in s_cursor:
                    level_list.append(s_row[0])
                    GFAtotal += s_row[1]
                    count += 1

            level_list = sorted(set(level_list))
            count = len(level_list)

            sum_fields = ["MAX_"+CEREPORTlevel]
            max_level = 0

            expression = """{} = {}""".format(arcpy.AddFieldDelimiters(out_stats_table, CEREPORTunique_OID_field),
                                              str(id))
            with arcpy.da.SearchCursor(out_stats_table, sum_fields, expression) as s_cursor:
                for s_row in s_cursor:
                    max_level = s_row[0]

            # check on MAX level and actual floor levels
            if count != max_level:
                failed_building_ids.append(id)
                msg_body = ("Building with UID: " + str(int(id)) + " failed. In the cue for edge processing...")
                msg(msg_body)
            else:
                # check if total gfa is footprint gfa * number of levels (rough check on levels that are way too small

                # required gfa
                extent_area = bm_common_lib.get_row_values_for_fields_with_floatvalue(None, org_buildings,
                                                                                      [MYSHAPEAREAFIELD],
                                                                                      CEREPORTunique_OID_field, id)[0]
                min_needed_gfa = max_level * extent_area * float(local_sensitivity)

                # actual gfa
                if min_needed_gfa > GFAtotal:
                    failed_building_ids.append(id)
                    msg_body = ("Building with UID: " + str(int(id)) + " failed. In the cue for edge processing...")
                    msg(msg_body)
                else:
                    msg_body = ("Building with UID: " + str(int(id)) + " -> split is OK.")
                    msg(msg_body)

        if len(failed_building_ids) > 0:
            failed_building_ids_astext = ','.join(map(str, failed_building_ids))
            building_lyr = "volumes_lyr"
            arcpy.MakeFeatureLayer_management(org_buildings, building_lyr)
            expression = """{} IN ({})""".format(arcpy.AddFieldDelimiters(building_lyr, CEREPORTunique_OID_field),
                                                 failed_building_ids_astext)

            arcpy.SelectLayerByAttribute_management(building_lyr, "NEW_SELECTION", expression)

            failed_buildings = os.path.join(ws, "failed_buildings")
            if arcpy.Exists(failed_buildings):
                arcpy.Delete_management(failed_buildings)

            arcpy.CopyFeatures_management(building_lyr, failed_buildings)

            # delete from split floors
            floors_lyr = "floors_lyr"
            arcpy.MakeFeatureLayer_management(split_buildings, floors_lyr)
            expression = """{} IN ({})""".format(arcpy.AddFieldDelimiters(floors_lyr, CEREPORTunique_OID_field),
                                                 failed_building_ids_astext)

            arcpy.SelectLayerByAttribute_management(floors_lyr, "NEW_SELECTION", expression)

            if int(arcpy.GetCount_management(floors_lyr).getOutput(0)) > 0:
                arcpy.DeleteFeatures_management(floors_lyr)

        else:
            failed_buildings = None

        msg_prefix = "Function get_failed_buildings completed successfully."
        failed = False

        return failed_building_ids, failed_buildings

    except:
        line, filename, synerror = trace()
        failed = True
        msg_prefix = ""
        raise FunctionError(
            {
                "function": "get_failed_buildings",
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
            if debug == 1:
                msg(msg_body)


def calculate_gfa(local_ws, local_buildings, local_floor_plates, method, debug):

    if debug == 1:
        msg("--------------------------")
        msg("Executing calculate_gfa...")

    start_time = time.perf_counter()

    try:
        out_stats_table = os.path.join(local_ws, "floorStats")
        if arcpy.Exists(out_stats_table):
            arcpy.Delete_management(out_stats_table)

        stats_fields = [[GFATOTALFIELD, "SUM"]]

        if method == "usage":
            stats_fields = [[GFATOTALFIELD, "SUM"], [CEREPORTtier, "FIRST"]]
            case_fields = [CEREPORTunique_OID_field, CEREPORTusage]
        elif method == "tier":
            stats_fields = [[GFATOTALFIELD, "SUM"], [CEREPORTusage, "FIRST"]]
            case_fields = [CEREPORTunique_OID_field, CEREPORTtier]
        else:
            case_fields = [CEREPORTunique_OID_field]

        arcpy.Statistics_analysis(local_floor_plates, out_stats_table, stats_fields, case_fields)

        if method == "usage":
            # get unique space use values from stats table
            usage_values = bm_common_lib.unique_values(out_stats_table, CEREPORTusage)

            # add as attributes to buildings layer
            chars = set('!@#$%^&*()_-+={}[]:;"<><.?/')

            for value in usage_values:
                if not any((c in chars) for c in value):
                    field_in_list = value
                    field_in_list = re.sub('[\s+]', '_', field_in_list)
                    attr_name = "gfa_" + field_in_list
                    bm_common_lib.add_field(local_buildings, attr_name, "DOUBLE", 20)
                else:
                    msg_prefix = "Invalid characters found in: " + value
                    msg_body = create_msg_body(msg_prefix, 0, 0)
                    msg(msg_body, WARNING)

            fields = [CEREPORTunique_OID_field, CEREPORTusage, "SUM_" + GFATOTALFIELD]

            # step through stats table - for each building ID, select in the buildings layer, find the space use
            # / tier attribute and set it to the SUM_area
            with arcpy.da.SearchCursor(out_stats_table, fields) as s_cursor:
                for s_row in s_cursor:
                    # find field in buildings
                    the_field = s_row[1]
                    the_field = re.sub('[\s+]', '_', the_field)
                    gfa_usage_field = bm_common_lib.find_field_by_wildcard(local_buildings, the_field)

                    #
                    whereclause = CEREPORTunique_OID_field + " = " + str(s_row[0])
                    with arcpy.da.UpdateCursor(local_buildings, gfa_usage_field, whereclause) as u_cursor:
                        for u_row in u_cursor:
                            u_row[0] = s_row[2]
                            u_cursor.updateRow(u_row)

        elif method == "tier":
            tier_values = bm_common_lib.unique_values(out_stats_table, CEREPORTtier)
            for value in tier_values:
                attr_name = "Tier" + str(int(value)) + "GFA"
                bm_common_lib.add_field(local_buildings, attr_name, "DOUBLE", 20)

                attr_name = "Tier" + str(int(value)) + "SpaceUse"
                bm_common_lib.add_field(local_buildings, attr_name, "TEXT", 50)

            fields = [CEREPORTunique_OID_field, CEREPORTtier, "SUM_" + GFATOTALFIELD, "FIRST_" + CEREPORTusage]

            # step through stats table - for each building ID, select in the buildings layer, find the space use
            # / tier attribute and set it to the SUM_area
            with arcpy.da.SearchCursor(out_stats_table, fields) as s_cursor:
                for s_row in s_cursor:
                    # find tier field in buildings
                    the_field = str(int(s_row[1]))
                    the_field = "Tier" + the_field + "GFA"
                    gfa_tier_field = bm_common_lib.find_field_by_wildcard(local_buildings, the_field)

                    # update the tier field in buildings
                    whereclause = CEREPORTunique_OID_field + " = " + str(s_row[0])
                    with arcpy.da.UpdateCursor(local_buildings, gfa_tier_field, whereclause) as u_cursor:
                        for u_row in u_cursor:
                            u_row[0] = s_row[2]
                            u_cursor.updateRow(u_row)

                    # find usage field in buildings
                    the_field = str(int(s_row[1]))
                    the_field = "Tier" + the_field + "SpaceUse"
                    usage_tier_field = bm_common_lib.find_field_by_wildcard(local_buildings, the_field)

                    # update the tier field in buildings
                    whereclause = CEREPORTunique_OID_field + " = " + str(s_row[0])
                    with arcpy.da.UpdateCursor(local_buildings, usage_tier_field, whereclause) as u_cursor:
                        for u_row in u_cursor:
                            u_row[0] = s_row[3]
                            u_cursor.updateRow(u_row)

        else:
            fieldList = ["SUM_" + GFATOTALFIELD]

            bm_common_lib.delete_fields(local_buildings, fieldList)
            arcpy.JoinField_management(local_buildings, CEREPORTunique_OID_field, out_stats_table,
                                       CEREPORTunique_OID_field, fieldList)

        msg_prefix = "calculate_gfa completed successfully."
        failed = False

    except:
        line, filename, synerror = trace()
        failed = True
        msg_prefix = ""
        raise FunctionError(
            {
                "function": "calculate_gfa",
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
            if debug == 1:
                msg(msg_body)


def calculate_footprint_area(ws, buildings, join_field, debug):
    if debug == 1:
        msg("--------------------------")
        msg("Executing calculate_footprint_area...")

    start_time = time.perf_counter()

    try:
        temp_footprint = os.path.join(ws, "temp_footprint")
        if arcpy.Exists(temp_footprint):
            arcpy.Delete_management(temp_footprint)

        arcpy.MultiPatchFootprint_3d(buildings, temp_footprint)
        bm_common_lib.delete_add_field(temp_footprint, MYSHAPEAREAFIELD, "DOUBLE")
        arcpy.CalculateField_management(temp_footprint, MYSHAPEAREAFIELD, "!" + SHAPEAREAFIELD + "!",
                                        "PYTHON_9.3", None)

        fieldList = [MYSHAPEAREAFIELD]

        bm_common_lib.delete_fields(buildings, fieldList)

        # Join two feature classes by the zonecode field and only carry
        # over the land use and land cover fields
        arcpy.JoinField_management(buildings, join_field, temp_footprint, join_field, fieldList)

        msg_prefix = "Function calculate_footprint_area completed successfully."
        failed = False

    except:
        line, filename, synerror = trace()
        failed = True
        msg_prefix = ""
        raise FunctionError(
            {
                "function": "calculate_footprint_area",
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
            if debug == 1:
                msg(msg_body)


def building_edges_to_floor_plates(ws, building_features, edge_features, local_z, by_building_type,
                                   minimum_floor_area, cluster_tolerance, debug, in_memory_switch):

    # relies on feature class that represent floors as edges. Can be created in cga with split(y) and comp(e)
    # requires a UID object representing the OID

    if debug == 1:
        msg("--------------------------")
        msg("Executing building_edges_to_floor_plates...")

    split_floor = True
    start_time = time.perf_counter()

    try:
        # 2D floor plate feature class
        floor_plates_2d = "floorplates_2d"
        floor_lines_2d = "floorlines_2d"

        floor_plates_2d_path = os.path.join(ws, floor_plates_2d)
        if arcpy.Exists(floor_plates_2d_path):
            arcpy.Delete_management(floor_plates_2d_path)

        floor_lines_2d_path = os.path.join(ws, floor_lines_2d)
        if arcpy.Exists(floor_lines_2d_path):
            arcpy.Delete_management(floor_lines_2d_path)

        geometry_type = "POLYGON"
        has_m = "ENABLED"
        has_z = "DISABLED"

        desc = arcpy.Describe(edge_features)
        sr = desc.spatialReference

        # Execute CreateFeatureclass
        arcpy.CreateFeatureclass_management(ws, floor_plates_2d, geometry_type, edge_features, has_m, has_z, sr)

        geometry_type = "POLYLINE"

        # Execute CreateFeatureclass
        arcpy.CreateFeatureclass_management(ws, floor_lines_2d, geometry_type, edge_features, has_m, has_z, sr)

        # loop through per building!!
        unique_idfield_values = bm_common_lib.unique_values(edge_features, CEREPORTunique_OID_field)

        edge_lyr = "edge_lyr"
        arcpy.MakeFeatureLayer_management(edge_features, edge_lyr)

        for uid in unique_idfield_values:
            # get unique building
            expression = """{} = {}""".format(arcpy.AddFieldDelimiters(edge_lyr, CEREPORTunique_OID_field), str(uid))

            arcpy.SelectLayerByAttribute_management(edge_lyr, "NEW_SELECTION", expression)

            # export to temp fc
#            if in_memory_switch:
            if 0:
                temp_building = "in_memory/temp_building"
            else:
                temp_building = os.path.join(ws, "temp_building")
                if arcpy.Exists(temp_building):
                    arcpy.Delete_management(temp_building)

            arcpy.CopyFeatures_management(edge_lyr, temp_building)

            building_lyr = "building_lyr"
            arcpy.MakeFeatureLayer_management(temp_building, building_lyr)

            # check area, if < 7 m2 or 75sqft: disregard...
            extent_area = bm_common_lib.get_row_values_for_fields_with_floatvalue(None, building_features,
                                                                                  [MYSHAPEAREAFIELD],
                                                                                  CEREPORTunique_OID_field, uid)[0]

            if local_z == "Feet":
                if extent_area < 75:
                    split_floor = False
                else:
                    split_floor = True
            else:
                if extent_area < 7:
                    split_floor = False
                else:
                    split_floor = True

            if split_floor:
                unique_field_values = bm_common_lib.unique_values(temp_building, CEREPORTlevel)

                # for each floor
                for value in unique_field_values:
                    start_time = time.perf_counter()

                    expression = """{} = {}""".format(arcpy.AddFieldDelimiters(building_lyr, CEREPORTlevel), str(value))

                    arcpy.SelectLayerByAttribute_management(building_lyr, "NEW_SELECTION", expression)

                    # export to temp fc
                    if in_memory_switch:
                        temp_edge = os.path.join("in_memory", "temp_edge")
                        temp_poly = os.path.join("in_memory", "temp_poly")
                        temp_dissolve = os.path.join("in_memory", "temp_dissolve")
                        temp_labels = os.path.join("in_memory", "temp_labels")
                    else:
                        temp_edge = os.path.join(ws, "temp_edge")
                        if arcpy.Exists(temp_edge):
                            arcpy.Delete_management(temp_edge)
                        temp_poly = os.path.join(ws, "temp_poly")
                        if arcpy.Exists(temp_poly):
                            arcpy.Delete_management(temp_poly)
                        temp_dissolve = os.path.join(ws, "temp_dissolve")
                        if arcpy.Exists(temp_dissolve):
                            arcpy.Delete_management(temp_dissolve)
                        temp_labels = os.path.join(ws, "temp_labels")
                        if arcpy.Exists(temp_labels):
                            arcpy.Delete_management(temp_labels)

                    # make the selected edge 2d
                    arcpy.CopyFeatures_management(building_lyr, temp_edge)
                    arcpy.Append_management(temp_edge, floor_lines_2d_path)

                    # get label feature from one of the lines
                    arcpy.FeatureToPoint_management(floor_lines_2d_path, temp_labels, "CENTROID")

                    # set elevation etc
                    elevation_values = bm_common_lib.unique_values(floor_lines_2d_path, CEREPORTelevation)
                    floorheight_values = bm_common_lib.unique_values(floor_lines_2d_path, CEREPORTfloorheight)

                    if by_building_type:
                        usage_values = bm_common_lib.unique_values(floor_lines_2d_path, CEREPORTusage)
                        tier_values = bm_common_lib.unique_values(floor_lines_2d_path, CEREPORTtier)
                        floorcolor_values = bm_common_lib.unique_values(floor_lines_2d_path, CEREPORTfloorcolor)

                    arcpy.RepairGeometry_management(floor_lines_2d_path)

                    msg_body = ("Executing FeatureToPolygon...")
                    msg(msg_body)
                    arcpy.FeatureToPolygon_management(floor_lines_2d_path, temp_poly, float(cluster_tolerance),
                                                      "ATTRIBUTES", temp_labels)

                    num_features = int(arcpy.GetCount_management(temp_poly).getOutput(0))

                    i = 0.1

                    # hack to force output
                    while num_features == 0 and i < 2:
                        arcpy.Delete_management(temp_poly)
                        arcpy.FeatureToPolygon_management(floor_lines_2d_path, temp_poly, float(cluster_tolerance) + i,
                                                          "ATTRIBUTES", temp_labels)
                        num_features = int(arcpy.GetCount_management(temp_poly).getOutput(0))
                        i += 0.2

                    # only 1 feature and smaller than min floor area -> discard
                    go_ahead = True
                    if num_features > 0:
                        if num_features == 1:
                            # get Shape_area
                            for row in arcpy.da.SearchCursor(temp_poly, ["SHAPE@AREA"]):
                                shape_area = row[0]
                                break

                            if shape_area < float(minimum_floor_area):
                                go_ahead = False

                        if go_ahead:
                            # not needed anymore because we report feet / meters now from CE
                            # if local_z == "Feet":
                            #     arcpy.CalculateField_management(temp_poly, CEREPORTelevation, elevation_
                            #     values[0] * 3.28)
                            # else:
                            arcpy.CalculateField_management(temp_poly, CEREPORTelevation, elevation_values[0])

                            bm_common_lib.set_row_values_for_field(None, temp_poly, CEREPORTunique_OID_field, uid, 0)
                            bm_common_lib.set_row_values_for_field(None, temp_poly, CEREPORTlevel, value, 0)
                            bm_common_lib.set_row_values_for_field(None, temp_poly, CEREPORTfloorheight,
                                                                   floorheight_values[0], 0)

                            if by_building_type:
                                usage_value = str(usage_values[0])
                                bm_common_lib.set_row_values_for_field(None, temp_poly, CEREPORTusage, usage_value, 0)
                                bm_common_lib.set_row_values_for_field(None, temp_poly, CEREPORTtier, tier_values[0], 0)
                                bm_common_lib.set_row_values_for_field(None, temp_poly, CEREPORTfloorcolor,
                                                                       floorcolor_values[0], 0)

                            schemaType = "NO_TEST"
                            arcpy.Append_management(temp_poly, floor_plates_2d_path, schemaType)

                            msg_body = ("Created floor: " + str(int(value)) + " for building with UID: " + str(uid))
                            end_time = time.perf_counter()

                            msg_body = create_msg_body(msg_body, start_time, end_time)
                            msg(msg_body)
                        else:
                            msg_body = ("Skipping Floor: " + str(int(value)) + " for building with UID: " +
                                        str(uid) + ": smaller than " + str(minimum_floor_area))
                            end_time = time.perf_counter()

                            msg_body = create_msg_body(msg_body, start_time, end_time)
                            msg(msg_body)
                    else:
                        msg_body = ("Can't create floor: " + str(int(value)) + " for building with UID: " +
                                    str(uid) + ": error in FeatureToPolyogn.")
                        end_time = time.perf_counter()

                        msg_body = create_msg_body(msg_body, start_time, end_time)
                        msg(msg_body)

                    # delete rows in line table
                    result = arcpy.TruncateTable_management(floor_lines_2d_path)
                    if result.status == 4:
                        pass

                    if in_memory_switch:
                        arcpy.Delete_management("in_memory")
            else:
                msg_body = ("Building area too small. Skipping building with UID: " + str(uid))
                msg(msg_body)

        # calculate GFATotal from SHAPE_Area
        arcpy.CalculateField_management(floor_plates_2d_path, GFATOTALFIELD, "!" + SHAPEAREAFIELD + "!", "PYTHON_9.3")

        msg_prefix = "Function building_edges_to_floor_plates completed successfully."
        failed = False

        return floor_plates_2d_path

    except:
        line, filename, synerror = trace()
        failed = True
        msg_prefix = ""
        raise FunctionError(
            {
                "function": "building_edges_to_floor_plates",
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
            if debug == 1:
                msg(msg_body)


def split_features(local_sw, local_features, local_rpk, debug):

    failed = True
    msg_prefix = ""

    if debug == 1:
        msg("--------------------------")
        msg("Executing split_features...")

    start_time = time.perf_counter()

    try:
        ffcer_output = os.path.join(local_sw, "FFCER_split_output")
        if arcpy.Exists(ffcer_output):
            arcpy.Delete_management(ffcer_output)

        # split into edges
        msg_body = "Splitting buildings..."
        msg(msg_body)
        arcpy.FeaturesFromCityEngineRules_3d(local_features, local_rpk, ffcer_output,
                                             "INCLUDE_EXISTING_FIELDS",
                                             "INCLUDE_REPORTS")

        msg_prefix = "Function split_features completed successfully."
        failed = False
        return ffcer_output

    except:
        line, filename, synerror = trace()
        failed = True
        msg_prefix = ""
        raise FunctionError(
            {
                "function": "split_features",
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
            if debug == 1:
                msg(msg_body)
            pass


def split_features_by_edges(local_sw, local_features, local_rpk, local_z, by_building_type, minimum_floor_area,
                            local_xy, debug, in_memory_switch):

    failed = True
    msg_prefix = ""
    local_floor_plates = None

    if debug == 1:
        msg("--------------------------")
        msg("Executing split_features...")

    start_time = time.perf_counter()

    try:
        ffcer_output = os.path.join(local_sw, "FFCER_split_edges_output")
        if arcpy.Exists(ffcer_output):
            arcpy.Delete_management(ffcer_output)

        ffcer_output_lines = os.path.join(local_sw, "FFCER_split_edges_output_Lines")
        if arcpy.Exists(ffcer_output_lines):
            arcpy.Delete_management(ffcer_output_lines)

        # split into edges
        msg_body = "Splitting failed buildings using edge detection..."
        msg(msg_body)
        arcpy.FeaturesFromCityEngineRules_3d(local_features, local_rpk, ffcer_output,
                                             "INCLUDE_EXISTING_FIELDS",
                                             "INCLUDE_REPORTS")

        edge_features = ffcer_output + "_Lines"

        num_features = int(arcpy.GetCount_management(edge_features).getOutput(0))

        # batch processing fo failed buildngs to keep memory delay in check
        if num_features > 0:
            batch_size = 10
            i = 1
            # 2D floor plate feature class
            local_floor_plates = "floorplates_2d_batched"

            floor_plates_2d_path = os.path.join(local_sw, local_floor_plates)
            if arcpy.Exists(floor_plates_2d_path):
                arcpy.Delete_management(floor_plates_2d_path)

            geometry_type = "POLYGON"
            has_m = "ENABLED"
            has_z = "DISABLED"

            desc = arcpy.Describe(edge_features)
            sr = desc.spatialReference

            # Execute CreateFeatureclass
            arcpy.CreateFeatureclass_management(local_sw, local_floor_plates, geometry_type, edge_features,
                                                has_m, has_z, sr)

            unique_idfield_values = bm_common_lib.unique_values(edge_features, CEREPORTunique_OID_field)

            for x in range(0, len(unique_idfield_values), batch_size):
                batch = unique_idfield_values[x:x + batch_size]
                string = ', '.join(str(e) for e in batch)

                batch_lyr = "batch_lyr"
                arcpy.MakeFeatureLayer_management(edge_features, batch_lyr)
                expression = """{0} IN ({1})""".format(arcpy.AddFieldDelimiters(batch_lyr,
                                                                                CEREPORTunique_OID_field), string)

                arcpy.SelectLayerByAttribute_management(batch_lyr, "NEW_SELECTION", expression)

                batch_features = os.path.join(local_sw, "batch_features_" + str(i))
                if arcpy.Exists(batch_features):
                    arcpy.Delete_management(batch_features)

                arcpy.CopyFeatures_management(batch_lyr, batch_features)
                i += 1

                batch_floor_plates = building_edges_to_floor_plates(local_sw, local_features, batch_features,
                                                                    local_z, by_building_type, minimum_floor_area,
                                                                    local_xy, debug, in_memory_switch)

                arcpy.Append_management(batch_floor_plates, local_floor_plates)

        msg_prefix = "Function split_features completed successfully."
        failed = False
        return local_floor_plates

    except:
        line, filename, synerror = trace()
        failed = True
        msg_prefix = ""
        raise FunctionError(
            {
                "function": "split_features",
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
            if debug == 1:
                msg(msg_body)
            pass


def set_value_for_field2_to_field1_when_null_or_zero(cn_table, field1, field2, debug):
    try:
        if debug == 1:
            msg("--------------------------")
            msg("Executing set_value_for_field1_to_field2_when_null_or_zero...")

        start_time = time.perf_counter()
        failed = True
        null_value = False
        field_name = ""

        field_list = [field1, field2]

        if arcpy.Exists(cn_table):
            with arcpy.da.UpdateCursor(cn_table, field_list) as cursor:
                for row in cursor:
                    if row[0] is None or row[0] == 0:
                        if row[1] is not None:
                            row[0] = row[1]

                    cursor.updateRow(row)

        msg_prefix = "Function set_value_for_field1_to_field2_when_null_or_zero completed successfully."
        failed = False
        return null_value

    except:
        line, filename, synerror = trace()
        failed = True
        msg_prefix = ""
        raise FunctionError(
            {
                "function": "set_value_for_field1_to_field2_when_null_or_zero",
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
            if debug == 1:
                msg(msg_body)
            else:
                pass


def get_roof_height_from_eave_height(ws, buildings, debug):
    if debug == 1:
        msg("--------------------------")
        msg("Executing get_roof_height_from_eave_height...")

    start_time = time.perf_counter()

    try:
        if bm_common_lib.check_fields(buildings, [EAVEHEIGHTfield], False, debug) == 0:
            if bm_common_lib.check_null_in_fields(buildings, [EAVEHEIGHTfield], True, debug):
                set_value_for_field2_to_field1_when_null_or_zero(buildings, EAVEHEIGHTfield, BLDGHEIGHTfield, debug)
#               bm_common_lib.set_null_to_value_in_fields(buildings, [EAVEHEIGHTfield], [0], True, verbose)

            if bm_common_lib.check_fields(buildings, [BLDGHEIGHTfield], False, debug) == 0:
                bm_common_lib.check_null_in_fields(buildings, [BLDGHEIGHTfield], True, debug)

                bm_common_lib.delete_add_field(buildings, ROOFHEIGHTFIELD, "DOUBLE")

                field_value = "!"+BLDGHEIGHTfield+"!-!" + EAVEHEIGHTfield+"! - "  + str(0.1)
                # little extra to make sure we don't get the extra bottom geometry

                arcpy.CalculateField_management(buildings, ROOFHEIGHTFIELD, field_value, "PYTHON_9.3")

                if bm_common_lib.check_null_in_fields(buildings, [ROOFHEIGHTFIELD], True, debug):
                    bm_common_lib.set_null_to_value_in_fields(buildings, [ROOFHEIGHTFIELD], [0], True, debug)

                msg_prefix = "get_roof_height_from_eave_height completed successfully."
                failed = False

                return ROOFHEIGHTFIELD
            else:
                msg_prefix = "get_roof_height_from_eave_height completed successfully."
                failed = False

                return None
        else:
            msg_prefix = "get_roof_height_from_eave_height completed successfully."
            failed = False

            return None

    except:
        line, filename, synerror = trace()
        failed = True
        msg_prefix = ""
        raise FunctionError(
            {
                "function": "get_roof_height_from_eave_height",
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
            if debug == 1:
                msg(msg_body)


def calculate_attribute_even(local_features, check_attribute, debug):

    if debug == 1:
        msg("--------------------------")
        msg("Executing calculate_floorlevel_even...")

    start_time = time.perf_counter()

    try:

        # add even attribute
        bm_common_lib.delete_add_field(local_features, EVENFLOORS, "SHORT")

        with arcpy.da.UpdateCursor(local_features, [check_attribute, EVENFLOORS]) as u_cursor:
            for u_row in u_cursor:
                if u_row[0] % 2 == 0: #even
                    u_row[1] = int(1)
                else:
                    u_row[1] = int(0)

                u_cursor.updateRow(u_row)

        msg_prefix = "Function calculate_floorlevel_even completed successfully."
        failed = False

    except:
        line, filename, synerror = trace()
        failed = True
        msg_prefix = ""
        raise FunctionError(
            {
                "function": "calculate_floorlevel_even",
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
            if debug == 1:
                msg(msg_body)


def split_buildings_into_floors(home_directory,
                                project_ws,
                                scratch_ws,
                                buildings_copy,
                                by_building_type,
                                building_type_table,
                                by_floor_parameters,
                                number_of_floors_attr,
                                ground_floor_height_attr,
                                ground_floor_height,
                                upper_floor_height_attr,
                                upper_floor_height,
                                roof_height_attr,
                                minimum_floor_area,
                                sensitivity,
                                xy_tolerance,
                                force_edge_split,
                                output_features,
                                buffer_value,
                                verbose,
                                in_memory_switch):
    try:
        scripts_directory = home_directory + "\\Scripts"
        rule_directory = home_directory + "\\rule_packages"
        log_directory = home_directory + "\\Logs"
        layer_directory = home_directory + "\\layer_files"

        spliterator_rpk = rule_directory + "\\Spliterator.rpk"
        spliterator_edges_rpk = rule_directory + "\\Spliterator_edges.rpk"
        split_buildings_rpk = rule_directory + "\\Split_Buildings_by_parameters.rpk"
        split_buildings_edges_rpk = rule_directory + "\\Split_Buildings_by_parameters_edges.rpk"
        edges_rpk = ""

        if os.path.exists(layer_directory):
            bm_common_lib.rename_file_extension(layer_directory, ".txt", ".lyrx")

        space_use_field_list = [BUILDINGID, SPACEUSEJOINFIELD, "Tier1SpaceUse", "Tier1NumFloors", "Tier1Color",
                                    "Tier1FloorHeightGround", "Tier1FloorHeightUpper", "Tier2SpaceUse",
                                    "Tier2NumFloors",
                                    "Tier2Color", "Tier2FloorHeight", "Tier3SpaceUse", "Tier3NumFloors",
                                    "Tier3Color", "Tier3FloorHeight", "Tier4SpaceUse", "Tier4NumFloors",
                                    "Tier4Color", "Tier4FloorHeight", "Tier5SpaceUse", "Tier5NumFloors",
                                    "Tier5Color", "Tier5FloorHeight", "Tier6SpaceUse", "Tier6NumFloors",
                                    "Tier6Color", "Tier6FloorHeight", "TopFloorSpaceUse", "TopFloorNumFloors",
                                    "TopFloorColor", "TopFloorFloorHeight", "RoofHeight"]

        space_use_gfa_field_list = ["Tier1SpaceUse", "Tier2SpaceUse", "Tier3SpaceUse", "Tier4SpaceUse",
                                    "Tier5SpaceUse", "Tier6SpaceUse", "Tier1GFA", "Tier2GFA", "Tier3GFA",
                                    "Tier4GFA", "Tier5GFA", "Tier6GFA"]


        space_use_field_list_long = ["Category", "Tier1SpaceUse","Tier1NumFloors","Tier1Type","Tier1Color","Tier1Concept",
                                "Tier1FloorHeightGround","Tier1FloorHeightUpper","Tier1FloorMinDimension","Tier1FloorMinArea","Tier1FloorMaxArea1Height",
                                "Tier1FloorMaxArea1","Tier1FloorMaxArea2Height","Tier1FloorMaxArea2","Tier1FloorMaxArea3Height","Tier1FloorMaxArea3",
                                "Tier1ParkingPerGFA","Tier2SpaceUse","Tier2NumFloors","Tier2Type","Tier2Color","Tier2Concept","Tier2FloorHeight",
                                "Tier2FloorMinDimension","Tier2FloorMinArea","Tier2FloorMaxArea1Height","Tier2FloorMaxArea1","Tier2FloorMaxArea2Height",
                                "Tier2FloorMaxArea2","Tier2FloorMaxArea3Height","Tier2FloorMaxArea3","Tier2ParkingPerGFA","Tier3SpaceUse","Tier3NumFloors",
                                "Tier3Type","Tier3Color","Tier3Concept","Tier3FloorHeight","Tier3FloorMinDimension","Tier3FloorMinArea",
                                "Tier3FloorMaxArea1Height","Tier3FloorMaxArea1","Tier3FloorMaxArea2Height","Tier3FloorMaxArea2","Tier3FloorMaxArea3Height",
                                "Tier3FloorMaxArea3","Tier3ParkingPerGFA","Tier4SpaceUse","Tier4NumFloors","Tier4Type","Tier4Color","Tier4Concept",
                                "Tier4FloorHeight","Tier4FloorMinDimension","Tier4FloorMinArea","Tier4FloorMaxArea1Height","Tier4FloorMaxArea1",
                                "Tier4FloorMaxArea2Height","Tier4FloorMaxArea2","Tier4FloorMaxArea3Height","Tier4FloorMaxArea3","Tier4ParkingPerGFA",
                                "Tier5SpaceUse","Tier5NumFloors","Tier5Type","Tier5Color","Tier5Concept","Tier5FloorHeight","Tier5FloorMinDimension",
                                "Tier5FloorMinArea","Tier5FloorMaxArea1Height","Tier5FloorMaxArea1","Tier5FloorMaxArea2Height","Tier5FloorMaxArea2",
                                "Tier5FloorMaxArea3Height","Tier5FloorMaxArea3","Tier5ParkingPerGFA","Tier6SpaceUse","Tier6NumFloors","Tier6Type",
                                "Tier6Color","Tier6Concept","Tier6FloorHeight","Tier6FloorMinDimension","Tier6FloorMinArea","Tier6FloorMaxArea1Height",
                                "Tier6FloorMaxArea1","Tier6FloorMaxArea2Height","Tier6FloorMaxArea2","Tier6FloorMaxArea3Height","Tier6FloorMaxArea3",
                                "Tier6ParkingPerGFA","TopFloorSpaceUse","TopFloorNumFloors","TopFloorType","TopFloorColor","TopFloorConcept",
                                "TopFloorFloorHeight","TopFloorFloorMinDimension","TopFloorFloorMinArea","TopFloorFloorMaxArea1Height",
                                "TopFloorFloorMaxArea1","TopFloorFloorMaxArea2Height","TopFloorFloorMaxArea2","TopFloorFloorMaxArea3Height",
                                "TopFloorFloorMaxArea3","TopFloorParkingPerGFA","RoofHeight","LandUse"]

        start_time = time.perf_counter()

        # check input exists
        if arcpy.Exists(buildings_copy):
            if bm_common_lib.check_valid_input(buildings_copy, True, ["MultiPatch"], True, True):
                input_type = arcpy.Describe(buildings_copy).shapetype

                if input_type == "MultiPatch":

                    floor_plates = None
                    failed_buildings = None

                    # add unique ID
                    unique_OID = arcpy.Describe(buildings_copy).OIDFieldName

                    if bm_common_lib.check_fields(buildings_copy, [CEREPORTunique_OID_field], False, verbose) == 0:
                        if bm_common_lib.check_null_in_fields(buildings_copy, [CEREPORTunique_OID_field], True, verbose):
                            bm_common_lib.delete_add_field(buildings_copy, CEREPORTunique_OID_field, "LONG")
                            arcpy.CalculateField_management(buildings_copy, CEREPORTunique_OID_field, "!" + unique_OID +
                                                            "!", "PYTHON_9.3")
                    else:
                        bm_common_lib.delete_add_field(buildings_copy, CEREPORTunique_OID_field, "LONG")
                        arcpy.CalculateField_management(buildings_copy, CEREPORTunique_OID_field, "!" + unique_OID + "!",
                                                        "PYTHON_9.3")

                    # calculate footprint area for each building
                    calculate_footprint_area(scratch_ws, buildings_copy, CEREPORTunique_OID_field, verbose)

                    num_buildings = int(arcpy.GetCount_management(buildings_copy).getOutput(0))
                    msg_body = create_msg_body("Creating floors for: " + str(num_buildings) + " buildings.", 0, 0)
                    msg(msg_body)

                    # if no space use table, we are using GroundFloorHeight and UpperfloorHeight for every building
                    msg_body = create_msg_body("Calculating required attributes...", 0, 0)
                    msg(msg_body)

                    # roof attribute is only used when not using BuildingType table because the Building
                    # Type table has a roof attribute
                    if by_building_type is False and by_floor_parameters is True:
                        # check user roofHeight attribute, copy to RoofHeight attribute
                        if len(roof_height_attr) > 0:
                            if bm_common_lib.check_fields(buildings_copy, [roof_height_attr], True, verbose) == 0:
                                if bm_common_lib.check_null_in_fields(buildings_copy, [roof_height_attr], True,
                                                                      verbose):
                                    bm_common_lib.set_null_to_value_in_fields(buildings_copy, [roof_height_attr],
                                                                              [0], True, verbose)
                                    msg_body = ("RoofHeight with NULL values set to 0. These buildings are split "
                                                "to the building height...")
                                    msg(msg_body)

                                if roof_height_attr != ROOFHEIGHTFIELD:
                                    bm_common_lib.delete_add_field(buildings_copy, ROOFHEIGHTFIELD, "DOUBLE")
                                    arcpy.CalculateField_management(buildings_copy, ROOFHEIGHTFIELD, "!" +
                                                                    roof_height_attr + "!", "PYTHON_9.3")

                            else:
                                # check if eaveHeight and TotalHeight are available
                                roof_height_attr = get_roof_height_from_eave_height(scratch_ws, buildings_copy, verbose)

                                if not roof_height_attr:
                                    bm_common_lib.delete_add_field(buildings_copy, ROOFHEIGHTFIELD, "DOUBLE")
                                    arcpy.CalculateField_management(buildings_copy, ROOFHEIGHTFIELD, 0, "PYTHON_9.3")
                                    msg_body = "Can't create RoofHeight attribute. Roofs will not be detected..."
                                    msg(msg_body)
                                else:
                                    msg_body = "Using BLDGHEIGHT and EAVEHEIGHT to calculate RoofHeight..."
                                    msg(msg_body)
                        else:
                            # check if eaveHeight and TotalHeight are available
                            roof_height_attr = get_roof_height_from_eave_height(scratch_ws, buildings_copy, verbose)

                            if not roof_height_attr:
                                bm_common_lib.delete_add_field(buildings_copy, ROOFHEIGHTFIELD, "DOUBLE")
                                arcpy.CalculateField_management(buildings_copy, ROOFHEIGHTFIELD, 0, "PYTHON_9.3")
                                msg_body = "RoofHeight attribute set to 0. Please use a roof height " \
                                           "attribute to detect roofs..."
                                msg(msg_body)
                            else:
                                msg_body = "Using BLDGHEIGHT and EAVEHEIGHT to calculate RoofHeight..."
                                msg(msg_body)

                    # check user NumFloors attribute, copy to NumFloors attribute
                    if len(number_of_floors_attr) > 0:
                        if bm_common_lib.check_fields(buildings_copy, [number_of_floors_attr], True, verbose) == 0:
                            if bm_common_lib.check_null_in_fields(buildings_copy, [number_of_floors_attr],
                                                                  True, verbose):
                                bm_common_lib.set_null_to_value_in_fields(buildings_copy, [number_of_floors_attr],
                                                                          [0], True, verbose)
                                msg_body = "NumFloors with NULL values set to 0. These buildings " \
                                           "are split by floor heights..."
                                msg(msg_body)

                            if number_of_floors_attr != NUMFLOORSFIELD:
                                bm_common_lib.delete_add_field(buildings_copy, NUMFLOORSFIELD, "DOUBLE")
                                arcpy.CalculateField_management(buildings_copy, NUMFLOORSFIELD, "!" +
                                                                number_of_floors_attr + "!", "PYTHON_9.3")
                        else:
                            msg_body = "Can't detect NumFloors attribute. Number of Floors will " \
                                       "not be used in splitting..."
                            msg(msg_body)
                    else:
                        msg_body = "Can't detect NumFloors attribute. Number of Floors will not be " \
                                   "used in splitting..."
                        msg(msg_body)

                    # check user GroundFloorHeight attr, copy to GroundFloorHeight attr
                    # deal with input of . and ,
                    ground_floor_height = re.sub("[,.]", ".", ground_floor_height)
                    if len(ground_floor_height_attr) > 0:
                        if bm_common_lib.check_fields(buildings_copy, [ground_floor_height_attr], True, verbose) == 0:
                            if bm_common_lib.check_null_in_fields(buildings_copy, [ground_floor_height_attr], True,
                                                                  verbose):
                                bm_common_lib.set_null_to_value_in_fields(buildings_copy, [ground_floor_height_attr],
                                                                          [float(ground_floor_height)],
                                                                      True, verbose)
                                msg_body = ("GroundFloorHeight with NULL values set to default value: " +
                                            str(ground_floor_height))
                                msg(msg_body)
                            if ground_floor_height_attr != GROUNDFLOORHEIGHT:
                                bm_common_lib.delete_add_field(buildings_copy, GROUNDFLOORHEIGHT, "DOUBLE")
                                arcpy.CalculateField_management(buildings_copy, GROUNDFLOORHEIGHT, "!" +
                                                                ground_floor_height_attr + "!", "PYTHON_9.3")
                        else:
                            bm_common_lib.delete_add_field(buildings_copy, GROUNDFLOORHEIGHT, "DOUBLE")
                            arcpy.CalculateField_management(buildings_copy, GROUNDFLOORHEIGHT,
                                                            float(ground_floor_height), "PYTHON_9.3", None)
                    else:
                        bm_common_lib.delete_add_field(buildings_copy, GROUNDFLOORHEIGHT, "DOUBLE")
                        arcpy.CalculateField_management(buildings_copy, GROUNDFLOORHEIGHT,
                                                        float(ground_floor_height), "PYTHON_9.3", None)

                    # check user UpperFloorHeight attr, copy to UpperFloorHeight attr
                    # deal with input of . and ,
                    upper_floor_height = re.sub("[,.]", ".", upper_floor_height)
                    if len(upper_floor_height_attr) > 0:
                        if bm_common_lib.check_fields(buildings_copy, [upper_floor_height_attr], True, verbose) == 0:
                            bm_common_lib.check_null_in_fields(buildings_copy, [upper_floor_height_attr], True, verbose)

                            if upper_floor_height_attr != UPPERLOORHEIGHT:
                                bm_common_lib.delete_add_field(buildings_copy, UPPERLOORHEIGHT, "DOUBLE")
                                arcpy.CalculateField_management(buildings_copy, UPPERLOORHEIGHT, "!" +
                                                                upper_floor_height_attr + "!", "PYTHON_9.3")
                        else:
                            bm_common_lib.delete_add_field(buildings_copy, UPPERLOORHEIGHT, "DOUBLE")
                            arcpy.CalculateField_management(buildings_copy, UPPERLOORHEIGHT,
                                                            float(upper_floor_height), "PYTHON_9.3", None)
                    else:
                        bm_common_lib.delete_add_field(buildings_copy, UPPERLOORHEIGHT, "DOUBLE")
                        arcpy.CalculateField_management(buildings_copy, UPPERLOORHEIGHT,
                                                        float(upper_floor_height), "PYTHON_9.3", None)

                    bm_common_lib.delete_add_field(buildings_copy, MINIMUMFLOORAREA, "DOUBLE")
                    arcpy.CalculateField_management(buildings_copy, MINIMUMFLOORAREA,
                                                    float(minimum_floor_area), "PYTHON_9.3", None)

                    # check Z unit
                    z_unit = bm_common_lib.get_z_unit(buildings_copy, verbose)
                    bm_common_lib.delete_add_field(buildings_copy, UNITS, "TEXT")
                    arcpy.CalculateField_management(buildings_copy, UNITS, "'" + z_unit + "'", "PYTHON_9.3", None)

                    # split features based on user input
                    if by_building_type is True and by_floor_parameters is False:
                        # load in building type table
                        if len(building_type_table) > 0:
                            if arcpy.Exists(building_type_table):
                                # parse space use table info

                                if bm_common_lib.check_fields(building_type_table, space_use_field_list,
                                                              True, verbose) == 0:
                                    spaceuse_gdb_table = building_type_table
                                else:
                                    spaceuse_gdb_table = None

                                if spaceuse_gdb_table:
                                    if SPACEUSEJOINFIELD in space_use_field_list:
                                        space_use_field_list.remove(SPACEUSEJOINFIELD)

                                    # check on required field in parcel layer
                                    if bm_common_lib.check_fields(buildings_copy, [SPACEUSEJOINFIELD], False,
                                                                  verbose) == 0:
                                        bm_common_lib.check_null_in_fields(buildings_copy, [SPACEUSEJOINFIELD], True,
                                                                           verbose)

                                        # delete old fields
                                        bm_common_lib.delete_fields(buildings_copy, space_use_gfa_field_list)
                                        results = arcpy.JoinField_management(buildings_copy, SPACEUSEJOINFIELD,
                                                                             spaceuse_gdb_table, SPACEUSEJOINFIELD,
                                                                             space_use_field_list)

                                        if not force_edge_split:
                                            if arcpy.Exists(spliterator_rpk):
                                                floor_plates = split_features(scratch_ws, buildings_copy,
                                                                              spliterator_rpk, verbose)
                                            else:
                                                msg_body = create_msg_body("Can't find " + spliterator_rpk +
                                                                           " rule package in " + rule_directory,
                                                                           0, 0)
                                                msg(msg_body, WARNING)

                                        edges_rpk = spliterator_edges_rpk

                                    else:
                                        msg_body = create_msg_body("Can't find " +SPACEUSEJOINFIELD+ " in " +
                                                                   bm_common_lib.get_name_from_feature_class(buildings_copy)
                                                                   + "!", 0, 0)
                                        msg(msg_body, WARNING)
                                        raise NoID
                                else:
                                    msg_body = create_msg_body("Failed to import " + building_type_table + "!", 0, 0)
                                    msg(msg_body, WARNING)
                                    raise NoTable
                            else:
                                msg_body = create_msg_body("Can't find: " + building_type_table + "!", 0, 0)
                                msg(msg_body, WARNING)
                                raise NoTable

                    elif by_building_type is False and by_floor_parameters is True:
                        if not force_edge_split:
                            if arcpy.Exists(split_buildings_rpk):
                                floor_plates = split_features(scratch_ws, buildings_copy, split_buildings_rpk, verbose)
                            else:
                                msg_body = create_msg_body("Can't find " + spliterator_rpk + " rule package in " +
                                                           rule_directory, 0, 0)
                                msg(msg_body, WARNING)

                        edges_rpk = split_buildings_edges_rpk


                    # CONTINUE HERE
                    # deal with multiple ground floor polys

                    if not force_edge_split:
                        # check for each building if all floor levels have been created
                        num_features = int(arcpy.GetCount_management(floor_plates).getOutput(0))

                        if num_features > 0:
                            failed_building_ids, failed_buildings = get_failed_buildings(scratch_ws,
                                                                                         buildings_copy,
                                                                                         floor_plates,
                                                                                         sensitivity,
                                                                                         verbose)
                        else:
                            msg_body = create_msg_body("Splitting of " +
                                                       bm_common_lib.get_name_from_feature_class(buildings_copy) +
                                                       " failed. Exiting...", 0, 0)
                            msg(msg_body, ERROR)
                            raise NoObjects
                    else:
                        failed_buildings = buildings_copy

                    if failed_buildings:
                        if arcpy.Exists(edges_rpk):
                            # split using edges
                            msg_body = ("Processing failed buildings...")
                            msg(msg_body)

                            floor_plates_edges = split_features_by_edges(scratch_ws,
                                                                         failed_buildings,
                                                                         edges_rpk,
                                                                         z_unit, by_building_type, minimum_floor_area,
                                                                         xy_tolerance, verbose, in_memory_switch)

                            if floor_plates_edges:
                                # turn into multipatches
                                floor_plates_edges_layer = "edges_lyr"
                                arcpy.MakeFeatureLayer_management(floor_plates_edges,
                                                                  floor_plates_edges_layer)

                                if z_unit == "Feet":
                                    edgesSymbologyLayer = layer_directory + "\\edges3Dfeet.lyrx"
                                else:
                                    edgesSymbologyLayer = layer_directory + "\\edges3Dmeters.lyrx"

                                if arcpy.Exists(edgesSymbologyLayer):
                                    arcpy.ApplySymbologyFromLayer_management(floor_plates_edges_layer,
                                                                             edgesSymbologyLayer)
                                else:
                                    raise NoLayerFile

                                out_edges_mp = os.path.join(scratch_ws, "edges_mp")
                                if arcpy.Exists(out_edges_mp):
                                    arcpy.Delete_management(out_edges_mp)

                                arcpy.Layer3DToFeatureClass_3d(floor_plates_edges_layer,
                                                               out_edges_mp)

                                msg_body = ("Merging feature classes...")
                                msg(msg_body)

                                if not force_edge_split:
                                    schemaType = "NO_TEST"
                                    arcpy.Append_management(out_edges_mp, floor_plates, schemaType)
                                else:
                                    floor_plates = out_edges_mp
                            else:
                                msg_body = create_msg_body("Error in splitting of failed buildings with UIDs:" +
                                                           str(failed_building_ids).strip('[]'), 0, 0)
                                msg(msg_body, ERROR)
                        else:
                            msg_body = create_msg_body(
                                "Can't find " + spliterator_edges_rpk + " rule package in " + rule_directory,
                                0, 0)
                            msg(msg_body, WARNING)

                    # add floor viz attribute (even/uneven)
                    calculate_attribute_even(floor_plates, CEREPORTlevel, verbose)

                    # add floor color attribute if not via BuildingType table
                    if by_building_type is False and by_floor_parameters is True:
                        bm_common_lib.delete_add_field(floor_plates, CEREPORTfloorcolor, "TEXT")
                        arcpy.CalculateField_management(floor_plates, CEREPORTfloorcolor, "'#FFFFFF'",
                                                        "PYTHON_9.3", None)

                    floorsDDD = os.path.join(scratch_ws, "floors_3D")
                    if arcpy.Exists(floorsDDD):
                        arcpy.Delete_management(floorsDDD)

                    polygon_floors = os.path.join(scratch_ws, "Floors_AsPolygons")
                    if arcpy.Exists(polygon_floors):
                        arcpy.Delete_management(polygon_floors)

                    arcpy.ddd.MultiPatchFootprint(floor_plates, polygon_floors)

                    if buffer_value != 0:
                        shrunk_floors = os.path.join(scratch_ws, "Floors_shrunk")
                        if arcpy.Exists(shrunk_floors):
                            arcpy.Delete_management(shrunk_floors)

                        if bm_common_lib.get_xy_unit(floor_plates, 0) == "Feet":
                            buffer_text = str(buffer_value) + " Feet"
                        else:
                            buffer_text = str(buffer_value) + " Meters"

                        arcpy.Buffer_analysis(polygon_floors, shrunk_floors, buffer_text, "FULL")

                        arcpy.FeatureTo3DByAttribute_3d(shrunk_floors, floorsDDD, CEREPORTelevation)

                        shrunk_layer = "shrunk_lyr"
                        arcpy.MakeFeatureLayer_management(floorsDDD, shrunk_layer)

                        floorsDDD_mp = os.path.join(scratch_ws, "floors_3D_mp")
                        if arcpy.Exists(floorsDDD_mp):
                            arcpy.Delete_management(floorsDDD_mp)

                        arcpy.Layer3DToFeatureClass_3d(shrunk_layer, floorsDDD_mp, "#", "DISABLE_COLORS_AND_TEXTURES")
                    else:
                        arcpy.FeatureTo3DByAttribute_3d(polygon_floors, floorsDDD, CEREPORTelevation)
                        floorsDDD_mp = floor_plates

                    if arcpy.Exists(output_features):
                        arcpy.Delete_management(output_features)

                    output_features_internal = str(output_features) + "_floors"
                    output_features_internal_polys = str(output_features) + "_floor_polys"

                    if arcpy.Exists(output_features_internal):
                        arcpy.Delete_management(output_features_internal)

                    if arcpy.Exists(output_features_internal_polys):
                        arcpy.Delete_management(output_features_internal_polys)

                    arcpy.CopyFeatures_management(floorsDDD_mp, output_features_internal)
                    arcpy.CopyFeatures_management(floorsDDD, output_features_internal_polys)
                    end_time = time.perf_counter()
                    msg_body = create_msg_body(
                        "Function split_features completed successfully.", start_time, end_time)
                    msg(msg_body)

                    return output_features_internal, output_features_internal_polys
                else:
                    end_time = time.perf_counter()
                    msg_body = create_msg_body("Input " +
                                               bm_common_lib.get_name_from_feature_class(buildings_copy) +
                                               " must be multipatch type. Exiting...!", start_time, end_time)
                    msg(msg_body, ERROR)
                    return None
            else:
                arcpy.AddError("Input data is not valid. Check your data.")
                return None
        else:
            end_time = time.perf_counter()
            msg_body = create_msg_body("Can't find: " +
                                       bm_common_lib.get_name_from_feature_class(buildings_copy) + "!",
                                       start_time, end_time)
            msg(msg_body, WARNING)
            return  None

        # end main code

    except LicenseError3D:
        print("3D Analyst license is unavailable")
        arcpy.AddError("3D Analyst license is unavailable")

    except FoundNullValues:
        print("Found NULL values in UID field. Remove field and rerun...")
        arcpy.AddError("Found NULL values in UID field. Remove field and rerun...")

    except NoTable:
        print("Error with Building Type Table. Exiting...")
        arcpy.AddError("Error with Building Type Table. Exiting...")

    except NoID:
        print("Error with Building Type Name attribute. Exiting...")
        arcpy.AddError("Error with Building Type Attribute Table. Exiting...")

    except NoLayerFile:
        print("Can't find Layer file. Exiting...")
        arcpy.AddError("Can't find Layer file. Exiting...")

    except NoObjects:
        print("No Objects created. Exiting...")
        arcpy.AddError("No Objects created. Exiting...")

    except arcpy.ExecuteError:
        line, filename, synerror = trace(TOOLNAME)
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
        line, filename, synerror = trace(TOOLNAME)
        msg("Error on %s" % line, ERROR)
        msg("Error in file name:  %s" % filename, ERROR)
        msg("with error message:  %s" % synerror, ERROR)

    finally:
        arcpy.CheckInExtension("3D")


def run(home_directory, project_ws, buildings, by_building_type, building_type_table, by_floor_parameters,
        number_of_floors_attr, ground_floor_height_attr, ground_floor_height, upper_floor_height_attr,
        upper_floor_height, roof_height_attr, minimum_floor_area, sensitivity, xy_tolerance,
        force_edge_split, output_features, buffer_value, debug):
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
            start_time = time.perf_counter()

            #  ensure numerical input is correct
            # fail safe for Europe's comma's
            minimum_floor_area = re.sub("[,.]", ".", minimum_floor_area)
            sensitivity = re.sub("[,.]", ".", sensitivity)
            xy_tolerance = re.sub("[,.]", ".", xy_tolerance)

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
                    if arcpy.Exists(buildings):
                        # check if projected coordinates
                        cs_name, cs_vcs_name, is_projected = bm_common_lib.get_cs_info(buildings, 0)

                        if is_projected:

                            buildings_copy = os.path.join(scratch_ws, "buildings_copy")
                            if arcpy.Exists(buildings_copy):
                                arcpy.Delete_management(buildings_copy)

                            # making a copy of the original parcel feature class
                            # let's honor selection
                            arcpy.CopyFeatures_management(buildings, buildings_copy)

                            output_fc, out_fc_polys = split_buildings_into_floors(home_directory,
                                                                                  project_ws,
                                                                                  scratch_ws,
                                                                                  buildings_copy,
                                                                                  by_building_type,
                                                                                  building_type_table,
                                                                                  by_floor_parameters,
                                                                                  number_of_floors_attr,
                                                                                  ground_floor_height_attr,
                                                                                  ground_floor_height,
                                                                                  upper_floor_height_attr,
                                                                                  upper_floor_height,
                                                                                  roof_height_attr,
                                                                                  minimum_floor_area,
                                                                                  sensitivity,
                                                                                  xy_tolerance,
                                                                                  force_edge_split,
                                                                                  output_features,
                                                                                  buffer_value,
                                                                                  verbose,
                                                                                  in_memory_switch)

                            if arcpy.Exists(output_fc):
                                output_layer = bm_common_lib.get_name_from_feature_class(output_fc)

                                arcpy.MakeFeatureLayer_management(output_fc, output_layer)

                                z_unit = bm_common_lib.get_z_unit(buildings, verbose)
                                if z_unit == "Feet":
                                    colorSymbologyLayer = layer_directory + "\\colorFloors_feet.lyrx"
                                else:
                                    colorSymbologyLayer = layer_directory + "\\colorFloors_meters.lyrx"

                                if arcpy.Exists(colorSymbologyLayer):
                                    arcpy.ApplySymbologyFromLayer_management(output_layer, colorSymbologyLayer)
                                else:
                                    msg_body = create_msg_body(
                                        "Can't find" + colorSymbologyLayer + " in " + layer_directory, 0, 0)
                                    msg(msg_body, WARNING)

                                # add the layer to the scene
                                arcpy.SetParameter(16, output_layer)

                                # calculate GFA per usage per building
                                if by_building_type is True:
                                    calculate_gfa(scratch_ws, buildings_copy, output_fc, "tier", verbose)
                                else:
                                    calculate_gfa(scratch_ws, buildings_copy, output_fc, "building", verbose)

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

