import arcpy
import os
import time
import math
import re
import locale
locale.setlocale(locale.LC_ALL, '')

from scripts import bm_common_lib
from scripts.bm_common_lib import create_msg_body, msg, trace


# constants
TOOLNAME = "roof_part_segmentation"
WARNING = "warning"
ERROR = "error"
grouping_field = "PRESEG_FID"
roof_form_field = "ROOFFORM"


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


class SpatialLicenseError(Exception):
    pass


class NoFlat(Exception):
    pass


class NoSegmentOutput(Exception):
    pass


class ProVersionRequired(Exception):
    pass


quick_analysis = True


def convert_areal_units(area_string, map_unit):
    class UnitError(Exception):
        pass

    metric_dict = \
        {'Square Kilometers': 1000000,
         'Hectares': 10000,
         'Ares': 100,
         'Square Meters': 1,
         'Square Decimeters': 0.01,
         'Square Centimeters': 0.0001,
         'Square Millimeters': 0.0000001,
         'Square Miles': 2589988,
         'Acres': 4047,
         'Square Yards': 0.8361,
         'Square Feet': 0.0929,
         'Square Inches': 0.0069}

    map_unit_sq = "Square " + map_unit

    try:
        split_string = area_string.split(" ", 1)
        input_number = float(split_string[0])
        unit = split_string[1]
        if unit in metric_dict.keys():
            output_number = input_number * metric_dict[unit]
        elif unit == "Unknown":
            output_number = input_number * metric_dict[map_unit_sq]
        else:
            raise UnitError

        output_area = str(output_number) + " Square Meters"

        return output_area

    except UnitError:
        arcpy.AddError("Input area unit not recognized")


# Create intermediate gdb workspace
def createIntGDB(path, name):
    intGDB = os.path.join(path, name)
    if not arcpy.Exists(intGDB):
        arcpy.CreateFileGDB_management(path, name, "CURRENT")
        return intGDB
    else:
        return intGDB


# Get Workspace from feature class location
def get_workspace_from_fc(feature_class, get_gdb):
    dir_name = os.path.dirname(arcpy.Describe(feature_class).catalogPath)
    desc = arcpy.Describe(dir_name)

    if hasattr(desc, "datasetType") and desc.datasetType == 'FeatureDataset':
        dir_name = os.path.dirname(dir_name)

    if get_gdb == "yes":
        return dir_name
    else:                   # directory where gdb lives
        return os.path.dirname(dir_name)


# Create Roof-Form Domain
def add_roof_form_domain(in_features):

    in_field = "ROOFFORM"
    fc_fields = [f.name for f in arcpy.ListFields(in_features)]
    if in_field in fc_fields:
        in_gdb = get_workspace_from_fc(in_features, "yes")
        dom_name = "RoofFormTypes"

        dom_desc = arcpy.Describe(in_gdb)
        domains = dom_desc.domains

        if dom_name not in domains:
            arcpy.CreateDomain_management(in_gdb, dom_name, "Valid Roof Form Types", "TEXT", "CODED")

            # Create coded value dictionary
            dom_dict = {"Flat": "Flat", "Shed": "Shed", "Gable": "Gable", "Hip": "Hip", "Mansard": "Mansard",
                        "Dome": "Dome", "Vault": "Vault", "Spherical": "Spherical"}

            # Add coded values to Domain
            for code in dom_dict:
                arcpy.AddCodedValueToDomain_management(in_gdb, dom_name, code, dom_dict[code])

        # Assign domain to features
        arcpy.AssignDomainToField_management(in_features, in_field, dom_name)

    return in_features


