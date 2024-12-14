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


def set_texture_quality_attribute(buildings, image_reduction, verbose):
    # MAIN
    try:
        # variables
        field = "ImageReduction"
        fieldtype = "SHORT"
        HFfield = "Units"
        HFfieldtype = "TEXT"
        eaveHeight = "EAVEHEIGHT"

        desc = arcpy.Describe(buildings)

        if desc.shapeType == "MultiPatch":
            if bm_common_lib.field_exist(buildings, eaveHeight):
                # Create and set workspace location in same directory as input feature class gdb
                workspacePath = bm_common_lib.get_work_space_from_feature_class(buildings, "no")
                scratch_ws = bm_common_lib.create_gdb(workspacePath, "Intermediate.gdb")
                arcpy.env.workspace = scratch_ws
                arcpy.env.overwriteOutput = True

                # get selected features
                desc = arcpy.Describe(buildings)
                oid_fieldname = desc.OIDFieldName
                selection = desc.FIDset
                sel_char = len(selection)
                selection = selection.replace("'", "")
                selection = selection.replace(";", ",")
                sel_count = len(desc.fidSet.split(";"))

                zUnits = bm_common_lib.get_z_unit(buildings, verbose)

                # add HeightFactor field
                if not bm_common_lib.field_exist(buildings, HFfield):
                    result = arcpy.AddField_management(buildings, HFfield, HFfieldtype)

                if zUnits == "Feet":
                    arcpy.CalculateField_management(buildings, HFfield, "'Feet'", "PYTHON_9.3", None)
                else:
                    arcpy.CalculateField_management(buildings, HFfield, "'Meters'", "PYTHON_9.3", None)

                # add Image Reduction attribute field
                if not bm_common_lib.field_exist(buildings, field):
                    result = arcpy.AddField_management(buildings, field, fieldtype)

                    # calculate field to zero
                    arcpy.CalculateField_management(buildings, field, 1, "PYTHON_9.3", None)

                    #reset selection
                    if sel_count > 0 and sel_char > 0:
                        query = """{0} IN ({1})""".format(arcpy.AddFieldDelimiters(buildings, oid_fieldname),selection)
                        arcpy.AddMessage(query)
                        arcpy.SelectLayerByAttribute_management(buildings, "NEW_SELECTION", query)

                # calculate field based on selection
                arcpy.CalculateField_management(buildings, field, int(image_reduction), "PYTHON_9.3", None)
                return True
            else:
                arcpy.AddError("The input layer needs to have an " + eaveHeight + " attribute. ")
                return False
        else:
            arcpy.AddError("The input layer needs to be a multipatch feature class")
            return False

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



def run(home_directory, project_ws, buildings, image_reduction, debug):
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
                    if arcpy.Exists(buildings):

                        # go to main function
                        success = set_texture_quality_attribute(buildings, image_reduction, verbose)

                        if success:
                            msg_body = create_msg_body("set_texture_quality_attribute completed successfully.", 0, 0)
                            msg(msg_body)
                        else:
                            msg_body = create_msg_body("Error. Exiting...", 0, 0)
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
