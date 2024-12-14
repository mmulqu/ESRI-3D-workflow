__author__ = "Gert van Maren"

import arcpy
from string import Template
import urllib.parse
import sys
import traceback
import time
import datetime as dt
import os
import json
import logging
import math
import requests
from itertools import islice
import scripts_uc.uc_settings as uc_settings
from arcgis.geometry import Geometry
import importlib
from scripts_uc.uc_settings import *
importlib.reload(uc_settings)  # force reload of the module

# Constants
NON_GP = "non-gp"
ERROR = "error"
WARNING = "warning"
in_memory_switch = True


# item_data class
class QueryFailed(Exception):
    pass


class ItemData(object):
    def __init__(self, data):
        self.__dict__ = json.loads(data)


class UrbanModel(object):
    def __init__(self, owner, model_name, model_id, version, folder_id, model_title, master_id, urban_api_url,
                 creation_date):
        self.owner = owner
        self.model_name = model_name
        self.model_id = model_id
        self.version = version
        self.folder_id = folder_id
        self.model_title = model_title
        self.master_id = master_id
        self.urban_api_url = urban_api_url
        self.creation_date = creation_date


class UrbanEvent20(object):
    def __init__(self, urban_model, master_id, global_id, event_name, scene_id, owner_name,
                 event_type, geometry, access):
        self.urban_model = urban_model
        self.master_id = master_id
        self.global_id = global_id
        self.event_name = event_name
        self.scene_id = scene_id
        self.owner_name = owner_name
        self.event_type = event_type
        self.geometry = geometry
        self.access = access


class UrbanEvent(object):
    def __init__(self, urban_model, master_id, global_id, event_name, event_type, scene_id):
        self.urban_model = urban_model
        self.master_id = master_id
        self.global_id = global_id
        self.event_name = event_name
        self.event_type = event_type
        self.scene_id = scene_id


class UrbanDesign(object):
    def __init__(self, urban_model, design_id, urban_model_id, design_type, title, owner, url):
        self.urban_model = urban_model
        self.design_id = design_id
        self.urban_model_id = urban_model_id
        self.design_type = design_type
        self.title = title
        self.owner = owner
        self.url = url


class Scenario(object):
    def __init__(self, urban_model, event, global_id, branch_name, context_webscene_id, webscene_id):
        self.urban_model = urban_model
        self.event = event
        self.global_id = global_id
        self.branch_name = branch_name
        self.context_webscene_id = context_webscene_id
        self.webscene_id = webscene_id


class Indicator(object):
    def __init__(self, urban_model, global_id, indicator_name, webscene_id):
        self.urban_model = urban_model
        self.global_id = global_id
        self.indicator_name = indicator_name
        self.webscene_id = webscene_id


class ZoneType(object):
    def __init__(self, urban_model, global_id, allowed_space_use_types, color):
        self.urban_model = urban_model
        self.global_id = global_id
        self.allowed_space_use_types = allowed_space_use_types
        self.color = color


class UrbanFeature(object):
    def __init__(self, geometry, attributes):
        self.geometry = geometry
        self.attributes = attributes


class FunctionError(Exception):

    """
    Raised when a function fails to run.
    """

    pass


def trace(*arg):

    """
    Trace finds the line, the filename
    and error message and returns it
    to the user
    """

    tb = sys.exc_info()[2]
    tbinfo = traceback.format_tb(tb)[0]

    # script name + line number
    line = tbinfo.split(", ")[1]

    # Get Python syntax error
    synerror = traceback.format_exc().splitlines()[-1]

    if len(arg) == 0:
        return line, __file__, synerror
    else:
        return line, arg[1], synerror


def msg(*arg):

    # Utility method that writes a logging info statement, a print statement and an
    # arcpy.AddMessage() statement all at once.
    if len(arg) == 1:
        logging.info(str(arg[0]) + "\n")
        arcpy.AddMessage(str(arg[0]))
    elif arg[1] == ERROR:
        logging.error(str(arg[0]) + "\n")
        arcpy.AddError(str(arg[0]))
    elif arg[1] == WARNING:
        logging.warning(str(arg[0]) + "\n")
        arcpy.AddWarning(str(arg[0]))
    elif arg[1] == NON_GP:
        logging.info(str(arg[0]) + "\n")
        arcpy.AddMessage(str(arg[0]))
#    print(str(arg[0]))

    return


def create_msg_body(msg_prefix, start_time, end_time):

    # Creates the message returned after each run of a function (successful or unsuccessful)
    diff = end_time - start_time

    if diff > 0:
        if msg_prefix == "":
            msg_prefix = "Elapsed time: "
        else:
            msg_prefix = msg_prefix + "  Elapsed time: "

        elapsed_time_mins = int(math.floor(diff/60))
        minutes_txt = " minutes "
        if elapsed_time_mins == 1:
            minutes_txt = " minute "
        if elapsed_time_mins > 0:
            elapsed_time_secs = int(round(diff - (60 * elapsed_time_mins)))
            seconds_txt = " seconds."
            if elapsed_time_secs == 1:
                seconds_txt = " second."
            elapsed_time_formatted = str(elapsed_time_mins) + minutes_txt + str(elapsed_time_secs) + seconds_txt
        else:
            elapsed_time_secs = round(diff - (60 * elapsed_time_mins), 2)
            seconds_txt = " seconds."
            if elapsed_time_secs == 1:
                seconds_txt = " second."
            elapsed_time_formatted = str(elapsed_time_secs) + seconds_txt

        msg_body = msg_prefix + elapsed_time_formatted

    else:
        msg_body = msg_prefix

    return msg_body


def log_message(in_file, message):
    directory = os.path.dirname(in_file)
    if not os.path.exists(directory):
        os.makedirs(directory)

    text_file = open(in_file, "a")
    text_file.write(message + "\n")
    text_file.close()


def set_up_logging(output_folder, file):

    arcpy.AddMessage("Executing set_up_logging...")
    start_time = time.perf_counter()

    try:
        # Make the 'logs' folder if it doesn't exist
        log_location = output_folder
        if not os.path.exists(log_location):
            os.makedirs(log_location)

        # Set up logging
        logging.getLogger('').handlers = []  # clears handlers
        date_prefix = dt.datetime.now().strftime('%Y%m%d_%H%M')

        log_file_date = os.path.join(log_location, file + "_" + date_prefix + ".log")
        log_file = os.path.join(log_location, file + ".log")
        log_file_name = log_file
        date_prefix = date_prefix + "\t"  # Inside messages, an extra tab to separate date and any following
                                          # text is desirable

        if os.path.exists(log_file):
            try:
                os.access(log_file, os.R_OK)
                log_file_name = log_file
            except FunctionError:
                log_file_name = log_file_date

        logging.basicConfig(level=logging.INFO,
                            filename=log_file_name,
                            format='%(asctime)s %(message)s',
                            datefmt='%Y-%m-%d %H:%M:%S')

        msg("Logging set up.  Log location: " + log_location)

        failed = False

    except:
        failed = True
        raise

    finally:
        if failed:
            msg_prefix = "An exception was raised in set_up_logging."
            end_time = time.perf_counter()
            msg_body = create_msg_body(msg_prefix, start_time, end_time)
            msg(msg_body, ERROR)


def chunks(data, size):
    it = iter(data)
    for i in range(0, len(data), size):
        yield {k:data[k] for k in islice(it, size)}


def now_dt():
    return int(dt.datetime.now().timestamp()*1000)


def create_gdb(path, name):
    try:
        int_gdb = os.path.join(path, name)

        if not arcpy.Exists(int_gdb):
            arcpy.CreateFileGDB_management(path, name, "CURRENT")
            return int_gdb
        else:
            return int_gdb

    except arcpy.ExecuteWarning:
        print((arcpy.GetMessages(1)))
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


def get_urban_api_url():
    scripts_dir = os.path.dirname(os.path.abspath(__file__))
    home_directory = os.path.dirname(scripts_dir)

    if os.path.exists(os.path.join(home_directory, "p20")):  # it is a package
        home_directory = os.path.join(home_directory, "p20")

    settings_directory = home_directory + "\\settings"

    json_file = os.path.join(settings_directory, "settings_urban.json")

    urban_api_url = None

    if arcpy.Exists(json_file):
        with open(json_file, "r") as content:
            settings_json = json.load(content)
            connection_dict = settings_json.get("connection")
            if connection_dict:
                urban_api_url = connection_dict.get("urban_api_url")

    return urban_api_url