def select_fc_within_raster_extent(ws, in_fc, scope_raster, out_fc):
    class NoInputFeatures(Exception):
        pass

    class NoFeaturesInRasterExtent(Exception):
        pass

    try:
        raster_polys = os.path.join(ws, "raster_polygons")
        if arcpy.Exists(raster_polys):
            arcpy.Delete_management(raster_polys)

        if quick_analysis:
            extent = arcpy.Describe(scope_raster).extent.polygon
            arcpy.management.CopyFeatures(extent, raster_polys)
        else:
            out_raster_polygons = os.path.join(ws, "out_raster_polygons")
            if arcpy.Exists(out_raster_polygons):
                arcpy.Delete_management(out_raster_polygons)

            if arcpy.Exists(out_fc):
                arcpy.Delete_management(out_fc)

            isnull_raster = os.path.join(ws, "isnull_raster")
            if arcpy.Exists(isnull_raster):
                arcpy.Delete_management(isnull_raster)

            # find NULL values for raster
            isnull = arcpy.sa.IsNull(scope_raster)

            # isnull.save(isnull_raster)

            arcpy.RasterToPolygon_conversion(isnull, out_raster_polygons, "SIMPLIFY")

            # select polygon that is NOT NULL
            where_notnull = "gridcode = 0"
            arcpy.Select_analysis(out_raster_polygons, raster_polys, where_notnull)

        # Look for selected features
        desc = arcpy.Describe(in_fc)
        input_count = None
        if desc.dataType == "FeatureLayer":
            oid_field = desc.OIDFieldName
            selection = desc.FIDSet
            select_list = selection.split("; ")
            if len(selection) > 0:
                select_list_num = [int(i) for i in select_list]
                if len(select_list_num) == 1:
                    where_clause = " = {0}".format(select_list_num[0])
                else:
                    where_clause = " IN {0}".format(str(tuple(select_list_num)))
                # check number of input features
                input_layer = "input_lyr"
                arcpy.MakeFeatureLayer_management(in_fc, input_layer, "{0}{1}".format(oid_field, where_clause))
                result = arcpy.GetCount_management(input_layer)
                input_count = int(result.getOutput(0))
            else:
                result = arcpy.GetCount_management(in_fc)
                input_count = int(result.getOutput(0))

                input_layer = "input_lyr"
                in_fc = bm_common_lib.get_full_path_from_layer(in_fc)
                arcpy.MakeFeatureLayer_management(in_fc, input_layer)
                # input_layer = in_fc
        else:
            # check number of input features
            input_layer = "input_lyr"
            arcpy.MakeFeatureLayer_management(in_fc, input_layer)
            result = arcpy.GetCount_management(input_layer)
            input_count = int(result.getOutput(0))

        if input_count == 0:
            raise NoInputFeatures

        # Select all footprints that are within the DSM polygon
        arcpy.SelectLayerByLocation_management(input_layer, "within", raster_polys)

        # Set the outputZFlag environment to Disabled
        arcpy.env.outputZFlag = "Disabled"

        # Write the selected features to a new featureclass
        arcpy.CopyFeatures_management(input_layer, out_fc)

        select_layer2 = "select_lyr2"
        arcpy.MakeFeatureLayer_management(out_fc, select_layer2)

        result = arcpy.GetCount_management(select_layer2)
        select_count = int(result.getOutput(0))

        if select_count == 0:
            raise NoFeaturesInRasterExtent

        arcpy.AddMessage("- {0} features of the {1} will be processed based on the available raster extent."
                         .format(str(select_count), str(input_count)))

        return out_fc

    # Return geoprocessing specific errors
    except arcpy.ExecuteWarning:
        print((arcpy.GetMessages(1)))
        arcpy.AddError(arcpy.GetMessages(1))

    except arcpy.ExecuteError:
        print((arcpy.GetMessages(2)))
        arcpy.AddError(arcpy.GetMessages(2))

    except NoFeaturesInRasterExtent:
        arcpy.AddError("No input features found within input raster extent")

    except NoInputFeatures:
        arcpy.AddError("Input feature class is empty")


def group_slope_areas(clipped_dsm, clipped_slope, output_dsm, min_slope, max_slope, number):
    if arcpy.Exists(output_dsm):
        arcpy.Delete_management(output_dsm)

    # Calculate sloped areas
    arcpy.AddMessage("- creating slope rasters")

    slope_ras = arcpy.sa.Raster(clipped_slope)
    # slope_areas_save = os.path.join(workspace, "slope_areas")
    slope_areas = arcpy.sa.Con(slope_ras, 1, 0, where_clause="VALUE >= {0} And VALUE <= {1}".format(str(min_slope),
                                                                                                    str(max_slope)))
    slope_breaks = arcpy.sa.Con(slope_ras, 1, 0, where_clause="VALUE > {0}".format(str(max_slope)))
    # slope_areas.save(slope_areas_save)

    # Shrink raster
    arcpy.AddMessage("- shrinking slope raster")
    slope_shrink_1 = arcpy.sa.Shrink(slope_areas, 2, 1)

    if slope_shrink_1.maximum > 0:
        # Grow raster
        arcpy.AddMessage("- growing slope raster")
        slope_grow = arcpy.sa.Expand(slope_shrink_1, 3, 1)

        # Set high slope areas to 0
        slope_groups = arcpy.sa.Con(slope_breaks, 0, slope_grow, "VALUE = 1")

        if slope_groups.maximum > 0:
            # Set 0 areas to null
            slope_groups_iso = arcpy.sa.SetNull(slope_groups, slope_groups, "VALUE = 0")

            # Region group
            region_group = arcpy.sa.RegionGroup(slope_groups_iso)
            # region_group.save(os.path.join(gdb, "region_group" + str(number)))

            # zonal statistics
            arcpy.AddMessage("- calculating slope raster statistics")
            slope_stat = arcpy.sa.ZonalStatistics(region_group, "VALUE", clipped_dsm, "MEAN")
            # slope_stat.save(os.path.join(gdb, "slope_group_stat" + str(number)))

            # Burn slope areas into input DSM
            dsm_ras = arcpy.sa.Raster(clipped_dsm)
            dsm_burn = arcpy.sa.Con(arcpy.sa.IsNull(slope_stat), dsm_ras, slope_stat)
            dsm_burn.save(output_dsm)

        else:
            arcpy.CopyRaster_management(clipped_dsm, output_dsm)

    else:
        arcpy.CopyRaster_management(clipped_dsm, output_dsm)

    return output_dsm


