import arcpy
import os
import time
import re
import arcpy.cartography as CA
from scripts import bm_common_lib
from scripts.bm_common_lib import  create_msg_body, msg, trace


# constants
ERROR = "error"
TOOLNAME = "Create3DFloodLevel"
WARNING = "warning"


# error classes
class StringHasSpace(Exception):
    pass


class HasSpace(Exception):
    pass


class NoRasterLayer(Exception):
    pass


class LicenseError3D(Exception):
    pass


class LicenseErrorSpatial(Exception):
    pass


class FunctionError(Exception):
    pass


class NoOutput(Exception):
    pass


class NotProjected(Exception):
    pass


class NoNoDataError(Exception):
    pass


class NoUnits(Exception):
    pass


class NoPolygons(Exception):
    pass


class NotSupported(Exception):
    pass


class NoLayerFile(Exception):
    pass


# used functions
def check_valid_raster_input(input_rasters, need_projected, need_vcs):
    valid = True
    no_project = False
    no_vcs = False
    no_res = False
    nr_rasters = 0

    base_sr = arcpy.Describe(input_rasters[0])
    base_cellX = round(float(str(base_sr.meanCellHeight).replace("e-", "")), 4)

    for raster in input_rasters:
        nr_rasters += 1
        # check if input raster has a projected coordinate system (required!)
        cs_name, cs_vcs_name, is_projected = bm_common_lib.get_cs_info(raster, 0)

        if is_projected != need_projected:
            no_project = True
            error_string = bm_common_lib.get_name_from_feature_class(raster) + " does NOT have a projected " \
                                                                               "coordinate system defined"
            arcpy.AddError(error_string)

        # check if has VCS
        if need_vcs:
            if not cs_vcs_name:
                no_vcs = True
                error_string = bm_common_lib.get_name_from_feature_class(raster) + " does NOT have a vertical " \
                                                                                   "coordinate system defined. " \
                                                                                   "Please define the VCS before " \
                                                                                   "running this tool."
                arcpy.AddError(error_string)

        # check if same resolution
        sr = arcpy.Describe(raster)
        cellX = round(float(str(sr.meanCellHeight).replace("e-", "")), 4)

        if cellX != base_cellX:
            no_res = True
            error_string = bm_common_lib.get_name_from_feature_class(raster) + " does NOT have the same " \
                                            "resolution as " + \
                                            bm_common_lib.get_name_from_feature_class(input_rasters[0]) + \
                                            "Please resample the raster."
            arcpy.AddError(error_string)

    if no_project or no_vcs or no_res:
        arcpy.AddMessage("1 or more rasters are not valid for further processing")
        valid = False
    else:
        # check mixed spatial references
        if bm_common_lib.check_same_spatial_reference(input_rasters, []) == 1:
            arcpy.AddError('Input raster data has mixed spatial references. Ensure all input is in the same spatial '
                           'reference, including the same vertical units. Please reproject the rasters.')
            valid = False

    return valid, nr_rasters