def check_min_version(version, min_version):
    ok = False

    if int(version[0]) >= int(min_version[0]) and \
            int(version[2]) >= int(min_version[2]) and \
            int(version[4]) >= int(min_version[4]) and \
            "alpha" not in version and \
            "beta" not in version:
        ok = True

    return ok


def get_supported_versions():
    scripts_dir = os.path.dirname(os.path.abspath(__file__))
    home_directory = os.path.dirname(scripts_dir)

    if os.path.exists(os.path.join(home_directory, "p20")):  # it is a package
        home_directory = os.path.join(home_directory, "p20")

    settings_directory = home_directory + "\\settings"

    json_file = os.path.join(settings_directory, "settings_urban.json")

    version_list = None

    if arcpy.Exists(json_file):
        with open(json_file, "r") as content:
            settings_json = json.load(content)
            schema_dict = settings_json.get("schema")
            if schema_dict:
                version_list = schema_dict.get("supported_versions")

    return version_list


def get_min_supported_version():
    scripts_dir = os.path.dirname(os.path.abspath(__file__))
    home_directory = os.path.dirname(scripts_dir)

    if os.path.exists(os.path.join(home_directory, "p20")):  # it is a package
        home_directory = os.path.join(home_directory, "p20")

    settings_directory = home_directory + "\\settings"

    json_file = os.path.join(settings_directory, "settings_urban.json")

    min_version = None

    if arcpy.Exists(json_file):
        with open(json_file, "r") as content:
            settings_json = json.load(content)
            schema_dict = settings_json.get("schema")
            if schema_dict:
                min_version = schema_dict.get("min_supported_version")

    return min_version


def get_schema_info(path):
    if path:
        home_directory = path
    else:
        scripts_dir = os.path.dirname(os.path.abspath(__file__))
        home_directory = os.path.dirname(scripts_dir)

    schema = None

    if os.path.exists(os.path.join(home_directory, "p20")):  # it is a package
        home_directory = os.path.join(home_directory, "p20")

    settings_directory = home_directory + "\\settings"

    json_file = os.path.join(settings_directory, "settings_urban.json")

    if arcpy.Exists(json_file):
        with open(json_file, "r") as content:
            settings_json = json.load(content)
            schema_dict_dict = settings_json.get("schema")
            if schema_dict_dict:
                schema = schema_dict_dict

    return schema


def valid_json(myjson):
    try:
        json_object = json.loads(myjson)
    except ValueError as e:
        return False
    return json_object


def get_urban_model_name_item_list(my_list):
    try:
        name_item_list = {}

        if len(my_list) > 0:
            for model in my_list:
                # get model name
                name = between(str(model), "title:", " type").replace('"', '')

                if name:
                    d_entry = {name: model}
                    name_item_list.update(d_entry)

            if len(name_item_list) > 0:
                return name_item_list
            else:
                return None
        else:
            return None

    except:
        raise FunctionError(
            {
                "function": "get_urban_model_name_list"
            }
        )


def get_group_urban_models(gis, grps, query):
    search_result = gis.content.search(query=query, item_type="Urban Model", max_items=-1)
    name_item_list = get_urban_model_name_item_list(search_result)

    # TODO deal with empty list

    if grps:
        lu = {grp.id: grp.title for grp in grps}
        for grpid, name in lu.items():
            q = "orgid:%s" % gis.properties.id
            q += ' type:("Urban Model")'
            q += ' group: %s' % grpid
            group_result = gis.content.advanced_search(query=q, max_items=-1)
            total = group_result['total']
            results = group_result['results']
            if total > 0:
                # add result from each group to name_item_list dictionary
                group_name_item_list = get_urban_model_name_item_list(results)
                temp_dict = dict(list(name_item_list.items()) + list(group_name_item_list.items()))

                name_item_list = temp_dict

    return name_item_list


def get_foldername_user(gis_user, folder_id):
    folder_name = None
    for fld in gis_user.folders:
        if fld['id'] == folder_id:
            folder_name = fld['title']
            break

    return folder_name


def after(value, a):
    # Find and validate first part.
    pos_a = value.rfind(a)
    if pos_a == -1:
        return None

    # Returns chars after the found string.
    adjusted_pos_a = pos_a + len(a)

    if adjusted_pos_a >= len(value):
        return None
    else:
        return value[adjusted_pos_a:]


def between(value, a, b):
    # Find and validate before-part.
    pos_a = value.find(a)
    if pos_a == -1:
        return None
    # Find and validate after part.
    pos_b = value.rfind(b)
    if pos_b == -1:
        return None
    # Return middle part.
    adjusted_pos_a = pos_a + len(a)
    if adjusted_pos_a >= pos_b:
        return None
    else:
        return value[adjusted_pos_a:pos_b]


def before(value, a):
    # Find first part and return slice before it.
    pos_a = value.find(a)
    if pos_a == -1:
        return None
    else:
        return value[0:pos_a]


def convert_string_to_list(string, delimiter, remove_bs, remove_sq):
    if remove_bs:
        string = string.replace("\\", "")
    if remove_sq:
        string = string.replace("'", "")

    li = list(string.split(delimiter))
    return li


def is_layer_url_in_item(item, url):
    try:
        source_url = None
        try:
            source_url = item.sourceUrl
        except:
            pass

        # check if url is the item.url
        if item.url == url:
            return True
        elif source_url:
            if source_url == url:
                return True
        else:  # if not, the url point to a layer in a collection
            item_layers = item.layers
            for lyr in item_layers:
                if lyr.url == url:
                    return True

        # if still not found -> blunt check
        if url in item.url:
            return True
        else:
            return False
    except:
        return False


def SOAP2REST(string):
    if string.find("arcgis/rest/services") == -1 or string.find("ArcGIS/rest/services") == -1:
        if string.find("arcgis/services") != -1:
            string2 = string.replace("arcgis/services", "arcgis/rest/services")
            return string2
        elif string.find("ArcGIS/services") != -1:
            string2 = string.replace("ArcGIS/services", "ArcGIS/rest/services")
            return string2
        else:
            return string
    else:
        return string


def find_item_in_search_results_by_url(search_result, s_type, name, url):
    s = 0
    item = None
    for i in search_result:
        # check that layer url is in item
        if is_layer_url_in_item(i, url):
            item = i
            break

    return item


def find_item_in_search_results(search_result, s_type, name, url):
    s = 0
    item = None
    for i in search_result:
        if s_type == "Scene Layer" or s_type == "Feature Layer":
            if name in str(i) and s_type in str(i):

                # check that layer url is in item
                if is_layer_url_in_item(i, url):
                    item = i
                    break

        elif s_type == "Raster Layer":
            if name in str(i) and (s_type in str(i) or "Imagery Layer" in str(i)):

                # check that layer url is in item
                if is_layer_url_in_item(i, url):
                    item = i
                    break
        else:
            if name in str(i):
                # check that layer url is in item
                if is_layer_url_in_item(i, url):
                    item = i
                    break
        s += 1

    return item


def get_item_name_from_url(url):
    if len(url) > 0:
        # get everything after services
        after_services = after(url, "rest/services/")
        name_string = before(after_services, "/")
    else:
        name_string = None

    return name_string


def strip_url_to_server(url):
    dirname = url

    while True:
        if len(dirname) > 0:
            basename = os.path.basename(dirname)
            if "Server" in basename:
                break
            else:
                dirname = os.path.dirname(dirname)
        else:
            dirname = url
            break

    return dirname


def search_item_by_url(gis, s_type, name, url):
    # owner search
    result = gis.content.search('url: ' + url, max_items=-1)

    if len(result) > 0:
        the_item = find_item_in_search_results_by_url(result, s_type, name, url)
    else:
        #  remove layers/n from url and try again
        strip_url = strip_url_to_server(url)
        result = gis.content.search('url: ' + strip_url, max_items=-1)
        if len(result) > 0:
            the_item = find_item_in_search_results_by_url(result, s_type, name, strip_url)
        else:
            arcpy.AddMessage("Searching outside your organization...")
            result = gis.content.search('url: ' + url, outside_org=True, max_items=-1)
            if len(result) > 0:
                the_item = find_item_in_search_results_by_url(result, s_type, name, url)
            else:
                #  remove layers/n from url and try again
                result = gis.content.search('url: ' + strip_url, outside_org=True, max_items=-1)

                if len(result) > 0:
                    the_item = find_item_in_search_results_by_url(result, s_type, name, strip_url)
                else:
                    the_item = None

    return the_item


