import os
from typing import Tuple, List

import arcpy
import pandas as pd


def count_cursor(cursor):
    counts = 0
    for counter in cursor:
        counts += 1
    cursor.reset()
    return counts
def get_workspace(dataset):
    desc = arcpy.Describe(value=dataset)
    dirname = os.path.dirname(desc.catalogPath)
    desc = arcpy.Describe(dirname)
    if hasattr(desc, "datasetType") and desc.datasetType == 'FeatureDataset':
        dirname = os.path.dirname(dirname)
    return dirname
def add_fields(source_table, target_table):

    target_fields = {f.name.lower() for f in arcpy.Describe(target_table).fields}
    source_domains = {domain.name:domain for domain in arcpy.da.ListDomains(get_workspace(source_table))}

    target_workspace = get_workspace(target_table)
    target_domains = {domain.name:domain for domain in arcpy.da.ListDomains(target_workspace)}
    for field in arcpy.Describe(source_table).fields:
        if field.name.lower() in target_fields:
            continue
        if field.domain != '' and field.domain not in target_domains:
            copy_domain(domain=source_domains[field.domain], workspace=target_workspace)
        arcpy.AddField_management(in_table=target_table,
                                  field_name=field.baseName,
                                  field_type=field_type_convert(field.type),
                                  field_precision=field.precision,
                                  field_scale=field.scale,
                                  field_length=field.length,
                                  field_alias=field.aliasName,
                                  field_is_nullable=field.isNullable,
                                  field_is_required=field.required,
                                  field_domain=field.domain)

def field_type_convert(prop: str) -> str:
    """
    Converts the field type returned from ``arcpy.Field`` to the name for `arcpy.AddField_management()`

    Args:
        prop (str): The field property to convert. If it doesn't need converting, return itself.
    """
    lookup = dict(smallinteger='SHORT', integer='LONG', string='TEXT')
    return lookup.get(prop.lower(), prop).upper()

def copy_domain(domain, workspace: str, name: str = None):
    """Copies a domain from one workspace to the other

        Args:
            domain: The domain object to copy.
            workspace (str): The target workspace to create the new domain.
            name (str): The new domain name, if desired. Defaults to ``None``.
    """
    split_policy_values = dict(DefaultValue='DEFAULT',
                        GeometryRatio = 'GEOMETRY_RATIO',
                        Duplicate='DUPLICATE')
    merge_policy_values =  dict(DefaultValue='DEFAULT',
                        SumValues = 'SUM_VALUES',
                        AreaWeighted='AREA_WEIGHTED')

    name = domain.name if name in ['', None] else name
    if domain is None:
        raise ValueError("Domain to copy was not found")
    splitPolicy = split_policy_values[domain.splitPolicy] if domain.splitPolicy in split_policy_values else split_policy_values['DefaultValue']
    mergePolicy = merge_policy_values[domain.mergePolicy] if domain.mergePolicy in merge_policy_values else merge_policy_values['DefaultValue']

    if domain.domainType.upper() == "CODEDVALUE":
        create_coded_domain(coded_values=list(domain.codedValues.items()),
                            code_type=domain.type,
                            workspace=workspace,
                            domain_name=name,
                            domain_desc=domain.description,
                            update_option='REPLACE')
    else:
        domainType = "RANGE"
        arcpy.CreateDomain_management(workspace, name,
                                      ' ' if domain.description in ['', None] else domain.description,
                                      domain.type.upper(),
                                      domainType,
                                      splitPolicy,
                                      mergePolicy)


def create_coded_domain(coded_values: List[Tuple],
                        code_type: str,
                        workspace: str,
                        domain_name: str,
                        domain_desc: str = None,
                        update_option: str = 'REPLACE'):
    """Creates a domain in target workspace from coded_values.

    Args:
        coded_values (list): A list of tuples containing coded values ``[(code1, desc1), (code2, desc2), ...]``.
        code_type (str): Type of domain. Valid types  ["TEXT", "FLOAT", "DOUBLE", "SHORT", "LONG", "DATE", "GUID"]
        workspace (str): The input workspace where the domain will be created.
        domain_name (str): The name of the domain.
        domain_desc (str): The description of the domain. Defaults to ``domain_name``.
        update_option (str): How to update the domain. Defaults to ``'REPLACE'``.


    Raises:
        ValueError: Mismatched datatypes in codes or values
        ValueError: Unsupported datatypes.

    """

    code_type = code_type.upper()
    field_types = {"TEXT", "FLOAT", "DOUBLE", "SHORT", "LONG", "DATE"}
    if code_type not in field_types:
        raise ValueError("Field type '{}' is not valid".format(code_type))
    code_length = ''
    value_length = ''
    codes, values = zip(*coded_values)
    if code_type == "TEXT":
        code_length = len(max(codes, key=len))
    value_length = len(max(values, key=len))
    # if code type is float and workspace is EGDB, cast to double.
    if code_type == "FLOAT":
        desc = arcpy.Describe(workspace)
        if desc.workspaceFactoryProgID.startswith('esriDataSourcesGDB.SdeWorkspaceFactory'):
            code_type = "DOUBLE"

    code_type = ('code', code_type)
    value_type = ('value', "TEXT")

    temp_workspace = 'in_memory'
    # temp_workspace = arcpy.env.scratchGDB

    table = arcpy.CreateUniqueName('table', temp_workspace)

    arcpy.CreateTable_management(temp_workspace, os.path.basename(table))
    arcpy.AddField_management(table, code_type[0], code_type[1], '', '', code_length)
    arcpy.AddField_management(table, value_type[0], value_type[1], '', '', value_length)

    fields = [code_type[0], value_type[0]]
    with arcpy.da.InsertCursor(table, fields) as cursor:
        for coded_value in coded_values:
            cursor.insertRow(coded_value)


    arcpy.TableToDomain_management(in_table=table,
                                   code_field='code',
                                   description_field='value',
                                   in_workspace=workspace,
                                   domain_name=domain_name,
                                   domain_description=' ' if domain_desc in ['', None] else domain_desc,
                                   update_option=update_option)

    try:
        arcpy.Delete_management(table)
    except:
        pass