def flood_from_raster(home_directory, scratch_ws, input_source, input_type, no_flood_value, baseline_elevation_raster,
                      baseline_elevation_value, outward_buffer, output_polygons, smoothing, smooth_edges, debug,
                      use_in_memory):
    try:
        tiff_directory = home_directory + "\\Tiffs"
        tin_directory = home_directory + "\\Tins"
        if not os.path.exists(tiff_directory):
            os.makedirs(tiff_directory)

        if not os.path.exists(tin_directory):
            os.makedirs(tin_directory)

        baseline_elevation_value = 0

        if not os.path.exists(tiff_directory):
            os.makedirs(tiff_directory)

        if not os.path.exists(tin_directory):
            os.makedirs(tin_directory)

        # check if input rasters are valid
        valid, nr_rasters = check_valid_raster_input([input_source], True, True)

        if valid:
            desc = arcpy.Describe(input_source)

            arcpy.AddMessage("Processing input source: " + bm_common_lib.get_name_from_feature_class(input_source))

            spatial_ref = desc.spatialReference

            # create IsNull to be used to clip and check for NoData.
            if use_in_memory:
                is_null0 = "memory/is_null0"
            else:
                is_null0 = os.path.join(scratch_ws, "is_null0")
                if arcpy.Exists(is_null0):
                    arcpy.Delete_management(is_null0)

            is_null_raster = arcpy.sa.IsNull(input_source)
            is_null_raster.save(is_null0)

            if spatial_ref.type == 'PROJECTED' or spatial_ref.type == 'Projected':
                # check input source type: projected rasters ONLY!!!!
                # check type, if polygon -> convert to raster
                if input_type == "RasterLayer" or input_type == "RasterDataset" or input_type == "raster":
                    # prep raster
                    # smooth result using focal stats
                    if smoothing > 0:
                        if use_in_memory:
                            focal_raster = "memory/focal_raster"
                        else:
                            focal_raster = os.path.join(scratch_ws, "focal_raster")
                            if arcpy.Exists(focal_raster):
                                arcpy.Delete_management(focal_raster)

                        if not (1 <= smoothing <= 100):
                            smoothing = 30

                        neighborhood = arcpy.sa.NbrRectangle(smoothing, smoothing, "CELL")

                        flood_elev_raster = arcpy.sa.FocalStatistics(input_source, neighborhood, "MEAN", "true")
                        flood_elev_raster.save(focal_raster)

                        # con
                        if use_in_memory:
                            smooth_input = "memory/smooth_input"
                        else:
                            smooth_input = os.path.join(scratch_ws, "smooth_input")
                            if arcpy.Exists(smooth_input):
                                arcpy.Delete_management(smooth_input)

                        output = arcpy.sa.Con(is_null0, input_source, flood_elev_raster)
                        output.save(smooth_input)

                        input_raster = smooth_input
                    else:
                        input_raster = input_source
                else:
                    raise NotSupported

                # use numeric value for determining non flooded areas: set these values to NoData.
                # We need NoData for clippng later on

                no_flood_value == "NoData"

                if no_flood_value != "NoData":
                    if bm_common_lib.is_number(no_flood_value):
                        msg_body = create_msg_body(
                            "Setting no flood value: " + no_flood_value + " to NoData in copy of " +
                            bm_common_lib.get_name_from_feature_class(
                                input_raster) + "...", 0, 0)
                        msg(msg_body)

                        if use_in_memory:
                            null_for_no_flooded_areas_raster = "memory/null_for_flooded"
                        else:
                            null_for_no_flooded_areas_raster = os.path.join(scratch_ws, "null_for_flooded")
                            if arcpy.Exists(null_for_no_flooded_areas_raster):
                                arcpy.Delete_management(null_for_no_flooded_areas_raster)

                        whereClause = "VALUE = " + no_flood_value

                        # Execute SetNull
                        outSetNull_temp = arcpy.sa.SetNull(input_raster, input_raster, whereClause)
                        outSetNull_temp.save(null_for_no_flooded_areas_raster)

                        input_raster = null_for_no_flooded_areas_raster
                    else:
                        raise ValueError
                else:
                    pass

                msg_body = create_msg_body(
                   "Checking for NoData values in raster: " + bm_common_lib.get_name_from_feature_class(
                       input_source) + ". NoData values are considered to be non-flooded areas!", 0, 0)
                msg(msg_body)

                max_value = arcpy.GetRasterProperties_management(is_null0, "MAXIMUM")[0]

                if int(max_value) == 1:
                    # 1. get the outline of the raster as polygon via RasterDomain
                    xy_unit = bm_common_lib.get_xy_unit(input_raster, 0)

                    if xy_unit:
                        cell_size = arcpy.GetRasterProperties_management(input_raster, "CELLSIZEX")

                        if baseline_elevation_raster:
                            # check celll size
                            cell_size_base = arcpy.GetRasterProperties_management(baseline_elevation_raster,
                                                                                  "CELLSIZEX")

                            if cell_size_base.getOutput(0) == cell_size.getOutput(0):
                                # Execute Plus
                                if use_in_memory:
                                    flood_plus_base_raster = "memory/flooding_plus_base"
                                else:
                                    flood_plus_base_raster = os.path.join(scratch_ws, "flooding_plus_base")
                                    if arcpy.Exists(flood_plus_base_raster):
                                        arcpy.Delete_management(flood_plus_base_raster)

                                listRasters = []
                                listRasters.append(input_raster)
                                listRasters.append(baseline_elevation_raster)

                                desc = arcpy.Describe(listRasters[0])
                                arcpy.MosaicToNewRaster_management(listRasters, scratch_ws, "flooding_plus_base",
                                                                   desc.spatialReference,
                                                                   "32_BIT_FLOAT", cell_size, 1, "SUM", "")

                                # check where there is IsNull and set the con values
                                if use_in_memory:
                                    is_Null = "memory/is_Null"
                                else:
                                    is_Null = os.path.join(scratch_ws, "is_Null")
                                    if arcpy.Exists(is_Null):
                                        arcpy.Delete_management(is_Null)

                                is_Null_raster = arcpy.sa.IsNull(input_raster)
                                is_Null_raster.save(is_Null)

                                # Con
                                if use_in_memory:
                                    flood_plus_base_raster_null = "memory/flooding_plus_base_null"
                                else:
                                    flood_plus_base_raster_null = os.path.join(scratch_ws, "flooding_plus_base_null")
                                    if arcpy.Exists(flood_plus_base_raster_null):
                                        arcpy.Delete_management(flood_plus_base_raster_null)

                                msg_body = create_msg_body("Adding baseline elevation raster to input flood layer...",
                                                           0, 0)
                                msg(msg_body)

                                fpbrn = arcpy.sa.Con(is_Null, input_raster, flood_plus_base_raster)
                                fpbrn.save(flood_plus_base_raster_null)

                                input_raster = flood_plus_base_raster_null
                            else:
                                arcpy.AddWarning("Cell size of " + input_raster + " is different than " +
                                                 baseline_elevation_raster + ". Ignoring Base Elevation Raster.")
                        else:
                            if baseline_elevation_value > 0:
                                if use_in_memory:
                                    flood_plus_base_raster = "memory/flood_plus_base"
                                else:
                                    flood_plus_base_raster = os.path.join(scratch_ws, "flooding_plus_base")
                                    if arcpy.Exists(flood_plus_base_raster):
                                        arcpy.Delete_management(flood_plus_base_raster)
                                arcpy.Plus_3d(input_raster, baseline_elevation_value, flood_plus_base_raster)

                                input_raster = flood_plus_base_raster

                        msg_body = create_msg_body("Creating 3D polygons...", 0, 0)
                        msg(msg_body)

                        if use_in_memory:
                            raster_polygons = "memory/raster_polygons"
                        else:
                            raster_polygons = os.path.join(scratch_ws, "raster_polygons")
                            if arcpy.Exists(raster_polygons):
                                arcpy.Delete_management(raster_polygons)

                        out_geom = "POLYGON"  # output geometry type
                        arcpy.RasterDomain_3d(input_raster, raster_polygons, out_geom)

                        XYdomain = arcpy.Describe(raster_polygons).spatialReference.domain

                        # 2. buffer it inwards so that we have a polygon only of the perimeter
                        # plus a few cells inward.
                        if 0: # use_in_memory: -> buffer sometime fails in memory
                            polygons_inward = "memory/inward_buffer"
                        else:
                            polygons_inward = os.path.join(scratch_ws, "inward_buffer")
                            if arcpy.Exists(polygons_inward):
                                arcpy.Delete_management(polygons_inward)

                        x = float(re.sub("[,.]", ".", str(cell_size.getOutput(0))))

                        if x < 0.1:
                            arcpy.AddError("Raster cell size is 0. Can't continue. Please check the raster properties.")
                            raise ValueError
                        else:
                            buffer_in = 3 * round(x, 2)  # int(x)

                            if xy_unit == "Feet":
                                buffer_text = "-" + str(buffer_in) + " Feet"
                            else:
                                buffer_text = "-" + str(buffer_in) + " Meters"

                            sideType = "OUTSIDE_ONLY"
                            arcpy.Buffer_analysis(raster_polygons, polygons_inward, buffer_text, sideType)

                            msg_body = create_msg_body("Buffering flood edges...", 0, 0)
                            msg(msg_body)

                            # 3. mask in ExtractByMask: gives just boundary raster with a few cells inwards
                            if use_in_memory:
                                extract_mask_raster = "memory/extract_mask"
                            else:
                                extract_mask_raster = os.path.join(scratch_ws, "extract_mask")
                                if arcpy.Exists(extract_mask_raster):
                                    arcpy.Delete_management(extract_mask_raster)

                            extract_temp_raster = arcpy.sa.ExtractByMask(input_raster, polygons_inward)
                            extract_temp_raster.save(extract_mask_raster)

                            # 4. convert the output to points
                            if use_in_memory:
                                extract_mask_points = "memory/extract_points"
                            else:
                                extract_mask_points = os.path.join(scratch_ws, "extract_points")
                                if arcpy.Exists(extract_mask_points):
                                    arcpy.Delete_management(extract_mask_points)

                            arcpy.RasterToPoint_conversion(extract_mask_raster, extract_mask_points, "VALUE")

                            msg_body = create_msg_body("Create flood points...", 0, 0)
                            msg(msg_body)

                            # 5. Interpolate: this will also interpolate outside the flood boundary which is
                            # what we need so we get a nice 3D poly that extends into the surrounding DEM
                            if use_in_memory:
                                interpolated_raster = "memory/interpolate_raster"
                            else:
                                interpolated_raster = os.path.join(scratch_ws, "interpolate_raster")
                                if arcpy.Exists(interpolated_raster):
                                    arcpy.Delete_management(interpolated_raster)

                            zField = "grid_code"
                            power = 2
                            searchRadius = arcpy.sa.RadiusVariable(12, 150000)

                            msg_body = create_msg_body("Interpolating flood points...", 0, 0)
                            msg(msg_body)

                            # Execute IDW
                            out_IDW = arcpy.sa.Idw(extract_mask_points, zField, cell_size, power)

                            # Save the output
                            out_IDW.save(interpolated_raster)

                            extent_poly = bm_common_lib.get_extent_feature(scratch_ws, polygons_inward)

                            msg_body = create_msg_body("Clipping interpolated raster...", 0, 0)
                            msg(msg_body)

                            # clip the input surface
                            if use_in_memory:
                                extent_clip_idwraster = "memory/extent_clip_idw"
                            else:
                                extent_clip_idwraster = os.path.join(scratch_ws, "extent_clip_idw")
                                if arcpy.Exists(extent_clip_idwraster):
                                    arcpy.Delete_management(extent_clip_idwraster)

                            # clip terrain to extent
                            arcpy.Clip_management(interpolated_raster, "#", extent_clip_idwraster, extent_poly)

                            # 6. clip the interpolated raster by (outward buffered) outline polygon
                            if 0:  # use_in_memory: -> buffer sometime fails in memory
                                polygons_outward = "memory/outward_buffer"
                            else:
                                polygons_outward = os.path.join(scratch_ws, "outward_buffer")
                                if arcpy.Exists(polygons_outward):
                                    arcpy.Delete_management(polygons_outward)

                            outward_buffer += 0.5 * round(x, 2)  #int(x)  # we buffer out by half the raster cellsize

                            if outward_buffer > 0:
                                if xy_unit == "Feet":
                                    buffer_text = str(outward_buffer) + " Feet"
                                else:
                                    buffer_text = str(outward_buffer) + " Meters"

                                sideType = "FULL"
                                arcpy.Buffer_analysis(raster_polygons, polygons_outward, buffer_text, sideType)

                                raster_polygons = polygons_outward

                            # clip the input surface
                            if use_in_memory:
                                flood_clip_raster = "memory/flood_clip_raster"
                            else:
                                flood_clip_raster = os.path.join(scratch_ws, "flood_clip_raster")
                                if arcpy.Exists(flood_clip_raster):
                                    arcpy.Delete_management(flood_clip_raster)

                            msg_body = create_msg_body("Clipping flood raster...", 0, 0)
                            msg(msg_body)

                            # clip terrain to extent
                            arcpy.Clip_management(interpolated_raster, "#", flood_clip_raster, raster_polygons)

                            # 7. Isnull, and Con to grab values from flood_clip_raster for
                            # create NUll mask
                            if use_in_memory:
                                is_Null = "memory/is_Null"
                            else:
                                is_Null = os.path.join(scratch_ws, "is_Null")
                                if arcpy.Exists(is_Null):
                                    arcpy.Delete_management(is_Null)

                            is_Null_raster = arcpy.sa.IsNull(input_raster)
                            is_Null_raster.save(is_Null)

                            # Con
                            if use_in_memory:
                                con_raster = "memory/con_raster"
                            else:
                                con_raster = os.path.join(scratch_ws, "con_raster")
                                if arcpy.Exists(con_raster):
                                    arcpy.Delete_management(con_raster)
                            temp_con_raster = arcpy.sa.Con(is_Null, interpolated_raster, input_raster)
                            temp_con_raster.save(con_raster)

                            msg_body = create_msg_body("Merging rasters...", 0, 0)
                            msg(msg_body)

                            # 8. focal stats on raster to smooth?

                            # 9. copy raster to geotiff
                            if use_in_memory:
                                 con_raster_tif = "memory/con_raster_tif"
                            else:
                                con_raster_tif = os.path.join(tiff_directory, "con_raster.tif")
                                if arcpy.Exists(con_raster_tif):
                                    arcpy.Delete_management(con_raster_tif)

                            arcpy.CopyRaster_management(con_raster, con_raster_tif, "#", "#", "#", "#", "#",
                                                        "32_BIT_FLOAT")

                            msg_body = create_msg_body("Copying to tiff...", 0, 0)
                            msg(msg_body)

                            # 10. raster to TIN
                            zTol = 0.1
                            maxPts = 1500000
                            zFactor = 1
                            con_tin = os.path.join(tin_directory, "con_tin")
                            if arcpy.Exists(con_tin):
                                arcpy.Delete_management(con_tin)

                            # Execute RasterTin
                            arcpy.RasterTin_3d(con_raster_tif, con_tin, zTol, maxPts, zFactor)
                            arcpy.Delete_management(con_raster_tif)

                            msg_body = create_msg_body("Deleting memory...", 0, 0)
                            msg(msg_body)

                            msg_body = create_msg_body("Creating TIN...", 0, 0)
                            msg(msg_body)

                            # 11. TIN triangles
                            if 0:  #use_in_memory:
                                arcpy.AddMessage("con_triangles")
                                con_triangles = "memory/con_triangles"
                            else:
                                con_triangles = os.path.join(scratch_ws, "con_triangles")
                                if arcpy.Exists(con_triangles):
                                    arcpy.Delete_management(con_triangles)

                            arcpy.TinTriangle_3d(con_tin, con_triangles)

                            msg_body = create_msg_body("Creating polygons...", 0, 0)
                            msg(msg_body)

                            # 12. make 2D polygons feature to feature class
                            arcpy.FeatureClassToFeatureClass_conversion(con_triangles, scratch_ws, "con_triangles_2D")

                            if smooth_edges:
                                # 12. clip with smooth polygon
                                smooth_polygons = os.path.join(scratch_ws, "smooth_raster_polygons")
                                if arcpy.Exists(smooth_polygons):
                                    arcpy.Delete_management(smooth_polygons)

                                msg_body = create_msg_body("Smoothing edges...", 0, 0)
                                msg(msg_body)

                                CA.SmoothPolygon(os.path.join(raster_polygons), smooth_polygons, "PAEK", x, "",
                                                 "FLAG_ERRORS")
                            else:
                                smooth_polygons = raster_polygons

                            if 0: #use_in_memory:
                                clip_smooth_triangles = "memory/clip_smooth_triangles"
                            else:
                                clip_smooth_triangles = os.path.join(scratch_ws, "clip_smooth_triangles")
                                if arcpy.Exists(clip_smooth_triangles):
                                    arcpy.Delete_management(clip_smooth_triangles)

                            # clip terrain to extent
                            arcpy.Clip_analysis(con_triangles, smooth_polygons, clip_smooth_triangles)

                            # clip to slightly lesser extent because of InterpolateShape fail.
                            arcpy.env.XYDomain = XYdomain
                            area_extent = bm_common_lib.get_extent_feature(scratch_ws, clip_smooth_triangles)

                            if 0:  # use_in_memory: -> buffer sometime fails in memory
                                extent_inward = "memory/inward_extent_buffer"
                            else:
                                extent_inward = os.path.join(scratch_ws, "inward_extent_buffer")
                                if arcpy.Exists(extent_inward):
                                    arcpy.Delete_management(extent_inward)

                            buffer_in = 3

                            if xy_unit == "Feet":
                                buffer_text = "-" + str(buffer_in) + " Feet"
                            else:
                                buffer_text = "-" + str(buffer_in) + " Meters"

                            sideType = "FULL"

                            arcpy.Buffer_analysis(area_extent, extent_inward, buffer_text, sideType)

                            if 0:  #use_in_memory:
                                clip2_smooth_triangles = "memory/clip2_smooth_triangles"
                            else:
                                clip2_smooth_triangles = os.path.join(scratch_ws, "clip2_smooth_triangles")
                                if arcpy.Exists(clip2_smooth_triangles):
                                    arcpy.Delete_management(clip2_smooth_triangles)

                            # clip terrain to extent
                            arcpy.Clip_analysis(clip_smooth_triangles, extent_inward, clip2_smooth_triangles)

                            # 13. interpolate on TIN
                            if 0: #use_in_memory:
                                arcpy.AddMessage("triangle3D")
                                clip_smooth_triangles3D = "memory/clip_smooth_triangles3D"
                            else:
                                # output 3D polygons to gdb
                                flood_level_poly = output_polygons + "_3Dpoly"
                                clip_smooth_triangles3D = os.path.join(flood_level_poly)