def search_item_by_name(gis, s_type, name, url):
    # owner search
    result = gis.content.search('title: ' + name, max_items=-1)

    if len(result) > 0:
        the_item = find_item_in_search_results(result, s_type, name, url)
    else:
        #  remove layers/n from url and try again
        strip_url = strip_url_to_server(url)
        result = gis.content.search('title: ' + name, max_items=-1)
        if len(result) > 0:
            the_item = find_item_in_search_results(result, s_type, name, strip_url)
        else:
            # search outside org
            arcpy.AddMessage("Searching outside your organization...")
            result = gis.content.search('title: ' + name, outside_org=True, max_items=-1)
            if len(result) > 0:
                the_item = find_item_in_search_results(result, s_type, name, url)
            else:
                #  remove layers/n from url and try again
                result = gis.content.search('title: ' + name, outside_org=True, max_items=-1)

                if len(result) > 0:
                    the_item = find_item_in_search_results_by_url(result, s_type, name, strip_url)
                else:
                    the_item = None

    return the_item


def get_layer_objects(aprx, layer_list):
    try:
        lyr_obj_list = list()
        found_multiple = False

        p = arcpy.mp.ArcGISProject("CURRENT")
        m = p.activeMap

        for lyr in m.listLayers():
            if not lyr.isGroupLayer:
                name = lyr.name
                if os.path.basename(name) in layer_list:
                    # give warning if 2 or more layers found with the same name
                    if len(lyr_obj_list) > 0:
                        for lyr_obj in lyr_obj_list:
                            if os.path.basename(name) == lyr_obj.name:
                                found_multiple = True

                    lyr_obj_list.append(lyr)

        if found_multiple:
            arcpy.AddWarning("Found multiple layers with the same name. Last layer in the Table Of Contents"
                             " will be used in the indicator.")

        return lyr_obj_list

    except:
        raise FunctionError(
            {
                "function": "get_layer_objects"
            }
        )


def get_datasource_lists(lyr_obj_list):
    '''
    gets dictionaries with name, datasource and feature type from layer objects
    :param lyr_obj_list: list of layer objects
    :return: dictionaries with name, datasource and feature type
    '''
    try:

        service_name_url_dict = dict()
        local_name_url_dict = dict()

        for lyr in lyr_obj_list:
            url_type_dict = dict()

            # TODO fix: HACK! sometimes dataSources in Pro are SOAP only so change to REST
            lyr_datasource = SOAP2REST(lyr.dataSource)

            # TODO fix: HACK! sometimes dataSources in Pro are encoded but FeatureLayer(url) does NOT like this
            if "%" in lyr_datasource:
                lyr_datasource = urllib.parse.unquote(lyr_datasource)

            # TODO fix: HACK! sometimes dataSources in Pro have double back slashes
            lyr_datasource = lyr_datasource.replace("\\", "/")

            if lyr.isFeatureLayer:
                url_type_dict[lyr_datasource] = "Feature Layer"
            elif lyr.isRasterLayer:
                url_type_dict[lyr_datasource] = "Raster Layer"
            elif lyr.isSceneLayer:
                url_type_dict[lyr_datasource] = "Scene Layer"
            else:
                url_type_dict[lyr_datasource] = "Unknown"

            # TODO fix: if lyr.isWebLayer: FAILS on some web layers so HACK

            # TODO check on service name if possible!!!
            if "http:" in lyr_datasource or "https:" in lyr_datasource:
                service_name_url_dict[os.path.basename(lyr.name)] = url_type_dict
            else:
                local_name_url_dict[os.path.basename(lyr.name)] = url_type_dict

        return service_name_url_dict, local_name_url_dict

    except:
        raise FunctionError(
            {
                "function": "get_layer_objects"
            }
        )


def get_unique_web_scene_name(gis, name):
    try:
        ext = 0
        ws_name = name + "_" + str(ext)

        while len(gis.content.search(query='title: ' + ws_name, item_type="Web Scene")) > 0:
            ext += 1
            ws_name = name + "_" + str(ext)

        return ws_name

    except:
        raise FunctionError(
            {
                "function": "get_unique_web_scene_name"
            }
        )


def get_name_from_feature_class(feature_class):
    desc_fc = arcpy.Describe(feature_class)
    return desc_fc.name


def get_z_unit(local_lyr):

    start_time = time.perf_counter()

    try:
        sr = arcpy.Describe(local_lyr).spatialReference
        local_unit = 'Meters'

        if sr.VCS:
            unit_z = sr.VCS.linearUnitName
        else:
            unit_z = sr.linearUnitName
            msg_body = ("Could not detect a vertical coordinate system for " + get_name_from_feature_class(local_lyr))
            msg(msg_body)
            msg_body = "Using linear units instead."
            msg(msg_body)

        if unit_z in ('Foot', 'Foot_US', 'Foot_Int'):
            local_unit = 'Feet'
        else:
            local_unit = 'Meters'

        msg_prefix = "Function get_z_unit completed successfully."
        failed = False

        return local_unit

    except:
        line, filename, synerror = trace()
        failed = True
        msg_prefix = ""
        raise FunctionError(
            {
                "function": "get_z_unit",
                "line": line,
                "filename": filename,
                "synerror": synerror,
                "arc": str(arcpy.GetMessages(2))
            }
        )

    finally:
        end_time = time.perf_counter()
        msg_body = create_msg_body(msg_prefix, start_time, end_time)
        if failed:
            msg(msg_body, ERROR)


def run_query(url, query_or_mutation, variables):
    '''
    A simple function to use requests.post to make the API call. Note the json= section.
    :param url:
    :param query:
    :param variables:
    :return:
    '''
    request = requests.post(url, json={'query': query_or_mutation})
    if request.status_code == 200:
        return request.json()
    else:
        arcpy.AddError("Query failed to run by returning code of {}. {}".format(request.status_code,
                                                                                query_or_mutation))
        return None


def get_indicators(urban_model, id_list):
    indicator_list = list()

    if not id_list:  # get all indicators
        query_template = Template("""query{
            indicators(urbanDatabaseId: "$udb_id", limit: 100){
                attributes{
                    IndicatorName
                    WebsceneItemId
                    GlobalID
            }
          }
        }""")

        query = query_template.substitute(udb_id=urban_model.master_id)

    elif len(id_list == 1):  # get indicator based on single ID
        query_template = Template("""query{
            indicator(urbanDatabaseId: "$fs_url", globalID: "$id"){
                attributes{
                    IndicatorName
                    WebsceneItemId
                    GlobalID
            }
          }
        }""")

        query = query_template.substitute(udb_id=urban_model.master_id, id=id_list[0])
    else:
        query_template = Template("""query{
            indicators(urbanDatabaseId: "$fs_url", globalIDs: $ids, , limit: 100){
                attributes{
                    IndicatorName
                    WebsceneItemId
                    GlobalID
            }
          }
        }""")

        query = query_template.substitute(udb_id=urban_model.master_id, ids=id_list)

    if query:
        result = run_query(urban_model.urban_api_url, query, None)  # Execute the query

        if result:
            if result['data']:
                indicator_dict_list = result['data']['indicators']
                if len(indicator_dict_list) > 0:
                    for i in indicator_dict_list:
                        indicator = Indicator(urban_model,
                                              i['attributes']['GlobalID'],
                                              i['attributes']['IndicatorName'],
                                              i['attributes']['WebsceneItemId'])

                        indicator_list.append(indicator)

    return indicator_list


def update_indicator_context_scene(urban_api_url, udb_id, scene_id, global_id):
    mutation_template = Template("""mutation{
             updateIndicators(urbanDatabaseId: "$udb_id", 
                              indicators: [
                                 {
                                     attributes:
                                     {
                                         GlobalID: "$global_id"
                                         WebsceneItemId: "$webscene_id"
                         }                
                     }
                  ] 
               )  
             {  
                attributes{
                    WebsceneItemId
                }              
             }               
          }""")

    query = mutation_template.substitute(udb_id=udb_id,
                                         webscene_id=scene_id,
                                         global_id=global_id)

    if query:
        result = run_query(urban_api_url, query, None)  # Execute the mutation

        if result:
            if result['data']:
                return True
            else:
                return False
        else:
            return False
    else:
        return False


