import arcpy
import math
import sys

# Constants.

proxyForInfinity = 1000000000
proxyForInfinitesimal = 0.000001
zToleranceForFlatSlope = 0.001


class MultipartInputNotSupported(Exception):
    pass


# debugging and notifications

# For debugging:
debugMode = True

# Feedback functions (print to GP tool output):
def pint(text):
    if debugMode is True:
        arcpy.AddMessage(text)


def p(label, text):
    if debugMode is True:
        if text is None:
            arcpy.AddMessage(label + " is None")
        else:
            arcpy.AddMessage(label + " " + str(text))


class Point(object):
    def __init__(self, x,y,z):
        self.x = float(x)
        self.y = float(y)
        self.z = float(z)
        #self.coordinates = [x,y,z]

    def __str__(self):
        return f"({self.x}, {self.y}, {self.z})"


class Vector(object):
    def __init__(self, x,y,z):
        self.x = float(x)
        self.y = float(y)
        self.z = float(z)

    def __str__(self):
        return f"({self.x}, {self.y}, {self.z})"


class Polyline(object):
    def __init__(self, listOfNodes):
        self.nodes = listOfNodes
        self.edges = []
        for nodeIndex in range(0,len(self.nodes) - 1):
            self.edges.append(NavLine(self.nodes[nodeIndex], self.nodes[nodeIndex + 1]))
        #self.edgeVectors = []
        #self.zMin = None
        #self.zMax = None

    def getNodes(self):
        return self.nodes


class Node(object):
    def __init__(self, x,y,z):
        self.x = float(x)
        self.y = float(y)
        self.z = float(z)
        self.turnCode = 0 # XX remove this attribute and attach it when needed. No functions use it except skeleton.

    def __str__(self):
        return "(" + str(self.x) + "," + str(self.y) + "," + str(self.z) + ")"


class Edge(object):
    def __init__(self, nodeA, nodeB):
        self.nodeA = nodeA
        self.nodeB = nodeB
        self.setback = 0
        self.vector = getVectorFromTwoPoints(self.nodeA, self.nodeB)

    def getMidpoint(self):
        halfVector = multiplyVector(self.vector, 0.5)
        midNode = copyNode(self.nodeA, halfVector)
        return midNode

    def __str__(self):
        return "Edge: PointA: " + str(self.nodeA) + " PointB: " + str(self.nodeB) + " Setback: "+ str(self.setback)


class Polygon(object):
    def __init__(self, listOfNodes):
        self.nodes = listOfNodes
        self.edges = []
        self.edgeVectors = []
        self.zMin = None
        self.zMax = None

    def setMinAndMaxZ(self):
        zMin = proxyForInfinity
        zMax = -proxyForInfinity
        for node in self.nodes:
            if node.z < zMin:
                zMin = node.z
        for node in self.nodes:
            if node.z > zMax:
                zMax = node.z
        self.zMin = zMin
        self.zMax = zMax


    def setFlatZ(self, zValue):
        for node in self.nodes:
            node.z = zValue

    def appendNode(self,node):
        self.nodes.append(node)

    def getNodes(self):
        return self.nodes

    def getArea(self):
        # Thanks to this web page for most simple area algorithm I could find:
        #  http://www.mathopenref.com/coordpolygonarea.html
        nodesWrapped = []
        nodesWrapped.extend(self.nodes)
        nodesWrapped.append(self.nodes[0])
        nodeCount = len(self.nodes)
        total = 0
        for index in range(0,nodeCount):
            thisX = nodesWrapped[index].x
            nextX = nodesWrapped[index + 1].x
            thisY = nodesWrapped[index].y
            nextY = nodesWrapped[index + 1].y
            thisX_nextY = thisX * nextY
            nextX_thisY = nextX * thisY
            total += (thisX_nextY - nextX_thisY)
        return abs(total / 2)


    def makeEdges(self):
        self.edges = []
        self.edgeVectors = []
        # This will rebuild edge list when called.
        for index in range(0,len(self.nodes)):
            if index > len(self.nodes) - 2:
                nextIndex = 0
            else:
                nextIndex = index + 1
            node1 = self.nodes[index]
            node2 = self.nodes[nextIndex]
            newEdge = Edge(node1, node2)
            self.edges.append(newEdge)
            self.edgeVectors.append(newEdge.vector)
        pass

    def __str__(self):
        ret = "Polygon: "
        for node in self.nodes:
            ret += str(node) + ","
        return ret


class NavLine(object):
    def __init__(self, nodeA, nodeB):
        self.nodeA = nodeA
        self.nodeB = nodeB
        # Direction of travel.
        self.vector = getVectorFromTwoPoints(self.nodeA, self.nodeB)
        self.type = None

    #def midPoint(self):
    #    copyNode(Node(self.nodeA, setVectorMagnitude(self.vector, 0.5 * ))

    def shrinkTowardsCenter(self, distance):
        return NavLine(copyNode(self.nodeA, setVectorMagnitude(self.vector, distance)),copyNode(self.nodeB, reverseVector(setVectorMagnitude(self.vector, distance))))


