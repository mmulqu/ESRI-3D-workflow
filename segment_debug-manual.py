import arcpy
import os
import sys
import time
import re
from arcpy.sa import *


def create_las_dataset(input_las_file, output_lasd, workspace):
    """
    Creates a LAS dataset from an input LAS file with ESRI recommended parameters.
    Args:
        input_las_file: Path to input LAS file
        output_lasd: Path for output LAS dataset
        workspace: Workspace for processing
    Returns:
        Path to created LAS dataset
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
        # Define main directories
        home_directory = r"G:\MMULQUEEN\Buildings3D\Automate_esri_new\fully-automated-3d"
        testdata_dir = r"G:\MMULQUEEN\Buildings3D\Automate_esri_new\fully-automated-3d-testdata"

        # Create a proper File Geodatabase if it doesn't exist
        gdb_name = "fully-automated-3d-esri-testing.gdb"
        project_ws = os.path.join(testdata_dir, gdb_name)

        if not arcpy.Exists(project_ws):
            arcpy.AddMessage(f"Creating new File Geodatabase: {project_ws}")
            arcpy.CreateFileGDB_management(testdata_dir, gdb_name)

        # Set the workspace environment
        arcpy.env.workspace = project_ws
        scratch_ws = arcpy.env.scratchGDB

        # Define input and output paths
        input_las_file = os.path.join(testdata_dir, "19TCG301639last.las")
        las_output_folder = os.path.join(testdata_dir, "las_datasets")
        if not os.path.exists(las_output_folder):
            os.makedirs(las_output_folder)
        output_lasd = os.path.join(las_output_folder, "lidar_data.lasd")
        # ---------------------------------------------------------------------------
        # STEP 1: Create LAS Dataset
        # ---------------------------------------------------------------------------
        # Create LAS dataset which will be our foundation for elevation extraction
        las_dataset = create_las_dataset(input_las_file, output_lasd, project_ws)

        # ---------------------------------------------------------------------------
        # STEP 2: Extract Elevation from LAS Dataset
        # ---------------------------------------------------------------------------
        # Import the elevation extraction module that will create DTM, DSM, and nDSM
        from scripts.extract_elevation_from_las import run as run_extract_elevation

        # Set parameters for elevation extraction
        # We use 0.3m cell size as it provides good detail while maintaining processing efficiency
        cell_size = "0.3"
        only_ground_plus_class_code = True
        class_code = 15  # Building class code in LAS classification system

        # Output elevation raster will be created directly in the geodatabase
        # This creates elev_dtm, elev_dsm, and elev_ndsm in the project geodatabase
        output_elevation_raster_base = os.path.join(project_ws, "elev")

        # Additional parameters for noise classification and height thresholds
        classify_noise = True
        minimum_height = "0.5"  # Minimum building height to consider
        maximum_height = "50"  # Maximum reasonable building height
        processing_extent = "#"
        debug = 1

        # Run the extract elevation tool to create our elevation surfaces
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

from scripts.roof_part_segmentation import run as run_segment_roof

final_footprints = os.path.join(project_ws, "final_footprints")  # Footprints from previous step
output_segments_debug = os.path.join(project_ws, "debug_roof_segments")  # Unique name for debugging

run_segment_roof(
    home_directory=home_directory,
    project_ws=project_ws,
    features=final_footprints,
    dsm=dsm_path,
    spectral_detail=15.5,
    spatial_detail=15,
    minimum_segment_size=10,
    regularization_tolerance="1.5",
    flat_only=False,
    min_slope=10,
    output_segments_ui=output_segments_debug,  # Debug path
    debug=1
)

arcpy.AddMessage(f"Roof segmentation output should be at: {output_segments_debug}")