def add_indicator(urban_api_url, db_id, attr_list):

    mutation_template = Template("""mutation{
         createIndicators(urbanDatabaseId: "$udb_id", 
                          indicators: [
                             {
                                 attributes:
                                 {
                                      EndDate: $start_date
                                      IndicatorName: "$name"
                                      IndicatorType: $type
                                      OwnerName: "$owner"
                                      StartDate: $end_date
                                      CustomID: "$name"
                                      Description: "$description"
                                      WebsceneItemId: "$webscene_id"
                     }                
                 }
              ] 
           )  
         {  
            attributes{
                EndDate
                IndicatorName
                IndicatorType
                OwnerName
                StartDate
                Description
                WebsceneItemId 
          }              
        }               
      }""")

    query = mutation_template.substitute(udb_id=db_id,
                                         start_date=attr_list[0],
                                         name=attr_list[1],
                                         type=attr_list[2],
                                         owner=attr_list[3],
                                         end_date=attr_list[4],
                                         description=attr_list[5],
                                         webscene_id=attr_list[6]
                                         )

    if query:
        result = run_query(urban_api_url, query, None)  # Execute the mutation

        if result:
            if result['data']:
                return True
            else:
                return False
        else:
            return False
    else:
        return False


def get_urban_models(urban_api_url, org_id, users):
    urban_model_list = list()

    offset_nr = 0
    do_continue = True

    while do_continue:
        nr_returns = 0

        if users:
            query_template = Template("""query{
                urbanModels(organization: "$org_id", owners: [$users], limit: 100, offset: $offset_nr)
                {
                    id
                    owner
                    created
                    title
                    version
                    urbanDatabaseId
                    folderId
                }
            }""")

            clean_list = '[%s]' % ', '.join(map(str, users))
            clean_list = ','.join(['"' + x + '"' for x in clean_list[1:-1].split(',')])

            query = query_template.substitute(org_id=org_id, users=clean_list, offset_nr=offset_nr)
        else:
            query_template = Template("""query{
                        urbanModels(organization: "$org_id", limit: 100, offset: $offset_nr)
                        {
                            id
                            owner
                            created
                            title
                            version
                            urbanDatabaseId
                            folderId
                        }
                    }""")

            query = query_template.substitute(org_id=org_id, offset_nr=offset_nr)

        if query:
            result = run_query(urban_api_url, query, None)  # Execute the query

            if result:
                if result['data']:
                    query_result = result['data']['urbanModels']
                    if query_result:
                        if len(query_result) > 0:
                            for m in query_result:
                                # we need these
                                try:
                                    owner = m['owner']
                                    name = m['title']
                                    id = m['id']
                                    version = m['version']
                                    title = m['title']
                                    master_id = m['urbanDatabaseId']
                                    creation_date = m['created']
                                    folder_id = m['folderId']

                                    if owner and name and id and version and title \
                                            and master_id and creation_date:  # and folder_id:
                                        if users:
                                            if folder_id:
                                                add_model = True
                                            else:
                                                add_model = True  # False (switched for now)
                                        else:
                                            add_model = True
                                    else:
                                        add_model = False
                                except:
                                    add_model = False

                                if add_model:
                                    if check_min_version(version, get_min_supported_version()):
                                        urban_model = UrbanModel(owner,
                                                                 name,
                                                                 id,
                                                                 version,
                                                                 folder_id,
                                                                 title,
                                                                 master_id,
                                                                 urban_api_url,
                                                                 creation_date)

                                        urban_model_list.append(urban_model)

                                nr_returns += 1
                        else:
                            do_continue = False
                    else:
                        do_continue = False
                else:
                    do_continue = False
            else:
                do_continue = False

        if nr_returns < 100:  # search limit = 100
            do_continue = False
        else:
            offset_nr += 100

    return urban_model_list


def get_urban_models_names_owner_date(model_list):
    try:
        name_list = list()

        for model in model_list:
            if model.creation_date:
                date_stamp = dt.datetime.fromtimestamp(model.creation_date/1000)
                name_list.append(model.model_title +
                                 " {" + model.owner +
                                 ": " + date_stamp.strftime("%d-%b-%Y") + "}")
            else:
                name_list.append(model.model_title + " {" + model.owner + "}")

        return name_list

    except:
        raise FunctionError(
            {
                "function": "get_urban_models_names_owner_date"
            }
        )


def get_urban_models_names_date(model_list):
    try:
        name_list = list()

        for model in model_list:
            if model.creation_date:
                date_stamp = dt.datetime.fromtimestamp(model.creation_date/1000)
                name_list.append(model.model_title +
                                 " {" + date_stamp.strftime("%d-%b-%Y") + "}")
            else:
                name_list.append(model.model_title)

        return name_list

    except:
        raise FunctionError(
            {
                "function": "get_urban_models_names_date"
            }
        )


def select_model_by_title_owner_date(model_list, title):
    try:
        model = None

        string_list = title.split("{")
        title_string = string_list[0].strip()
        string_list = string_list[1].split(":")
        owner = string_list[0].replace("}", "")
        date = string_list[1].strip().replace("}", "")

        for m in model_list:
            date_stamp = dt.datetime.fromtimestamp(m.creation_date / 1000)
            m_date = date_stamp.strftime("%d-%b-%Y")

            if m.model_title == title_string and m.owner == owner and date == m_date:
                model = m
                break
        return model

    except:
        raise FunctionError(
            {
                "function": "select_model_by_title"
            }
        )


def select_model_by_title_owner(model_list, title):
    try:
        model = None

        string_list = title.split("{")
        title_string = string_list[0].strip()
        owner = string_list[1].replace("}", "")

        for m in model_list:
            if m.model_title == title_string and m.owner == owner:
                model = m
                break
        return model

    except:
        raise FunctionError(
            {
                "function": "select_model_by_title"
            }
        )


def select_model_by_title_date(model_list, title):
    try:
        model = None

        string_list = title.split("{")
        title_string = string_list[0].strip()
        date = string_list[1].replace("}", "")

        for m in model_list:
            date_stamp = dt.datetime.fromtimestamp(m.creation_date / 1000)
            m_date = date_stamp.strftime("%d-%b-%Y")

            if m.model_title == title_string and date == m_date:
                model = m
                break
        return model

    except:
        raise FunctionError(
            {
                "function": "select_model_by_title"
            }
        )


def select_model_by_title(model_list, title):
    try:
        model = None

        string_list = title.split("{")
        title_string = string_list[0].strip()

        for m in model_list:
            if m.model_title == title_string:
                model = m
                break
        return model

    except:
        raise FunctionError(
            {
                "function": "select_model_by_title"
            }
        )


def select_event_by_title(event_list, title):
    try:
        event = None
        for e in event_list:
            ui_event_name = str(e.event_name +
                                " (" + e.access + " " + e.event_type.lower() + ")")
            if ui_event_name == title:
                event = e
                break
        return event

    except:
        raise FunctionError(
            {
                "function": "select_event_by_title"
            }
        )


def select_scenario_by_title(scenario_list, title):
    try:
        scenario = None
        for s in scenario_list:
            if s.branch_name == title:
                scenario = s
                break
        return scenario

    except:
        raise FunctionError(
            {
                "function": "select_scenario_by_title"
            }
        )


def get_scenarios(urban_model, event):
    scenario_list = list()

    query_template = Template("""query{
         branches(urbanDatabaseId: "$udb_id", urbanEventID: "$event_globalid", limit: 100){
             attributes{
                 GlobalID
                 BranchName
                 ContextWebsceneItemId
                 WebsceneItemId
         }
       }
     }""")

#    filter_string = "UrbanEventID='" + event.global_id + "'"
    query = query_template.substitute(udb_id=event.master_id, event_globalid=event.global_id)

    if query:
        result = run_query(urban_model.urban_api_url, query, None)  # Execute the query

        if result:
            if result['data']:
                query_result = result['data']['branches']
                if query_result:
                    if len(query_result) > 0:
                        for e in query_result:
                            scenario = Scenario(urban_model,
                                                event,
                                                e['attributes']['GlobalID'],
                                                e['attributes']['BranchName'],
                                                e['attributes']['ContextWebsceneItemId'],
                                                e['attributes']['WebsceneItemId'])

                            scenario_list.append(scenario)

                        return scenario_list
                    else:
                        return None
                else:
                    return None
            else:
                return None
        else:
            return None
    else:
        return None


def get_urban_event_geometry(urban_model, event, get_z, output_ws, output_features, layer, debug):
    urban_event_list = list()
    query_template = Template("""query{
         urbanEvents(urbanDatabaseId: "$udb_id", filter: "$type_string"){
             attributes{
                 GlobalID
                 EventName

         }
             geometry{
                 rings
                 spatialReference{
                    wkid
                } 
         }
       }
     }""")

    type_string = "EventName='" + event.event_name + "'"

    query = query_template.substitute(udb_id=event.master_id, type_string=type_string)

    if query:
        result = run_query(urban_model.urban_api_url, query, None)  # Execute the query

        if result:
            if result['data']:
                output_name = str(os.path.basename(output_features))

                query_result = result['data']['urbanEvents']
                if query_result:
                    if len(query_result) > 0:
                        for e in query_result:

                            geom_json = json.dumps(e['geometry'])

                            pass
                            # urban_event = UrbanEvent(urban_model,
                            #                          master_id,
                            #                          e['attributes']['GlobalID'],
                            #                          e['attributes']['EventName'],
                            #                          e['attributes']['EventType'],
                            #                          e['attributes']['ContextWebsceneItemId'])

                        arcpy.AddMessage("Created " + layer + " feature class "
                                         + os.path.join(output_ws, output_name) + ".")
                    else:
                        return None
                else:
                    return None

    if len(urban_event_list) > 0:
        return urban_event_list
    else:
        return None


