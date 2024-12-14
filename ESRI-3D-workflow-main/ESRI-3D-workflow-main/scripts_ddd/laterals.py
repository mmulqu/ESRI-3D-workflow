import logging
import os
import uuid
from typing import Iterator

import arcpy
import numpy as np
import pandas as pd

from scripts_ddd._common import *
from . import *


logger = logging.getLogger(__name__)


class CalculateZBySlope(object):
    SCRATCH = 'in_memory'
    REMOVE_TEMP_DATASETS = True

    ORIG_FID = 'FID'
    SHAPE_FIELD = 'Shape@'
    SHAPE_X = SHAPE_FIELD + 'X'
    SHAPE_Y = SHAPE_FIELD + 'Y'
    SHAPE_Z = SHAPE_FIELD + 'Z'
    Z_OFFSET = SHAPE_FIELD + 'Offset'
    NEAR_DIST = 'NEAR_DIST'
    NEAR_FID = 'FID_3D_LINE'

    def __init__(self,
                 lines_3d: str,
                 lines_2d: str,
                 slope_field: str = None, default_slope: float = None, slope_is_positive: bool = True,
                 use_end_vertex: bool = True):

        self.lines_3d = lines_3d
        self.lines_2d = lines_2d
        self.input_desc = arcpy.Describe(self.lines_2d)

        self.slope_field = 'Shape@Slope' if slope_field is None else slope_field
        self.use_end_vertex = use_end_vertex
        self.default_slope = default_slope or 0
        self.positive_slope = slope_is_positive

        # Unique guid for each FC
        self.guid = f'_{uuid.uuid4().hex}'

        self.df: pd.DataFrame = None

    def cleanup(self, item):
        if not self.REMOVE_TEMP_DATASETS:
            return
        try:
            arcpy.Delete_management(item)
        except:
            pass

    def read_source(self):
        msg = 'Reading input features (1/6)'
        logger.debug(msg)
        arcpy.SetProgressorLabel(msg)

        # Fields are optional, so initialize if not present
        cursor_fields = [f for f in [self.slope_field]
                         if f.lower() in
                         {f.baseName.lower() for f in self.input_desc.fields}]

        array = arcpy.da.FeatureClassToNumPyArray(in_table=self.lines_2d,
                                                  field_names=['OID@', self.SHAPE_X, self.SHAPE_Y, *cursor_fields],
                                                  where_clause=f'{self.input_desc.shapeFieldName} IS NOT null',
                                                  explode_to_points=True)
        df = pd.DataFrame(array)
        if self.slope_field not in df:
            df[self.slope_field] = self.default_slope

        df.fillna({self.slope_field: self.default_slope}, inplace=True)
        df.rename(columns={"OID@": self.ORIG_FID}, inplace=True)

        # The vertices will always be grouped by the line they belong to.
        shape_cols = [self.SHAPE_X, self.SHAPE_Y]
        group = df.groupby(self.ORIG_FID)

        # Flip line if endpoint is at the snapping line.
        if self.use_end_vertex:
            # Cumulative count gives us the vertex number, so it's efficient to "flip" the line this way.
            df['rank'] = group.cumcount()
            df.sort_values([self.ORIG_FID, 'rank'], ascending=[True, False], inplace=True)
            df.reset_index(drop=True, inplace=True)

        # To scale the Z position of each vertex, we need to calculate the distance between each vertex and then
        # keep a running tally (cumulative sum) of distances back to the starting point.
        # https://stackoverflow.com/q/1401712
        # Z offset at each vertex is tan(slope) * distance
        points = df[shape_cols]
        shifted = group[shape_cols].shift(1)
        df['dist'] = np.linalg.norm(points.values - shifted.values, axis=1)
        df[self.Z_OFFSET] = np.tan(np.deg2rad(np.absolute(df[self.slope_field]))) * group['dist'].cumsum().fillna(0)
        if not self.positive_slope:
            df[self.Z_OFFSET] *= -1

        df.drop(columns=[self.slope_field, 'dist'], inplace=True)
        self.df = df

    def snap(self, df) -> Iterator[float]:
        msg = 'Snapping line end to 3D features (5/6)'
        logger.debug(msg)
        arcpy.SetProgressorLabel(msg)
        total = len(df)
        step = max(total // 100, 10)
        arcpy.SetProgressor(type='STEP', message=msg, min_range=0, max_range=total, step_value=step)

        generator = df[[self.SHAPE_FIELD, self.SHAPE_X, self.SHAPE_Y]].itertuples(index=False, name=None)
        for i, (line, x, y) in enumerate(generator, 1):
            if not i % step:
                logger.debug("...{:.0f}%".format(100 * i / total))
                arcpy.SetProgressorPosition()
            yield line.snapToLine(arcpy.Point(x, y)).firstPoint.Z

        arcpy.ResetProgressor()

    def read_3d_lines(self):

        # Export the starting point of each lateral to feature class.
        msg = 'Exporting end points (2/6)'
        logger.debug(msg)
        arcpy.SetProgressorLabel(msg)
        shape_fields = [self.SHAPE_X, self.SHAPE_Y]
        point_df: pd.DataFrame = self.df.groupby(self.ORIG_FID)[shape_fields].first()
        point_fc = os.path.join(self.SCRATCH, f'{self.guid}_vertex')
        arcpy.da.NumPyArrayToFeatureClass(in_array=point_df.to_records(index=False),
                                          out_table=point_fc,
                                          shape_fields=shape_fields,
                                          spatial_reference=self.input_desc.spatialReference)

        # Create near table linking starting points to nearest 3D line.
        msg = 'Generating near table (3/6)'
        logger.debug(msg)
        arcpy.SetProgressorLabel(msg)
        near_table = arcpy.GenerateNearTable_analysis(in_features=point_fc,
                                                      near_features=self.lines_3d,
                                                      out_table=os.path.join(self.SCRATCH, f'{self.guid}_near'),
                                                      search_radius=None,
                                                      location=False,
                                                      angle=False,
                                                      closest=True)[0]
        self.cleanup(point_fc)

        # The vertex oid (IN_FID) is the wrong value when the point oid does not start at 1 (such as when the input
        # has a selection). Instead of writing the FID to the point FC, and then joining to the near table, we can
        # use the original values and index by position, offseting by 1 because objectID starts at 1.

        # Points 17 and 5 are missing from the near table because they are outside of the tolerance.
        # In order to link 2/4 back to 22/12, we need to slice by positions 1/3.
        #
        # | DF oid | FC oid | near table IN_FID |
        # |--------|--------|-------------------|
        # | 17     | 1      | 2                 |
        # | 22     | 2      | 4                 |
        # | 5      | 3      |                   |
        # | 12     | 4      |                   |
        near_df = pd.DataFrame(arcpy.da.TableToNumPyArray(near_table, ['IN_FID', 'NEAR_FID', 'NEAR_DIST']))
        near_df['IN_FID'] = point_df.index.values[tuple([near_df['IN_FID'].values - 1])]
        near_df.rename(columns=dict(NEAR_DIST=self.NEAR_DIST, NEAR_FID=self.NEAR_FID), inplace=True)

        self.cleanup(near_table)

        # Read line shapes and join with near table.
        msg = 'Reading input 3D features (4/6)'
        logger.debug(msg)
        arcpy.SetProgressorLabel(msg)
        with arcpy.da.SearchCursor(self.lines_3d, ['OID@', self.SHAPE_FIELD]) as cursor:
            line_df = cursor_to_df(cursor)
            line_df = remove_null_rows(line_df, self.SHAPE_FIELD)
            line_df = (line_df
                       .set_index('OID@')
                       .merge(near_df, left_index=True, right_on=self.NEAR_FID)
                       .set_index('IN_FID'))

        # Join line geometry to first points
        # Snap point to line and extract Z value
        df = point_df.merge(line_df, left_index=True, right_index=True)
        df[self.SHAPE_Z] = list(self.snap(df))

        columns = [self.SHAPE_Z, self.NEAR_DIST, self.NEAR_FID]
        self.df = self.df.merge(df[columns], left_on=self.ORIG_FID, right_index=True)

    def create_output_fc(self, output: str) -> str:
        describe = arcpy.Describe(self.lines_3d)
        path, name = os.path.split(output)
        line_fc = arcpy.CreateFeatureclass_management(out_path=path,
                                                      out_name=name,
                                                      geometry_type='POLYLINE',
                                                      has_m='DISABLED',
                                                      has_z='ENABLED',
                                                      spatial_reference=describe.spatialReference)[0]
        arcpy.AddFields_management(in_table=line_fc,
                                   field_description=[(self.ORIG_FID, 'LONG'),
                                                      (self.NEAR_FID, 'LONG'),
                                                      (self.NEAR_DIST, 'FLOAT')])

        return line_fc

    def post_process(self, fc: str):
        """ Brings over original fields """

        # Bring over original fields
        logger.debug('Joining original Attributes')
        arcpy.JoinField_management(in_data=fc,
                                   in_field=self.ORIG_FID,
                                   join_table=self.lines_2d,
                                   join_field=self.input_desc.oidFieldName)

    def main(self, result: str):
        self.read_source()
        self.read_3d_lines()
        df = self.df

        # Flip the lines back to their original digitized direction. This needs to occur before merging with Z values
        # because we only want to flip the line in 2D space.
        if self.use_end_vertex:
            df.sort_values([self.ORIG_FID, 'rank'], ascending=[True, True], inplace=True)
        df[self.SHAPE_Z] += df[self.Z_OFFSET]

        # To create a polyline from a list of vertices, we need to find each OID and split at the boundary.
        # Faster implementation of df.groupby().apply(list) adopted from https://stackoverflow.com/a/42550516
        shape_cols = [self.SHAPE_X, self.SHAPE_Y, self.SHAPE_Z]
        attribute_cols = [self.ORIG_FID, self.NEAR_FID, self.NEAR_DIST]
        index = np.unique(df[self.ORIG_FID].values, return_index=True)[1]
        shape_data = (arr.tolist() for arr in np.split(df[shape_cols].values, index[1:]))
        data: pd.DataFrame = df.iloc[index, [df.columns.tolist().index(col) for col in attribute_cols]]
        data[self.SHAPE_FIELD] = list(shape_data)

        msg = 'Saving lines (6/6)'
        logger.debug(msg)
        arcpy.SetProgressorLabel(msg)
        total = len(data)
        step = max(total // 100, 10)
        arcpy.SetProgressor(type='STEP', message=msg, min_range=0, max_range=total, step_value=step)

        line_fc = self.create_output_fc(result)
        fields = [self.SHAPE_FIELD, *attribute_cols]
        generator = data[fields].itertuples(index=False, name=None)

        with arcpy.da.InsertCursor(line_fc, fields) as cursor:
            for i, row in enumerate(generator, 1):
                if not i % step:
                    logger.debug("...{:.0f}%".format(100 * i / total))
                    arcpy.SetProgressorPosition()
                cursor.insertRow(row)
        self.post_process(line_fc)