def create_segment_polygons(footprints, dsm, slope_ras, spectral_detail, spatial_detail, min_segment_size,
                            lc_segments, ws, number, minimum_slope, home_folder, flat_only):

    gdb = createIntGDB(home_folder, "Analysis.gdb")
    extent_param = "NO_MAINTAIN_EXTENT"

    # Clip DSM raster to building footprints
    arcpy.AddMessage("- Clipping raster to building extents")
    clip_dsm = os.path.join(gdb, 'clip_dsm')
    clip_slope = os.path.join(gdb, 'clip_slope')
    if arcpy.Exists(clip_dsm):
        arcpy.Delete_management(clip_dsm)

    arcpy.Clip_management(in_raster=dsm, rectangle='#', out_raster=clip_dsm, in_template_dataset=footprints,
                          clipping_geometry='ClippingGeometry', maintain_clipping_extent=extent_param)

    if not flat_only:
        if arcpy.Exists(clip_slope):
            arcpy.Delete_management(clip_slope)
        slope_group_dsm = os.path.join(gdb, "slope_group_dsm")  # + str(number))
        arcpy.Clip_management(in_raster=slope_ras, rectangle='#', out_raster=clip_slope, in_template_dataset=footprints,
                              clipping_geometry='ClippingGeometry', maintain_clipping_extent=extent_param)
        group_slope_areas(clip_dsm, clip_slope, slope_group_dsm, minimum_slope, 60, number)
        clip_dsm = slope_group_dsm

    arcpy.AddMessage("- Segmenting clipped raster")

    # Run segment mean shift on clipped DSM
    sms_dsm = os.path.join(gdb, 'sms_dsm')
    if arcpy.Exists(sms_dsm):
        arcpy.Delete_management(sms_dsm)

    try:
        seg_raster = arcpy.sa.SegmentMeanShift(clip_dsm, spectral_detail, spatial_detail, min_segment_size)
        seg_raster.save(sms_dsm)
        arcpy.Delete_management(clip_dsm)
        success = True
    except:
        success = False

    if success:
        # Raster to polygon
        arcpy.AddMessage("- Polygonizing segments")
        sms_poly = os.path.join(ws, 'sms_poly')
        if arcpy.Exists(sms_poly):
            arcpy.Delete_management(sms_poly)
        arcpy.RasterToPolygon_conversion(in_raster=sms_dsm, out_polygon_features=sms_poly, simplify='NO_SIMPLIFY')

        poly_select = "poly_select"
        arcpy.MakeFeatureLayer_management(sms_poly, poly_select, "gridcode <> 0")

        if arcpy.Exists(lc_segments):
            arcpy.Delete_management(lc_segments)

        # Copy selection to output
        arcpy.CopyFeatures_management(poly_select, lc_segments)

        return lc_segments
    else:
        return None


def process_segments(segments, footprints, min_poly_size, reg_tolerance,
                     group_field, sms_poly_reg, fail_list,
                     workspace):

    # Eliminate small polygons
    # Select all small polygons to be eliminated
    ws = os.path.dirname(segments)
    if ws == "memory":
        area_field_name = "geom_area"
        arcpy.AddField_management(segments, area_field_name, "DOUBLE")
        arcpy.CalculateField_management(segments, area_field_name, "!shape.area!", "PYTHON_9.3")
    else:
        area_field_name = arcpy.Describe(segments).areaFieldName
    arcpy.MakeFeatureLayer_management(segments, "elim_select")
    area_selection = "{0} < {1}".format(area_field_name, str(min_poly_size))
    # arcpy.AddMessage("- area selection = " + area_selection)
    arcpy.SelectLayerByAttribute_management("elim_select", "NEW_SELECTION", area_selection)

    # Eliminate small polygons
    arcpy.AddMessage("- Merging small segments with larger neighbors")
    sms_poly_elim = os.path.join(workspace, "sms_poly_elim")

    arcpy.Eliminate_management("elim_select", sms_poly_elim)

    # spatial join group id to segments
    arcpy.AddMessage("- Joining unique ID to segment polygons")
    sms_poly_join = os.path.join(workspace, 'sms_poly_join')
    arcpy.SpatialJoin_analysis(sms_poly_elim, footprints, sms_poly_join, join_type='KEEP_COMMON',
                               match_option='HAVE_THEIR_CENTER_IN')

    # Regularize adjacent building footprints
    arcpy.AddMessage("- Regularizing segments. This step may take some time depending on size"
                     " of the input data.")
    start_time = time.time()

    # set regularize env settings
    arcpy.env.parallelProcessingFactor = "75%"
    precision = 0.25

    arcpy.RegularizeAdjacentBuildingFootprint_3d(sms_poly_join, group_field, sms_poly_reg,
                                                 'RIGHT_ANGLES_AND_DIAGONALS', tolerance=reg_tolerance,
                                                 precision=precision)

    arcpy.ClearEnvironment("parallelProcessingFactor")

    # Create list of features that failed regularization, and delete them
    if len(arcpy.ListFields(sms_poly_reg, "STATUS")) > 0:
        with arcpy.da.UpdateCursor(sms_poly_reg, ["STATUS", grouping_field]) as u_cur:
            for row in u_cur:
                if row[0] == 1:
                    if row[1] not in fail_list:
                        fail_list.append(row[1])
                    u_cur.deleteRow()

    end_time = time.time()
    time_diff = int(end_time - start_time)
    arcpy.AddMessage("- Segments regularized in {0} seconds.".format(str(time_diff)))

    return sms_poly_reg


