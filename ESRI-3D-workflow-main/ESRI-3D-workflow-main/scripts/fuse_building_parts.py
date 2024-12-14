import arcpy

import os
from scripts import bm_common_lib
from scripts.bm_common_lib import create_msg_body, msg, trace

# constants
TOOLNAME = "fuse_building_parts"
WARNING = "warning"
ERROR = "error"


class FunctionError(Exception):

    """
    Raised when a function fails to run.
    """

    pass


class StringHasSpace(Exception):
    pass


class HasSpace(Exception):
    pass


class LicenseError3D(Exception):
    pass


class LicenseErrorSpatial(Exception):
    pass


def fuse_buildings_parts(input_layer, grouping_field, outp_mp):
    try:
        aprx = arcpy.mp.ArcGISProject('CURRENT')
        mapType = aprx.activeMap.mapType
        mapName = aprx.activeMap.name
        lgs_name = "3D Basemap"

        desc = arcpy.Describe(input_layer)

        if desc.shapeType == "Polygon":
            # check if in edit session
            workspace = os.path.dirname(bm_common_lib.get_full_path_from_layer(input_layer))

            # Start an edit session. Must provide the workspace.
            edit = arcpy.da.Editor(workspace)

            if not edit.isEditing:
                if mapType == "SCENE":
                    if mapName != lgs_name:
                        arcpy.AddMessage("Make sure you run this tool in a SCENE view with the Output "
                                         "Building Polygon layer you used in the Create LOD2 Buildings task.")

                    arcpy.AddMessage("De-selecting...")
                    arcpy.SelectLayerByAttribute_management(input_layer, "CLEAR_SELECTION")

                    # convert lyr to multipatch
                    arcpy.AddMessage("Converting layer to multipatch")
                    # inputMP =  os.path.join(arcpy.Describe(inputLyr).path, "shells4Union")
                    outputMP = os.path.join(arcpy.Describe(input_layer).path, outp_mp)
                    arcpy.Layer3DToFeatureClass_3d(input_layer, outputMP, grouping_field)

                    # Join Original fields
                    joinOrigFields(outputMP, input_layer, grouping_field, grouping_field)
                    arcpy.AddMessage("Completed.")
                    return outp_mp
                else:
                    arcpy.AddError("The active view is a 2D map. Make sure you run this tool in a SCENE view with the "
                                   "Output Building Polygon layer you used in the Create LOD2 Buildings task.")
                    return None
            else:
                arcpy.AddWarning("ArcGIS Pro has in an edit session. Please save your changes first!")
                return None
        elif desc.shapeType == "MultiPatch":
            arcpy.AddMessage("Layer type is multipatch, no fusion applied.")
            return None
        else:
            arcpy.AddError("Layer type must be polygon!")
            return None

    except Exception as err:
        arcpy.AddError(err)


def joinOrigFields(origFC, newFC, origJoinField, newJoinField):
    try:
        origFields = [f.name for f in arcpy.ListFields(origFC)]
        newFields = [f.name for f in arcpy.ListFields(newFC)]
        joinList = [item for item in origFields if item not in newFields]

        # Join fields to original feature class
        result = arcpy.JoinField_management(origFC, origJoinField, newFC, newJoinField, joinList)

    except Exception as err:
        arcpy.AddWarning("ArcGIS Pro has in an edit session. Please save your changes first!")
        arcpy.AddError(err)


def run(home_directory, project_ws, input_layer, grouping_field,
                        output_mp, debug):
    try:
        if debug == 1:
            delete_intermediate_data = False
            verbose = 1
        else:
            delete_intermediate_data = True
            verbose = 0

        if os.path.exists(os.path.join(home_directory, "p20")):  # it is a package
            home_directory = os.path.join(home_directory, "p20")

        arcpy.AddMessage("Project Home Directory is: " + home_directory)

        for a in home_directory:
            if a.isspace():
                raise HasSpace

        if bm_common_lib.check_directory(home_directory):
            arcpy.env.overwriteOutput = True

            if arcpy.CheckExtension("3D") == "Available":
                arcpy.CheckOutExtension("3D")

                if arcpy.CheckExtension("Spatial") == "Available":
                    arcpy.CheckOutExtension("Spatial")

                    # check if input exists
                    if arcpy.Exists(input_layer):

                        # go to main function
                        out_put_features = fuse_buildings_parts(input_layer, grouping_field, output_mp)

                        if out_put_features:
                                msg_body = create_msg_body("fuse_building_parts completed successfully.", 0, 0)
                                msg(msg_body)
                        else:
                            msg_body = create_msg_body("No fusing. Exiting...", 0, 0)
                            msg(msg_body, WARNING)

                        arcpy.ClearWorkspaceCache_management()

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