#                                clip_smooth_triangles3D = os.path.join(scratch_ws, "clip_smooth_triangles3D")

                                if arcpy.Exists(clip_smooth_triangles3D):
                                    arcpy.Delete_management(clip_smooth_triangles3D)

                            msg_body = create_msg_body("Interpolating polygons on TIN", 0, 0)
                            msg(msg_body)
                            arcpy.InterpolateShape_3d(con_tin, clip2_smooth_triangles, clip_smooth_triangles3D, "#", 1,
                                                      "LINEAR", "VERTICES_ONLY")

                            # 13. to multipatch
                            # temp layer
                            flood_level_layer = "flood_level_layer"
                            arcpy.MakeFeatureLayer_management(clip_smooth_triangles3D, flood_level_layer)

                            flood_level_mp = output_polygons + "_3D"

                            if arcpy.Exists(flood_level_mp):
                                arcpy.Delete_management(flood_level_mp)

                            arcpy.Layer3DToFeatureClass_3d(flood_level_layer, flood_level_mp)

                            # layer to be added to TOC
                            flood_level_layer_mp = bm_common_lib.get_name_from_feature_class(flood_level_mp)
                            arcpy.MakeFeatureLayer_management(flood_level_mp, flood_level_layer_mp)

                            arcpy.AddMessage("Results written to: " + flood_level_mp + " and " +
                                             clip_smooth_triangles3D)

                            if use_in_memory:
                                arcpy.Delete_management("memory")

                            arcpy.ResetEnvironments()

                            return flood_level_layer_mp

                        # 14. adjust 3D Z feet to meters???
                    else:
                        raise NoUnits
                else:
                    raise NoNoDataError
            else:
                raise NotProjected
        else:
            return None

    except NotProjected:
        print("Input data needs to be in a projected coordinate system. Exiting...")
        arcpy.AddError("Input data needs to be in a projected coordinate system. Exiting...")

    except NoLayerFile:
        print("Can't find Layer file. Exiting...")
        arcpy.AddError("Can't find Layer file. Exiting...")

    except LicenseError3D:
        print("3D Analyst license is unavailable")
        arcpy.AddError("3D Analyst license is unavailable")

    except LicenseErrorSpatial:
        print("Spatial Analyst license is unavailable")
        arcpy.AddError("Spatial Analyst license is unavailable")

    except NoNoDataError:
        print("Input raster does not have NODATA values")
        arcpy.AddError("Input raster does not have NODATA values")

    except NoUnits:
        print("No units detected on input data")
        arcpy.AddError("No units detected on input data")

    except NoPolygons:
        print("Input data can only be polygon features or raster datasets.")
        arcpy.AddError("Input data can only be polygon features or raster datasets.")

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


