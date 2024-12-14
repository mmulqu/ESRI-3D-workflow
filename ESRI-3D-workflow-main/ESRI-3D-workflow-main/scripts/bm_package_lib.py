# -------------------------------------------------------------------------------
# Name:        package_lib
# Purpose:     Contains functions for packaging
#
# Author:      Gert van Maren
#
# Created:     14/12/2019
# Copyright:   (c) Esri 2019
# updated:
# updated:
# updated:

# -------------------------------------------------------------------------------

import arcpy
import os
import sys


# Constants
NON_GP = "non-gp"
ERROR = "error"
WARNING = "warning"


def set_data_paths_for_packaging(data_dir, gdb, fc, model_dir, pf,
                                 table_dir, table,
                                 lidar_dir, las_file,
                                 rule_dir, rule, settings_dir, sf,
                                 layer_dir, lf,
                                 task_dir, task_file,
                                 script_dir, script_file,
                                 ddd_script_dir, ddd_script_file,
                                 scripts_sub, scripts_sub_file):
    try:
        script_path = sys.path[0]
#        this_folder = os.path.dirname(script_path)
        this_folder = script_path
        data_path = os.path.join(this_folder, data_dir)
        one_fc = os.path.join(data_path, gdb, fc)

        model_path = os.path.join(this_folder, model_dir)
        one_modelfile = os.path.join(model_path, pf)

        table_path = os.path.join(this_folder, table_dir)
        one_tablefile = os.path.join(table_path, table)

        lidar_path = os.path.join(this_folder, lidar_dir)
        one_lasfile = os.path.join(lidar_path, las_file)

        rule_path = os.path.join(this_folder, rule_dir)
        one_rulefile = os.path.join(rule_path, rule)

        settings_path = os.path.join(this_folder, settings_dir)
        one_settingfile = os.path.join(settings_path, sf)

        layer_path = os.path.join(this_folder, layer_dir)
        one_layerfile = os.path.join(layer_path, lf)

        task_path = os.path.join(this_folder, task_dir)
        one_taskfile = os.path.join(task_path, task_file)

        script_extra_path = os.path.join(this_folder, script_dir)
        one_scriptfile = os.path.join(script_extra_path, script_file)

        ddd_script_extra_path = os.path.join(this_folder, ddd_script_dir)
        one_ddd_scriptfile = os.path.join(ddd_script_extra_path, ddd_script_file)

        sub_script_extra_path = os.path.join(this_folder, ddd_script_dir, scripts_sub)
        one_sub_scriptfile = os.path.join(sub_script_extra_path, scripts_sub_file)

    except arcpy.ExecuteWarning:
        arcpy.AddWarning(arcpy.GetMessages(1))

    except arcpy.ExecuteError:
        arcpy.AddError(arcpy.GetMessages(2))

    # Return any other type of error
    except:
        # By default any other errors will be caught here
        #
        e = sys.exc_info()[1]
        print((e.args[0]))
        arcpy.AddError(e.args[0])


def rename_file_extension(data_dir, from_extension, to_extension):
    try:
        files = os.listdir(data_dir)
        for filename in files:
            infilename = os.path.join(data_dir, filename)
            if os.path.isfile(infilename):
                file_ext = os.path.splitext(filename)[1]
                if from_extension == file_ext:
                    newfile = infilename.replace(from_extension, to_extension)
                    if not os.path.isfile(newfile):
                        os.rename(infilename, newfile)

    except arcpy.ExecuteWarning:
        arcpy.AddWarning(arcpy.GetMessages(1))

    except arcpy.ExecuteError:
        arcpy.AddError(arcpy.GetMessages(2))

    # Return any other type of error
    except:
        # By default any other errors will be caught here
        #
        e = sys.exc_info()[1]
        print((e.args[0]))
        arcpy.AddError(e.args[0])
