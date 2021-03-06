# -*- coding: utf-8 -*-

"""
/***************************************************************************
 LeastCostPath
                                 A QGIS plugin
 Find the least cost path with given cost raster and points
 Generated by Plugin Builder: http://g-sherman.github.io/Qgis-Plugin-Builder/
                              -------------------
        begin                : 2018-12-12
        copyright            : (C) 2018 by FlowMap Group@SESS.PKU
        email                : xurigong@gmail.com
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""

__author__ = 'FlowMap Group@SESS.PKU'
__date__ = '2018-12-12'
__copyright__ = '(C) 2018 by FlowMap Group@SESS.PKU'

# This will get replaced with a git SHA1 when you do a git archive

__revision__ = '$Format:%H$'

from PyQt5.QtCore import QCoreApplication, QVariant
from PyQt5.QtGui import QIcon
from qgis.core import (
    QgsFeature,
    QgsGeometry,
    QgsPoint,
    QgsField,
    QgsFields,
    QgsWkbTypes,
    QgsProcessing,
    QgsFeatureSink,
    QgsProcessingException,
    QgsProcessingAlgorithm,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterRasterLayer,
    QgsProcessingParameterBand,
    QgsProcessingParameterBoolean
)
import processing
from .dijkstra_algorithm import dijkstra
from math import floor, sqrt
import queue
import collections


class LeastCostPathAlgorithm(QgsProcessingAlgorithm):
    """
    This is the Least Cost Path Plugin that runs dijkstra algorithm
    """

    # Constants used to refer to parameters and outputs. They will be
    # used when calling the algorithm from another algorithm, or when
    # calling from the QGIS console.

    INPUT_COST_RASTER = 'INPUT_COST_RASTER'
    INPUT_RASTER_BAND = 'INPUT_RASTER_BAND'
    INPUT_START_LAYER = 'INPUT_START_LAYER'
    INPUT_END_LAYER = 'INPUT_END_LAYER'
    BOOLEAN_FIND_LEAST_PATH_TO_ALL_ENDS = 'BOOLEAN_FIND_LEAST_PATH_TO_ALL_ENDS'
    BOOLEAN_OUTPUT_LINEAR_REFERENCE = 'BOOLEAN_OUTPUT_LINEAR_REFERENCE'
    OUTPUT = 'OUTPUT'

    def initAlgorithm(self, config):
        """
        Here we define the inputs and output of the algorithm, along
        with some other properties.
        """
        self.addParameter(
            QgsProcessingParameterRasterLayer(
                self.INPUT_COST_RASTER,
                self.tr('Cost raster layer'),
            )
        )

        self.addParameter(
            QgsProcessingParameterBand(
                self.INPUT_RASTER_BAND,
                self.tr('Cost raster band'),
                0,
                self.INPUT_COST_RASTER,
            )
        )

        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.INPUT_START_LAYER,
                self.tr('Start-point layer'),
                [QgsProcessing.TypeVectorPoint]
            )
        )

        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.INPUT_END_LAYER,
                self.tr('End-point(s) layer'),
                [QgsProcessing.TypeVectorPoint]
            )
        )

        self.addParameter(
            QgsProcessingParameterBoolean(
                self.BOOLEAN_FIND_LEAST_PATH_TO_ALL_ENDS,
                self.tr('Only connect with the nearest end points'),
                defaultValue = False
            )
        )

        self.addParameter(
            QgsProcessingParameterBoolean(
                self.BOOLEAN_OUTPUT_LINEAR_REFERENCE,
                self.tr('Include liner referencing (PolylineM type)')
            )
        )

        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT,
                self.tr('Output least cost path')
            )
        )

    def processAlgorithm(self, parameters, context, feedback):
        """
        Here is where the processing itself takes place.
        """
        feedback.setProgress(1)

        cost_raster = self.parameterAsRasterLayer(
            parameters,
            self.INPUT_COST_RASTER,
            context
        )

        cost_raster_band = self.parameterAsInt(
            parameters,
            self.INPUT_RASTER_BAND,
            context
        )

        start_source = self.parameterAsSource(
            parameters,
            self.INPUT_START_LAYER,
            context
        )

        find_nearest = self.parameterAsBool(
            parameters,
            self.BOOLEAN_FIND_LEAST_PATH_TO_ALL_ENDS,
            context
        )

        output_linear_reference = self.parameterAsBool(
            parameters,
            self.BOOLEAN_OUTPUT_LINEAR_REFERENCE,
            context
        )

        end_source = self.parameterAsSource(
            parameters,
            self.INPUT_END_LAYER,
            context
        )

        # If source was not found, throw an exception to indicate that the algorithm
        # encountered a fatal error. The exception text can be any string, but in this
        # case we use the pre-built invalidSourceError method to return a standard
        # helper text for when a source cannot be evaluated
        if cost_raster is None:
            raise QgsProcessingException(self.invalidSourceError(parameters, self.INPUT_COST_RASTER))
        if cost_raster_band is None:
            raise QgsProcessingException(self.invalidSourceError(parameters, self.INPUT_RASTER_BAND))
        if start_source is None:
            raise QgsProcessingException(self.invalidSourceError(parameters, self.INPUT_START_LAYER))
        if end_source is None:
            raise QgsProcessingException(self.invalidSourceError(parameters, self.INPUT_START_LAYER))

        if cost_raster.crs() != start_source.sourceCrs() \
                or start_source.sourceCrs() != end_source.sourceCrs():
            raise QgsProcessingException(self.tr("ERROR: The input layers have different CRSs."))

        if cost_raster.rasterType() not in [cost_raster.Multiband, cost_raster.GrayOrUndefined]:
            raise QgsProcessingException(self.tr("ERROR: The input cost raster is not numeric."))

        sink_fields = MinCostPathHelper.create_fields()
        output_geometry_type = QgsWkbTypes.LineStringM if output_linear_reference else QgsWkbTypes.LineString
        (sink, dest_id) = self.parameterAsSink(
            parameters,
            self.OUTPUT,
            context,
            fields=sink_fields,
            geometryType=output_geometry_type,
            crs=cost_raster.crs(),
        )

        # If sink was not created, throw an exception to indicate that the algorithm
        # encountered a fatal error. The exception text can be any string, but in this
        # case we use the pre-built invalidSinkError method to return a standard
        # helper text for when a sink cannot be evaluated
        if sink is None:
            raise QgsProcessingException(self.invalidSinkError(parameters, self.OUTPUT))

        start_features = list(start_source.getFeatures())
        # feedback.pushInfo(str(len(start_features)))

        # row_col, pointxy, id
        start_tuples = MinCostPathHelper.features_to_tuples(start_features, cost_raster)
        if len(start_tuples) == 0:
            raise QgsProcessingException(self.tr("ERROR: The start-point layer contains no legal point."))
        elif len(start_tuples) >= 2:
            raise QgsProcessingException(self.tr("ERROR: The start-point layer contains more than one legal point."))
        start_tuple = start_tuples[0]

        end_features = list(end_source.getFeatures())
        # feedback.pushInfo(str(len(end_features)))
        end_tuples = MinCostPathHelper.features_to_tuples(end_features, cost_raster)
        if len(end_tuples) == 0:
            raise QgsProcessingException(self.tr("ERROR: The end-point layer contains no legal point."))

        # if start_row_col in end_row_cols:
        #     raise QgsProcessingException(self.tr("ERROR: The end-point(s) overlap with start point."))
        # feedback.pushInfo(str(start_col_rows))
        # feedback.pushInfo(str(end_col_rows))

        block = MinCostPathHelper.get_all_block(cost_raster, cost_raster_band)
        matrix, contains_negative = MinCostPathHelper.block2matrix(block)
        feedback.pushInfo(self.tr("The size of cost raster is: %d * %d") % (block.height(), block.width()))

        if contains_negative:
            raise QgsProcessingException(self.tr("ERROR: Cost raster contains negative value."))

        feedback.pushInfo(self.tr("Searching least cost path..."))

        result = dijkstra(start_tuple, end_tuples, matrix, find_nearest, feedback)
        # feedback.pushInfo(str(min_cost_path))
        if result is None:
            raise QgsProcessingException(self.tr("ERROR: Search canceled."))

        if len(result) == 0:
            raise QgsProcessingException(self.tr("ERROR: The end-point(s) is not reachable from start-point."))

        feedback.setProgress(100)
        feedback.pushInfo(self.tr("Search completed! Saving path..."))

        for path, costs, terminal_tuples in result:
            for terminal_tuple in terminal_tuples:
                path_points = MinCostPathHelper.create_points_from_path(cost_raster, path, start_tuple[1], terminal_tuple[1])
                if output_linear_reference:
                    # add linear reference
                    for point, cost in zip(path_points, costs):
                        point.addMValue(cost)
                
                total_cost = costs[-1]
                path_feature = MinCostPathHelper.create_path_feature_from_points(path_points, (start_tuple[2], terminal_tuple[2],total_cost), sink_fields)
                sink.addFeature(path_feature, QgsFeatureSink.FastInsert)

        # start_point = start_row_cols_dict[start_row_col]
        # end_point = end_row_cols_dict[selected_end]
        # path_points = MinCostPathHelper.create_points_from_path(cost_raster, min_cost_path, start_point, end_point)
        # if output_linear_reference:
        #     # add linear reference
        #     for point, cost in zip(path_points, costs):
        #         point.addMValue(cost)
        # total_cost = costs[-1]
        # path_feature = MinCostPathHelper.create_path_feature_from_points(path_points, total_cost, sink_fields)

        # sink.addFeature(path_feature, QgsFeatureSink.FastInsert)
        return {self.OUTPUT: dest_id}

    def name(self):
        """
        Returns the algorithm name, used for identifying the algorithm. This
        string should be fixed for the algorithm, and must not be localised.
        The name should be unique within each provider. Names should contain
        lowercase alphanumeric characters only and no spaces or other
        formatting characters.
        """
        return 'Least Cost Path'

    def displayName(self):
        """
        Returns the translated algorithm name, which should be used for any
        user-visible display of the algorithm name.
        """
        return self.tr(self.name())

    def group(self):
        """
        Returns the name of the group this algorithm belongs to. This string
        should be localised.
        """
        return self.tr(self.groupId())

    def groupId(self):
        """
        Returns the unique ID of the group this algorithm belongs to. This
        string should be fixed for the algorithm, and must not be localised.
        The group id should be unique within each provider. Group id should
        contain lowercase alphanumeric characters only and no spaces or other
        formatting characters.
        """
        return ''

    def tr(self, string):
        return QCoreApplication.translate('Processing', string)

    def createInstance(self):
        return LeastCostPathAlgorithm()

    def helpUrl(self):
        return 'https://github.com/Gooong/LeastCostPath'

    def shortHelpString(self):
        return self.tr("""
        Please ensure all the input layers have the same CRS.

        - Cost raster layer: Numeric raster layer that represents the cost of each spatial unit. It should not contains negative value. Pixel with `NoData` value represent it is unreachable.
        
        - Cost raster band: The input band of the cost raster.
        
        - Start-point layer: Layer that contains just one start point.
        
        - End-point(s) layer: Layer that contains the destination point(s).
        
        - Only connect with the nearest end points: If more than one destination are provided, it will find the least cost path to all the end points by default. If enabled, the least cost path will only connect start point with the nearest end point.

        - \[Optional\] Include liner referencing (PolylineM type): If selected, this algorithm will output the least cost path in `PolylineM` type, with the accumulated cost as linear referencing value.
                
        """)

    def shortDescription(self):
        return self.tr('Find the least cost path with given cost raster and points.')

    def svgIconPath(self):
        return ''

    def tags(self):
        return ['least', 'cost', 'path', 'distance', 'raster', 'analysis', 'road']


class MinCostPathHelper:

    @staticmethod
    def _point_to_row_col(pointxy, raster_layer):
        xres = raster_layer.rasterUnitsPerPixelX()
        yres = raster_layer.rasterUnitsPerPixelY()
        extent = raster_layer.dataProvider().extent()

        col = floor((pointxy.x() - extent.xMinimum()) / xres)
        row = floor((extent.yMaximum() - pointxy.y()) / yres)

        return row, col

    @staticmethod
    def _row_col_to_point(row_col, raster_layer):
        xres = raster_layer.rasterUnitsPerPixelX()
        yres = raster_layer.rasterUnitsPerPixelY()
        extent = raster_layer.dataProvider().extent()

        x = (row_col[1] + 0.5) * xres + extent.xMinimum()
        y = extent.yMaximum() - (row_col[0] + 0.5) * yres
        return QgsPoint(x, y)

    @staticmethod
    def create_points_from_path(cost_raster, min_cost_path, start_point, end_point):
        path_points = list(
            map(lambda row_col: MinCostPathHelper._row_col_to_point(row_col, cost_raster), min_cost_path))
        path_points[0].setX(start_point.x())
        path_points[0].setY(start_point.y())
        path_points[-1].setX(end_point.x())
        path_points[-1].setY(end_point.y())
        return path_points

    @staticmethod
    def create_fields():
        start_field = QgsField("start point id", QVariant.Int, "int")
        end_field = QgsField("end point id", QVariant.Int, "int")
        cost_field = QgsField("total cost", QVariant.Double, "double", 10, 3)
        fields = QgsFields()
        fields.append(start_field)
        fields.append(end_field)
        fields.append(cost_field)
        return fields

    @staticmethod
    def create_path_feature_from_points(path_points, attr_vals, fields):
        polyline = QgsGeometry.fromPolyline(path_points)
        feature = QgsFeature(fields)
        # feature.setAttribute(0, 1) # id
        start_index = feature.fieldNameIndex("start point id")
        end_index = feature.fieldNameIndex("end point id")
        cost_index = feature.fieldNameIndex("total cost")
        feature.setAttribute(start_index, attr_vals[0])
        feature.setAttribute(end_index, attr_vals[1])
        feature.setAttribute(cost_index, attr_vals[2])  # cost
        feature.setGeometry(polyline)
        return feature

    @staticmethod
    def features_to_tuples(point_features, raster_layer):
        row_cols = []

        extent = raster_layer.dataProvider().extent()
        # if extent.isNull() or extent.isEmpty:
        #     return list(col_rows)

        for point_feature in point_features:
            if point_feature.hasGeometry():

                point_geom = point_feature.geometry()
                if point_geom.wkbType() == QgsWkbTypes.MultiPoint:
                    multi_points = point_geom.asMultiPoint()
                    for pointxy in multi_points:
                        if extent.contains(pointxy):
                            row_col = MinCostPathHelper._point_to_row_col(pointxy, raster_layer)
                            row_cols.append((row_col, pointxy, point_feature.id()))

                elif point_geom.wkbType() == QgsWkbTypes.Point:
                    pointxy = point_geom.asPoint()
                    if extent.contains(pointxy):
                        row_col = MinCostPathHelper._point_to_row_col(pointxy, raster_layer)
                        row_cols.append((row_col, pointxy, point_feature.id()))

        return row_cols

    @staticmethod
    def get_all_block(raster_layer, band_num):
        provider = raster_layer.dataProvider()
        extent = provider.extent()

        xres = raster_layer.rasterUnitsPerPixelX()
        yres = raster_layer.rasterUnitsPerPixelY()
        width = floor((extent.xMaximum() - extent.xMinimum()) / xres)
        height = floor((extent.yMaximum() - extent.yMinimum()) / yres)
        return provider.block(band_num, extent, width, height)

    @staticmethod
    def block2matrix(block):
        contains_negative = False
        matrix = [[None if block.isNoData(i, j) else block.value(i, j) for j in range(block.width())]
                  for i in range(block.height())]

        for l in matrix:
            for v in l:
                if v is not None:
                    if v < 0:
                        contains_negative = True

        return matrix, contains_negative
