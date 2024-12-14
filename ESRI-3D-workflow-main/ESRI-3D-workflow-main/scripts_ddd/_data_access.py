################################################
# Databases
#

def lowerMe(fieldName):
    return fieldName.lower() if "@" not in fieldName else fieldName

##############################################################
# Data access helpers for tables and feature classes.


# FieldAccess: This object is used for building search queries, and accessing field values.
# init - fieldList is all of the fields you want in the search cursor.
# setRow - use during cursor to access that cursor's values.
# getValue - used during cursor to access value by field name (rather than by row number).


class FieldAccess(object):

    def __init__(self, fieldList):
        self.row = None
        self.fieldList = [field.lower() if "@" not in field else field for field in fieldList]
        self.fieldDictionary = {}
        fieldIndex = 0
        for fieldName in self.fieldList:
            self.fieldDictionary[fieldName] = fieldIndex
            fieldIndex += 1

    def setRow(self, row):
        self.row = row

    def getValue(self, fieldName):
        fieldName = fieldName.lower() if "@" not in fieldName else fieldName
        if fieldName in self.fieldList:
            return self.row[self.fieldDictionary[fieldName]]
        else:
            return None


class NewRow(object):

    def __init__(self):
        self.fieldInsertDictionary = {}

    def setFieldNames(self, fieldNameList):
        for fieldName in fieldNameList:
            self.fieldInsertDictionary[lowerMe(fieldName)] = None

    def set(self, fieldName, fieldValue):
        self.fieldInsertDictionary[lowerMe(fieldName)] = fieldValue

    def getFieldNamesList(self):
        return list(self.fieldInsertDictionary.keys())

    # Note: below use of dictionary is not affected by unordered nature of dictionary.
    def getFieldValuesList(self):
        ret = []
        fieldNamesList = list(self.fieldInsertDictionary.keys())
        for fieldName in fieldNamesList:
            ret.append(self.fieldInsertDictionary.get(fieldName))
        return ret

    def addFields(self, fieldInsertDictionary):
        self.fieldInsertDictionary.update(fieldInsertDictionary)
