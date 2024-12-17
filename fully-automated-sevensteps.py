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
        classify_noise = False
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

        # ---------------------------------------------------------------------------
        # STEP 3: Create Draft Footprint Raster
        # ---------------------------------------------------------------------------
        from scripts.create_building_mosaic import run as run_building_mosaic

        # Get spatial reference from LAS dataset and set up environment
        las_spatial_ref = arcpy.Describe(las_dataset).spatialReference
        arcpy.AddMessage(f"Using spatial reference from LAS dataset: {las_spatial_ref.name}")

        # Set environment settings to ensure consistent processing
        arcpy.env.cellSize = "0.6 Meters"  # Standard cell size for building detection
        arcpy.env.outputCoordinateSystem = las_spatial_ref

        # Set up output locations
        # Intermediate rasters go to a folder, final mosaic goes to geodatabase
        out_folder = os.path.join(testdata_dir, "building_mosaic_rasters")
        if not os.path.exists(out_folder):
            os.makedirs(out_folder)

        # Define the full path for the mosaic dataset in the geodatabase
        out_mosaic = os.path.join(project_ws, "building_mosaic")

        # Log important paths for debugging
        arcpy.AddMessage(f"Current workspace: {arcpy.env.workspace}")
        arcpy.AddMessage(f"Output folder for intermediate rasters: {out_folder}")
        arcpy.AddMessage(f"Output mosaic dataset path: {out_mosaic}")

        # Run the building mosaic tool to create initial building footprint raster
        run_building_mosaic(
            home_directory=home_directory,
            project_ws=project_ws,
            in_lasd=las_dataset,
            out_folder=out_folder,
            out_mosaic=out_mosaic,
            spatial_ref=las_spatial_ref,
            cell_size="0.6 Meters",
            debug=debug
        )
        # ---------------------------------------------------------------------------
        # STEP 4: Run Focal Statistics
        # ---------------------------------------------------------------------------
        try:
            arcpy.AddMessage("Running Focal Statistics...")

            # The focal statistics operation helps clean up the building mosaic by smoothing
            # noisy pixels using the predominant value in a 3x3 neighborhood. This reduces
            # fragmentation in the building footprints.

            # Input and output paths should be in the geodatabase for optimal performance
            focal_input = out_mosaic  # Using the mosaic dataset we created
            out_focal = os.path.join(project_ws, "focal_mosaic")

            # Define a 3x3 neighborhood - this size balances detail preservation with noise reduction
            # Small enough to preserve building edges, large enough to remove isolated pixels
            neighborhood = NbrRectangle(3, 3, "CELL")
            statistics_type = "MAJORITY"  # Uses most common value in neighborhood
            ignore_nodata = "DATA"  # Only considers valid data cells in calculations

            # Run Focal Statistics to smooth the building raster
            # This helps create more coherent building shapes by removing noise
            focal_result = FocalStatistics(
                in_raster=focal_input,
                neighborhood=neighborhood,
                statistics_type=statistics_type,
                ignore_nodata=ignore_nodata
            )

            # Save the result to the geodatabase - this will be our input for footprint creation
            focal_result.save(out_focal)
            arcpy.AddMessage("Focal Statistics completed successfully")

        except arcpy.ExecuteError:
            arcpy.AddError("Error in Focal Statistics:")
            arcpy.AddError(arcpy.GetMessages(2))
            raise
        except Exception as e:
            arcpy.AddError(f"An unexpected error occurred in Focal Statistics: {str(e)}")
            raise

        # ---------------------------------------------------------------------------
        # STEP 5: Create footprints from raster
        # ---------------------------------------------------------------------------
        from scripts.footprints_from_raster import run as run_footprints_from_raster

        arcpy.AddMessage("Creating footprints from raster...")

        # Define input/output paths - using full paths ensures reliability
        in_focal_raster = os.path.join(project_ws, "focal_mosaic")
        output_poly = os.path.join(project_ws, "final_footprints")

        # Log paths for debugging purposes
        arcpy.AddMessage(f"Input focal raster path: {in_focal_raster}")
        arcpy.AddMessage(f"Output footprints path: {output_poly}")

        # Set parameters based on ESRI's recommended workflow
        # These parameters have been optimized for typical building characteristics
        min_area = "32 SquareMeters"  # Minimum size to be considered a building
        simplify_tolerance = "1.5 Meters"  # Balance between detail and generalization

        # Parameters for circle detection and building size categories
        reg_circles = True  # Enable circular building detection
        circle_min_area = "4000 SquareFeet"  # Size threshold for circular buildings
        min_compactness = 0.85  # How circular a shape needs to be (0-1)
        circle_tolerance = "10 Feet"  # Tolerance for circle regularization

        # Define parameters for different building size categories
        # Each category gets appropriate regularization settings
        lg_reg_method = "ANY_ANGLE"  # Large buildings can have any orientation
        lg_min_area = "25000 SquareFeet"
        lg_tolerance = "2 Feet"

        med_reg_method = "RIGHT_ANGLES_AND_DIAGONALS"  # Medium buildings prefer standard angles
        med_min_area = "5000 SquareFeet"
        med_tolerance = "4 Feet"

        sm_reg_method = "RIGHT_ANGLES"  # Small buildings are simplified to right angles
        sm_tolerance = "4 Feet"

        try:
            # Verify input raster exists before processing
            if not arcpy.Exists(in_focal_raster):
                arcpy.AddError(f"Input focal raster does not exist: {in_focal_raster}")
                raise ValueError(f"Input raster not found: {in_focal_raster}")

            # Run the footprints extraction tool
            run_footprints_from_raster(
                home_directory=home_directory,
                project_ws=project_ws,
                in_raster=in_focal_raster,
                min_area=min_area,
                split_features="",  # Optional parameter for splitting complex buildings
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

        except arcpy.ExecuteError as e:
            arcpy.AddError(f"ArcPy error in footprints creation: {str(e)}")
            arcpy.AddError(arcpy.GetMessages(2))
            raise
        except Exception as e:
            arcpy.AddError(f"Error in footprints creation: {str(e)}")
            raise

        # ---------------------------------------------------------------------------
        # STEP 6: Segment Roofs
        from scripts.roof_part_segmentation import run as run_segment_roof

        arcpy.AddMessage("Starting roof segmentation process...")

        # Set up paths
        roof_segments_folder = os.path.join(home_directory, "roof_forms")
        if not os.path.exists(roof_segments_folder):
            os.makedirs(roof_segments_folder)
            arcpy.AddMessage(f"Created roof forms folder at: {roof_segments_folder}")

        # Define inputs and outputs
        dsm_path = os.path.join(project_ws, "elev_dsm")
        roof_segments = os.path.join(project_ws, "roof_segments")

        try:
            # Run segmentation with parameters matching the tool's expected types
            run_segment_roof(
                home_directory=home_directory,
                project_ws=project_ws,
                features=output_poly,  # Path to footprints
                dsm=dsm_path,  # Path to DSM
                spectral_detail="15.5",  # Keep as string
                spatial_detail="15",  # Keep as string
                minimum_segment_size=10,  # Number (not string)
                regularization_tolerance="1.5",  # Keep as string
                flat_only=False,  # Boolean (not string)
                min_slope=10,  # Number (not string)
                output_segments_ui=roof_segments,
                debug=1  # Number
            )

            # Verify outputs
            segmented_output = roof_segments + "_segmented"
            if not arcpy.Exists(segmented_output):
                arcpy.AddError(f"Segmentation failed to create output: {segmented_output}")
                raise ValueError("Segmentation output not created")

            # Expected intermediate outputs in Analysis.gdb
            analysis_outputs = ['clip_dsm', 'clip_slope', 'sms_dsm']
            analysis_gdb = os.path.join(home_directory, "Analysis.gdb")
            for output in analysis_outputs:
                if not arcpy.Exists(os.path.join(analysis_gdb, output)):
                    arcpy.AddWarning(f"Note: Expected intermediate output not found: {output}")

            arcpy.AddMessage("Roof segmentation completed successfully")

        except arcpy.ExecuteError as e:
            arcpy.AddError(f"ArcPy error in roof segmentation: {str(e)}")
            arcpy.AddError(arcpy.GetMessages(2))
            raise
        except Exception as e:
            arcpy.AddError(f"Error in roof segmentation: {str(e)}")
            raise

        # ---------------------------------------------------------------------------
        # ---------------------------------------------------------------------------
        # STEP 7: Extract Roof Forms
        # ---------------------------------------------------------------------------
        from scripts.extract_roof_form import run as run_extract_roof_form

        arcpy.AddMessage("Starting roof form extraction...")

        # The input is the segmented output from Step 6
        segmented_roofs = os.path.join(project_ws, "roof_segments_segmented")

        # Define paths to our elevation surfaces
        dsm_path = os.path.join(project_ws, "elev_dsm")
        dtm_path = os.path.join(project_ws, "elev_dtm")
        ndsm_path = os.path.join(project_ws, "elev_ndsm")

        # Define output path
        output_roofforms = os.path.join(project_ws, "roof_forms")

        # Log our paths
        arcpy.AddMessage(f"Input segmented roofs path: {segmented_roofs}")
        arcpy.AddMessage(f"Output roof forms path: {output_roofforms}")

        try:
            # Verify inputs exist
            if not arcpy.Exists(segmented_roofs):
                arcpy.AddError(f"Segmented roofs file not found at: {segmented_roofs}")
                raise ValueError(f"Input segmented roofs file not found: {segmented_roofs}")

            # Run roof form extraction with parameters matching tool expectations
            run_extract_roof_form(
                home_directory=home_directory,
                project_ws=project_ws,
                buildings_layer=segmented_roofs,  # Feature layer/path
                dsm=dsm_path,  # Path as string
                dtm=dtm_path,  # Path as string
                ndsm=ndsm_path,  # Path as string
                flat_roofs=False,  # Boolean value
                min_flat_roof_area="32",  # String
                min_slope_roof_area="32",  # String
                min_roof_height="0.5",  # String
                output_buildings=output_roofforms,  # Path as string
                simplify_buildings="true",  # String (not boolean)
                simplify_tolerance="0.3",  # String
                debug=1  # Number
            )

            # Verify the output was created
            if not arcpy.Exists(output_roofforms):
                arcpy.AddError(f"Roof form extraction failed to create output: {output_roofforms}")
                raise ValueError("Roof form output not created")

            arcpy.AddMessage("Roof form extraction completed successfully")

        except arcpy.ExecuteError as e:
            arcpy.AddError(f"ArcPy error in roof form extraction: {str(e)}")
            arcpy.AddError(arcpy.GetMessages(2))
            raise
        except Exception as e:
            arcpy.AddError(f"Error in roof form extraction: {str(e)}")
            raise

    # These are the except blocks for the main try block that started at the beginning of main()
    except arcpy.ExecuteError:
        arcpy.AddError("Error in process:")
        arcpy.AddError(arcpy.GetMessages(2))
    except Exception as e:
        arcpy.AddError(f"An unexpected error occurred: {str(e)}")

if __name__ == "__main__":
    main()