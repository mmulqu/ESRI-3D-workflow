import logging
import math
from typing import Tuple, Iterable

import arcpy

logger = logging.getLogger(__name__)


class Trenching(object):
    def __init__(self, pixel_size: float):

        self.pixel_size = pixel_size

        self.spatial_reference = None

        # Running list of the widest features which will be used for draping
        self.widest = []

    def vectorize(self, layer: str, depth: float, width: float) -> Iterable[Tuple[float, arcpy.Polygon]]:

        logger.debug(getattr(layer, 'name', layer))
        # Use the spatial reference of the first layer
        if self.spatial_reference is None:
            self.spatial_reference = arcpy.Describe(layer).spatialReference

        if width < self.pixel_size:
            logger.warning(f'Increasing width to {self.pixel_size} to match pixel size')
            width = self.pixel_size

        # It's better to end up short on width since there might be other surface assets that we don't want to sink.
        # Depth is fine going a bit more.
        # The number of iterations is based on the pixel diagonal.
        # We always want at least 1 iteration.
        iterations = max(int(math.floor(width / math.sqrt(pow(self.pixel_size, 2) * 2))), 1)
        depth_factor = depth / iterations

        # Dissolving here means we only need a single call to buffer for the features instead of 1 per feature.
        arcpy.env.outputCoordinateSystem = self.spatial_reference
        dissolve = arcpy.Dissolve_management(in_features=layer,
                                             out_feature_class=arcpy.Geometry())[0]

        loop = range(1, iterations + 1)
        for i, j in zip(reversed(loop), loop):
            logger.debug(f'\t{j}/{iterations}')

            # The last polygon is the largest.
            polygon = dissolve.buffer(j * self.pixel_size)
            if i == 1:
                self.widest.append(polygon)

            yield i * depth_factor, polygon

    def main(self, features: Iterable[Tuple[float, arcpy.Polygon]], output_vector: str, output_raster: str):

        target = arcpy.CreateFeatureclass_management(out_path='in_memory',
                                                     out_name='vectors',
                                                     geometry_type='POLYGON',
                                                     spatial_reference=self.spatial_reference)[0]

        arcpy.AddField_management(target, 'value', 'SHORT')

        with arcpy.da.InsertCursor(target, ['value', 'SHAPE@']) as cursor:
            for row in features:
                cursor.insertRow(row)

        arcpy.Dissolve_management(in_features=self.widest, out_feature_class=output_vector)

        logger.debug('Creating raster')

        arcpy.PolygonToRaster_conversion(in_features=target,
                                         value_field='value',
                                         out_rasterdataset=output_raster,
                                         priority_field='value',
                                         cellsize=self.pixel_size)
