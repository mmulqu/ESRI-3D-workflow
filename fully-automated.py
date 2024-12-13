import arcpy
import os
import sys
import time
import re
from arcpy.sa import *


def create_las_dataset(input_las_file, output_lasd, workspace):
    """
    Creates a LAS dataset from an input LAS file

    Parameters:
    input_las_file (str): Path to the input .las file
    output_lasd (str): Path where the .lasd file will be created
    workspace (str): Path to the workspace directory

    Returns:
    str: Path to the created LAS dataset
    """
    try:
        arcpy.AddMessage(f"Creating LAS dataset from {input_las_file}")

        # Create LAS dataset with ESRI recommended parameters
        arcpy.management.CreateLasDataset(
            input_las_file,
            output_lasd,
            folder_recursion="NO_RECURSION",
            compute_stats="COMPUTE_STATS",
            relative_paths="RELATIVE_PATHS",
            create_las_prj="FILES_MISSING_PROJECTION"
        )

        arcpy.AddMessage("LAS dataset created successfully")
        return output_lasd

    except arcpy.ExecuteError:
        arcpy.AddError("Error creating LAS dataset")
        arcpy.AddError(arcpy.GetMessages())
        raise
    except Exception as e:
        arcpy.AddError(f"Unexpected error: {str(e)}")
        raise