def get_urban_events20(urban_model, design_id, search_type, access, users):
    urban_event_list = list()
    query_template = Template("""query{
         $query_type(urbanDatabaseId: "$udb_id", limit: 100, offset: $offset_nr){
             attributes{
                 GlobalID
                 EventName
                 ContextWebsceneItemId
                 OwnerName
             }
             geometry{
                     rings
                     spatialReference{
                        wkid
                    } 
                }
       }
     }""")

    offset_nr = 0
    do_continue = True

    if search_type.lower() == "plan":
        query_type = "plans"
    else:
        query_type = "projects"

    while do_continue:
        nr_returns = 0

        query = query_template.substitute(query_type=query_type, udb_id=design_id, offset_nr=offset_nr)

        if query:
            result = run_query(urban_model.urban_api_url, query, None)  # Execute the query

            if result:
                if result['data']:
                    if search_type.lower() == "plan":
                        query_result = result['data']['plans']
                    else:
                        query_result = result['data']['projects']

                    if query_result:
                        if len(query_result) > 0:
                            for e in query_result:
                                geom_json = json.dumps(e['geometry'])

                                urban_event = UrbanEvent20(urban_model,
                                                           design_id,
                                                           e['attributes']['GlobalID'],
                                                           e['attributes']['EventName'],
                                                           e['attributes']['ContextWebsceneItemId'],
                                                           e['attributes']['OwnerName'],
                                                           search_type,
                                                           geom_json,
                                                           access)

                                # filter on users
                                if users:
                                    if e['attributes']['OwnerName'] in users:
                                        urban_event_list.append(urban_event)
                                else:
                                    urban_event_list.append(urban_event)

                                nr_returns += 1
                        else:
                            do_continue = False
                    else:
                        do_continue = False
                else:
                    do_continue = False
            else:
                do_continue = False

        if nr_returns < 100:  # search limit = 100
            do_continue = False
        else:
            offset_nr += 100

    return urban_event_list


def get_urban_events(urban_model, design_id, search_type):
    urban_event_list = list()
    query_template = Template("""query{
         urbanEvents(urbanDatabaseId: "$udb_id", limit: 100, offset: $offset_nr){
             attributes{
                 GlobalID
                 EventName
                 EventType
                 ContextWebsceneItemId
         }
       }
     }""")

#    type_string = "EventType='" + search_type.lower() + "'"
    offset_nr = 0
    do_continue = True

    while do_continue:
        nr_returns = 0

        query = query_template.substitute(udb_id=design_id, offset_nr=offset_nr)

        if query:
            result = run_query(urban_model.urban_api_url, query, None)  # Execute the query

            if result:
                if result['data']:
                    query_result = result['data']['urbanEvents']
                    if query_result:
                        if len(query_result) > 0:
                            for e in query_result:
                                if e['attributes']['EventType'].lower() == search_type.lower():
                                    urban_event = UrbanEvent(urban_model,
                                                             design_id,
                                                             e['attributes']['GlobalID'],
                                                             e['attributes']['EventName'],
                                                             e['attributes']['EventType'],
                                                             e['attributes']['ContextWebsceneItemId'])
                                    urban_event_list.append(urban_event)

                                nr_returns += 1
                        else:
                            do_continue = False
                    else:
                        do_continue = False
                else:
                    do_continue = False
            else:
                do_continue = False

        if nr_returns < 100:  # search limit = 100
            do_continue = False
        else:
            offset_nr += 100

    return urban_event_list


def get_urban_events_for_designs(gis, urban_model, urban_designs, search_name):
    try:
        urban_event_list = list()
        fail = False

        for design in urban_designs:
            try:
                if urban_model.model_id == design.urban_model_id:
                    # use featureServiceID of item to make UrbanEvent via URBAN API
                    # TODO -> confirm there can only be 1 event per plan or project: see[0]
                    all_urban_events = get_urban_events20(urban_model, design.design_id, search_name,
                                                          "private", [gis.users.me.username])
                    if len(all_urban_events) > 0:
                        urban_event_list.append(all_urban_events[0])
            except:
                fail = True

        return urban_event_list
    except:
        raise FunctionError(
            {
                "function": "get_urban_events_for_designs"
            }
        )


def get_private_urban_events(urban_events_design, urban_events_master):

    private_urban_event_list = list()

    if len(urban_events_design) > 0 and len(urban_events_master) > 0:
        for d_event in urban_events_design:
            add = True
            for m_event in urban_events_master:
                # check if in master events on name and urban model id
                if d_event.urban_model.master_id == m_event.urban_model.master_id \
                        and d_event.event_name == m_event.event_name:
                    add = False
            if add:
                private_urban_event_list.append(d_event)
    return private_urban_event_list


def get_urban_designs(urban_model, users, search_type):
    urban_design_list = list()
    offset_nr = 0
    do_continue = True

    while do_continue:
        nr_returns = 0

        if users:
            query_template = Template("""query{
                     urbanDesigns(owners: [$users], limit: 100, offset: $offset_nr){
                         id
                         urbanModelId
                         type
                         title
                         owner
                         url
                         access
                   }
                 }""")

            clean_list = '[%s]' % ', '.join(map(str, users))
            clean_list = ','.join(['"' + x + '"' for x in clean_list[1:-1].split(',')])

            query = query_template.substitute(users=clean_list, offset_nr=offset_nr)
        else:
            query_template = Template("""query{
                                 urbanDesigns(limit: 100, offset: $offset_nr){
                                     id
                                     urbanModelId
                                     type
                                     title
                                     owner
                                     url
                               }
                             }""")

            query = query_template.substitute(offset_nr=offset_nr)

        if query:
            result = run_query(urban_model.urban_api_url, query, None)  # Execute the query

            if result:
                if result['data']:
                    query_result = result['data']['urbanDesigns']
                    if query_result:
                        if len(query_result) > 0:
                            for e in query_result:
                                if e['type'].lower() == search_type.lower():
                                    urban_design = UrbanDesign(urban_model,
                                                               e['id'],
                                                               e['urbanModelId'],
                                                               e['type'],
                                                               e['title'],
                                                               e['owner'],
                                                               e['url'])

                                    urban_design_list.append(urban_design)

                                nr_returns += 1
                        else:
                            do_continue = False
                    else:
                        do_continue = False
                else:
                    do_continue = False
            else:
                do_continue = False

        if nr_returns < 100:  # search limit = 100
            do_continue = False
        else:
            offset_nr += 100

    return urban_design_list


def get_event_context_scene(urban_api_url, udb_id):
    scene_id_list = list()

    query_template = Template("""query{
         urbanEvents(urbanDatabaseId: "$udb_id", limit: 100){
             attributes{
                 GlobalID
                 ContextWebsceneItemId
         }
       }
     }""")

    query = query_template.substitute(udb_id=udb_id)

    if query:
        result = run_query(urban_api_url, query, None)  # Execute the query

        if result:
            if result['data']:
                event_list = result['data']['urbanEvents']
                if len(event_list) > 0:
                    for e in event_list:
                        context_scene_id = e['attributes']['ContextWebsceneItemId']
                        scene_id_list.append(context_scene_id)

                    return scene_id_list
                else:
                    return None
            else:
                return None
        else:
            return None
    else:
        return None


def get_base_context_scene(urban_api_url, model_id):
    query_template = Template("""query{
        urbanModelConfig(urbanModelId: "$model_id"){
                customBaselayersItemId
                name
          }
        }""")

    query = query_template.substitute(model_id=model_id)

    if query:
        result = run_query(urban_api_url, query, None)  # Execute the query

        if result:
            if result['data']:
                model_config = result['data']['urbanModelConfig']
                return model_config['customBaselayersItemId']
            else:
                return None
        else:
            return None
    else:
        return None