def get_pro_version() -> Tuple[str]:
    """ Gets the Pro Version and Build number """
    data = arcpy.GetInstallInfo()
    return data['Version'], data['BuildNumber']


def get_absolute_path_from_relative(item: str):
    """ Gets the absolute path of a table, taking arcpy.env.workspace into account """
    if arcpy.env.workspace is None:
        path = item
    else:
        # If item already has a root (eg C:), then os.path.join will use that
        path = os.path.join(arcpy.env.workspace, item)

    return os.path.abspath(path)
def change_dtypes(record_array):
    import numpy as np
    dt = record_array.dtype
    dt = dt.descr # this is now a modifiable list, can't modify numpy.dtype
    for i,dtype in enumerate(dt):
        if "O" in dtype[1]:

            # get the len of the longest string in this column
            # get the records
            ar =  record_array[dtype[0]]
            #Filter out none and nan
            ix = np.isin(ar, [None,np.nan])
            #set the None to empty string
            ar[ix] = ''
            max_len = 256
            if len(ar) != 0:
                max_len = len(max(ar,key=len))
            new_type = f'<U{max_len}'
            dt[i] = (dt[i][0], new_type)
            record_array[dtype[0]] = ar
    dt = np.dtype(dt)
    # data = numpy.array(data, dtype=dt) # option 1
    return record_array.astype(dt)

def df_to_cursor(data_frame: pd.DataFrame, cursor):
    """Inserts rows from data_frame to cursor

    Args:
        data_frame (pandas.DataFrame): A DataFrame. Only the subset of fields used by the cursor will be inserted.
        cursor (arcpy.da.InsertCursor): An opened insert cursor.

    """

    cursor_fields = [f.lower() for f in cursor.fields]
    data_frame.columns = data_frame.columns.str.lower()

    # If there are fields in the cursor that aren't present in the DF, they need to be added.
    for field in cursor_fields:
        if field not in data_frame.columns:
            data_frame[field] = None

    # Keep only those fields that are present in the cursor.
    data_frame = data_frame[cursor_fields]

    for row in data_frame.itertuples(index=False, name=None):
        cursor.insertRow(row)


def df_to_table(data_frame: pd.DataFrame, table):
    """Appends data_frame contents to table

    Args:
        data_frame (pandas.DataFrame): A DataFrame.
        table (str): The target.
    """
    if not data_frame.empty:
        with arcpy.da.InsertCursor(table, data_frame.columns.tolist()) as iCursor:
            df_to_cursor(data_frame, iCursor)


def remove_null_rows(df, test_column):
    """Removed rows with a null value in a column from a panda DataFrame
        Args:
            df (panda.DataFrame): A DataFrame with a geomtr
            test_column (str): Column name to test for null values
        Returns:
            pandas.DataFrame: DataFrame representation of the table.
    """
    return df[~df[test_column].isnull()]


def cursor_to_df(cursor, header=None, has_blob=False):
    """Converts a cursor object to pandas DataFrame
        Args:
            cursor (``arcpy.da.SearchCursor``): A cursor to iterate over.
            header (list): The list of field names to use as header. Defaults to ``None`` which uses the field names as
                reported by the cursor object.
            has_blob (bool): If the cursor, contains blob fields, set this to True. Will process line by line instead of
                loading directly from generator.
        Returns:
            pandas.DataFrame: DataFrame representation of the table.
        Raises:
            ValueError: If the number of fields does not match the record length.
        Examples:
            >>> cursor = arcpy.da.SearchCursor('data', ['OID@', 'SHAPE@X'])
            >>> cursor_to_df(cursor, ['ID', 'X'])
                   ID     X
                0   1  5000
                1   2  1500
    """
    if header is None:
        header = cursor.fields

    if len(header) != len(cursor.fields):
        raise ValueError('The length of header does not match the cursor.')

    # Blob fields are special because they return memoryviews. They need to be cast to bytes otherwise the memoryviews
    # all reference the most recent row. Because of this, the inner loop has to be a list comprehension.
    if has_blob:
        cursor = ([value.tobytes()
                   if isinstance(value, memoryview)
                   else value
                   for value in row]
                  for row in cursor)

    return pd.DataFrame.from_records(cursor, columns=header)