# Below will write a list of FunPolygon to a multi-part arcpy Polygon.
def funPolylineToArcpyPolyline(funPolylines):
    if funPolylines is None:
        pint("Error: funPolylineToArcpyPolyline: input is None")
        return None
    elif len(funPolylines) == 0:
        pint("Error: funPolylineToArcpyPolyline: polyline count is zero.")
        return None
    else:
        polylineArray = arcpy.Array()
        partCount = 0
        for funPolyline in funPolylines:
            if funPolyline is not None:
                funPoints = funPolyline.getNodes()
                newArcpyPoints = []
                for funPoint in funPoints:
                    newArcpyPoint = arcpy.Point(funPoint.x, funPoint.y, funPoint.z, None, 0)
                    newArcpyPoints.append(newArcpyPoint)
                    pointArray = arcpy.Array(newArcpyPoints)
                polylineArray.append(pointArray)
            else:
                pint("Error: funPolylineToArcpyPolyline: polyline is None.")
            partCount += 1
        multipartFeature = arcpy.Polyline(polylineArray, None, True, False)
        return multipartFeature


# Below will write a list of FunPolygons to a multi-part arcpy Polygon.
def funPolygonToArcpyPolygon(funPolygons):
    if funPolygons is None:
        pint("Error: funPolygonToArcpyPolygon: input is None")
        return None
    elif len(funPolygons) == 0:
        pint("Error: funPolygonToArcpyPolygon: polygon count is zero.")
        return None
    else:
        polygonArray = arcpy.Array()
        partCount = 0
        for funPolygon in funPolygons:
            if funPolygon is not None:
                funPoints = funPolygon.getNodes()
                newArcpyPoints = []
                for funPoint in funPoints:
                    newArcpyPoint = arcpy.Point(funPoint.x, funPoint.y, funPoint.z, None, 0)
                    newArcpyPoints.append(newArcpyPoint)
                    pointArray = arcpy.Array(newArcpyPoints)
                polygonArray.append(pointArray)
            else:
                pint("Error: funPolygonToArcpyPolygon: polygon is None.")
            partCount += 1
        multipartFeature = arcpy.Polygon(polygonArray, None, True, False)
        return multipartFeature


def arcpyPolylineToVGPolyline(arcpyPolyline):
    try:
        if arcpyPolyline is None:
            pint("Input polyline is Null.")
            raise Exception
        polylineNodes = []
        partCount = 0
        for part in arcpyPolyline:
            partCount += 1
            for pnt in part:
                if pnt:
                    node = Node(pnt.X, pnt.Y, pnt.Z)
                    polylineNodes.append(node)
        if partCount > 1:
            pint("Multipart input shape not supported.")
            return None
        else:
            return Polyline(polylineNodes)

    except MultipartInputNotSupported:
        print("Multipart features are not supported. Exiting...")
        arcpy.AddError("Multipart features are not supported. Exiting...")

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


def reverseVector(A):
    return Vector(-A.x, -A.y, -A.z)


def multiplyVector(vector, multiple):
    return Vector(vector.x * multiple, vector.y * multiple, vector.z * multiple)


def getVectorFromTwoPoints(pointA, pointB):
    # PointA is start. PointB is end.
    return Vector(pointB.x - pointA.x, pointB.y - pointA.y, pointB.z - pointA.z)


def magnitude(A):
    return math.sqrt(pow(A.x,2) + pow(A.y,2) + pow(A.z,2))


def crossProduct(A, B):
    cross = [A.y*B.z - A.z*B.y, A.z*B.x - A.x*B.z, A.x*B.y - A.y*B.x]
    return Vector(cross[0],cross[1],cross[2])

def addVectors(A, B):
    return Vector(A.x + B.x, A.y + B.y, A.z + B.z)


def scalarProjection(A,B):
    # Projects A onto B.
    angle = angleBetweenTwoVectors(A,B)
    scalar = magnitude(A) * math.cos(angle)
    return scalar


def setVectorMagnitude(A, magnitude):
    unit = unitizeVector(A)
    return Vector(unit.x * magnitude, unit.y * magnitude, unit.z * magnitude)


def copyNode(node, vector):
    return Node(node.x + vector.x, node.y + vector.y, node.z + vector.z)


def unitizeVector(A):
    mag = magnitude(A)
    return Vector(A.x/mag, A.y/mag, A.z/mag)


def dotProduct(A,B):
    return (A.x * B.x) + (A.y * B.y) + (A.z * B.z)


def angleBetweenTwoVectors(A,B):
    dotAB = dotProduct(A,B)
    productOfMagnitudes = magnitude(A) * magnitude(B)
    if productOfMagnitudes == 0:
        pint("Angle between two vectors has division by zero.")
    # Handle floating point error where acos evaluates number outside of valid domain of -1 to 1.
    dotOverMagProduct = dotAB/productOfMagnitudes
    if dotOverMagProduct > 1:
        dotOverMagProduct = 1
    elif dotOverMagProduct < -1:
        dotOverMagProduct = -1

    angle = math.acos(dotOverMagProduct)
    return angle