def add_base_context_scene(urban_api_url, model_id, scene_id):

    mutation_template = Template("""mutation{
        updateUrbanModelConfig(urbanModelId: "$model_id", 
            urbanModelConfig: 
            {
                customBaselayersItemId: "$scene_id"
            }
        )  
        {
            customBaselayersItemId
        }
      }""")

    query = mutation_template.substitute(model_id=model_id, scene_id=scene_id)

    if query:
        result = run_query(urban_api_url, query, None)  # Execute the mutation

        if result:
            if result['data']:
                return True
            else:
                return False
        else:
            return False
    else:
        return False


def add_base_layer(urban_api_url, model_id, base_layer_type, layer_id):

    if base_layer_type == "Existing buildings for schematic visualization":
        base_layer_param = "existingBuildingsLayerItemId"
    elif base_layer_type == "Existing buildings for satellite visualization":
        base_layer_param = "existingSatelliteBuildingsLayerItemId"
    elif base_layer_type == "Existing trees":
        base_layer_param = "existingTreesLayerItemId"
    else:
        base_layer_param = None

    if base_layer_param:
        mutation_template = Template("""mutation{
            updateUrbanModelConfig(urbanModelId: "$model_id", 
                urbanModelConfig: 
                {
                    $base_layer_param: "$layer_id"
                }
            )  
            {
                $base_layer_param
            }
          }""")

        query = mutation_template.substitute(model_id=model_id, base_layer_param=base_layer_param, layer_id=layer_id)

        if query:
            result = run_query(urban_api_url, query, None)  # Execute the mutation

            if result:
                if result['data']:
                    return True
                else:
                    return False
            else:
                return False
        else:
            return False
    else:
        return False


def update_event_context_scene(urban_api_url, udb_id, scene_id, global_id):
        mutation_template = Template("""mutation{
             updateUrbanEvents(urbanDatabaseId: "$udb_id", 
                              urbanEvents: [
                                 {
                                     attributes:
                                     {
                                         GlobalID: "$global_id"
                                         ContextWebsceneItemId: "$webscene_id"
                         }                
                     }
                  ] 
               )  
             {  
                attributes{
                    ContextWebsceneItemId
                }              
             }               
          }""")

        query = mutation_template.substitute(udb_id=udb_id,
                                             webscene_id=scene_id,
                                             global_id=global_id)

        if query:
            result = run_query(urban_api_url, query, None)  # Execute the mutation

            if result:
                if result['data']:
                    return True
                else:
                    return False
            else:
                return False
        else:
            return False


def update_scenario_context_scene(urban_api_url, udb_id, scene_id, global_id):
    mutation_template = Template("""mutation{
             updateBranches(urbanDatabaseId: "$udb_id", 
                              branches: [
                                 {
                                     attributes:
                                     {
                                         GlobalID: "$global_id"
                                         ContextWebsceneItemId: "$webscene_id"
                         }                
                     }
                  ] 
               )  
             {  
                attributes{
                    ContextWebsceneItemId
                }              
             }               
          }""")

    query = mutation_template.substitute(udb_id=udb_id,
                                         webscene_id=scene_id,
                                         global_id=global_id)

    if query:
        result = run_query(urban_api_url, query, None)  # Execute the mutation

        if result:
            if result['data']:
                return True
            else:
                return False
        else:
            return False
    else:
        return False


def get_parcel_globalids(urban_api_url, udb_id, scenario_id):
    parcel_list = list()
    query_template = Template("""query{
         parcels(urbanDatabaseId: "$udb_id", branchID: "$scenario_id", limit: 100, offset: $offset_nr){
             attributes{
                 GlobalID
                }
             geometry{
                     spatialReference{
                        wkid
                    } 
                }
       }
     }""")

    offset_nr = 0
    do_continue = True
    wkid = None

    while do_continue:
        nr_returns = 0

        query = query_template.substitute(udb_id=udb_id, scenario_id=scenario_id, offset_nr=offset_nr)

        if query:
            result = run_query(urban_api_url, query, None)  # Execute the query

            if result:
                if result['data']:
                    query_result = result['data']['parcels']
                    if query_result:
                        if len(query_result) > 0:
                            for e in query_result:
                                parcel_list.append(e['attributes']['GlobalID'])
                                nr_returns += 1
                                wkid = e['geometry']['spatialReference']['wkid']
                        else:
                            do_continue = False
                    else:
                        do_continue = False
                else:
                    do_continue = False
            else:
                do_continue = False

        # arcpy.AddMessage("Retrieved: " + str(len(parcel_list)) + " parcels...")

        if nr_returns < 100:  # search limit = 100
            do_continue = False
        else:
            offset_nr += 100

    return parcel_list


def delete_parcels(urban_api_url, udb_id, global_ids):
    mutation_template = Template("""mutation{
                            deleteParcels(urbanDatabaseId: "$udb_id",
                            globalIDs: $global_ids
                        )
                    {  
                        attributes{
                            GlobalID
                            }
                    }               
    }""")

    global_ids_as_string = json.dumps(global_ids)

    query = mutation_template.substitute(udb_id=udb_id, global_ids=global_ids_as_string)

    if query:
        result = run_query(urban_api_url, query, None)  # Execute the mutation

        if result:
            if result['data']:
                return True
            else:
                return False
        else:
            return False
    else:
        return False


def update_parcels_edgeinfo(urban_api_url, udb_id, global_id_edgeinfo_dict):
    attribute_template_list = list()
    global_ids = global_id_edgeinfo_dict.keys()

    # TODO deal with dynamic edge infos
    edge_info = """
            EdgeInfos: [
                            {
                                adjacencies: [
                                        {
                                            category:"cat_testhnhn4"
                                            type: "street"
                                            width: 0
                                        }
                                ]
                                orientation: "front"
                        },
                        {
                                adjacencies: [
                                        {
                                            category:"cat_testnhnh3"
                                            type: "street"
                                            width: 0
                                        }
                                ]
                                orientation: "side"
                        }
            ]
        """

    # create attributes for global_ids

    for global_id in global_ids:
        attribute_template = Template("""{   
                                            attributes:
                                            {
                                                GlobalID: "$global_id"
                                                $edge_info
                                                
                                            }
                                        }""")

        attribute_sub = attribute_template.substitute(global_id=global_id, edge_info=edge_info)
        attribute_template_list.append(attribute_sub)

    clean_list = '[%s]' % ', '.join(map(str, attribute_template_list))

    mutation_template = Template("""mutation{
        updateParcels(urbanDatabaseId: "$udb_id",
                            parcels: 
                                $attribute_template_list                            
                        )
            {
                attributes{
                    GlobalID
                }
            }
        }""")

    query = mutation_template.substitute(udb_id=udb_id, attribute_template_list=clean_list)

    if query:
        result = run_query(urban_api_url, query, None)  # Execute the mutation

        if result:
            if result['data']:
                return True
            else:
                return False
        else:
            return False
    else:
        return False


def get_attribute_type_info(urban_model, attribute_type):
    field_info_dict = {}

    type_template = Template("""{
         __type(name: "$attr_type"){
                name
                fields
                {
                    name
                    type
                    {
                        name
                        kind
                        ofType
                        {
                            name
                            kind
                            ofType
                            {
                                name
                                kind
                                ofType
                                {
                                    name
                                    kind
                                }
                            }
                        }
                    }
                }
        }
    }""")

    query = type_template.substitute(attr_type=attribute_type)
    result = run_query(urban_model.urban_api_url, query, None)  # Execute the query

    if result:
        if result['data']:
            query_result = result['data']['__type']['fields']
            if query_result:
                if len(query_result) > 0:
                    for f in query_result:
                        field_json = json.dumps(f)
                        field_name = f['name']
                        type_dict = f['type']

                        while True:
                            type_name = type_dict['name']
                            type_kind = type_dict['kind']
                            if type_name != 'null' and (type_kind == 'SCALAR' or
                                                        type_kind == 'OBJECT') and len(type_dict) > 0:
                                break
                            else:
                                type_dict = type_dict['ofType']

                        field_info_dict[field_name] = type_name

            if len(field_info_dict) > 0:
                return field_info_dict
            else:
                return None
        else:
            return None
    else:
        return None