def densify_shape(shape: arcpy.Geometry, **kwargs) -> arcpy.Geometry:
    """
        Densifies the shape if it contains true curves. kwargs match shape.densify()

        For a projected coordinate system:
            All units passed in are assumed to be meters and will be converted accordingly.
            By default, the following parameters are used:
                method = 'DISTANCE'
                distance = 10
                deviation = 1

        For a geographic coordinate system:
            All units passed in are assumed to be degrees and will be converted accordingly.
            By default, the following parameters are used:
                method = 'ANGLE'
                distance = .001
                deviation = 5
    """

    if 'curvePaths' not in shape.JSON:
        return shape

    is_projected = shape.spatialReference.type == 'Projected'

    method = kwargs.pop('method', 'DISTANCE' if is_projected else 'ANGLE')
    distance = kwargs.pop('distance', 10 if is_projected else .001)
    deviation = kwargs.pop('deviation', 1 if is_projected else 5)

    # Densify on PCS uses the underlying spatial reference units, so we need to convert from meters.
    if is_projected:
        distance /= shape.spatialReference.metersPerUnit

    # Similarly, GCS needs the units in radians
    else:
        import math
        deviation = math.radians(deviation)

    return shape.densify(method=method, distance=distance, deviation=deviation)


def arcpy_describe(item):
    """ Returns item if already described, describes it if not """
    if isinstance(item, str):
        item = arcpy.Describe(item)
    return item


def walk_gdb(gdb: str, datatype: str = None, type: str = None, full_path=True):
    """Walks a gdb for items.

    Args:
        gdb (str): The path to the Geodatabase.
        datatype (str): The data type to limit the results returned.
            Defaults to ``None``: return all datatypes.
        type (str): Feature and raster data types can be further limited by type.
            Defaults to ``None``: return all types.
        full_path (bool): A boolean value to return the full path.
            Defaults to ``False``: return only the feature class name.

    Yields:
        each item in ``gdb``

    Examples:
        >>> list(walk_gdb("c:/temp/test.gdb"))
        ["serviceArea", "wHydrant", "wMains", "wValves", "Mains_Hydrant_REL", "accountsTable"]

    Note:
        See documentation on `arcpy.da.Walk()`_ for valid ``datatype`` and ``type``.

    See Also:
        :py:func:`listFeatureClassesInGDB` for listing Feature Classes and
        :py:func:`listTablesInGDB` for listing Tables.

    .. _arcpy.da.Walk():
        http://pro.arcgis.com/en/pro-app/arcpy/data-access/walk.htm


    """

    for dirpath, dirnames, filenames in arcpy.da.Walk(gdb, datatype=datatype, type=type):
        # When the datatype is specifically feature dataset, we want to include them.
        if datatype is not None and datatype.lower() == 'FeatureDataset'.lower():
            for dirname in dirnames:
                yield os.path.normpath(os.path.join(dirpath if full_path else '', dirname))

        for filename in filenames:
            yield os.path.normpath(os.path.join(dirpath if full_path else '', filename))


def list_feature_classes_in_gdb(gdb: str, full_path: bool = False) -> List[str]:
    """List all Feature Classes in a geodatabase, including those inside Feature Datasets.

    Args:
        gdb (str):  The path to the geodatabase.
        full_path (bool): A boolean value to return the full path.
            Defaults to ``False``: return only the feature class name.

    Returns:
        list: The feature class names.

    Examples:
        >>> list_feature_classes_in_gdb("c:/temp/test.gdb")
        ["serviceArea", "wHydrant", "wMains", "wValves"]
        >>> list_feature_classes_in_gdb("c:/temp/test.gdb", "w*", True)
        ["c:/temp/test.gdb/wHydrant", "c:/temp/test.gdb/wMains", "c:/temp/test.gdb/wValves"]

    See Also:
        :py:func:`walkGDB` for listing other geodatabase items.

    """

    return list(walk_gdb(gdb, datatype='FeatureClass', full_path=full_path))


def get_workspace_from_path(item: str):
    """ Gets the path to the workspace (folder, gdb, sde) """
    while not os.path.exists(item):
        item = os.path.dirname(item)
    return item


def create_gdb(path, name):
    """ returns a gdb based on folder and name """
    int_gdb = os.path.join(path, name)

    if not arcpy.Exists(int_gdb):
        arcpy.CreateFileGDB_management(path, name, "CURRENT")
        return int_gdb
    else:
        return int_gdb


def get_name_from_feature_class(feature_class):
    """ returns name from input feature class"""
    desc_fc = arcpy.Describe(feature_class)
    return desc_fc.name