def create_grids(start_x, start_y, cell_size_x, cell_size_y, rows, columns, spatial_ref, output_grids):
    grid_path = os.path.dirname(output_grids)
    grid_name = os.path.basename(output_grids)
    arcpy.CreateFeatureclass_management(grid_path, grid_name, "POLYGON", spatial_reference=spatial_ref)

    with arcpy.da.InsertCursor(output_grids, "SHAPE@") as i_cur:
        for r in range(0, rows):
            min_y = start_y + (r * cell_size_y)
            for c in range(0, columns):
                bottom_left = arcpy.Point(start_x + (c * cell_size_x), min_y)
                bottom_right = arcpy.Point(start_x + (c * cell_size_x) + cell_size_x, min_y)
                top_right = arcpy.Point(start_x + (c * cell_size_x) + cell_size_x, min_y + cell_size_y)
                top_left = arcpy.Point(start_x + (c * cell_size_x), min_y + cell_size_y)

                array = arcpy.Array([bottom_left, bottom_right, top_right, top_left])

                grid = arcpy.Polygon(array)

                i_cur.insertRow([grid])

    return output_grids


# Segment in batches of a set size to avoid decrease in output resolution
def batch_segment(in_features, min_grid_size_meters, dsm, spectral_detail, spatial_detail, min_segment_size,
                  seg_poly_fc, minimum_slope, workspace, home_folder, flat_only, in_memory_switch,
                  scratch_ws):

    desc = arcpy.Describe(in_features)
    spatial_ref = desc.spatialReference
    meters_per_unit = spatial_ref.metersPerUnit

    continue_processing = False
    slope_ras = os.path.join(workspace, "slope_ras")
    if not flat_only:
        try:
            arcpy.Slope_3d(dsm, slope_ras, "DEGREE")
            continue_processing = True
        except:
            continue_processing = False
    else:
        continue_processing = True

    if continue_processing:
        features_to_process = in_features

        # Check for selection
        if desc.dataType == "FeatureLayer":
            if len(desc.FIDSet) > 0:
                features_to_process = "memory/extent_features"
                arcpy.AddMessage("- Copying input features...")
                arcpy.CopyFeatures_management(in_features, features_to_process)
                desc = arcpy.Describe(features_to_process)

        # Get extent of input features
        extent = desc.extent
        max_x = extent.XMax
        max_y = extent.YMax
        min_x = extent.XMin
        min_y = extent.YMin

        width = max_x - min_x
        height = max_y - min_y

        width_m = width * meters_per_unit
        height_m = height * meters_per_unit

        width_div = 1
        height_div = 1

        if width_m > min_grid_size_meters:
            width_div = math.floor(width_m/min_grid_size_meters)
        if height_m > min_grid_size_meters:
            height_div = math.floor(height_m/min_grid_size_meters)

        # Run segmentation in batches if extent dimensions exceed batch size
        if width_div > 1 or height_div > 1:
            arcpy.AddMessage("- Batch segmenting input data due to large extent")

            # Create grids for processing
            grid_size_x = width/width_div
            grid_size_y = height/height_div

            if in_memory_switch:
                batch_grids = os.path.join("memory", "batch_grids")
            else:
                batch_grids = os.path.join(scratch_ws, "batch_grids")
                if arcpy.Exists(batch_grids):
                    arcpy.Delete_management(batch_grids)

            create_grids(min_x, min_y, grid_size_x, grid_size_y, height_div, width_div, spatial_ref, batch_grids)

            # Create merge segments
            out_path = os.path.dirname(seg_poly_fc)
            out_name = os.path.basename(seg_poly_fc)
            arcpy.CreateFeatureclass_management(out_path, out_name, "POLYGON", "", "DISABLED", "DISABLED",
                                                spatial_ref)
            arcpy.AddField_management(seg_poly_fc, "gridcode", "LONG")
            arcpy.AddField_management(seg_poly_fc, "Id", "LONG")

            # Create centroid points for input features
            fp_centroids = "memory/fp_centroids"
            arcpy.FeatureToPoint_management(features_to_process, fp_centroids, "CENTROID")

            # Select grids that contain input centroids
            grid_select = "grid_select"
            arcpy.MakeFeatureLayer_management(batch_grids, grid_select)
            arcpy.SelectLayerByLocation_management(grid_select, "INTERSECT", fp_centroids)

            selection = arcpy.Describe(grid_select).FIDSet
            select_list = selection.split("; ")
            select_count = len(select_list)

            # Process each grid cell
            index = 1
            with arcpy.da.SearchCursor(grid_select, "SHAPE@") as cursor:
                for row in cursor:
                    arcpy.AddMessage("- Processing batch grid {0} of {1}".format(str(index), str(select_count)))
                    out_batch_segments = os.path.join(workspace, "out_seg" + str(index))

                    # Select footprints within grid extent
                    shape = row[0]
                    fp_select = "fp_select"
                    arcpy.MakeFeatureLayer_management(features_to_process, fp_select)

                    arcpy.SelectLayerByLocation_management(fp_select, "HAVE_THEIR_CENTER_IN", shape)

                    if not in_memory_switch:
                        select_grid = os.path.join(scratch_ws, "select_grid")
                        if arcpy.Exists(select_grid):
                            arcpy.Delete_management(select_grid)

                        arcpy.CopyFeatures_management(fp_select, select_grid)

                    out_batch_segments = create_segment_polygons(fp_select, dsm, slope_ras, spectral_detail,
                                                                 spatial_detail, min_segment_size,
                                                                 out_batch_segments, workspace, index,
                                                                 minimum_slope, home_folder, flat_only)

                    if out_batch_segments:
                        arcpy.Append_management(out_batch_segments, seg_poly_fc)
                        arcpy.Delete_management(out_batch_segments)
                    else:
                        arcpy.AddWarning("Segment Mean Shift failed for batch grid {0}. Original polygons will be "
                                         "used for this batch.".format(str(index)))

                    index += 1

        else:
            create_segment_polygons(features_to_process, dsm, slope_ras, spectral_detail, spatial_detail,
                                    min_segment_size,
                                    seg_poly_fc, workspace, 1, minimum_slope, home_folder, flat_only)
    else:
        arcpy.AddError("Error in creating slope raster.")