def get_lod1_buildings(urban_model, scenario):
    lod1_buildings_list = list()

    attribute_type_info = get_attribute_type_info(urban_model, "LOD1BuildingAttributes")

    if attribute_type_info:
        query_template = Template("""query{
             lod1Buildings(urbanDatabaseId: "$udb_id", branchID: "$branch_id", limit: 100, offset: $offset_nr){
                 attributes{
                     GlobalID
                     BranchID
                     CustomID
                     Height
                }
                 geometry{
                     rings
                     spatialReference{
                        wkid
                    } 
                }
           }
        }""")

        offset_nr = 0
        do_continue = True

        while do_continue:
            nr_returns = 0

            query = query_template.substitute(udb_id=scenario.event.master_id, branch_id=scenario.global_id,
                                              offset_nr=offset_nr)

            if query:
                result = run_query(urban_model.urban_api_url, query, None)  # Execute the query

                if result:
                    if result['data']:
                        query_result = result['data']['lod1Buildings']
                        if query_result:
                            if len(query_result) > 0:
                                for e in query_result:
                                    geom_json = json.dumps(e['geometry'])
                                    attributes = json.dumps(e['attributes'])

                                    urban_feature = UrbanFeature(geometry=geom_json,
                                                                 attributes=attributes)

                                    lod1_buildings_list.append(urban_feature)
                            else:
                                do_continue = False
                        else:
                            do_continue = False
                    else:
                        do_continue = False
                else:
                    do_continue = False

            if nr_returns < 100:  # search limit = 100
                do_continue = False
            else:
                offset_nr += 100

        if len(lod1_buildings_list) > 0:
            return lod1_buildings_list, attribute_type_info
        else:
            return lod1_buildings_list, attribute_type_info
    else:
        arcpy.AddWarning("Can't read attributes for " + "Lod1BuildingAttributes" + ". Exiting...")
        return lod1_buildings_list, attribute_type_info


# Field Exists
def field_exist(feature_class, field_name):
    field_list = arcpy.ListFields(feature_class, field_name)
    field_count = len(field_list)
    if field_count == 1:
        return True
    else:
        return False


def add_field(feature_class, field, field_type, length):
    try:
        if not field_exist(feature_class, field):
            arcpy.AddField_management(feature_class, field, field_type, field_length=length)

    except arcpy.ExecuteWarning:
        print((arcpy.GetMessages(1)))
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


def create_polygon_from_rings(feature_geometry, sr):

    # Create a polygon geometry
    geom_type = None
    has_z = False
    array = arcpy.Array()

    # get rings from feature geometry

    feature_ring_list = feature_geometry.get("rings")

    # get outer ring -> donuts are not supported
    outer_ring = feature_ring_list[0]

    for pnt in outer_ring:
        if len(pnt) == 3:
            array.add(arcpy.Point(pnt[0], pnt[1], pnt[2]))
            has_z = True
            geom_type = "3D"
        elif len(pnt) == 2:
            array.add(arcpy.Point(pnt[0], pnt[1]))
            has_z = False
            geom_type = "2D"
        else:
            pass

    if len(feature_ring_list) > 1:
        arcpy.AddWarning("Found inner rings in feature. donuts are not supported.")

    return arcpy.Polygon(array, sr, has_z), geom_type


def create_polygon_featureclass(lod1_features, attribute_type_info, output_features):
    geometry_type = "POLYGON"
    has_m = "DISABLED"
    has_z = "ENABLED"

    # get spatial reference
    json_geometry = valid_json(lod1_features[0].geometry)
    sr_dict = json_geometry.get("spatialReference")
    wkid = sr_dict.get("wkid")
    sr = arcpy.SpatialReference(wkid)

    # Execute CreateFeatureclass
    if arcpy.Exists(output_features):
        arcpy.Delete_management(output_features)

    output_name = os.path.basename(output_features)
    output_dir = os.path.dirname(output_features)
    arcpy.CreateFeatureclass_management(output_dir, output_name, geometry_type, "", has_m,
                                        has_z, sr)

    # add known attribute fields
    schema_fields = attribute_type_info.keys()
    json_attributes = valid_json(lod1_features[0].attributes)
    queried_fields = json_attributes.keys()
    cursor_fields = ["SHAPE@"]

    for f in schema_fields:
        if f in queried_fields:
            attr_type = attribute_type_info.get(f)

            if attr_type == "String":
                field_type = "TEXT"
                field_length = 1000000000
            elif attr_type == "Float":
                field_type = "FLOAT"
                field_length = 50
            elif attr_type == "GlobalID":
                field_type = "TEXT"
                field_length = 50
            else:
                field_type = "TEXT"
                field_length = 50

            add_field(output_features, f, field_type, field_length)

            cursor_fields.append(f)

    # add geometries and attribute values
    with arcpy.da.InsertCursor(output_features, cursor_fields) as curs:
        for feature in lod1_features:
            tuple_list = []

            # create polygonZ object
            polygon, geom_type = create_polygon_from_rings(valid_json(feature.geometry), sr)
            tuple_list.append(polygon)

            json_attributes = valid_json(feature.attributes)
            for f in queried_fields:
                f_value = json_attributes.get(f)
                tuple_list.append(f_value)

            curs_tuple = tuple(tuple_list)
            curs.insertRow(curs_tuple)
    del curs

    num_features = arcpy.GetCount_management(output_features).getOutput(0)
    if int(num_features) > 0:
        return output_features
    else:
        arcpy.AddWarning("No features created in " + output_features + ". Exiting...")
        return None


def get_attribute_list_as_string(local_attribute_dict, urban_model, branch_id, urban_type_dict):
    attr_list_as_string = None
    field_value_str_list = list ()

    urban_fields_list = list(urban_type_dict.keys())

    # check against Urban schema
    for field in local_attribute_dict:
        if field in urban_fields_list:
            if field not in ["GlobalID", "BranchID"]:
                local_value = local_attribute_dict.get(field)
                if local_value is None:
                    pass
                else:
                    # check data_type in Urban
                    urban_data_type = urban_type_dict.get(field)
                    if urban_data_type.lower() in ['float', 'long', 'short', 'double', 'int']:
                        try:
                            val = int(local_attribute_dict.get(field))
                            skip = False
                        except ValueError:
                            try:
                                val = float(local_attribute_dict.get(field))
                                skip = False
                            except ValueError:
                                skip = True

                        if not skip:
                            field_value_str = field + ": " + str(local_attribute_dict.get(field))
                            field_value_str_list.append(field_value_str)
                    elif urban_data_type.lower() == 'boolean':
                        val = int(local_attribute_dict.get(field))
                        if val == 0:
                            field_value_str = field + ": false"
                        else:
                            field_value_str = field + ": true"
                        field_value_str_list.append(field_value_str)
                    elif field == "EdgeInfos":
                        # pass
                        # replace quotes, comma's and set EdgeInfo Enum
                        edge_info_json = valid_json(local_attribute_dict.get(field))
                        field_value_str = field + ": " + str(local_attribute_dict.get(field))
                        remove_str = field_value_str.replace("\"adjacencies\"", "adjacencies")
                        remove_str = remove_str.replace("\"orientation\"", "orientation")
                        remove_str = remove_str.replace("\"category\"", "category")
                        remove_str = remove_str.replace("\"type\"", "type")
                        remove_str = remove_str.replace("\"width\"", "width")
                        replace_str = remove_str.replace("\",", "\"\n")
                        replace_str = replace_str.replace("\"street\"", "Street")
                        replace_str = replace_str.replace("\"front\"", "Front")
                        replace_str = replace_str.replace("\"side\"", "Side")
                        replace_str = replace_str.replace("\"rear\"", "Rear")
                        field_value_str_list.append(replace_str)
                    elif field == "Skyplanes":
                        # pass
                        # replace quotes, comma's and set EdgeInfo Enum
                        edge_info_json = valid_json(local_attribute_dict.get(field))
                        field_value_str = field + ": " + str(local_attribute_dict.get(field))
                        remove_str = field_value_str.replace("\"adjacency\"", "adjacency")
                        remove_str = remove_str.replace("\"angle\"", "angle")
                        remove_str = remove_str.replace("\"horizontalOffset\"", "horizontalOffset")
                        remove_str = remove_str.replace("\"orientation\"", "orientation")
                        remove_str = remove_str.replace("\"verticalOffset\"", "verticalOffset")
                        replace_str = remove_str.replace("\",", "\"\n")
                        replace_str = replace_str.replace("\"street\"", "Street")
                        replace_str = replace_str.replace("\"interior\"", "Interior")
                        replace_str = replace_str.replace("\"side\"", "Side")
                        replace_str = replace_str.replace("\"rear\"", "Rear")
                        replace_str = replace_str.replace("\"front\"", "Front")
                        field_value_str_list.append(replace_str)
                    elif field == "Tiers":
                        # pass
                        # replace quotes, comma's and set EdgeInfo Enum
                        edge_info_json = valid_json(local_attribute_dict.get(field))
                        field_value_str = field + ": " + str(local_attribute_dict.get(field))
                        remove_str = field_value_str.replace("\"setbacks\"", "setbacks")
                        remove_str = remove_str.replace("\"startHeight\"", "startHeight")
                        remove_str = remove_str.replace("\"front\"", "front")
                        remove_str = remove_str.replace("\"rear\"", "rear")
                        remove_str = remove_str.replace("\"side\"", "side")
                        remove_str = remove_str.replace("\"interior\"", "interior")
                        remove_str = remove_str.replace("\"street\"", "street")
                        remove_str = remove_str.replace("\"value\"", "value")
                        replace_str = remove_str.replace("\",", "\"\n")
                        field_value_str_list.append(replace_str)
                    else:
                        field_value_str = field + ": " + "\"" + local_attribute_dict.get(field) + "\""
                        field_value_str_list.append(field_value_str)

    # add "BranchID":
    field_value_str = "BranchID: " + "\"" + branch_id + "\""
    field_value_str_list.append(field_value_str)

    final_string = ""
    if len(field_value_str_list) > 0:
        for e in field_value_str_list:
            final_string = final_string + e + "\n"

        #  attr_list_as_string = '[%s]' % ', '.join(map(str, field_value_str_list))

    return final_string


