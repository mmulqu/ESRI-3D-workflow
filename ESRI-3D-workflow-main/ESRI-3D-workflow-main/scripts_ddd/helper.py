from scripts_ddd._common import *
import arcgisscripting
import functools
import logging
import sys
import arcpy

logger = logging.getLogger(__name__)


def log_version_info():
    """ Logs the version info of Pro and the tools """
    logger.info(f'''ArcGIS Pro {".".join(get_pro_version())}''')


def gp_wrapper(func):
    """Function decorator for geoprocessing tools"""

    def write_call(func, kwargs):
        """ Writes the debug call for easy execution """

        f = ".".join((func.__module__, func.__qualname__))
        params = ["{}={}".format(k, repr(v)) for k, v in kwargs.items()]
        s = " " * len(f)
        logger.debug('{}({})'.format(f, ",\n {}".format(s).join(params)))

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            write_call(func, kwargs)
            return func(*args, **kwargs)

        # TODO: can we hide the awful stack trace when a user cancels GP tool?
        except (arcgisscripting.ExecuteAbort, KeyboardInterrupt):
            pass

        except arcgisscripting.ExecuteError:
            # This logs the pretty hyperlinked arcpy error code.
            logger.error(arcpy.GetMessages(severity=2))
            sys.exit(1)

        except Exception as e:
            if not isinstance(e, SystemExit):
                logger.error('A python error occurred.')
                logger.exception('EXCEPTION')
                sys.exit(2)

        finally:
            pass

    return wrapper


class ParamWrapper(object):
    """ Wrapper class for converting parameter objects to native arcpy/python types """

    def __init__(self, parameter: arcpy.Parameter):
        self.parameter = parameter

    @staticmethod
    def _get_value(value_object):
        """ Extract the value (or values) from the parameter """
        try:
            # Multivalue parameter
            return value_object.values
        except (AttributeError, NameError):
            # Special case for some data types that are accessed as p.value.value
            while hasattr(value_object, 'value'):
                value_object = value_object.value

            # Convert empty strings to None
            if isinstance(value_object, str) and not value_object:
                value_object = None
            return value_object

    def _convert(self):
        values = self._get_value(self.parameter)

        # Value Table is a special parameter type
        # There can be multiple datatypes (returned as a list)
        if 'Value Table' in self.parameter.datatype:
            return [[self._get_value(cell) for cell in row] for row in values or []]
        elif self.parameter.multiValue:
            if values is None:
                # If an optional multivalue parameter is not specified, None is the value.
                # Change this to an empty list as the code will *generally* be expecting a list to iterate over.
                return []
            else:
                return [self._get_value(v) for v in values]
        else:
            return values

    def get_values(self):
        # We're assuming that objects with parameterType properties are arcpy.Parameter() objects
        if hasattr(self.parameter, 'parameterType'):
            return self._convert()
        else:
            return self.parameter


def set_folder(parameter: arcpy.Parameter):
    """ Sets the folder to the home folder of the current Project """
    if parameter.value:
        return
    try:
        parameter.value = arcpy.mp.ArcGISProject('CURRENT').homeFolder
    except OSError:
        return
