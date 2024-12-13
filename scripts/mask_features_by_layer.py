import arcpy
import os
import sys
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


class NoFeatures(Exception):
    pass


def SetDefinitionQuery(project, input_features, def_query):
    try:
        outahere = False
        for m in project.listMaps():
            if m.mapType == "SCENE":
                for lyr in m.listLayers():
                    if lyr.name == bm_common_lib.get_name_from_feature_class(input_features):
                        if lyr.isFeatureLayer:
                            lyr.definitionQuery = def_query
                            outahere = True
                            break
                        else:
                            arcpy.AddMessage("Layer: " + bm_common_lib.get_name_from_feature_class(input_features) +
                                             " does NOT support definition queries...")
            if outahere:
                break


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


def MaskLayerByLayers(scratch_ws, input_layer, featureclass, selectFeatures):
    try:
        # variables
        inputLayer = "input_lyr"
        selectLayer = "select_lyr"

        # Make a layer
        arcpy.MakeFeatureLayer_management(input_layer, inputLayer)
        arcpy.SelectLayerByAttribute_management(inputLayer, "CLEAR_SELECTION")

        markField = "mark"
        input_count = 0

        # delete/add marking field for definition query
        bm_common_lib.delete_add_field(featureclass, markField, "SHORT")
        arcpy.CalculateField_management(featureclass, markField, "0", "PYTHON_9.3")

        goahead = 1

        for layer in selectFeatures:
            arcpy.MakeFeatureLayer_management(layer, selectLayer)
            arcpy.SelectLayerByAttribute_management(selectLayer, "CLEAR_SELECTION")

            layer_footprint = os.path.join(scratch_ws, "layer_footprint")
            if arcpy.Exists(layer_footprint):
                arcpy.Delete_management(layer_footprint)

            # check if multipatch
            input_type = arcpy.Describe(layer).shapetype

            if input_type == "MultiPatch":
                # create footprint layer for select by location ( 3d model sometimes fails)
                arcpy.ddd.MultiPatchFootprint(layer, layer_footprint)
            else:
                if input_type == "Polyline" or input_type == "Point":
                    result = arcpy.Buffer_analysis(layer, layer_footprint, 1)
                else:
                    goahead = 0;
                    arcpy.AddMessage(bm_common_lib.get_name_from_feature_class(layer)+
                                     " is not a supported geometry type, ignoring for masking...")

            if goahead == 1:
                arcpy.AddMessage("Selecting features that intersect with " +
                                 bm_common_lib.get_name_from_feature_class(layer))
                arcpy.SelectLayerByLocation_management(input_layer,"INTERSECT",layer_footprint, "", "NEW_SELECTION")
                arcpy.AddMessage("SelectByLocation done...")
                arcpy.CalculateField_management(input_layer, markField, "1", "PYTHON_9.3")
                result = arcpy.GetCount_management(input_layer)
                input_count = input_count + int(result.getOutput(0))
                arcpy.SelectLayerByAttribute_management(input_layer, "CLEAR_SELECTION")
            else:
                goahead = 1

        arcpy.AddMessage(str(input_count)+" features in the " +
                         bm_common_lib.get_name_from_feature_class(featureclass)+" layer will be hidden.")

    except arcpy.ExecuteWarning:
        print(arcpy.GetMessages(1))
        arcpy.AddWarning(arcpy.GetMessages(1))

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


def mask_features_by_layer(input_features, list_of_select_features, verbose):
    # Start Main Process
    try:
        aprx = arcpy.mp.ArcGISProject("CURRENT")
        clear_query = ""
        SetDefinitionQuery(aprx, input_features, clear_query)

        arcpy.AddMessage("Definition query cleared...")

        # Create and set workspace location in same directory as input feature class gdb
        workspacePath = bm_common_lib.get_work_space_from_feature_class(input_features.dataSource, "no")
        scratch_ws = bm_common_lib.create_gdb(workspacePath, "Intermediate.gdb")
        arcpy.env.workspace = scratch_ws
        arcpy.env.overwriteOutput = True

        MaskLayerByLayers(scratch_ws, input_features, input_features.dataSource, list_of_select_features)

        def_query = "mark = 0"
        SetDefinitionQuery(aprx, input_features, def_query)

    except arcpy.ExecuteWarning:
        arcpy.AddWarning(arcpy.GetMessages(1))

    except arcpy.ExecuteError:
        arcpy.AddError(arcpy.GetMessages(2))


def run(home_directory, project_ws, input_features, list_of_select_features, debug):
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
                    if arcpy.Exists(input_features):

                        # go to main function
                        mask_features_by_layer(input_features, list_of_select_features, verbose)

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