def create_parcels(urban_model, udb_id, branch_id, feature_json_dict,  wkid):
    feature_template_list = list()

    feature_list = feature_json_dict.get('features')
    urban_type_dict = get_attribute_type_info(urban_model, "ParcelAttributes")

    # step through features and get geometry and attributes
    for feature in feature_list:
        rings_dict = feature.get('geometry')
        rings_list = rings_dict.get('rings')
        rings_list_as_string = '[%s]' % ', '.join(map(str, rings_list))

        attr_list_as_string = get_attribute_list_as_string(feature.get('attributes'), urban_model,
                                                           branch_id,
                                                           urban_type_dict)

        # remove [] and replace , with \n
#        remove_str = attr_list_as_string.replace("[", "")
#        remove_str = remove_str.replace("]", "")
#        replace_str = remove_str.replace(",", "\n")

        feature_template = Template("""{   
                                            attributes:
                                            {
                                                $attr_list
                                            }
                                            geometry:
                                            {
                                                rings: $rings_list
                                                spatialReference:
                                                {
                                                    wkid:$wkid
                                                }
                                            }
                                            
                                        }""")

        feature_sub = feature_template.substitute(attr_list=attr_list_as_string,
                                                  rings_list=rings_list_as_string,
                                                  wkid=wkid)
        feature_template_list.append(feature_sub)

    clean_feature_attribute_list = '[%s]' % ', '.join(map(str, feature_template_list))

    mutation_template = Template("""mutation{
        createParcels(urbanDatabaseId: "$udb_id",
                            parcels:
                                $feature_attribute_list
                        )
            {
                attributes{
                    GlobalID
                }
            }
        }""")

    query = mutation_template.substitute(udb_id=udb_id,
                                         feature_attribute_list=clean_feature_attribute_list)

    if query:
        result = run_query(urban_model.urban_api_url, query, None)  # Execute the mutation

        if result:
            if len(result) > 0:
                if result['data']:
                    query_result = result['data']['createParcels']
                    if query_result:
                        if len(query_result) > 0:
                            return True
                        else:
                            return False
                    else:
                        return False
                else:
                    return False
            else:
                return False
        else:
            return False
    else:
        return False


def check_feature_schema_wkid_in_urban(feature_class, feature_as_dict, urban_model, attributes, urban_wkid):
    local_field_list = list()
    local_field_dict_list = feature_as_dict.get('fields')
    for lfd in local_field_dict_list:
        field_name = lfd.get('name')
        local_field_list.append(field_name)

    urban_type_dict = get_attribute_type_info(urban_model, attributes)
    urban_fields_list = list(urban_type_dict.keys())

    # check if the local layer has all the needed fields
    result = all(elem in local_field_list for elem in urban_fields_list)

    if result:
        sr_dict = feature_as_dict.get('spatialReference')
        wkid = sr_dict.get("wkid")

        if wkid == urban_wkid:
            result = True
        else:
            arcpy.AddWarning("Input layer: " + feature_class + " does not have the same coordinate system as the " \
                             "scenario parcel layer in Urban. Exiting...")
            result = False
        pass
    else:
        arcpy.AddWarning("Input layer: " + feature_class + " does not have all the necessary fields that are "
                         "required to update the scenario parcel layer. Exiting...")
        arcpy.AddMessage("Tip: use 'Get Scenario' to retrieve the existing scenario parcel layer in Urban  that you "
                         "want to update, "
                         "modify this local layer (except the schema) and use the modified layer to update the "
                         "scenario parcels.")

    return result


def get_full_path_from_layer(in_layer):
    dir_name = os.path.dirname(arcpy.Describe(in_layer).catalogPath)
    layer_name = arcpy.Describe(in_layer).name

    return os.path.join(dir_name, layer_name)


def get_cs_info(local_lyr, debug):

    if debug == 1:
        msg("--------------------------")
        msg("Executing is_projected...")

    start_time = time.perf_counter()

    try:
        cs_name = None
        cs_vcs_name = None
        projected = False

        sr = arcpy.Describe(local_lyr).spatialReference

        if sr:
            cs_name = sr.name
            msg_prefix = "Coordinate system: " + cs_name
            msg_body = create_msg_body(msg_prefix, 0, 0)
            if debug:
                msg(msg_body)

            if sr.type == 'PROJECTED' or sr.type == 'Projected':
                projected = True
                msg_prefix = "Coordinate system type: Projected."
                msg_body = create_msg_body(msg_prefix, 0, 0)
                if debug:
                    msg(msg_body)
            else:
                projected = False
                msg_prefix = "Coordinate system type: Geographic."
                msg_body = create_msg_body(msg_prefix, 0, 0)
                if debug:
                    msg(msg_body)

            if sr.VCS:
                cs_vcs_name = sr.VCS.name
                msg_prefix = "Vertical coordinate system: " + cs_vcs_name
                msg_body = create_msg_body(msg_prefix, 0, 0)
                if debug:
                    msg(msg_body)
            else:
                msg_prefix = "No Vertical coordinate system detected."
                msg_body = create_msg_body(msg_prefix, 0, 0)
                if debug:
                    msg(msg_body)
        else:
            msg_prefix = "No coordinate system detected."
            msg_body = create_msg_body(msg_prefix, 0, 0)
            if debug:
                msg(msg_body)

        msg_prefix = "Function is_projected completed successfully."
        failed = False

        return cs_name, cs_vcs_name, projected

    except:
        line, filename, synerror = trace()
        failed = True
        msg_prefix = ""
        raise FunctionError(
            {
                "function": "is_projected",
                "line": line,
                "filename": filename,
                "synerror": synerror,
                "arc": str(arcpy.GetMessages(2))
            }
        )

    finally:
        end_time = time.perf_counter()
        msg_body = create_msg_body(msg_prefix, start_time, end_time)
        if failed:
            msg(msg_body, ERROR)
        else:
            if debug == 1:
                msg(msg_body)


def check_valid_input(input_features, need_projected, shape_type_list, need_z_value, no_shape_file):
    # shapefiles are not supported
    try:
        valid = False
        do_continue = True

        if no_shape_file:
            item_name = get_full_path_from_layer(input_features)
            if '.shp' in item_name:
                do_continue = False
                arcpy.AddError("Shapefiles are not supported. Please copy to a geodatabase.")

        if do_continue:
            num = int(arcpy.GetCount_management(input_features).getOutput(0))
            if num > 0:
                # check if input feature has a projected coordinate system (required!)
                cs_name, cs_vcs_name, is_projected = get_cs_info(input_features, 0)

                if 1:  # is_projected == need_projected:
                    desc = arcpy.Describe(input_features)

                    if desc.shapeType in shape_type_list:
                        z_values = desc.hasZ
                        if need_z_value:
                            if z_values == need_z_value:
                                valid = True
                            else:
                                arcpy.AddWarning(f'Error: Only features with Z values are supported')
                        else:
                            valid = True
                    else:
                        shape_type_list_string = ", ".join(shape_type_list)
                        arcpy.AddWarning(f'Error: Only {shape_type_list_string} data types are supported.')
                else:
                    arcpy.AddWarning("Only projected coordinate systems are supported.")
            else:
                arcpy.AddWarning("No features found.")
        return valid

    except arcpy.ExecuteError:
        # Get the tool error messages
        msgs = arcpy.GetMessages(2)
        arcpy.AddError(msgs)
    except Exception:
        e = sys.exc_info()[1]
        arcpy.AddMessage("Unhandled exception: " + str(e.args[0]))