def snap_line_endpoints(lines, snap_features, tolerance, ws):
    # Create line endpoints
    arcpy.AddMessage("- Snapping endpoints to original footprints")
    spatial_ref = arcpy.Describe(lines).spatialReference
    endpoints = os.path.join(ws, "endpoints")
    arcpy.CreateFeatureclass_management(ws, "endpoints", "POINT", "", "DISABLED", "DISABLED", spatial_ref)
    arcpy.AddFields_management(endpoints, [["orig_id", "LONG", None, None, None], ["position", "TEXT", None, 8, None]])
    with arcpy.da.SearchCursor(lines, ["SHAPE@", "OID@"]) as line_cur:
        with arcpy.da.InsertCursor(endpoints, ["SHAPE@", "orig_id", "position"]) as point_cur:
            for row in line_cur:
                shape = row[0]
                oid = row[1]
                first_point = shape.firstPoint
                last_point = shape.lastPoint
                if first_point != last_point:
                    point_cur.insertRow([first_point, oid, "first"])
                    point_cur.insertRow([last_point, oid, "last"])

    # Snap endpoints to snap features
    arcpy.Snap_edit(endpoints, [[snap_features, "EDGE", tolerance]])    # [[snap_features, "VERTEX", tolerance],
                                                                        # [snap_features, "EDGE", tolerance]])

    # Replace line endpoints with snapped points
    first_dict = {}
    last_dict = {}
    with arcpy.da.SearchCursor(endpoints, ["SHAPE@", "orig_id", "position"]) as s_cur:
        for item in s_cur:
            if item[2] == "first":
                first_dict[item[1]] = item[0].centroid
            else:
                last_dict[item[1]] = item[0].centroid

    with arcpy.da.UpdateCursor(lines, ["SHAPE@", "OID@"]) as u_cur:
        for row in u_cur:
            if row[1] in first_dict.keys():
                for part in row[0]:
                    part.replace(0, first_dict[row[1]])
                    part.replace(part.count - 1, last_dict[row[1]])
                    row[0] = arcpy.Polyline(part)

                u_cur.updateRow(row)


def integrate_segment_breaklines(input_segments, buildings, lc_segments, tolerance, workspace):

    arcpy.AddMessage("- Creating segment breaklines")

    # Convert segments to lines
    rough_segment_lines = os.path.join(workspace, "rough_segment_lines")
    if arcpy.Exists(rough_segment_lines):
        arcpy.Delete_management(rough_segment_lines)
    arcpy.PolygonToLine_management(input_segments, rough_segment_lines)

    # Select lines representing shared borders
    breaklines = os.path.join(workspace, "breaklines")
    if arcpy.Exists(breaklines):
        arcpy.Delete_management(breaklines)
    arcpy.Select_analysis(rough_segment_lines, breaklines, "\"LEFT_FID\" > -1")

    # Convert Buildings to line
    footprint_lines = os.path.join(workspace, "footprint_lines")
    if arcpy.Exists(footprint_lines):
        arcpy.Delete_management(footprint_lines)
    arcpy.PolygonToLine_management(buildings, footprint_lines)

    # Snap break lines to footprints
    snap_line_endpoints(breaklines, footprint_lines, tolerance, workspace)

    arcpy.AddMessage("- Recreating footprints to include breaklines")
    # Merge break lines and footprint lines
    clean_segment_lines = os.path.join(workspace, "clean_segment_lines")
    if arcpy.Exists(clean_segment_lines):
        arcpy.Delete_management(clean_segment_lines)
    arcpy.Merge_management([footprint_lines, breaklines], clean_segment_lines)

    # Convert segment lines to polygon
    if arcpy.Exists(lc_segments):
        arcpy.Delete_management(lc_segments)
    arcpy.FeatureToPolygon_management(clean_segment_lines, lc_segments)

    # Delete polygons outside original extent
    arcpy.MakeFeatureLayer_management(lc_segments, "delete_lyr")

    arcpy.SelectLayerByLocation_management("delete_lyr", "WITHIN", buildings, invert_spatial_relationship="INVERT")

    arcpy.DeleteFeatures_management("delete_lyr")

    return lc_segments


