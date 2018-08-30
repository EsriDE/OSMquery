# -*- coding: utf-8 -*-
"""
/***************************************************************************
 OSMQuery
 A Python toolbox for ArcGIS
 OSM Overpass API frontend
                             -------------------
        begin                : 2018-08-20
        copyright            : (C) 2018 by Riccardo Klinger
        email                : riccardo.klinger at gmail dot com
        contributor          : Riccardo Klinger
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

import arcpy
import requests
import json
import time
from os.path import dirname, join, abspath, isfile


class Toolbox(object):
    def __init__(self):
        """Define the toolbox (the name of the toolbox is the name of the
        .pyt file)."""
        self.label = "OSM Query Toolbox"
        self.alias = "OSM Query Toolbox"

        # List of tool classes associated with this toolbox
        self.tools = [Tool]


class Tool(object):
    def __init__(self):
        """Define the tool (tool name is the name of the class)."""
        self.label = "Get OSM Data"
        self.description = ""
        self.canRunInBackground = False

    def getConfig(self, configItem):
        ###load config file
        json_file_config = join(dirname(abspath(__file__)), 'config/tags.json')
        if isfile(json_file_config):
            with open(json_file_config) as f:
                config_json = json.load(f)
        array = []
        ###select all major tags:
        if configItem == "all":
            for tag in config_json:
                array.append(tag)
        ###select all keys for the desried tag:
        if configItem != "all":
            for key in config_json[configItem]:
                array.append(key)
        return array

    def getServer(self):
        ###load config file
        json_file_config = join(dirname(abspath(__file__)), 'config/servers.json')
        if isfile(json_file_config):
            with open(json_file_config) as f:
                config_json = json.load(f)
        array = []
        ###select all major tags:
        for server in config_json["overpass_servers"]:
            array.append(server)
        return array

    def getParameterInfo(self):
        """Define parameter definitions"""
        ###let's read the config files with Tags and keys###
        param0 = arcpy.Parameter(
            displayName="OSM tag key",
            name="in_tag",
            datatype="GPString",
            parameterType="Required",
            direction="Input"
        )
        param0.filter.list = self.getConfig('all')
        param0.value = param0.filter.list[0]
        param1 = arcpy.Parameter(
            displayName="OSM tag value",
            name="in_key",
            datatype="GPString",
            parameterType="Required",
            direction="Input",
            multiValue=True
        )
        param2 = arcpy.Parameter(
            displayName="Spatial extent indication method",
            name="in_regMode",
            datatype="GPString",
            parameterType="Required",
            direction="Input"
        )
        param2.filter.list = ["Geocode a region name","Define a bounding box"]
        param2.value = "Define a bounding box"
        param3 = arcpy.Parameter(
            displayName="Region name",
            name="in_region",
            datatype="GPString",
            parameterType="Optional",
            direction="Input"
        )
        param4 = arcpy.Parameter(
            displayName="Bounding box",
            name="in_bbox",
            datatype="GPExtent",
            parameterType="Optional",
            direction="Input"
        )
        param5 = arcpy.Parameter(
            displayName="Output CRS",
            name="in_crs",
            datatype="GPCoordinateSystem",
            parameterType="Required",
            direction="Input"
        )
        param5.value = arcpy.SpatialReference(4326)
        param_out0 = arcpy.Parameter(
            displayName="Layer containing OSM point data",
            name="out_nodes",
            datatype="GPFeatureLayer",
            parameterType="Derived",
            direction="Output"
        )
        param_out1 = arcpy.Parameter(
            displayName="Layer containing OSM line data",
            name="out_ways",
            datatype="GPFeatureLayer",
            parameterType="Derived",
            direction="Output"
        )
        param_out2 = arcpy.Parameter(
            displayName="Layer containing OSM polygon data",
            name="out_poly",
            datatype="GPFeatureLayer",
            parameterType="Derived",
            direction="Output"
        )
        params = [param0, param1, param2, param3, param4, param5, param_out0, param_out1, param_out2]

        return params

    def isLicensed(self):
        """Set whether tool is licensed to execute."""
        return True

    def updateParameters(self, parameters):
        """Modify the values and properties of parameters before internal
        validation is performed.  This method is called whenever a parameter
        has been changed."""
        #update the parameters of keys accroding the values of "in_tag"
        parameters[1].filter.list = self.getConfig(parameters[0].value)
        if parameters[2].value == "Geocode a region name":
            parameters[3].enabled = True
            parameters[4].enabled = False
        else:
            parameters[3].enabled = False
            parameters[4].enabled = True
        #parameters[1].value = parameters[1].filter.list[0]
        return

    def updateMessages(self, parameters):
        """Modify the messages created by internal validation for each tool
        parameter.  This method is called after internal validation."""
        return

    def execute(self, parameters, messages):
        """The source code of the tool."""
        sr = arcpy.SpatialReference()
        sr.loadFromString(parameters[5].value)
        arcpy.AddMessage(sr.factoryCode)
        # Constants for building the query to the Overpass API
        QUERY_URL = "http://overpass-api.de/api/interpreter"
        QUERY_START = "[out:json][timeout:25];("
        QUERY_END = ');(._;>;);out;>;'

        def create_result_fc(geometry_type, fields):
            fc_name = '%ss_%s' % (geometry_type, str(timestamp))
            fc = join(arcpy.env.scratchWorkspace, fc_name)

            arcpy.AddMessage("\nCreating %s feature layer %s..." % (geometry_type.lower(), fc_name))
            if geometry_type == 'Line':
                geometry_type = 'Polyline'
            arcpy.CreateFeatureclass_management(arcpy.env.scratchWorkspace, fc_name, geometry_type.upper(), "",
                                                "DISABLED",
                                                "DISABLED", sr, "")
            arcpy.AddMessage("\tAdding attribute OSM_ID...")
            arcpy.AddField_management(fc, "OSM_ID", "DOUBLE", 12, 0, "", "OSM_ID")
            for field in fields:
                try:
                    field = field.replace(":", "")
                    arcpy.AddMessage("\tAdding attribute %s..." % field)
                    arcpy.AddField_management(fc, field, "STRING", 255, "", "", field, "NULLABLE")
                except:
                    arcpy.AddMessage("\tAdding attribute %s failed.")
            return fc

        keys = parameters[1].value.exportToString().split(";")

        if parameters[2].value != "Geocode a region name":
            bboxHead = ''
            if parameters[4].value.spatialReference != arcpy.SpatialReference(4326):
                LL = arcpy.PointGeometry(arcpy.Point(parameters[4].value.XMin,parameters[4].value.YMin), parameters[4].value.spatialReference).projectAs(arcpy.SpatialReference(4326))
                UR = arcpy.PointGeometry(arcpy.Point(parameters[4].value.XMax,parameters[4].value.YMax), parameters[4].value.spatialReference).projectAs(arcpy.SpatialReference(4326))
                bbox = [LL.extent.YMin, LL.extent.XMin, UR.extent.YMax, UR.extent.XMax]
            else:
                bbox = [parameters[4].value.YMin,parameters[4].value.XMin,parameters[4].value.YMax,parameters[4].value.XMax]
            bboxData = '(' + ','.join(str(e) for e in bbox) + ');'
        else:
            ###getting areaID from Nominatim:
            nominatimURL = 'https://nominatim.openstreetmap.org/search?q=' + parameters[3].valueAsText + '&format=json'
            NominatimResponse = requests.get(nominatimURL)
            arcpy.AddMessage("\nGecoding region using the url %s..." % nominatimURL)
            try:
                NominatimData = NominatimResponse.json()

                for result in NominatimData:
                    if result["osm_type"] == "relation":
                        areaID = result['osm_id']
                        try:
                            arcpy.AddMessage("\tFound region " + result['display_name'])
                        except:
                            arcpy.AddMessage("\tFound region " + str(areaID))
                        break
                bboxHead = 'area(' + str(int(areaID) + 3600000000) + ')->.searchArea;'
                bboxData = '(area.searchArea);'
            except:
                arcpy.AddError("\tNo region found!")
                return

        # Get data using urllib
        # The tool makes the user supply at least one key
        if len(keys) == 1 and "'* (any value, including the ones listed below)'" not in keys:
            arcpy.AddMessage("\nCollecting " + parameters[0].value + " = " + keys[0])
            nodeData = 'node["' + parameters[0].value + '"="' + keys[0] + '"]'
            wayData = 'way["' + parameters[0].value + '"="' + keys[0] + '"]'
            relationData = 'relation["' + parameters[0].value + '"="' + keys[0] + '"]'
        elif len(keys) > 1 and "'* (any value, including the ones listed below)'" not in keys:
            arcpy.AddMessage("\nCollecting " + parameters[0].value + " = " + "|".join(keys))
            nodeData = 'node["' + parameters[0].value + '"~"' + "|".join(keys) + '"]'
            wayData = 'way["' + parameters[0].value + '"~"' + "|".join(keys) + '"]'
            relationData = 'relation["' + parameters[0].value + '"~"' + "|".join(keys) + '"]'
        #replace any query if star is selected:
        elif "'* (any value, including the ones listed below)'" in keys:
            arcpy.AddMessage("\nCollecting " + parameters[0].value + " = * (any value)")
            nodeData = 'node["' + parameters[0].value + '"]'
            wayData = 'way["' + parameters[0].value + '"]'
            relationData = 'relation["' + parameters[0].value + '"]'

        query = QUERY_START + bboxHead + nodeData + bboxData + wayData + bboxData + relationData + bboxData + QUERY_END
        arcpy.AddMessage("Issuing Overpass API query:")
        arcpy.AddMessage(query)
        response = requests.get(QUERY_URL, params={'data': query})
        if response.status_code!=200:
            arcpy.AddMessage("\tOverpass server response was " + str(response.status_code) )
            return
        try:
            data = response.json()
        except:
            arcpy.AddMessage("\tOverpass API responded with non JSON data: ")
            arcpy.AddError(response.text)
            return
        if len(data["elements"]) == 0:
            arcpy.AddMessage("\tNo data found!")
            return
        else:
            arcpy.AddMessage("\tCollected " + str(len(data["elements"])) + " objects (incl. reverse objects)")
        arcpy.env.overwriteOutput = True
        arcpy.env.addOutputsToMap = True

        timestamp =  int(time.time())
        ########################################################
        ###creating feature classes according to the response###
        ########################################################

        points = [element for element in data['elements'] if element["type"] == "node"]
        lines = [element for element in data['elements'] if element["type"] == "way" and
                 (element["nodes"][0] != element["nodes"][len(element["nodes"])-1])]
        polygons = [element for element in data['elements'] if element["type"] == "way" and
                    (element["nodes"][0] == element["nodes"][len(element["nodes"])-1])]

        points_created = True if len(points) > 0 else False
        lines_created = True if len(lines) > 0 else False
        polygons_created = True if len(polygons) > 0 else False

        # Iterate through elements per geometry type (points (nodes), lines (open ways; i.e. start and end node are not
        # identical), polygons (closed ways) and collect attributes
        point_fc_fields = set()
        line_fc_fields = set()
        polygon_fc_fields = set()

        for element in [e for e in points if "tags" in e]:
            for tag in element["tags"]:
                point_fc_fields.add(tag)

        for element in [e for e in lines if "tags" in e]:
            for tag in element["tags"]:
                line_fc_fields.add(tag)

        for element in [e for e in polygons if "tags" in e]:
            for tag in element["tags"]:
                polygon_fc_fields.add(tag)

        if len(points) > 0:
            point_fc = create_result_fc('Point', point_fc_fields)
            point_fc_cursor = arcpy.InsertCursor(point_fc)
        else:
            arcpy.AddMessage("\nData contains no point features.")

        if len(lines) > 0:
            line_fc = create_result_fc('Line', line_fc_fields)
            line_fc_cursor = arcpy.InsertCursor(line_fc)
        else:
            arcpy.AddMessage("\nData contains no line features.")

        if len(polygons) > 0:
            polygon_fc = create_result_fc('Polygon', polygon_fc_fields)
            polygon_fc_cursor = arcpy.InsertCursor(polygon_fc)
        else:
            arcpy.AddMessage("\nData contains no polygon features.")

        #######################################################
        ###filling feature classes according to the response###
        #######################################################
        for element in data['elements']:
            ###we deal with nodes first
            if element["type"]=="node" and "tags" in element:
                row = point_fc_cursor.newRow()
                if sr.factoryCode != 4326:
                    PtGeometry = arcpy.PointGeometry(arcpy.Point(element["lon"], element["lat"]), arcpy.SpatialReference(4326)).projectAs(sr)
                else:
                    PtGeometry = arcpy.PointGeometry(arcpy.Point(element["lon"], element["lat"]), arcpy.SpatialReference(4326))
                row.setValue("SHAPE", PtGeometry)
                row.setValue("OSM_ID", element["id"])
                for tag in element["tags"]:
                    try:
                        row.setValue(tag.replace(":", ""), element["tags"][tag])
                    except:
                        arcpy.AddMessage("Adding value failed.")
                point_fc_cursor.insertRow(row)
                del row
            if element["type"]=="way" and "tags" in element:
                ### getting needed Node Geometries:
                nodes = element["nodes"]
                nodeGeoemtry = []
                ### finding nodes in reverse mode
                for node in nodes:
                    for NodeElement in data['elements']:
                        if NodeElement["id"] == node:
                            if sr.factoryCode != 4326:
                                nodeGeoemtry.append(arcpy.PointGeometry(arcpy.Point(NodeElement["lon"],NodeElement["lat"]), arcpy.SpatialReference(4326)).projectAs(sr).firstPoint)
                            else:
                                nodeGeoemtry.append(arcpy.Point(NodeElement["lon"],NodeElement["lat"]))
                            break

                if nodes[0]==nodes[len(nodes)-1]:
                    row = polygon_fc_cursor.newRow()
                    pointArray = arcpy.Array(nodeGeoemtry)
                    row.setValue("SHAPE", pointArray)
                    row.setValue("OSM_ID", element["id"])
                    ###now deal with the way tags:
                    if "tags" in element:
                        for tag in element["tags"]:
                            try:
                                row.setValue(tag.replace(":", ""), element["tags"][tag])
                            except:
                                arcpy.AddMessage("Adding value failed.")
                    polygon_fc_cursor.insertRow(row)
                    del row
                else: #lines have different start end endnodes:
                    row = line_fc_cursor.newRow()
                    pointArray = arcpy.Array(nodeGeoemtry)
                    row.setValue("SHAPE", pointArray)
                    row.setValue("OSM_ID", element["id"])
                    ###now deal with the way tags:
                    if "tags" in element:
                        for tag in element["tags"]:
                            try:
                                row.setValue(tag.replace(":", ""), element["tags"][tag])
                            except:
                                arcpy.AddMessage("Adding value failed.")
                    line_fc_cursor.insertRow(row)
                    del row

        if points_created:
            del point_fc_cursor
            parameters[6].value = point_fc
        if lines_created:
            del line_fc_cursor
            parameters[7].value = line_fc
        if polygons_created:
            del polygon_fc_cursor
            parameters[8].value = polygon_fc
        return