def main():
    try:
        # ---------------------------------------------------------------------------
        # STEP 0: Set up workspace and input parameters
        # ---------------------------------------------------------------------------
        home_directory = r"C:\path\to\project\home"
        project_ws = r"C:\path\to\project\workspace"

        # Input LAS file path
        input_las_file = r"C:\path\to\your_data.las"  # Update this path

        # Create output LAS dataset path
        output_lasd = os.path.join(project_ws, "lidar_data.lasd")

        # ---------------------------------------------------------------------------
        # STEP 1: Create LAS Dataset
        # ---------------------------------------------------------------------------
        las_dataset = create_las_dataset(input_las_file, output_lasd, project_ws)

        # ---------------------------------------------------------------------------
        # STEP 2: Extract Elevation from LAS Dataset
        # ---------------------------------------------------------------------------
        # Parameters matching ESRI workflow
        cell_size = "0.3"  # 0.3m cell size as specified
        only_ground_plus_class_code = True
        class_code = 15  # Building class code
        output_elevation_raster_base = os.path.join(project_ws, "elevation_output")
        classify_noise = True
        minimum_height = "0.5"
        maximum_height = "50"
        processing_extent = "#"
        debug = 1

        # Import the extract elevation module
        from scripts.extract_elevation_from_las import run as run_extract_elevation

        # Run the extract elevation tool using the created LAS dataset
        run_extract_elevation(
            home_directory=home_directory,
            project_ws=project_ws,
            input_las_dataset=las_dataset,
            cell_size=cell_size,
            only_ground_plus_class_code=only_ground_plus_class_code,
            class_code=class_code,
            output_elevation_raster=output_elevation_raster_base,
            classify_noise=classify_noise,
            minimum_height=minimum_height,
            maximum_height=maximum_height,
            processing_extent=processing_extent,
            debug=debug
        )

        # ---------------------------------------------------------------------------
        # ---------------------------------------------------------------------------
        # STEP 3: Create Draft Footprint Raster
        # ---------------------------------------------------------------------------
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

        # In main():
        try:
            arcpy.AddMessage("Creating Draft Footprint Raster...")

            # Set up parameters for building mosaic
            dsm = output_elevation_raster_base + "_dsm"
            out_folder = os.path.join(project_ws, "building_mosaic_rasters")
            out_mosaic = os.path.join(project_ws, "project.gdb", "building_mosaic")

            if not os.path.exists(out_folder):
                os.makedirs(out_folder)

            # Get spatial reference from LAS dataset
            spatial_ref = arcpy.Describe(las_dataset).spatialReference

            # Set cell size to 0.6m as per ESRI workflow
            cell_size = "0.6 Meters"

            # Convert cell size to dataset units
            metric_cell_size = get_metric_from_linear_unit(cell_size)
            las_m_per_unit = spatial_ref.metersPerUnit
            cell_size_conv = metric_cell_size / las_m_per_unit

            # Create mosaic dataset if it doesn't exist
            if not arcpy.Exists(out_mosaic):
                out_gdb = os.path.dirname(out_mosaic)
                mosaic_name = os.path.basename(out_mosaic)

                arcpy.CreateMosaicDataset_management(
                    out_gdb,
                    mosaic_name,
                    spatial_ref,
                    None,
                    "8_BIT_UNSIGNED",
                    "CUSTOM",
                    None
                )
                arcpy.AddMessage('Mosaic dataset {} created...'.format(out_mosaic))

            # Create LAS Dataset Layer for buildings (class code 6)
            lasd_layer = "lasd_layer"
            arcpy.MakeLasDatasetLayer_management(las_dataset, lasd_layer, 6)

            # Create building point raster
            bldg_pt_raster = os.path.join(out_folder, "building_points.tif")
            arcpy.LasPointStatsAsRaster_management(
                lasd_layer,
                bldg_pt_raster,
                "PREDOMINANT_CLASS",
                "CELLSIZE",
                cell_size_conv
            )

            # Add raster to mosaic dataset
            arcpy.AddMessage('Adding raster to mosaic dataset...')
            arcpy.AddRastersToMosaicDataset_management(
                out_mosaic,
                "Raster Dataset",
                out_folder,
                "UPDATE_CELL_SIZES",
                "UPDATE_BOUNDARY",
                "NO_OVERVIEWS",
                None,
                0,
                1500,
                None,
                None,
                "SUBFOLDERS",
                "ALLOW_DUPLICATES",
                "NO_PYRAMIDS",
                "NO_STATISTICS",
                "NO_THUMBNAILS",
                None,
                "NO_FORCE_SPATIAL_REFERENCE",
                "NO_STATISTICS",
                None
            )

            # Update mosaic cell size
            arcpy.AddMessage('Updating mosaic cell size...')
            cellSize = arcpy.GetRasterProperties_management(out_mosaic, "CELLSIZEX")
            cellSize = re.sub("[,.]", ".", cellSize.getOutput(0))
            newSize = float(float(cellSize) / 2)
            arcpy.SetMosaicDatasetProperties_management(out_mosaic, cell_size=newSize)

            # Cleanup
            arcpy.Delete_management(lasd_layer)

            arcpy.AddMessage("Draft Footprint Raster created successfully")

        except arcpy.ExecuteError:
            arcpy.AddError(arcpy.GetMessages(2))
        except Exception as e:
            arcpy.AddError(f"An error occurred: {str(e)}")

        # ---------------------------------------------------------------------------
        # ---------------------------------------------------------------------------
        # STEP 4: Run Focal Statistics
        # ---------------------------------------------------------------------------
        try:
            arcpy.AddMessage("Running Focal Statistics...")

            # Input raster from the mosaic dataset
            in_raster = out_mosaic

            # Define neighborhood as 3x3 rectangle in cell units
            # as specified in ESRI workflow: "Rectangle 3x3, unit_type=cell"
            neighborhood = NbrRectangle(3, 3, "CELL")

            # Set statistics type to MAJORITY
            # as specified in ESRI workflow: "stats type=MAJORITY"
            statistics_type = "MAJORITY"

            # Set ignore_nodata to "DATA" to ignore NoData values in calculations
            # as specified in ESRI workflow: "ignore NoData"
            ignore_nodata = "DATA"

            # Define output path
            out_focal = os.path.join(out_folder, "focal_building_mosaic.tif")

            # Run Focal Statistics with explicit parameters
            focal_result = FocalStatistics(
                in_raster=in_raster,
                neighborhood=neighborhood,
                statistics_type=statistics_type,
                ignore_nodata=ignore_nodata
            )

            # Save the result
            focal_result.save(out_focal)

            arcpy.AddMessage("Focal Statistics completed successfully")

        except arcpy.ExecuteError:
            arcpy.AddError("Error in Focal Statistics:")
            arcpy.AddError(arcpy.GetMessages(2))
        except Exception as e:
            arcpy.AddError(f"An unexpected error occurred in Focal Statistics: {str(e)}")

        # ---------------------------------------------------------------------------
    # ---------------------------------------------------------------------------
    # STEP 5: Create footprints from raster
    # ---------------------------------------------------------------------------
    try:
        arcpy.AddMessage("Creating footprints from raster...")

        # Parameters from ESRI workflow
        min_area = "32 SquareMeters"  # Minimum building area = 32 sqm
        split_features = None  # No split features
        simplify_tolerance = "0.3 Meters"  # 0.3m as specified
        output_poly = os.path.join(project_ws, "project.gdb", "final_footprints")

        # Default parameters for various building types
        reg_circles = True  # Enable circle regularization
        circle_min_area = "100 SquareMeters"
        min_compactness = 0.75
        circle_tolerance = "2 Meters"

        # Large building parameters
        lg_reg_method = "ORTHO"  # Orthogonal regularization for large buildings
        lg_min_area = "500 SquareMeters"
        lg_tolerance = "2 Meters"

        # Medium building parameters
        med_reg_method = "ORTHO"
        med_min_area = "200 SquareMeters"
        med_tolerance = "1 Meters"

        # Small building parameters
        sm_reg_method = "ORTHO"
        sm_tolerance = "0.5 Meters"

        # Import and run the footprints from raster module
        from scripts.footprints_from_raster import run as run_footprints_from_raster

        run_footprints_from_raster(
            home_directory=home_directory,
            project_ws=project_ws,
            in_raster=out_focal,  # Using the focal statistics output
            min_area=min_area,
            split_features=split_features,
            simplify_tolerance=simplify_tolerance,
            output_poly=output_poly,
            reg_circles=reg_circles,
            circle_min_area=circle_min_area,
            min_compactness=min_compactness,
            circle_tolerance=circle_tolerance,
            lg_reg_method=lg_reg_method,
            lg_min_area=lg_min_area,
            lg_tolerance=lg_tolerance,
            med_reg_method=med_reg_method,
            med_min_area=med_min_area,
            med_tolerance=med_tolerance,
            sm_reg_method=sm_reg_method,
            sm_tolerance=sm_tolerance,
            debug=debug
        )

        arcpy.AddMessage("Building footprints created successfully")

    except arcpy.ExecuteError:
        arcpy.AddError("Error creating building footprints:")
        arcpy.AddError(arcpy.GetMessages(2))
    except Exception as e:
        arcpy.AddError(f"An unexpected error occurred while creating building footprints: {str(e)}")


if __name__ == "__main__":
    main()