def segment_roof_parts(project_ws, footprints, dsm, spectral_detail, spatial_detail, min_segment_size, reg_tolerance,
                       minimum_slope, output_fc, group_field, in_memory_switch, scratch_ws, flat_only,
                       home_folder):
    try:
        if in_memory_switch:
            workspace = "memory"
        else:
            workspace = scratch_ws

        fail_list = []

        # Get minimum area for output polygons
        # Identify area of each cell
        dsm_desc = arcpy.Describe(dsm)
        m_per_unit = dsm_desc.spatialReference.metersPerUnit
        unit_per_meter = 1 / m_per_unit
        cell_x = arcpy.GetRasterProperties_management(dsm, "CELLSIZEX").getOutput(0)
        cell_y = arcpy.GetRasterProperties_management(dsm, "CELLSIZEY").getOutput(0)

        cell_x = float(re.sub("[,.]", ".", cell_x))
        cell_y = float(re.sub("[,.]", ".", cell_y))

        cell_size = (float(cell_x) * m_per_unit) * (float(cell_y) * m_per_unit)  # Cell size in square meters
        # Identify min area of segments
        min_poly_size = cell_size * min_segment_size * (unit_per_meter * unit_per_meter)

        extent_param = "NO_MAINTAIN_EXTENT"

        orig_footprints = footprints

        if flat_only:
            flat_num = 0
            with arcpy.da.SearchCursor(footprints, "ROOFFORM") as cursor:
                for row in cursor:
                    if row[0] == 'Flat':
                        flat_num += 1
            if flat_num == 0:
                raise NoFlat

        # Calculate unique id
        arcpy.AddMessage("- Calculating unique ID of footprints")
        fp_desc = arcpy.Describe(footprints)
        oid = fp_desc.OIDFieldName

        # Create a copy of selection if it exists
        copy_fp = os.path.join(scratch_ws, "copy_fp")
        if fp_desc.dataType == "FeatureLayer":
            footprint_fc = fp_desc.catalogPath
            if len(arcpy.ListFields(footprint_fc, group_field)) == 0:
                arcpy.AddField_management(footprints, group_field, 'TEXT')

            arcpy.CalculateField_management(footprint_fc, group_field, '!{0}!'.format(oid), 'PYTHON3')

            # Create a copy feature class if a selection exists
            if len(fp_desc.FIDSet) > 0:
                if arcpy.Exists(copy_fp):
                    arcpy.Delete_management(copy_fp)
                arcpy.CopyFeatures_management(footprints, copy_fp)
                footprints = copy_fp
                fp_desc = arcpy.Describe(copy_fp)

        else:
            if len(arcpy.ListFields(footprints, group_field)) == 0:
                arcpy.AddField_management(footprints, group_field, 'TEXT')

            arcpy.CalculateField_management(footprints, group_field, '!{0}!'.format(oid), 'PYTHON3')

        # Select only flat roofs to be processed
        non_flat_lyr = "other_lyr"
        flat_fc = os.path.join(workspace, "flat_roofs")

        if flat_only:
            arcpy.AddMessage("- Selecting all flat roofs to process")
            flat_lyr = "flat_lyr"
            arcpy.MakeFeatureLayer_management(footprints, flat_lyr, "{0} = 'Flat'".format(roof_form_field))
            if arcpy.Exists(flat_fc):
                arcpy.Delete_management(flat_fc)
            arcpy.CopyFeatures_management(flat_lyr, flat_fc)

            # Select all other features to merge at the end
            arcpy.MakeFeatureLayer_management(footprints, non_flat_lyr, "{0} <> 'Flat'".format(roof_form_field))

            footprints = flat_lyr
            fp_desc = arcpy.Describe(flat_fc)

        arcpy.AddMessage("- Selecting footprints within valid DSM values")
        footprints_in_dsm = os.path.join(workspace, "footprints_in_dsm")
        select_fc_within_raster_extent(workspace, footprints, dsm, footprints_in_dsm)

        fp_desc = arcpy.Describe(footprints_in_dsm)

        # Clip DSM to footprint extent - write to gdb instead of memory
        if 1:   # optimize later...
            arcpy.AddMessage("- Clipping DSM to footprint extent")
            dsm_clip = os.path.join(scratch_ws, "dsm_clip")
            if arcpy.Exists(dsm_clip):
                arcpy.Delete_management(dsm_clip)

            fp_extent = fp_desc.extent
            fp_envelope = "{0} {1} {2} {3}".format(fp_extent.XMin - 10, fp_extent.YMin - 10, fp_extent.XMax + 10,
                                                   fp_extent.YMax + 10)
            arcpy.Clip_management(dsm, rectangle=fp_envelope, out_raster=dsm_clip, maintain_clipping_extent=extent_param)
        else:
            dsm_clip = dsm

        # Burn minimum building elevation into DSM
        if flat_only:
            arcpy.AddMessage("- Subtracting building base elevation from DSM")
            # rasterize building base elevation
            base_field = "BASEELEV"
            base_elev_ras = os.path.join(workspace, "base_elev_ras")
            arcpy.env.snapRaster = dsm_clip
            arcpy.env.cellSize = dsm_clip
            fp_lyr = "fp_lyr"
            arcpy.MakeFeatureLayer_management(footprints_in_dsm, fp_lyr)
            arcpy.FeatureToRaster_conversion(fp_lyr, base_field, base_elev_ras)

            # Substract base elevation from DSM
            dsm_burn = os.path.join(workspace, "dsm_burn")
            dsm_subtract = arcpy.sa.Minus(dsm_clip, base_elev_ras)
            dsm_subtract.save(dsm_burn)

            dsm = dsm_burn

        arcpy.AddMessage("- Starting batch processing...")
        rough_segments = os.path.join(workspace, "rough_segments")
        batch_segment(footprints_in_dsm, 1000, dsm_clip, spectral_detail, spatial_detail, min_segment_size,
                      rough_segments, minimum_slope, workspace, home_folder, flat_only, in_memory_switch,
                      scratch_ws)

        if arcpy.Exists(rough_segments):
            result = arcpy.GetCount_management(rough_segments)
            input_count = int(result.getOutput(0))

            if input_count > 0:

                # Regularize segments
                reg_segments = os.path.join(workspace, "reg_segments")
                process_segments(rough_segments, footprints_in_dsm, min_poly_size, reg_tolerance, grouping_field,
                                 reg_segments, fail_list, workspace)

                clean_segments = os.path.join(workspace, "clean_segments")
                integrate_segment_breaklines(reg_segments, footprints_in_dsm, clean_segments, reg_tolerance, workspace)

                union_fc = os.path.join(workspace, "union_fc")
                arcpy.Union_analysis([footprints_in_dsm, clean_segments], union_fc, "NO_FID")

                # Eliminate small polygons
                # Select all small polygons to be eliminated
                if os.path.dirname(union_fc) == "memory":
                    area_field_name = "geom_area"
                    if not bm_common_lib.field_exist(union_fc, area_field_name):
                        arcpy.AddField_management(union_fc, area_field_name, "DOUBLE")
                    arcpy.CalculateField_management(union_fc, area_field_name, "!shape.area!", "PYTHON_9.3")
                else:
                    area_field_name = arcpy.Describe(union_fc).areaFieldName
                arcpy.MakeFeatureLayer_management(union_fc, "elim_select")
                area_selection = "{0} < {1}".format(area_field_name, str(min_poly_size))
                arcpy.SelectLayerByAttribute_management("elim_select", "NEW_SELECTION", area_selection)

                # Eliminate small polygons
                arcpy.AddMessage("- Merging small segments with larger neighbors")

                arcpy.Eliminate_management("elim_select", output_fc)

                if area_field_name == "geom_area":
                    arcpy.DeleteField_management(output_fc, area_field_name)

                # Append non-flat features
                if flat_only:
                    arcpy.AddMessage("- Updating roof height")
                    segID = "segID"
                    arcpy.AddField_management(output_fc, segID, "LONG")
                    arcpy.CalculateField_management(output_fc, segID, "!{0}!".format(oid))
                    height_table = os.path.join("memory", "height_table")
                    arcpy.sa.ZonalStatisticsAsTable(output_fc, segID, dsm_clip, height_table, 'DATA', 'MEAN')
                    arcpy.TableToTable_conversion(height_table, scratch_ws, "height_table")

                    arcpy.JoinField_management(output_fc, segID, height_table, segID, ["MEAN"])
                    arcpy.CalculateField_management(output_fc, "BLDGHEIGHT", "!MEAN!", "PYTHON3")
                    arcpy.DeleteField_management(output_fc, "MEAN")
                    arcpy.DeleteField_management(output_fc, segID)

                    # Append non-flat features
                    arcpy.Append_management(non_flat_lyr, output_fc)

                    if arcpy.Exists(flat_fc):
                        arcpy.Delete_management(flat_fc)

                # Apply roof form domain if field exists
                add_roof_form_domain(output_fc)

                if arcpy.Exists(copy_fp):
                    arcpy.Delete_management(copy_fp)

                arcpy.env.workspace = scratch_ws

                sms_remnant_list = arcpy.ListRasters("*_interIndex")
                file_remnants = [os.path.join(scratch_ws, f) for f in sms_remnant_list]
                for file in file_remnants:
                    arcpy.Delete_management(file)

                file_remnants = [os.path.join(project_ws, f) for f in sms_remnant_list]
                for file in file_remnants:
                    arcpy.Delete_management(file)

                # add symbology and add layer to TOC
                output_layer = bm_common_lib.get_name_from_feature_class(output_fc)  # + "_segmented"
                arcpy.MakeFeatureLayer_management(output_fc, output_layer)

                z_unit = bm_common_lib.get_z_unit(output_fc, 0)

                layer_directory = os.path.join(home_folder, "layer_files")

                if z_unit == "Feet":
                    SymbologyLayer = layer_directory + "\\LOD2BuildingShells_feet.lyrx"
                else:
                    SymbologyLayer = layer_directory + "\\LOD2BuildingShells_meters.lyrx"

                if flat_only:
                    if arcpy.Exists(SymbologyLayer):
                        arcpy.ApplySymbologyFromLayer_management(output_layer, SymbologyLayer)
                    else:
                        msg_body = create_msg_body("Can't find" + SymbologyLayer + " in " + layer_directory, 0, 0)
                        msg(msg_body, WARNING)

                # add the layer to the scene
                arcpy.SetParameter(9, output_layer)

                if bm_common_lib.is_layer(orig_footprints) == 1:
                    arcpy.SelectLayerByAttribute_management(orig_footprints, "CLEAR_SELECTION")

                arcpy.Delete_management("memory")

                return output_fc
            else:
                arcpy.AddError("Error in segmenting footprints. Please reduce the size input footprints and DSM.")
                return None
        else:
            arcpy.AddError("Error in segmenting footprints. Please reduce the size input footprints and DSM.")
            return None

    except NoFlat:
        print("No buildings attributed with 'ROOFORM' = 'Flat' in the input")
        arcpy.AddError("No buildings attributed with 'ROOFORM' = 'Flat' in the input")

    except NoSegmentOutput:
        print("Error creating output.")
        arcpy.AddError("Error creating output.")

    finally:
        if fail_list:
            if len(fail_list) > 0:
                f_list_str = [str(i) for i in fail_list]
                arcpy.AddWarning("{0} input features failed to be regularized due to overly complex segmentation.\n"
                                 "These output features will be identical to their inputs.\n"
                                 "The input OIDs of these features are: {1})"
                                 .format(str(len(fail_list)), ', '.join(f_list_str)))


