import arcpy
import os
import sys
import time
import re
from arcpy.sa import *


def create_las_dataset(input_las_file, output_lasd, workspace):
    """
    Creates a LAS dataset from an input LAS file
    """
    try:
        arcpy.AddMessage(f"Creating LAS dataset from {input_las_file}")

        # Delete existing LAS dataset if it exists
        if arcpy.Exists(output_lasd):
            arcpy.AddMessage(f"Deleting existing LAS dataset: {output_lasd}")
            arcpy.Delete_management(output_lasd)

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
        # Enable overwriting of outputs
        arcpy.env.overwriteOutput = True

        # ---------------------------------------------------------------------------
        # STEP 0: Set up workspace and input parameters
        # ---------------------------------------------------------------------------
        home_directory = r"G:\MMULQUEEN\Buildings3D\Automate_esri_new\fully-automated-3d"
        project_ws = r"G:\MMULQUEEN\Buildings3D\Automate_esri_new\fully-automated-3d-testdata\fully-automated-3d-testing.gdb"

        # Set the workspace environment
        arcpy.env.workspace = project_ws
        scratch_ws = arcpy.env.scratchGDB

        # Input LAS file path
        input_las_file = r"G:\MMULQUEEN\Buildings3D\Automate_esri_new\fully-automated-3d-testdata\19TCG301639last.las"

        # Create output LAS dataset path
        las_output_folder = os.path.join(os.path.dirname(project_ws), "las_datasets")
        if not os.path.exists(las_output_folder):
            os.makedirs(las_output_folder)
        output_lasd = os.path.join(las_output_folder, "lidar_data.lasd")

        # ---------------------------------------------------------------------------
        # STEP 1: Create LAS Dataset
        # ---------------------------------------------------------------------------
        las_dataset = create_las_dataset(input_las_file, output_lasd, project_ws)

        # ---------------------------------------------------------------------------
        # STEP 2: Extract Elevation from LAS Dataset
        # ---------------------------------------------------------------------------
        # Import the extract elevation module
        from scripts.extract_elevation_from_las import run as run_extract_elevation

        # Parameters for elevation extraction
        cell_size = "0.3"  # 0.3m cell size as specified
        only_ground_plus_class_code = True
        class_code = 15  # Building class code
        output_elevation_raster_base = "elev"
        classify_noise = True
        minimum_height = "0.5"
        maximum_height = "50"
        processing_extent = "#"
        debug = 1

        # Run the extract elevation tool
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
        # STEP 3: Create Draft Footprint Raster
        # ---------------------------------------------------------------------------
        from scripts.create_building_mosaic import run as run_building_mosaic

        # Set up parameters for building mosaic
        out_folder = os.path.join(os.path.dirname(project_ws), "building_mosaic_rasters")
        if not os.path.exists(out_folder):
            os.makedirs(out_folder)
        out_mosaic = "building_mosaic"

        # Get spatial reference from LAS dataset
        spatial_ref = arcpy.Describe(las_dataset).spatialReference

        # Set cell size to 0.6m as per ESRI workflow
        mosaic_cell_size = "0.6 Meters"

        # Run the building mosaic tool
        run_building_mosaic(
            home_directory=home_directory,
            project_ws=project_ws,
            in_lasd=las_dataset,
            out_folder=out_folder,
            out_mosaic=out_mosaic,
            spatial_ref=spatial_ref,
            cell_size=mosaic_cell_size,
            debug=debug
        )

        # ---------------------------------------------------------------------------
        # STEP 4: Run Focal Statistics
        # ---------------------------------------------------------------------------
        try:
            arcpy.AddMessage("Running Focal Statistics...")

            # Get full path to mosaic dataset and verify it exists
            full_mosaic_path = os.path.join(project_ws, out_mosaic)
            if not arcpy.Exists(full_mosaic_path):
                raise arcpy.ExecuteError(f"Input mosaic dataset {full_mosaic_path} does not exist")

            # Create output path for focal statistics
            out_focal = os.path.join(project_ws, "focal_mosaic")
            if arcpy.Exists(out_focal):
                arcpy.Delete_management(out_focal)

            # Set up focal statistics parameters
            neighborhood = NbrRectangle(3, 3, "CELL")  # 3x3 cell neighborhood

            # Check if input is integer or float to determine valid statistics
            desc = arcpy.Describe(full_mosaic_path)
            if desc.pixelType in ['U1', 'U2', 'U4', 'U8', 'S8', 'U16', 'S16', 'U32', 'S32']:
                # Integer raster - can use MAJORITY
                statistics_type = "MAJORITY"
            else:
                # Float raster - use MEAN instead
                statistics_type = "MEAN"

            arcpy.AddMessage(f"Using {statistics_type} statistics for focal analysis")

            # Create temporary in memory workspace for processing
            arcpy.env.workspace = "in_memory"

            # Run Focal Statistics
            focal_result = FocalStatistics(
                in_raster=full_mosaic_path,
                neighborhood=neighborhood,
                statistics_type=statistics_type,
                ignore_nodata="DATA"
            )

            # Save the result to geodatabase
            focal_result.save(out_focal)

            # Verify output was created
            if not arcpy.Exists(out_focal):
                raise arcpy.ExecuteError(f"Failed to create focal statistics output at {out_focal}")

            arcpy.AddMessage("Focal Statistics completed successfully")

            # Reset workspace
            arcpy.env.workspace = project_ws

        except arcpy.ExecuteError:
            arcpy.AddError("Error in Focal Statistics:")
            arcpy.AddError(arcpy.GetMessages(2))
            raise
        except Exception as e:
            arcpy.AddError(f"An unexpected error occurred in Focal Statistics: {str(e)}")
            raise

        # Clear temporary workspace
        arcpy.Delete_management("in_memory")

        # ---------------------------------------------------------------------------
        # STEP 5: Create footprints from raster
        # ---------------------------------------------------------------------------
        from scripts.footprints_from_raster import run as run_footprints_from_raster

        arcpy.AddMessage("Creating footprints from raster...")

        # Parameters from ESRI workflow
        min_area = "32 SquareMeters"
        split_features = None
        simplify_tolerance = "0.3 Meters"
        output_poly = "final_footprints"

        # Default parameters for various building types
        reg_circles = True
        circle_min_area = "100 SquareMeters"
        min_compactness = 0.75
        circle_tolerance = "2 Meters"

        # Building size parameters
        lg_reg_method = "ORTHO"
        lg_min_area = "500 SquareMeters"
        lg_tolerance = "2 Meters"
        med_reg_method = "ORTHO"
        med_min_area = "200 SquareMeters"
        med_tolerance = "1 Meters"
        sm_reg_method = "ORTHO"
        sm_tolerance = "0.5 Meters"

        # Run the footprints from raster tool
        run_footprints_from_raster(
            home_directory=home_directory,
            project_ws=project_ws,
            in_raster=out_focal,
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
        arcpy.AddError("Error in process:")
        arcpy.AddError(arcpy.GetMessages(2))
    except Exception as e:
        arcpy.AddError(f"An unexpected error occurred: {str(e)}")


if __name__ == "__main__":
    main()