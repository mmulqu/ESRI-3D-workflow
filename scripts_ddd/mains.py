from scripts_ddd._common import *
import collections
import logging
import os
import uuid

import arcpy
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


def guid() -> str:
    return uuid.uuid4().hex


class CreateZFeatures(object):
    """
    Adds z information to point and line feature classes.
    This is an enhanced version of arcpy.FeatureTo3DByAttribute for handling missing data.

    Elevations can be specified based on the following. They are listed in order of preference, so the raster surface
    will only replace missing field values and the TIN will only replace missing surface raster elevations.
        Field values
        Raster Surface
        Interpolated from field values (TIN created from known good start/end elevations)

    For lines...
    Only the start/end points are interpolated, so that there is a consistent slope through the entire line instead of
    a (potentially) different slope between each vertex. This is one of the key differences of interpolating the entire
    line (eg with arcpy.AddSurfaceInformation)

    An "error" field is written to the output feature class detailing the state of the elevations:
        Error - missing data that was unable to be interpolated
        Interpolated - missing data that was replaced
        Good - all good :)
    """
    SCRATCH = 'in_memory'

    ERROR = 0
    OK = 1
    INTERPOLATED = 2

    ERROR_DOMAIN_NAME = 'Interpolate Z Values - Error Types'
    ERROR_DOMAIN_CODES = {ERROR: 'Missing Elevation', OK: 'Good Elevation', INTERPOLATED: 'Interpolated Elevation'}

    ORIG_FID = 'FID'
    ERROR_FIELD = 'error_type'
    STARTING_FIELD = 'is_start'

    def __init__(self,
                 input_lines: str, start_elevation: str = None, end_elevation: str = None,
                 z_factor: float = 1,
                 default_elevation: float = -99, elevation_mask: float = None):

        self.input = input_lines
        self.input_desc = arcpy.Describe(input_lines)
        self.IS_LINE = self.input_desc.shapeType.upper() == 'Polyline'.upper()
        self.shape_token = 'SHAPE@' if self.IS_LINE else 'SHAPE@XY'

        self.start_field = start_elevation or 'start'
        self.end_field = end_elevation or 'end'
        self.fields = [self.start_field]
        if self.IS_LINE:
            self.fields.append(self.end_field)

        nt = collections.namedtuple('Field', ['x', 'y'])
        self.start_shape = nt('START@X', 'START@Y')
        self.end_shape = nt('END@X', 'END@Y')

        self.default_elevation = default_elevation
        self.elevation_mask = elevation_mask

        self.elevation_scale = z_factor or 1

    def read_source_and_convert(self) -> pd.DataFrame:
        """ Replace missing elevations with default
            Convert elevations based on units
        """

        # Elevation fields are optional, so initialize if not present.
        cursor_fields = [f for f in self.fields
                         if f.lower() in
                         {f.name.lower() for f in self.input_desc.fields}]

        with arcpy.da.SearchCursor(in_table=self.input,
                                   field_names=['OID@', self.shape_token, *cursor_fields]) as cursor:
            df = cursor_to_df(cursor)
            df = remove_null_rows(df, self.shape_token)
            df.rename(columns={"OID@": self.ORIG_FID}, inplace=True)
            for field in self.fields:
                if field not in df.columns:
                    df[field] = None

        # Add X/Y fields for the point attributes, which are used during interpolation
        if self.IS_LINE:
            extract = df[self.shape_token].apply(lambda f: (f.firstPoint.X, f.firstPoint.Y,
                                                            f.lastPoint.X, f.lastPoint.Y))
            df[self.start_shape.x], df[self.start_shape.y], df[self.end_shape.x], df[self.end_shape.y] = zip(*extract)
        else:
            df[self.start_shape.x], df[self.start_shape.y] = zip(*df[self.shape_token])

        # Find all null elevations and mark these lines as errors. During interpolation, this will be overwritten.
        if self.elevation_mask is not None:
            df.replace({f: self.elevation_mask for f in self.fields}, value=np.nan, inplace=True)
        # Warn the user if the error elevation they choose is within the lowest and highest elevations.
        lowest = df[self.fields].min().min()
        highest = df[self.fields].max().max()
        if lowest <= self.default_elevation <= highest:
            arcpy.AddWarning((f'The default value is within the range of elevations of your data. '
                              f'Choosing a number outside this range is suggested to highlight missing data. '              
                              f'({lowest} <= {self.default_elevation} <= {highest}).'))
            # logger.warning((f'The default value is within the range of elevations of your data. '
            #                 f'Choosing a number outside this range is suggested to highlight missing data. '
            #                 f'({lowest} <= {self.default_elevation} <= {highest}).'))


        df[self.ERROR_FIELD] = self.OK
        null_mask = df[self.start_field].isnull()
        if self.IS_LINE:
            null_mask |= df[self.end_field].isnull()
        df.loc[null_mask, self.ERROR_FIELD] = self.ERROR

        # The default elevation is applied after scaling because this value is used
        # as an obvious cue to the user that the elevation was missing.
        df[self.fields] *= self.elevation_scale

        return df

    def _extract_vertices(self, df: pd.DataFrame, use_start: bool, export_null: bool) -> np.ndarray:
        """ Creates numpy array of the vertices """
        from numpy.lib import recfunctions

        if use_start:
            shape_fields = list(self.start_shape)
            elevation_field = self.start_field
        else:
            shape_fields = list(self.end_shape)
            elevation_field = self.end_field

        # Easily rename the shape fields.
        shape_fields = dict(zip(shape_fields, ['X', 'Y']))

        if export_null:
            mask = df[elevation_field].isnull()
        else:
            # Only create 3D point when the Z value is not null (this will be used to create TIN)
            mask = df[elevation_field].notnull()
            shape_fields[elevation_field] = 'Z'

        # An additional field will store 1 if the point is the starting vertex and 0 for end.
        # With FID, this can be used to uniquely identify what elevation to update.
        # Rename shape fields so that both start/end vertices can be combined.
        array = df.loc[mask, [self.ORIG_FID, *shape_fields]].to_records(index=False)
        array = recfunctions.rec_append_fields(base=array,
                                               names=self.STARTING_FIELD,
                                               data=[use_start] * array.size,
                                               dtypes=np.int8)
        array = recfunctions.rename_fields(base=array, namemapper=shape_fields)
        return array

    def create_vertex_fc(self, df: pd.DataFrame, export_good_elevations: bool):
        """" Extracts the start/end vertices of the line and creates a point feature class

            "Good" elevations are needed when creating a TIN
            "Bad" elevations are needed when interpolating against a raster surface
        """
        # When exporting the good elevations (for building a TIN) the Z values come from the field.
        shape_fields = ['X', 'Y']
        if export_good_elevations:
            shape_fields.append('Z')

        array = self._extract_vertices(df, use_start=True, export_null=not export_good_elevations)
        if self.IS_LINE:
            end = self._extract_vertices(df, use_start=False, export_null=not export_good_elevations)
            array = np.concatenate((array, end))

        name = 'good' if export_good_elevations else 'missing'
        fc = os.path.join(self.SCRATCH, f'vertex_{name}_{guid()}')
        logger.debug(f'Creating vertex fc {fc} with {len(array)} points')
        arcpy.da.NumPyArrayToFeatureClass(in_array=array,
                                          out_table=fc,
                                          shape_fields=shape_fields,
                                          spatial_reference=self.input_desc.spatialReference)
        return fc

    def interpolate_invalid_elevations(self, df: pd.DataFrame, raster: str, offset: float):
        """ Creates feature class with points from the start/end elevations """

        fc = self.create_vertex_fc(df, export_good_elevations=False)

        logger.debug('Adding surface information')
        arcpy.AddSurfaceInformation_3d(in_feature_class=fc,
                                       in_surface=raster,
                                       out_property='Z')

        # Some points may not be located (eg out of raster extent)
        with arcpy.da.SearchCursor(fc, [self.ORIG_FID, self.STARTING_FIELD, 'Z'],
                                   where_clause='Z IS NOT NULL') as cursor:
            interpolated = cursor_to_df(cursor)
            interpolated['Z'] += offset

        # Changing the boolean starting values to the names of the fields allows for easy updating.
        # GroupBy -> Unstack creates a column for each the starting/end elevation. Depending on which
        # vertices were created, some of these values will be NaN (which DataFrame.update ignores)
        interpolated.replace({self.STARTING_FIELD: {1: self.start_field, 0: self.end_field}}, inplace=True)
        interpolated: pd.DataFrame = interpolated.groupby([self.ORIG_FID, self.STARTING_FIELD]).first().unstack()
        interpolated.columns = interpolated.columns.droplevel(0)
        interpolated[self.ERROR_FIELD] = self.INTERPOLATED

        df.set_index(self.ORIG_FID, inplace=True)
        df.update(interpolated)
        df.reset_index(inplace=True)

    def post_process(self, fc: str):
        """ Assigns domains and brings over original fields """

        # Bring over original fields
        logger.debug('Joining original Attributes')
        arcpy.JoinField_management(in_data=fc,
                                   in_field=self.ORIG_FID,
                                   join_table=self.input,
                                   join_field=self.input_desc.oidFieldName)

        # If a user created a shapefile, we can't assign domains
        gdb = get_workspace_from_path(fc)
        logger.debug('Creating output domain')
        if os.path.splitext(gdb)[-1].lower() in ('.gdb', '.sde'):
            domains = {d.name.lower() for d in arcpy.da.ListDomains(gdb)}
            if self.ERROR_DOMAIN_NAME.lower() not in domains:
                arcpy.CreateDomain_management(in_workspace=gdb,
                                              domain_name=self.ERROR_DOMAIN_NAME,
                                              domain_description='',
                                              field_type='SHORT',
                                              domain_type='CODED')

                for code, desc in self.ERROR_DOMAIN_CODES.items():
                    arcpy.AddCodedValueToDomain_management(in_workspace=gdb,
                                                           domain_name=self.ERROR_DOMAIN_NAME,
                                                           code=code,
                                                           code_description=desc)

            arcpy.AssignDomainToField_management(in_table=fc,
                                                 field_name=self.ERROR_FIELD,
                                                 domain_name=self.ERROR_DOMAIN_NAME)

    def create_3d_lines(self, df: pd.DataFrame, output_lines: str):
        """ Converts dataframe to line feature class and adds the elevation information """

        df.fillna({f: self.default_elevation for f in self.fields}, inplace=True)

        fc = arcpy.CreateFeatureclass_management(out_path=self.SCRATCH,
                                                 out_name=f'lines_{uuid.uuid4().hex}',
                                                 geometry_type=self.input_desc.shapeType,
                                                 has_m='DISABLED',
                                                 has_z='DISABLED',
                                                 spatial_reference=self.input_desc.spatialReference)[0]
        logger.debug(f'Writing temporary results to {fc}')
        # Strip source table name if input layers was part of a join
        target_fields = [f.split('.')[-1] for f in self.fields]
        arcpy.AddFields_management(in_table=fc,
                                   field_description=[(self.ORIG_FID, 'LONG', None, None, None),
                                                      *[(f, 'DOUBLE', None, None, None) for f in target_fields],
                                                      (self.ERROR_FIELD, 'SHORT', 'Error Type', None, None)])

        source_fields = [self.ORIG_FID, *self.fields, self.ERROR_FIELD, self.shape_token]
        target_fields = [self.ORIG_FID, *target_fields, self.ERROR_FIELD, self.shape_token]
        with arcpy.da.InsertCursor(fc, target_fields) as cursor:
            for row in df[source_fields].itertuples(index=False, name=None):
                cursor.insertRow(row)

        logger.debug(f'Converting lines to 3D {output_lines}')
        arcpy.FeatureTo3DByAttribute_3d(in_features=fc,
                                        out_feature_class=output_lines,
                                        height_field=self.start_field.split('.')[-1],
                                        to_height_field=self.end_field.split('.')[-1] if self.IS_LINE else None)

    def create_tin(self, df: pd.DataFrame) -> str:
        """ Creates TIN from the good elevation values """

        fc = self.create_vertex_fc(df, export_good_elevations=True)
        good_count = int(arcpy.GetCount_management(fc)[0])
        tin = os.path.join(arcpy.env.scratchFolder, f'tin_{guid()}')

        logger.info(f'Creating TIN from {good_count:,}/{len(df)*2:,} points')
        logger.debug(tin)
        return arcpy.CreateTin_3d(out_tin=tin,
                                  spatial_reference=self.input_desc.spatialReference,
                                  in_features=f'{fc} Shape.Z Mass_Points <None>',
                                  constrained_delaunay='DELAUNAY')[0]

    def main(self,
             output_lines: str,
             interpolate_invalid: bool = False,
             surface_raster: str = None,
             raster_offset: float = 0):

        df = self.read_source_and_convert()

        if surface_raster is not None:
            self.interpolate_invalid_elevations(df, raster=surface_raster, offset=raster_offset or 0)

        if interpolate_invalid:
            # the TIN does not need to be offset because the elevations are derived from surrounding points
            tin = self.create_tin(df)
            self.interpolate_invalid_elevations(df, raster=tin, offset=0)

            arcpy.Delete_management(tin)

        self.create_3d_lines(df, output_lines)
        self.post_process(output_lines)


