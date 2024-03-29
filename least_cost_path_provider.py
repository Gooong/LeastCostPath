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

from qgis.core import QgsProcessingProvider
from .least_cost_path_algorithm import LeastCostPathAlgorithm


class LeastCostPathProvider(QgsProcessingProvider):

    def __init__(self):
        QgsProcessingProvider.__init__(self)
    

    def unload(self):
        """
        Unloads the provider. Any tear-down steps required by the provider
        should be implemented here.
        """
        pass

    def loadAlgorithms(self):
        """
        Loads all algorithms belonging to this provider.
        """
        
        self.addAlgorithm(LeastCostPathAlgorithm())

    def id(self):
        """
        Returns the unique provider id, used for identifying the provider. This
        string should be a unique, short, character only string, eg "qgis" or
        "gdal". This string should not be localised.
        """
        return 'Cost distance analysis'

    def name(self):
        """
        Returns the provider name, which is used to describe the provider
        within the GUI.

        This string should be short (e.g. "Lastools") and localised.
        """
        return self.tr('Cost distance analysis')

    def longName(self):
        """
        Returns the a longer version of the provider name, which can include
        extra details such as version numbers. E.g. "Lastools LIDAR tools
        (version 2.2.1)". This string should be localised. The default
        implementation returns the same string as name().
        """
        return self.name()
