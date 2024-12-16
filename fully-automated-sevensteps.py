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
        # ---------------------------------------------------------------------------
        # After creating basic building footprints, we now analyze the roof structures.
        # This step uses the DSM (showing roof shapes) and our footprints to identify
        # distinct roof segments based on elevation patterns.

        from scripts.roof_part_segmentation import run as run_segment_roof
        dsm_path = str(os.path.join(project_ws, "elev_dsm"))
        arcpy.AddMessage("Segmenting roofs...")

        # Reference the elevation surfaces we created in Step 2
        # The DSM captures roof shapes, while nDSM shows height above ground
        dsm_path = os.path.join(project_ws, "elev_dsm")
        dtm_path = os.path.join(project_ws, "elev_dtm")
        ndsm_path = os.path.join(project_ws, "elev_ndsm")

        # Define output path for the segmented roof features
        output_segments = os.path.join(project_ws, "roof_segments")

        # Log our paths for debugging
        arcpy.AddMessage(f"Using DSM from: {dsm_path}")
        arcpy.AddMessage(f"Using nDSM from: {ndsm_path}")
        arcpy.AddMessage(f"Output segments path: {output_segments}")

        # Set segmentation parameters based on ESRI recommendations
        # These parameters control how finely we divide roof surfaces
        spectral_detail = 15.5  # Controls sensitivity to elevation changes
        spatial_detail = 15  # Controls minimum segment size
        min_segment_size = 10  # Minimum number of cells for a valid segment

        try:
            # Run the roof segmentation process
            # This tool analyzes elevation patterns to identify distinct roof planes
            # Run the roof segmentation process
            # STEP 6: Segment Roofs
            # Fix in Roof Segmentation Parameters
            # Define the path to the final footprints from the previous step
            final_footprints = os.path.join(project_ws, "final_footprints")  # Fully qualified path

            # Output path for segmented roofs
            output_segments = os.path.join(project_ws, "roof_segments")

            # Call the roof segmentation function
            run_segment_roof(
                home_directory=home_directory,
                project_ws=project_ws,
                features=final_footprints,  # Use the full feature path here
                dsm=dsm_path,
                spectral_detail=15.5,
                spatial_detail=15,
                minimum_segment_size=10,
                regularization_tolerance="1.5",
                flat_only=False,
                min_slope=10,
                output_segments_ui=output_segments,
                debug=debug
            )

            arcpy.AddMessage("Roof segmentation completed successfully")

        except arcpy.ExecuteError as e:
            arcpy.AddError(f"ArcPy error in roof segmentation: {str(e)}")
            arcpy.AddError(arcpy.GetMessages(2))
            raise
        except Exception as e:
            arcpy.AddError(f"Error in roof segmentation: {str(e)}")
            raise

        # ---------------------------------------------------------------------------
        # STEP 7: Extract Roof Forms
        # ---------------------------------------------------------------------------
        # This final step analyzes the roof segments to determine overall roof shape
        # (e.g., gabled, hipped, flat) and calculates key measurements like height
        # and slope direction.

        from scripts.extract_roof_form import run as run_extract_roof_form

        arcpy.AddMessage("Extracting roof forms...")

        # Define output path for the final roof form features
        output_roofforms = os.path.join(project_ws, "roof_forms")

        # Log key information for debugging
        arcpy.AddMessage(f"Input segments path: {output_segments}")
        arcpy.AddMessage(f"Output roof forms path: {output_roofforms}")

        try:
            # Run the roof form extraction
            # Ensure all parameters are initialized and converted to strings
            min_flat_roof_area = str(min_flat_roof_area or "32")
            min_slope_roof_area = str(min_slope_roof_area or "32")
            min_roof_height = str(min_roof_height or "0.5")
            simplify_tolerance = str(simplify_tolerance or "0.3")

            # Add debug messages
            arcpy.AddMessage(f"Using min_flat_roof_area: {min_flat_roof_area}")
            arcpy.AddMessage(f"Using min_slope_roof_area: {min_slope_roof_area}")
            arcpy.AddMessage(f"Using min_roof_height: {min_roof_height}")
            arcpy.AddMessage(f"Using simplify_tolerance: {simplify_tolerance}")

            # Call the roof form extraction
            run_extract_roof_form(
                home_directory=home_directory,
                project_ws=project_ws,
                buildings_layer=f"{output_segments}_segmented",
                dsm=dsm_path,
                dtm=dtm_path,
                ndsm=ndsm_path,
                flat_roofs=False,
                min_flat_roof_area=min_flat_roof_area,
                min_slope_roof_area=min_slope_roof_area,
                min_roof_height=min_roof_height,
                output_buildings=output_roofforms,
                simplify_buildings=True,
                simplify_tolerance=simplify_tolerance,
                debug=debug
            )

            arcpy.AddMessage("Roof form extraction completed successfully")

        except arcpy.ExecuteError as e:
            arcpy.AddError(f"ArcPy error in roof form extraction: {str(e)}")
            arcpy.AddError(arcpy.GetMessages(2))
            raise
        except Exception as e:
            arcpy.AddError(f"Error in roof form extraction: {str(e)}")
            raise

    except arcpy.ExecuteError:
        arcpy.AddError("Error in process:")
        arcpy.AddError(arcpy.GetMessages(2))
    except Exception as e:
        arcpy.AddError(f"An unexpected error occurred: {str(e)}")


if __name__ == "__main__":
    main()