def run(home_directory, project_ws,
        features, dsm, spectral_detail, spatial_detail, minimum_segment_size,
        regularization_tolerance, flat_only, min_slope, output_segments_ui, debug):
    try:
        if debug == 1:
            delete_intermediate_data = True
            verbose = 1
            in_memory_switch = False
        else:
            delete_intermediate_data = True
            verbose = 0
            in_memory_switch = True

        pro_version = arcpy.GetInstallInfo()['Version']
        if (int(pro_version[0]) >= 2 and int(pro_version[2]) >= 2) or int(pro_version[0]) >= 3:
            arcpy.AddMessage("ArcGIS Pro version: " + pro_version)
        else:
            raise ProVersionRequired

        output_segments = output_segments_ui + "_segmented"

        # fail safe for Europese's comma's
        spectral_detail = float(re.sub("[,.]", ".", spectral_detail))
        spatial_detail = float(re.sub("[,.]", ".", spatial_detail))
        regularization_tolerance = re.sub("[,.]", ".", regularization_tolerance)

        if os.path.exists(os.path.join(home_directory, "p20")):      # it is a package
            home_directory = os.path.join(home_directory, "p20")

        arcpy.AddMessage("Project Home Directory is: " + home_directory)

        for a in home_directory:
            if a.isspace():
                raise HasSpace

        if bm_common_lib.check_directory(home_directory):
            # set directories

            log_directory = os.path.join(home_directory, "Logs")
            if not os.path.exists(log_directory):
                os.makedirs(log_directory)

            bm_common_lib.set_up_logging(log_directory, TOOLNAME)

            # rename layer files (for packaging)
            layer_directory = os.path.join(home_directory, "layer_files")
            if os.path.exists(layer_directory):
                bm_common_lib.rename_file_extension(layer_directory, ".txt", ".lyrx")

            scratch_ws = bm_common_lib.create_gdb(home_directory, "Intermediate.gdb")
            arcpy.env.workspace = scratch_ws
            arcpy.env.overwriteOutput = True

            if arcpy.CheckExtension("3D") == "Available":
                arcpy.CheckOutExtension("3D")

                if arcpy.CheckExtension("Spatial") == "Available":
                    arcpy.CheckOutExtension("Spatial")

                    output_fc = segment_roof_parts(project_ws=project_ws,
                                                   footprints=features, dsm=dsm, spectral_detail=spectral_detail,
                                                   spatial_detail=spatial_detail,
                                                   min_segment_size=minimum_segment_size,
                                                   reg_tolerance=regularization_tolerance,
                                                   minimum_slope=min_slope, output_fc=output_segments,
                                                   group_field=grouping_field,
                                                   in_memory_switch=in_memory_switch,
                                                   scratch_ws=scratch_ws,
                                                   flat_only=flat_only,
                                                   home_folder=home_directory)

                    if arcpy.Exists(output_fc):
                        arcpy.ClearWorkspaceCache_management()

                        if delete_intermediate_data:
                            fcs = bm_common_lib.listFcsInGDB(scratch_ws)

                            msg_prefix = "Deleting intermediate data..."

                            msg_body = bm_common_lib.create_msg_body(msg_prefix, 0, 0)
                            bm_common_lib.msg(msg_body)

                            for fc in fcs:
                                arcpy.Delete_management(fc)
                    else:
                        print("Could not segment roofs. One or more errors. Exiting...")
                        arcpy.AddError("Could not segment roofs. One or more errors. Exiting...")
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