def run(input_source, no_flood_value, baseline_elevation_raster, baseline_elevation_value,
        smooth_factor, smooth_edges, output_features, debug):
    # MAIN
    try:
        aprx = arcpy.mp.ArcGISProject("CURRENT")
        home_directory = aprx.homeFolder
        in_memory_switch = False
        delete_intermediate_data = True

        if os.path.exists(os.path.join(home_directory, "p20")):  # it is a package
            home_directory = os.path.join(home_directory, "p20")

        arcpy.AddMessage("Project Home Directory is: " + home_directory)

        for a in home_directory:
            if a.isspace():
                raise HasSpace

        if bm_common_lib.check_spaces(output_features):
            raise StringHasSpace

        if bm_common_lib.check_directory(home_directory):
            log_directory = home_directory + "\\Logs"
            layer_directory = home_directory + "\\layer_files"

            if not os.path.exists(log_directory):
                os.makedirs(log_directory)

            # rename layer files (for packaging)
            if os.path.exists(layer_directory):
                bm_common_lib.rename_file_extension(layer_directory, ".txt", ".lyrx")

            scratch_ws = bm_common_lib.create_gdb(home_directory, "Intermediate.gdb")
            arcpy.env.workspace = scratch_ws
            arcpy.env.overwriteOutput = True

            bm_common_lib.set_up_logging(log_directory, TOOLNAME)

            if arcpy.CheckExtension("3D") == "Available":
                arcpy.CheckOutExtension("3D")

                if arcpy.CheckExtension("Spatial") == "Available":
                    arcpy.CheckOutExtension("Spatial")

                    # check if input exists
                    if arcpy.Exists(input_source):
                        full_path_source = bm_common_lib.get_full_path_from_layer(input_source)
                        full_path_baseline_raster = None

                        desc = arcpy.Describe(input_source)

                        flood_polygons = flood_from_raster(home_directory=home_directory,
                                                           scratch_ws=scratch_ws,
                                                           input_source=full_path_source,
                                                           input_type=desc.dataType,
                                                           no_flood_value=no_flood_value,
                                                           baseline_elevation_raster=full_path_baseline_raster,
                                                           baseline_elevation_value=baseline_elevation_value,
                                                           outward_buffer=0,
                                                           output_polygons=output_features,
                                                           smoothing=smooth_factor,
                                                           smooth_edges=smooth_edges,
                                                           debug=debug,
                                                           use_in_memory=in_memory_switch)

                        if flood_polygons:
                            # create layer, set layer file
                            # apply transparency here // checking if symbology layer is present
                            z_unit = bm_common_lib.get_z_unit(flood_polygons, debug)

                            if z_unit == "Feet":
                                floodSymbologyLayer = layer_directory + "\\flood3Dfeet.lyrx"
                            else:
                                floodSymbologyLayer = layer_directory + "\\flood3Dmeter.lyrx"

                            output_layer = bm_common_lib.get_name_from_feature_class(flood_polygons)
                            arcpy.MakeFeatureLayer_management(flood_polygons, output_layer)

                            if arcpy.Exists(floodSymbologyLayer):
                                arcpy.ApplySymbologyFromLayer_management(output_layer, floodSymbologyLayer)
                            else:
                                msg_body = create_msg_body("Can't find" + floodSymbologyLayer + " in " +
                                                           layer_directory, 0,
                                                           0)
                                msg(msg_body, WARNING)

                            if output_layer:
                                if z_unit == "Feet":
                                    arcpy.SetParameter(7, output_layer)
                                else:
                                    arcpy.SetParameter(8, output_layer)
                            else:
                                raise NoOutput

                            if delete_intermediate_data:
                                fcs = bm_common_lib.listFcsInGDB(scratch_ws)

                                msg_prefix = "Deleting intermediate data..."

                                msg_body = bm_common_lib.create_msg_body(msg_prefix, 0, 0)
                                bm_common_lib.msg(msg_body)

                                for fc in fcs:
                                    arcpy.Delete_management(fc)

                            msg_body = create_msg_body("create_3Dflood_level_tbx completed successfully.", 0, 0)
                            msg(msg_body)
                    else:
                        raise NoRasterLayer

                    arcpy.ClearWorkspaceCache_management()
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

    except NoRasterLayer:
        print("Can't find Raster layer. Exiting...")
        arcpy.AddError("Can't find Raster layer. Exiting...")

    except NoOutput:
        print("Can't create output. Exiting...")
        arcpy.AddError("Can't create output. Exiting...")

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

