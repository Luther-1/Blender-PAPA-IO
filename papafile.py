# The MIT License
# 
# Copyright (c) 2013, 2014  Raevn
# Copyright (c) 2021        Marcus Der      marcusder@hotmail.com
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import ctypes
import struct
from pathlib import Path
from mathutils import * # has vectors and quaternions
from math import ceil, log2
import platform
from os import path
from array import array

class PapaComponent: # abstract interface meant for compiling
    def build(self):
        self.__headerBytes = bytearray(self.headerSize())
        self.__bodyBytes = bytearray(self.bodySize())
        self.buildComponent()
    
    def buildComponent(self):
        raise NotImplementedError(type(self))
    
    def applyOffset(self, offset):
        raise NotImplementedError(type(self))
    
    def headerSize(self):
        raise NotImplementedError(type(self))
    
    def bodySize(self):
        raise NotImplementedError(type(self))
    
    def componentSize(self):
        return self.headerSize() + self.bodySize()
    
    def getHeaderBytes(self):
        return self.__headerBytes
    
    def getBodyBytes(self):
        return self.__bodyBytes

class PapaString(PapaComponent):
    def __init__(self, data):
        self.__data = data
    
    def getString(self):
        return self.__data
    
    def __str__(self):
        return self.__data
    
    def buildComponent(self):
        data = self.getBodyBytes()
        string = bytes(self.__data, "utf-8")
        data[0:len(string)] = string

        struct.pack_into('<q', self.getHeaderBytes(), 0, len(self.getString()))
    
    def applyOffset(self, offset):
        struct.pack_into('<q',self.getHeaderBytes(),8,offset)
    
    def headerSize(self):
        return 16
    
    def bodySize(self):
        return ceilNextEight(len(self.__data))
        

class PapaTexture(PapaComponent):
    formatMap = {
        -1:"UNKNOWN",
        1:"R8G8B8A8",
		2:"R8G8B8X8",
		3:"B8G8R8A8",
		4:"DXT1",
		5:"DXT3", # partial PA support
		6:"DXT5",
		13:"R8",
    }

    def __init__(self, nameIndex: int, formatIndex: int,SRGB: bool, width: int, height: int, imageData: float, filepath = None):
        self.__nameIndex = nameIndex
        self.__formatIndex = formatIndex
        self.__SRGB = SRGB
        self.__width = width
        self.__height = height
        self.__imageData = imageData
        self.__filepath = filepath
    
    def getNameIndex(self):
        return self.__nameIndex
    
    def getFormatIndex(self):
        return self.__formatIndex

    def getSRGB(self):
        return self.__SRGB

    def getFormatString(self):
        return PapaTexture.formatMap[self.getFormatIndex()]

    def getWidth(self):
        return self.__width

    def getHeight(self):
        return self.__height
    
    def getImageData(self): # RGBA float array
        return self.__imageData

    def hasFilepath(self):
        return self.__filepath != None

    def getFilepath(self):
        if not self.hasFilepath():
            raise ReferenceError("Papatexture has no filepath")
        return self.__filepath

    def hasData(self):
        return len(self.__imageData) != 0

    def __str__(self):
        return "PapaTexture: \n\tFormat: "+self.getFormatString() +"\n\tName index: "+str(self.getNameIndex()) \
            + "\n\tDimensions: ("+str(self.getWidth()) +", "+str(self.getHeight())+")"

    # only linked textures may be built
    def buildComponent(self):
        struct.pack_into('<hbbhhq', self.getHeaderBytes(), 0, self.getNameIndex(),0,0,0,0,0)
    
    def applyOffset(self, offset):
        struct.pack_into('<q',self.getHeaderBytes(),16,-1)
    
    def headerSize(self):
        return 24
    
    def bodySize(self):
        return 0

class PapaIndexBuffer(PapaComponent):
    def __init__(self, format: int, indices: tuple):
        self.__format=format
        self.__indices=indices
    
    def getNumIndices(self) -> int:
        return len(self.__indices)
    
    def getIndex(self, ind) -> int:
        return self.__indices[ind]
    
    def getFormat(self) -> int:
        return self.__format
    
    def getFormatName(self) -> str:
        if(self.__format==0):
            return "UInt16"
        return "UInt32"
    def __str__(self):
        return self.getFormatName() + ": " + str(self.getNumIndices())+" indices ("+str(self.getNumIndices()//3) + " triangles)" 
    
    def buildComponent(self):
        # body
        data = self.getBodyBytes()
        if(self.__format == 0): # short
            struct.pack_into('<'+'H'*len(self.__indices), data, 0, *self.__indices) # * unpacks the elements of the iterable into individual arguments
        else: # int
            struct.pack_into('<'+'I'*len(self.__indices), data, 0, *self.__indices)
        
        struct.pack_into('<BxxxIq', self.getHeaderBytes(), 0, self.__format,len(self.__indices),self.bodySize())
    
    def applyOffset(self, offset):
        struct.pack_into('<q',self.getHeaderBytes(),16,offset)
    
    def headerSize(self):
        return 24
    
    def bodySize(self):
        return len(self.__indices) * (2 if self.__format == 0 else 4)

class PapaVertex:
    def __init__(self, pos: Vector, norm: Vector = None, binorm: Vector = None, tan: Vector = None, col: list = None,
                texcoord1: list = None, texcoord2: list = None, bones: list = [], weights: list = []):
        self.__position=pos
        self.__normal=norm
        self.__binormal=binorm
        self.__tangent=tan
        self.__colour=col
        # the UVs are flipped across the Y axis for some reason
        if texcoord1:
            texcoord1 = [texcoord1[0],1 - texcoord1[1]]
        if texcoord2:
            texcoord2 = [texcoord2[0],1 - texcoord2[1]]
        self.__texcoord1 = texcoord1
        self.__texcoord2 = texcoord2

        self.__boneMap = {}
        for x in range(len(weights)):
            if(weights[x]==0):
                break
            self.__boneMap[bones[x]] = weights[x]
        self.__bones=bones
        self.__weights=weights

    def getPosition(self) -> Vector:
        return self.__position

    def getNormal(self) -> Vector:
        return self.__normal
        
    def getBinormal(self) -> Vector:
        return self.__binormal

    def getTangent(self) -> Vector:
        return self.__tangent

    def getColour(self) -> list:
        return self.__colour

    def getTexcoord1(self) -> list:
        return self.__texcoord1

    def getTexcoord2(self) -> list:
        return self.__texcoord2

    def getBones(self) -> list:
        return self.__bones

    def getWeights(self) -> list:
        return self.__weights
    
    def getWeight(self, boneIndex):
        return self.__boneMap.get(boneIndex,0)

class PapaVertexBuffer(PapaComponent):
    formatMap = {
        0:"Position3",
        5:"Position3Normal3TexCoord2",
		6:"Position3Normal3Color4TexCoord2",
		7:"Position3Normal3Color4TexCoord4",
		8:"Position3Weights4bBones4bNormal3TexCoord2",
		10:"Position3Normal3Tan3Bin3TexCoord4"
    }

    def __init__(self, format, vertices):
        self.__format=format
        self.__vertices=vertices
    
    def getNumVertices(self) -> int:
        return len(self.__vertices)
    
    def getVertex(self, ind) -> PapaVertex:
        return self.__vertices[ind]
    
    def getFormat(self) -> int:
        return self.__format
    
    def getFormatName(self) -> str:
        return PapaVertexBuffer.formatMap[self.__format]
    
    def __str__(self):
        return self.getFormatName() + ": " + str(self.getNumVertices()) +" vertices"
    
    def buildComponent(self):
        # body
        vertexFormat = self.getFormat()
        numberOfVertices = self.getNumVertices()
        data = self.getBodyBytes()
        if (vertexFormat == 0): # Position3
            for i in range(numberOfVertices):
                loc = self.getVertex(i).getPosition()
                struct.pack_into('<fff', data, 12 * i,loc[0],loc[1],loc[2])

        elif (vertexFormat == 5): # Position3Normal3TexCoord2
            for i in range(numberOfVertices):
                v = self.getVertex(i)

                p = v.getPosition()
                n = v.getNormal()
                t1 = v.getTexcoord1()

                struct.pack_into('<ffffffff', data, 32 * i,p[0],p[1],p[2],n[0],n[1],n[2],t1[0],t1[1])

        elif (vertexFormat == 6): # Position3Normal3Color4TexCoord2
            for i in range(numberOfVertices):
                v = self.getVertex(i)

                p = v.getPosition()
                n = v.getNormal()
                c = v.getColour()
                t1 = v.getTexcoord1()

                struct.pack_into('<ffffffBBBBff', data, 36 * i,p[0],p[1],p[2],n[0],n[1],n[2],c[0],c[1],c[2],c[3],t1[0],t1[1])

        elif (vertexFormat == 7): # Position3Normal3Color4TexCoord4
            for i in range(numberOfVertices):
                v = self.getVertex(i)

                p = v.getPosition()
                n = v.getNormal()
                c = v.getColour()
                t1 = v.getTexcoord1()
                t2 = v.getTexcoord2()

                struct.pack_into('<ffffffBBBBff', data, 44 * i,p[0],p[1],p[2],n[0],n[1],n[2],c[0],c[1],c[2],c[3],t1[0],t1[1],t2[0],t2[1])

        elif (vertexFormat == 8): # Position3Weights4bBones4bNormal3TexCoord2
            for i in range(numberOfVertices):
                v = self.getVertex(i)

                p = v.getPosition()
                w = v.getWeights()
                b = v.getBones()
                n = v.getNormal()
                t1 = v.getTexcoord1()
                struct.pack_into('<fffBBBBBBBBfffff', data, 40 * i,p[0],p[1],p[2],w[0],w[1],w[2],w[3],b[0],b[1],b[2],b[3],n[0],n[1],n[2],t1[0],t1[1])
                
        elif (vertexFormat == 10): # Position3Normal3Tan3Bin3TexCoord4
            for i in range(numberOfVertices):
                v = self.getVertex(i)

                p = v.getPosition()
                n = v.getNormal()
                t = v.getTangent()
                b = v.getBinormal()
                t1 = v.getTexcoord1()
                t2 = v.getTexcoord2()

                struct.pack_into('<ffffffffffffffff', data, 64 * i,p[0],p[1],p[2],n[0],n[1],n[2],t[0],t[1],t[2],b[0],b[1],b[2],t1[0],t1[1],t2[0],t2[1])
        
        struct.pack_into('<BxxxIq', self.getHeaderBytes(), 0, self.__format,len(self.__vertices),self.bodySize())
    
    def applyOffset(self, offset):
        struct.pack_into('<q',self.getHeaderBytes(),16,offset)
    
    def headerSize(self):
        return 24
    
    def bodySize(self):
        vertexFormat = self.getFormat()
        if (vertexFormat == 0): # Position3
            return 12 * self.getNumVertices()
        elif (vertexFormat == 5): # Position3Normal3TexCoord2
            return 32 * self.getNumVertices()
        elif (vertexFormat == 6): # Position3Normal3Color4TexCoord2
            return 36 * self.getNumVertices()
        elif (vertexFormat == 7): # Position3Normal3Color4TexCoord4
            return 44 * self.getNumVertices()
        elif (vertexFormat == 8): # Position3Weights4bBones4bNormal3TexCoord2
            return 40 * self.getNumVertices()
        elif (vertexFormat == 10): # Position3Normal3Tan3Bin3TexCoord4
            return 64 * self.getNumVertices()

class PapaMaterialGroup:
    POINTS = 0
    LINES = 1
    TRIANGLES = 2
    primitiveTypes = ["PRIM_Points","PRIM_Lines","PRIM_Triangles"]
    def __init__(self, nameIndex: int, materialIndex: int, firstIndex: int, numPrimitives: int, primitiveType: int):
        self.__nameIndex=nameIndex
        self.__materialIndex=materialIndex
        self.__firstIndex=firstIndex
        self.__numPrimitives=numPrimitives
        self.__primitiveType=primitiveType
    def getNameIndex(self):
        return self.__nameIndex
    
    def getMaterialIndex(self):
        return self.__materialIndex
    
    def getFirstIndex(self):
        return self.__firstIndex
    
    def getNumPrimitives(self):
        return self.__numPrimitives
    
    def getPrimitiveType(self):
        return self.__primitiveType
    
    def getPrimitiveTypeString(self):
        if(self.__primitiveType>=0 and self.__primitiveType<=2):
            return PapaMaterialGroup.primitiveTypes[self.__primitiveType]
        return "ErrorType("+str(self.__primitiveType)+")"

    def __str__(self):
        return "PapaMaterialGroup: \n\tStart Index: " + str(self.getFirstIndex()) + "\n\tNumber of Primitives: "\
                + str(self.getNumPrimitives()) + "\n\tPrimitive Type: "+self.getPrimitiveTypeString()

class PapaMesh(PapaComponent):
    def __init__(self, vBufferIndex: int, iBufferIndex: int, materialGroups: list):
        self.__vBuffer=vBufferIndex
        self.__iBuffer=iBufferIndex
        self.__materialGroups=materialGroups
    
    def getVertexBufferIndex(self) -> int:
        return self.__vBuffer
    
    def getIndexBufferIndex(self) -> int:
        return self.__iBuffer
    
    def getNumMaterialGroups(self) -> int:
        return len(self.__materialGroups)
    
    def getMaterialGroup(self, ind) -> PapaMaterialGroup:
        return self.__materialGroups[ind]
    
    def __str__(self):
        return "PapaMesh: \n\tVertex Buffer: " + str(self.getVertexBufferIndex()) + "\n\tIndex Buffer: "\
                + str(self.getIndexBufferIndex()) + "\n\t" + str(self.getNumMaterialGroups()) +" Material Group(s)"

    def buildComponent(self):
        # body
        data = self.getBodyBytes()
        for i in range(self.getNumMaterialGroups()):
            group = self.getMaterialGroup(i)
            struct.pack_into('<HHIIBxxx', data, 16 * i, group.getNameIndex(), group.getMaterialIndex(),
                group.getFirstIndex(), group.getNumPrimitives(), group.getPrimitiveType())
        
        struct.pack_into('<HHhxx', self.getHeaderBytes(), 0, self.getVertexBufferIndex(), self.getIndexBufferIndex(), self.getNumMaterialGroups())
    
    def applyOffset(self, offset):
        struct.pack_into('<q',self.getHeaderBytes(),8,offset)
    
    def headerSize(self):
        return 16
    
    def bodySize(self):
        return 16 * self.getNumMaterialGroups()

class PapaBone(PapaComponent):
    def __init__(self, nameIndex: int, parentBone: int, translation: Vector, rotation: Quaternion, shearScale: Matrix, bindToBone: Matrix):
        self.__nameIndex = nameIndex
        self.__parentBone = parentBone
        self.__translation = translation
        self.__rotation = rotation
        self.__shearScale = shearScale
        self.__bindToBone = bindToBone
    
    def getNameIndex(self) -> int:
        return self.__nameIndex
    
    def getParentBoneIndex(self) -> int:
        return self.__parentBone
    
    def getTranslation(self) -> Vector: # relative to parent
        return self.__translation
    
    def getRotation(self) -> Quaternion: # relative to parent
        return self.__rotation

    def setParentIndex(self, index):
        self.__parentBone = index
    
    def getShearScale(self) -> Matrix:
        return self.__shearScale
    
    def getBindToBone(self) -> Matrix:
        return self.__bindToBone

    def buildComponent(self):

        data = self.getBodyBytes()
        t = self.getTranslation()
        q = self.getRotation()
        struct.pack_into('<hhfffffff', data, 0, self.getNameIndex(),self.getParentBoneIndex(),t[0],t[1],t[2],q[0],q[1],q[2],q[3])

        # shearScale
        s = self.getShearScale()
        struct.pack_into('<fffffffff', data, 32,s[0][0],s[1][0],s[2][0],
                                                s[0][1],s[1][1],s[2][1],
                                                s[0][2],s[1][2],s[2][2])
        
        m = self.getBindToBone()
        struct.pack_into('<ffffffffffffffff', data, 68, m[0][0],m[1][0],m[2][0],m[3][0],
                                                        m[0][1],m[1][1],m[2][1],m[3][1],
                                                        m[0][2],m[1][2],m[2][2],m[3][2],
                                                        m[0][3],m[1][3],m[2][3],m[3][3])
    
    def applyOffset(self, offset):
        pass
    
    def headerSize(self):
        return 0
    
    def bodySize(self):
        return 132

class PapaSkeleton(PapaComponent):
    def __init__(self, bones: list):
        self.__bones = bones
    
    def getNumBones(self):
        return len(self.__bones)
    
    def getBone(self, ind) -> PapaBone:
        return self.__bones[ind]

    def setBoneList(self, bones:list):
        self.__bones = bones
    
    def __str__(self):
        return "PapaSkeleton with " + str(self.getNumBones()) + " bone(s)"

    def buildComponent(self):

        data = self.getBodyBytes()
        loc = 0
        for i in range(self.getNumBones()):
            b = self.getBone(i)
            b.build()
            data[loc:loc+len(b.getBodyBytes())] = b.getBodyBytes()
            loc += b.bodySize()
        
        struct.pack_into('<Hxxxxxx',self.getHeaderBytes(),0,self.getNumBones())
    
    def applyOffset(self, offset):
        struct.pack_into('<q',self.getHeaderBytes(),8,offset)
    
    def headerSize(self):
        return 16
    
    def bodySize(self):
        size = 0
        for i in range(self.getNumBones()):
            size += self.getBone(i).componentSize()
        return ceilNextEight(size)

class PapaMatrixParameter:
    def __init__(self, nameIndex, matrix: Matrix):
        self.__nameIndex=nameIndex
        self.__matrix=matrix
    
    def getNameIndex(self) -> int:
        return self.__nameIndex

    def getMatrix(self) -> Matrix:
        return self.__matrix

class PapaVectorParameter:
    def __init__(self, nameIndex, vector: Vector):
        self.__nameIndex=nameIndex
        self.__vector=vector
    
    def getNameIndex(self) -> int:
        return self.__nameIndex

    def getVector(self) -> Vector:
        return self.__vector

class PapaTextureParameter:
    def __init__(self, nameIndex, textureIndex):
        self.__nameIndex=nameIndex
        self.__textureIndex=textureIndex
    
    def getNameIndex(self) -> int:
        return self.__nameIndex

    def getTextureIndex(self) -> int:
        return self.__textureIndex

class PapaMaterial(PapaComponent):
    def __init__(self, nameIndex: int, vectorParams: list, textureParams: list, matrixParams: list):
        self.__nameIndex = nameIndex
        self.__vectorParams = vectorParams
        self.__textureParams = textureParams
        self.__matrixParams = matrixParams
        
    def getShaderNameIndex(self) -> int:
        return self.__nameIndex

    def getNumMatrixParams(self) -> int:
        return len(self.__matrixParams)

    def getNumTextureParams(self) -> int:
        return len(self.__textureParams)

    def getNumVectorParams(self) -> int:
        return len(self.__vectorParams)

    def getMatrixParam(self, index) -> PapaMatrixParameter:
        return self.__matrixParams[index]

    def getTextureParam(self, index) -> PapaTextureParameter:
        return self.__textureParams[index]

    def getVectorParam(self, index) -> PapaVectorParameter:
        return self.__vectorParams[index]

    def getMatrixParamByName(self, papaFile, name: str) -> PapaMatrixParameter:
        for p in self.__matrixParams:
            if papaFile.getString(p.getNameIndex()) == name:
                return p

    def getTextureParamByName(self, papaFile, name: str) -> PapaTextureParameter:
        for p in self.__textureParams:
            if papaFile.getString(p.getNameIndex()) == name:
                return p

    def getVectorParamByName(self, papaFile, name: str) -> PapaVectorParameter:
        for p in self.__vectorParams:
            if papaFile.getString(p.getNameIndex()) == name:
                return p

    def __str__(self):
        return "PapaMaterial with " + str(self.getNumVectorParams()) + " Vector parameter(s), " + str(self.getNumTextureParams()) \
                + " Texture parameter(s), and " + str(self.getNumMatrixParams()) + " Matrix parameter(s)"

    def buildComponent(self):
        # body
        data = self.getBodyBytes()
        currentOffset = 0
        self.__vectorOffset = 0
        for x in range(self.getNumVectorParams()):
            vec = self.getVectorParam(x)
            v = vec.getVector()
            struct.pack_into('<hxxffff', data, currentOffset, vec.getNameIndex(), v[0],v[1],v[2],v[3])
            currentOffset += 24 # only takes 20 bytes but papatran buffers 4 more bytes

        currentOffset = ceilEight(currentOffset)
        self.__textureOffset = currentOffset
        for x in range(self.getNumTextureParams()):
            tex = self.getTextureParam(x)
            struct.pack_into('<HH', data, currentOffset, tex.getNameIndex(), tex.getTextureIndex())
            currentOffset+=4

        currentOffset = ceilEight(currentOffset)
        self.__matrixOffset = currentOffset
        for x in range(self.getNumMatrixParams()):
            mat = self.getMatrixParam(x)
            struct.pack_into('<HH', data, currentOffset, mat.getNameIndex())
            m = mat.getMatrix()
            struct.pack_into('<ffffffffffffffff', data, currentOffset + 4,  m[0][0],m[1][0],m[2][0],m[3][0],
                                                                            m[0][1],m[1][1],m[2][1],m[3][1],
                                                                            m[0][2],m[1][2],m[2][2],m[3][2],
                                                                            m[0][3],m[1][3],m[2][3],m[3][3])
            currentOffset+=72 # only takes 68
        
        struct.pack_into('<HHHH', self.getHeaderBytes(), 0, self.getShaderNameIndex(), self.getNumVectorParams(), self.getNumTextureParams(), self.getNumMatrixParams())
    
    def applyOffset(self, offset):
        if(self.getNumVectorParams() != 0):
            struct.pack_into('<q', self.getHeaderBytes(), 8, offset + self.__vectorOffset)
        else:
            struct.pack_into('<q', self.getHeaderBytes(), 8, -1)

        if(self.getNumTextureParams() != 0):
            struct.pack_into('<q', self.getHeaderBytes(), 16, offset + self.__textureOffset)
        else:
            struct.pack_into('<q', self.getHeaderBytes(), 16, -1)

        if(self.getNumMatrixParams() != 0):
            struct.pack_into('<q', self.getHeaderBytes(), 24, offset + self.__matrixOffset)
        else:
            struct.pack_into('<q', self.getHeaderBytes(), 24, -1)

    def headerSize(self):
        return 32

    def bodySize(self):
        size = 0
        size+=24 * self.getNumVectorParams()
        size+=4 * self.getNumTextureParams()
        size+=72 * self.getNumMatrixParams()
        return size
        

class PapaMeshBinding(PapaComponent):
    def __init__(self,nameIndex: int, meshIndex: int, meshToModel: Matrix, boneMap: list):
        self.__nameIndex = nameIndex
        self.__meshIndex = meshIndex
        self.__meshToModel = meshToModel
        self.__boneMap = boneMap
    
    def getNameIndex(self) -> int:
        return self.__nameIndex
    
    def getMeshIndex(self) -> int:
        return self.__meshIndex
    
    def getMeshToModel(self) -> Matrix:
        return self.__meshToModel
    
    def getBoneMapping(self, ind) -> int:
        return self.__boneMap[ind]

    def buildComponent(self):
        # body
        data = self.getBodyBytes()
        for i in range(len(self.__boneMap)):
            struct.pack_into('<H',data, 2 * i, self.__boneMap[i])

        struct.pack_into('<hHHxx', self.getHeaderBytes(), 0, self.getNameIndex(), self.getMeshIndex(), len(self.__boneMap))
        m = self.getMeshToModel()
        struct.pack_into('<ffffffffffffffff', self.getHeaderBytes(), 8, m[0][0],m[1][0],m[2][0],m[3][0],
                                                                        m[0][1],m[1][1],m[2][1],m[3][1],
                                                                        m[0][2],m[1][2],m[2][2],m[3][2],
                                                                        m[0][3],m[1][3],m[2][3],m[3][3])
    
    def applyOffset(self, offset):
        if len(self.__boneMap) == 0:
            offset = -1
        struct.pack_into('<q',self.getHeaderBytes(),72,offset)
    
    def headerSize(self):
        return 80
    
    def bodySize(self):
        return ceilEight(len(self.__boneMap) * 2)
    
    def __str__(self):
        boneMapString = ""
        limit = 5
        x = 0
        total = len(self.__boneMap)
        while x < total:
            boneMapString+="\n\t\t" + str(x)+ " -> " + str(self.__boneMap[x])
            same = x < total-limit
            for i in range(x,min(total,x+limit)):
                if self.__boneMap[i] != i:
                    same = False
                    break
            if same:
                while x < total - 2 and self.__boneMap[x] == x:
                    x+=1
                boneMapString+="\n\t\t..."
            x+=1
        
        return "PapaMeshBinding: \n\tName Index: " + str(self.getNameIndex()) + "\n\tMesh Index: "\
                + str(self.getMeshIndex()) + ("\n\tBone Mappings:"+boneMapString if len(self.__boneMap) != 0 else "")

class PapaModel(PapaComponent):
    def __init__(self, nameIndex: int, skeletonIndex: int, modelToScene: Matrix, meshBindings: list):
        self.__nameIndex = nameIndex
        self.__skeletonIndex = skeletonIndex
        self.__modelToScene = modelToScene
        self.__meshBindings = meshBindings
    
    def getNameIndex(self) -> int:
        return self.__nameIndex
    
    def getSkeletonIndex(self) -> int:
        return self.__skeletonIndex
    
    def getModelToScene(self) -> Matrix:
        return self.__modelToScene
    
    def getNumMeshBindings(self):
        return len(self.__meshBindings)
    
    def getMeshBinding(self, ind) -> PapaMeshBinding:
        return self.__meshBindings[ind]
    
    def addMeshBinding(self, meshBinding):
        self.__meshBindings.append(meshBinding)
    
    def __str__(self):
        return "PapaModel:\n\tName Index: "+str(self.getNameIndex())+"\n\tSkeleton Index: "+str(self.getSkeletonIndex()) \
            + "\n\t"+str(self.getNumMeshBindings())+" Mesh Binding(s)"

    def buildComponent(self):
        for i in range(self.getNumMeshBindings()):
            self.getMeshBinding(i).build()
        struct.pack_into('<hhHxx', self.getHeaderBytes(), 0, self.getNameIndex(), self.getSkeletonIndex(), self.getNumMeshBindings())
        m = self.getModelToScene()
        struct.pack_into('<ffffffffffffffff', self.getHeaderBytes(), 8, m[0][0],m[1][0],m[2][0],m[3][0],
                                                                        m[0][1],m[1][1],m[2][1],m[3][1],
                                                                        m[0][2],m[1][2],m[2][2],m[3][2],
                                                                        m[0][3],m[1][3],m[2][3],m[3][3])
        # data is added in applyOffset since we have to wait for the subcomponents to build
    
    def applyOffset(self, offset):
        localOffset = offset
        if(self.getNumMeshBindings()!=0):
            struct.pack_into('<q',self.getHeaderBytes(),72,offset)
        else:
            struct.pack_into('<q',self.getHeaderBytes(),72,-1)
        
        for i in range(self.getNumMeshBindings()):
            m = self.getMeshBinding(i)
            localOffset+=m.headerSize()
        
        for i in range(self.getNumMeshBindings()):
            m = self.getMeshBinding(i)
            m.applyOffset(localOffset)
            localOffset+=m.bodySize()
        
        location = 0 # add the mesh bindings to our data array
        for i in range(self.getNumMeshBindings()):
            m = self.getMeshBinding(i)
            self.getBodyBytes()[location:location+len(m.getHeaderBytes())] = m.getHeaderBytes()
            location+=m.headerSize()
        
        for i in range(self.getNumMeshBindings()):
            m = self.getMeshBinding(i)
            self.getBodyBytes()[location:location+len(m.getBodyBytes())] = m.getBodyBytes()
            location+=m.bodySize()
    
    def headerSize(self):
        return 80
    
    def bodySize(self):
        size = 0
        for x in range(self.getNumMeshBindings()):
            size += self.getMeshBinding(x).componentSize()
        return size

class AnimationBone:
    def __init__(self, nameIndex: int, name: str, translations: list, rotations: list):
        self.__nameIndex = nameIndex
        self.__name = name # need both since these structures have no connection to parent papafile
        self.__translations = translations
        self.__rotations = rotations
    
    def getNameIndex(self) -> int:
        return self.__nameIndex

    def getName(self) -> str:
        return self.__name
    
    def getTranslation(self, index) -> Vector:
        return self.__translations[index]
    
    def getRotation(self, index) -> Quaternion:
        return self.__rotations[index]

    def setNameIndex(self, index):
        self.__nameIndex = index
    
    def setTranslation(self, index: int, translation: Vector):
        self.__translations[index] = translation
    
    def setRotation(self, index: int, rotation: Quaternion):
        self.__rotations[index] = rotation

class PapaAnimation(PapaComponent):
    def __init__(self, nameIndex: int, numBones: int, numFrames: int, fpsNumerator:int, fpsDenominator: int, transformData: AnimationBone):
        self.__nameIndex = nameIndex
        self.__numBones = numBones
        self.__numFrames = numFrames
        self.__fpsNumerator = fpsNumerator
        self.__fpsDenominator = fpsDenominator
        self.__animationSpeed = fpsNumerator / fpsDenominator
        self.__transformData = transformData
        self.__transformMap = {}
        for bone in transformData:
            self.__transformMap[bone.getName()] = bone
    
    def getNameIndex(self) -> int:
        return self.__nameIndex
    
    def getNumBones(self) -> int:
        return self.__numBones
    
    def getNumFrames(self) -> int:
        return self.__numFrames
    
    def getAnimationSpeed(self) -> int:
        return self.__animationSpeed
    
    def getFpsNumerator(self) -> int:
        return self.__fpsNumerator

    def getFpsDenominator(self) -> int:
        return self.__fpsDenominator
    
    def getAnimationBone(self, index) -> AnimationBone:
        if type(index) == int:
            return self.__transformData[index]
        try:
            return self.__transformMap[index] # find by name. If it fails, there is no data for this bone. (not every bone gets data)
        except KeyError:
            return None
    
    def __str__(self):
        return "PapaAnimation: \n\tName Index: "+str(self.getNameIndex())+"\n\tNumber of bones: "+str(self.getNumBones())+"\n\t"+str(self.getNumFrames())+" frames(s)\n\t" \
            + str(self.getAnimationSpeed())+" FPS"
    
    def buildComponent(self):

        data = self.getBodyBytes()
        for x in range(self.getNumBones()):
            struct.pack_into('<H',data,2 * x, self.getAnimationBone(x).getNameIndex())
        off = ceilEight(self.getNumBones() * 2)

        for f in range(self.getNumFrames()):
            for b in range(self.getNumBones()):
                bone = self.getAnimationBone(b)
                t = bone.getTranslation(f)
                q = bone.getRotation(f)
                struct.pack_into('<fffffff', data, off,t[0],t[1],t[2],q[0],q[1],q[2],q[3])
                off+=28
        struct.pack_into('<hHIII',self.getHeaderBytes(),0,self.getNameIndex(),self.getNumBones(),self.getNumFrames(),self.getFpsNumerator(), self.getFpsDenominator())
    
    def applyOffset(self, offset):
        if(self.getNumBones() !=0):
            struct.pack_into('<q',self.getHeaderBytes(),16,offset)
        else:
            struct.pack_into('<q',self.getHeaderBytes(),16,-1)

        if(self.getNumFrames() !=0):
            struct.pack_into('<q',self.getHeaderBytes(),24,offset + ceilEight(self.getNumBones() * 2))
        else:
            struct.pack_into('<q',self.getHeaderBytes(),24,-1)
    
    def headerSize(self):
        return 32
    
    def bodySize(self):
        return ceilEight(2 * self.getNumBones()) + (28 * self.getNumBones() * self.getNumFrames())

class PapaFile:

    textureLibrary = None

    @classmethod
    def loadTextureLibrary(cls):
        # Code sourced from https://stackoverflow.com/questions/50168719/python-load-library-from-different-platform-windows-linux-or-os-x
        platName = platform.uname()[0]
        libName = ""
        if(platName == "Windows"):
            libName = "PTex.dll"
        elif(platName == "Linux"):
            libName = "PTex.so"
        else:
            libName = "PTex.dylib"
        libPath = path.dirname(path.abspath(__file__)) + path.sep + libName
        if path.exists(libPath):
            try:
                cls.textureLibrary = ctypes.cdll.LoadLibrary(libPath)
                cls.textureLibrary.argTypes = (ctypes.c_char_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.POINTER(ctypes.POINTER(ctypes.c_float)))
                cls.textureLibrary.resType = None
                print("Papa IO: Texture library "+libName+" successfully loaded.")
                return
            except Exception as e:
                print("Papa IO: Error loading texture library "+libName+", Python decompiler will be used. ("+str(e)+")")
                return
        print("Papa IO: Texture library "+libName+" not found, Python decompiler will be used.")

    def __init__(self, filepath: str = None, verbose = False, readLinked = False, signature = ""):
        self.__verbose = verbose
        self.__filepath = filepath
        self.__readLinked = readLinked
        self.__signature = signature
        self.__setupData()
        if filepath != None:
            file = open(filepath, 'rb')
            try:
                self.__parseData(file)
            finally:
                file.close()

    def logv(self, string):
        if(self.__verbose):
            print(string)
    
    def __setupData(self):
        self.__stringTable = []
        self.__textureTable = []
        self.__vertexBufferTable = []
        self.__indexBufferTable = []
        self.__materialTable = []
        self.__meshTable = []
        self.__skeletonTable = []
        self.__modelTable = []
        self.__animationTable = []

        self.__allComponents = [self.__stringTable, self.__textureTable, self.__vertexBufferTable, self.__indexBufferTable, self.__materialTable, 
            self.__meshTable, self.__skeletonTable, self.__modelTable, self.__animationTable]

    # ---------- decompiler portion -------------

    def __parseData(self, file):
        #PapaFile, I=UINT(32), H=USHORT(16), q=LONG(64)
        header = struct.unpack('<IHHHHHHHHHHHHHHqqqqqqqqq', file.read(104))
        papaCheck = header[0]
        if papaCheck != 0x50617061:
            raise IOError('File signature does not match papa file signature')

        file.seek(26)
        self.__signature = file.read(6)
        if self.__signature[0] == 0:
            self.__signature = ""
        else:
            t = ""
            for x in range(6):
                if self.__signature[x]!=0:
                    t+=chr(self.__signature[x])
            self.__signature = t

        self.__numberOfStrings = header[3]
        self.__numberOfTextures = header[4]
        self.__numberOfVertexBuffers = header[5]
        self.__numberOfIndexBuffers = header[6]
        self.__numberOfMaterials = header[7]
        self.__numberOfMeshes = header[8]
        self.__numberOfSkeletons = header[9]
        self.__numberOfModels = header[10]
        self.__numberOfAnimations = header[11]

        # 3 short buffer
        self.__offsetStringsHeader = header[15]
        self.__offsetTexturesHeader = header[16]
        self.__offsetVerticesHeader = header[17]
        self.__offsetIndicesHeader = header[18]
        self.__offsetMaterialsHeader = header[19]
        self.__offsetMeshHeader = header[20]
        self.__offsetSkeletonHeader = header[21]
        self.__offsetModelHeader = header[22]
        self.__offsetAnimationHeader = header[23]

        self.__readStrings(file)
        self.__readTextures(file)
        self.__readVBuffers(file)
        self.__readIBuffers(file)
        self.__readMaterials(file)
        self.__readMeshes(file)
        self.__readSkeletons(file)
        self.__readModels(file)
        self.__readAnimations(file)
        
    def __readStrings(self, file):
        if (self.__offsetStringsHeader < 0):
            return
        
        file.seek(self.__offsetStringsHeader)
        self.logv("Loading Strings...")
        for i in range(0, self.__numberOfStrings):
            currentString = struct.unpack('<qq', file.read(16))
            length = currentString[0]
            stringOffset = currentString[1]
            
            restore = file.tell() # returns the current position reading from in the file

            file.seek(stringOffset)
            self.__stringTable.append(PapaString(file.read(length).decode("utf-8")))
            self.logv("\"" + str(self.__stringTable[len(self.__stringTable) - 1]) + "\"")

            file.seek(restore)

    def __dxtDecodeColourMap(self, data):
        colours = [None, None, None, None] # [R, G, B]
        colour0 = ((data[0]) | (data[1] << 8))
        colour1 = ((data[2]) | (data[3] << 8))

        colours[0] = [(colour0>>8) & 0b11111000, (colour0>>3) & 0b11111100, (colour0<<3) & 0b11111000]
        colours[1] = [(colour1>>8) & 0b11111000, (colour1>>3) & 0b11111100, (colour1<<3) & 0b11111000]
        if colour0 > colour1:
            colours[2] = [  (2 * colours[0][0] + 	colours[1][0]) / 765,
                            (2 * colours[0][1] + 	colours[1][1]) / 765,
                            (2 * colours[0][2] +    colours[1][2]) / 765]
            colours[3] = [  (colours[0][0] + 	2 * colours[1][0]) / 765,
                            (colours[0][1] + 	2 * colours[1][1]) / 765,
                            (colours[0][2] + 	2 * colours[1][2]) / 765]
        else:
            colours[2] = [  (colours[0][0] +    colours[1][0]) / 510,
                            (colours[0][1] +    colours[1][1]) / 510,
                            (colours[0][2] +    colours[1][2]) / 510]
            colours[3] = [0,0,0]

        colours[0][0]/=255
        colours[0][1]/=255
        colours[0][2]/=255

        colours[1][0]/=255
        colours[1][1]/=255
        colours[1][2]/=255
        return colours

    def __dxtDecodeAlphaMap(self, data):
        alphaValues = [None] * 16

        alphaMap = [None] * 8
        alphaMap[0] = data[0]
        alphaMap[1] = data[1]

        if(alphaMap[0] > alphaMap[1]):
            for j in range(1,7):
                alphaMap[j+1] = ((7-j) * alphaMap[0] + j * alphaMap[1]) / 7
        else:
            for j in range(1,5):
                alphaMap[j+1] = ((5-j) * alphaMap[0] + j * alphaMap[1]) / 5
            alphaMap[6] = 0
            alphaMap[7] = 255

        for i in range(8):
            alphaMap[i]/=255 # normalize
        
        alphaBits = 0
        for i in range(2,8): # pack the rest of the data into a single long for easy access
            alphaBits |= data[i] << ((i-2) * 8)
        
        for j in range(16):
            alphaValues[j] = alphaMap[alphaBits & 0b111]
            alphaBits>>=3
        return alphaValues

    def __readTextures(self, file):
        if(self.__offsetTexturesHeader < 0):
            return

        file.seek(self.__offsetTexturesHeader)
        self.logv("Loading Textures...")
        papaTexturesHeader = []
        for x in range(self.__numberOfTextures):
            papaTexturesHeader.append(struct.unpack('<hBBHHqq', file.read(24))) # ignore mipmaps

        # this is a compressed down version of PTexEdit's texture reader
        for x in range(self.__numberOfTextures):
            nameIndex = papaTexturesHeader[x][0]
            formatIndex = papaTexturesHeader[x][1]
            srgb = papaTexturesHeader[x][2] & 0b1000_0000 == 0b1000_0000
            width = papaTexturesHeader[x][3]
            height = papaTexturesHeader[x][4]
            heightZero = height - 1 # 0 based index
            dataSize = papaTexturesHeader[x][5] # unused
            offsetTexture = papaTexturesHeader[x][6]

            if(dataSize == -1 or offsetTexture == -1): # the texture is linked, see if we can find the source...
                path = Path(self.__filepath)
                lastPath = None
                while path != lastPath and path.name.lower() != "pa" and path.name.lower() != "pa_ex1": # keep looking up the path until we are in the 'pa' or 'pa_ex1' directory
                    lastPath = path
                    path = path.parent

                if path == lastPath or not Path(str(path.parent) + self.getString(nameIndex)).exists(): # failed to find it
                    # we append None here because even if we miss, we should respect that the texture was meant to exist.
                    # Not appending None would mean that indices would become incorrect later on (Texture Parameters)
                    self.__textureTable.append(None)
                    self.logv("Linked file for texture \"" + self.getString(nameIndex) + "\" cannot be found. Ignoring.")
                    continue

                path = path.parent # move into 'media' directory (deferring this allows for better mod file support)
                fullPath = str(path) + self.getString(nameIndex)

                if not self.__readLinked: # keep the texture stub anyway
                    self.__stringTable.append(PapaString(fullPath))
                    tex = PapaTexture(len(self.__stringTable)-1,-1,False,-1,-1,[], fullPath)
                    self.__textureTable.append(tex)
                    self.logv("(texture stub)")
                    self.logv(self.__textureTable[len(self.__textureTable) - 1])
                    continue

                subfile = PapaFile(fullPath)
                if subfile.getNumTextures() != 1:
                    self.__stringTable.append(PapaString(fullPath))
                    tex = PapaTexture(len(self.__stringTable)-1,-1,False,-1,-1,[], fullPath)
                    self.__textureTable.append(tex)
                    self.logv("Linked file for texture \"" + self.getString(nameIndex) + "\" malformed. Creating texture stub")
                    self.logv(tex)
                    continue
                
                # copy the data to a new PapaTexture and create a new string for it (mildly jank)
                tex = subfile.getTexture(0)
                texName = subfile.getString(tex.getNameIndex())
                self.__stringTable.append(PapaString(texName))
                tex = PapaTexture(len(self.__stringTable)-1,tex.getFormatIndex(),tex.getSRGB(),tex.getWidth(),tex.getHeight(),tex.getImageData(), tex.getFilepath())

                self.__textureTable.append(tex) # acquire the linked texture
                self.logv("(externally loaded)")
                self.logv(self.__textureTable[len(self.__textureTable) - 1])
                continue

            numberOfPixels = width * height
            numberOfValues = numberOfPixels * 4 # (destination, not source)
            texData = []

            if PapaFile.textureLibrary:
                file.seek(offsetTexture)
                if(formatIndex==13): # R8
                    rawData = file.read(numberOfPixels)
                elif formatIndex == 1 or formatIndex == 2 or formatIndex == 3:
                    rawData = file.read(numberOfValues)
                elif formatIndex == 4: # DXT1
                    rawData = file.read(ceil(width/4) * ceil(height / 4) * 8) # 8 bytes per block
                elif formatIndex == 6: # DXT5
                    rawData = file.read(ceil(width/4) * ceil(height / 4) * 16) # 16 bytes per block
                
                if (numberOfValues & (numberOfValues-1)) == 0: # test if the number of values is a power of two
                    # if it is, we can allocate our array faster using this method (don't ask why this is faster because i don't know)
                    texData = array('f',[0.0])
                    for _ in range(int(log2(numberOfValues))):
                        texData.extend(texData)
                else:
                    texData = array('f',[0.0] * numberOfValues)
                dataPointer = texData.buffer_info()[0]
                PapaFile.textureLibrary.decodeTexture(ctypes.c_char_p(rawData), ctypes.c_int(width), ctypes.c_int(height),
                    ctypes.c_int(formatIndex), ctypes.cast(dataPointer,ctypes.POINTER(ctypes.c_float)))
            else:
                # for some reason blender flips this data across the x axis, so we must invert y
                file.seek(offsetTexture)
                if formatIndex == 1: # RGBA8888
                    texData = [None] * numberOfValues
                    tempData = struct.unpack('<' + 'B' * numberOfValues,file.read(numberOfValues))
                    for y in range(height):
                        for x in range(width):
                            i = (x + (heightZero - y) * width) * 4
                            i2 = (x + y * width) * 4
                            texData[i] = tempData[i2] / 255
                            texData[i+1] = tempData[i2+1] / 255
                            texData[i+2] = tempData[i2+2] / 255
                            texData[i+3] = tempData[i2+3] / 255
                elif formatIndex == 2: # RGBX8888
                    texData = [None] * numberOfValues
                    tempData = struct.unpack('<' + 'B' * numberOfValues,file.read(numberOfValues)) # ignore alpha data
                    for y in range(height):
                        for x in range(width):
                            i = (x + (heightZero - y) * width) * 4
                            i2 = (x + y * width) * 4
                            texData[i]=tempData[i2]/255
                            texData[i+1]=tempData[i2+1]/255
                            texData[i+2]=tempData[i2+2]/255
                            texData[i+3]=1
                elif formatIndex == 3: #BGRA8888
                    texData = [None] * numberOfValues
                    tempData = struct.unpack('<' + 'B' * numberOfValues,file.read(numberOfValues))
                    for y in range(height):
                        for x in range(width):
                            i = (x + (heightZero - y) * width) * 4
                            i2 = (x + y * width) * 4
                            texData[i]=tempData[i2]/255
                            texData[i+1]=tempData[i2+1]/255
                            texData[i+2]=tempData[i2+2]/255
                            texData[i+3]=tempData[i2+3]/255
                            t = texData[i]
                            texData[i] = texData[i2+2]
                            texData[i+2] = t
                elif formatIndex == 4: # DXT1
                    texData = [None] * numberOfValues

                    for y in range(0,height,4):
                        for x in range(0,width,4):
                            colourBuffer = struct.unpack('<BBBB',file.read(4))
                            colours = self.__dxtDecodeColourMap(colourBuffer)

                            bits = struct.unpack('<I',file.read(4))[0]
                            for yy in range(4):
                                for xx in range(4):
                                    colourIndex = bits & 0b11
                                    if yy + y < height and xx + x < width: # copy our colour data into the array
                                        idx = (xx + x + (heightZero - (yy + y)) * width) * 4
                                        col = colours[colourIndex]
                                        texData[idx] = col[0]
                                        texData[idx+1] = col[1]
                                        texData[idx+2] = col[2]
                                        texData[idx+3] = 1
                                    bits>>=2
                elif formatIndex == 6: # DXT5

                    texData = [None] * numberOfValues

                    for y in range(0,height,4):
                        for x in range(0,width,4):

                            alphaBuffer = struct.unpack('<BBBBBBBB',file.read(8))
                            alphaValues = self.__dxtDecodeAlphaMap(alphaBuffer)

                            colourBuffer = struct.unpack('<BBBB',file.read(4))
                            colours = self.__dxtDecodeColourMap(colourBuffer)

                            bits = struct.unpack('<I',file.read(4))[0]
                            for yy in range(4):
                                for xx in range(4):
                                    colourIndex = bits & 0b11
                                    if yy + y < height and xx + x < width: # copy our colour data into the array
                                        idx = (xx+x + (heightZero-(yy+y)) * width) * 4
                                        col = colours[colourIndex]
                                        texData[idx] = col[0]
                                        texData[idx+1] = col[1]
                                        texData[idx+2] = col[2]
                                        texData[idx+3] = alphaValues[xx + yy * 4]
                                    bits>>=2
                elif formatIndex == 13: # R8
                    temp = struct.unpack('<' + 'B' * numberOfPixels,file.read(numberOfPixels))
                    texData = [None] * numberOfValues
                    for y in range(height):
                        for x in range(width):
                            idx = x + (heightZero - y) * width * 4
                            idx2 = x + y * width
                            texData[idx] = temp[idx2] / 255 # copy just the red channel
                            texData[idx + 1] = 0 # G
                            texData[idx + 2] = 0 # B
                            texData[idx + 3] = 1 # A
            self.__textureTable.append(PapaTexture(nameIndex, formatIndex, srgb, width, height, texData, self.__filepath))
            self.logv(self.__textureTable[len(self.__textureTable) - 1])


    def __readVBuffers(self, file):
        if(self.__offsetVerticesHeader < 0):
            return
        
        self.logv("Loading Vertex Buffers...")
        file.seek(self.__offsetVerticesHeader)
        papaVerticesHeader = []
        for x in range(self.__numberOfVertexBuffers):
            papaVerticesHeader.append(struct.unpack('<IIqq', file.read(24)))

        for x in range(self.__numberOfVertexBuffers):

            vertexFormat = papaVerticesHeader[x][0]
            numberOfVertices = papaVerticesHeader[x][1]
            offsetVertices = papaVerticesHeader[x][3]
            #PapaVertex

            vertices = []

            file.seek(offsetVertices)
            if (vertexFormat == 0): # Position3
                for _ in range(numberOfVertices):
                    currentVertex = struct.unpack('<fff', file.read(12))

                    p = Vector([currentVertex[0],currentVertex[1],currentVertex[2]])

                    vertices.append(PapaVertex(p))
            
            elif (vertexFormat == 5): # Position3Normal3TexCoord2
                for _ in range(numberOfVertices):
                    currentVertex = struct.unpack('<ffffffff', file.read(32))

                    p = Vector([currentVertex[0],currentVertex[1],currentVertex[2]])
                    n = Vector([currentVertex[3],currentVertex[4],currentVertex[5]])
                    t1 = [currentVertex[6],currentVertex[7]]

                    vertices.append(PapaVertex(p, norm=n, texcoord1=t1))

            elif (vertexFormat == 6): # Position3Normal3Color4TexCoord2
                for _ in range(numberOfVertices):
                    currentVertex = struct.unpack('<ffffffBBBBff', file.read(36))

                    p = Vector([currentVertex[0],currentVertex[1],currentVertex[2]])
                    n = Vector([currentVertex[3],currentVertex[4],currentVertex[5]])
                    c = [currentVertex[6],currentVertex[7],currentVertex[8],currentVertex[9]]
                    t1 = [currentVertex[10],currentVertex[11]]

                    vertices.append(PapaVertex(p, norm=n, col=c, texcoord1=t1))

            elif (vertexFormat == 7): # Position3Normal3Color4TexCoord4
                for _ in range(numberOfVertices):
                    currentVertex = struct.unpack('<ffffffBBBBffff', file.read(44))

                    p = Vector([currentVertex[0],currentVertex[1],currentVertex[2]])
                    n = Vector([currentVertex[3],currentVertex[4],currentVertex[5]])
                    c = [currentVertex[6],currentVertex[7],currentVertex[8],currentVertex[9]]
                    t1 = [currentVertex[10],currentVertex[11]]
                    t2 = [currentVertex[12],currentVertex[13]]

                    vertices.append(PapaVertex(p, norm=n, col=c, texcoord1=t1, texcoord2=t2))

            elif (vertexFormat == 8): # Position3Weights4bBones4bNormal3TexCoord2
                for _ in range(numberOfVertices):
                    currentVertex = struct.unpack('<fffBBBBBBBBfffff', file.read(40))

                    p = Vector([currentVertex[0],currentVertex[1],currentVertex[2]])
                    weight = [currentVertex[3]/255,currentVertex[4]/255,currentVertex[5]/255,currentVertex[6]/255]
                    bone = [currentVertex[7],currentVertex[8],currentVertex[9],currentVertex[10]]
                    n = Vector([currentVertex[11],currentVertex[12],currentVertex[13]])
                    t1 = [currentVertex[14],currentVertex[15]]

                    vertices.append(PapaVertex(p, bones=bone, weights=weight, norm=n, texcoord1=t1))
                    
            elif (vertexFormat == 10): # Position3Normal3Tan3Bin3TexCoord4
                for _ in range(numberOfVertices):
                    currentVertex = struct.unpack('<ffffffffffffffff', file.read(64))

                    p = Vector([currentVertex[0],currentVertex[1],currentVertex[2]])
                    n = Vector([currentVertex[3],currentVertex[4],currentVertex[5]])
                    t = Vector([currentVertex[6],currentVertex[7],currentVertex[8]])
                    b = Vector([currentVertex[9],currentVertex[10],currentVertex[11]])
                    t1 = [currentVertex[12],currentVertex[13]]
                    t2 = [currentVertex[14],currentVertex[15]]

                    vertices.append(PapaVertex(p, norm=n, tan=t, binorm=b, texcoord1=t1, texcoord2=t2))
            self.__vertexBufferTable.append(PapaVertexBuffer(vertexFormat, vertices))
            self.logv(self.__vertexBufferTable[len(self.__vertexBufferTable) - 1])
    


    def __readIBuffers(self, file):
        if(self.__offsetIndicesHeader < 0):
            return
        
        self.logv("Loading Index Buffers...")
        file.seek(self.__offsetIndicesHeader)
        papaIndicesHeader = []
        for x in range(self.__numberOfIndexBuffers):
            papaIndicesHeader.append(struct.unpack('<BxxxIqq', file.read(24)))
        for x in range(self.__numberOfIndexBuffers):
            format = papaIndicesHeader[x][0]
            numberOfIndices = papaIndicesHeader[x][1]
            dataSize = papaIndicesHeader[x][2]
            offsetIndices = papaIndicesHeader[x][3]

            #PapaTriangle
            file.seek(offsetIndices)
            if(format == 0):
                self.__indexBufferTable.append(PapaIndexBuffer(0,struct.unpack('<'+'H'*numberOfIndices,file.read(dataSize))))
            elif(format == 1):
                self.__indexBufferTable.append(PapaIndexBuffer(1,struct.unpack('<'+'I'*numberOfIndices,file.read(dataSize))))
            else:
                raise IOError('Invalid index buffer format for index buffer '+str(x))
            self.logv(self.__indexBufferTable[len(self.__indexBufferTable) - 1])
    


    def __readMaterials(self, file):
        if(self.__offsetMaterialsHeader < 0):
            return
        
        self.logv("Loading Materials...")
        file.seek(self.__offsetMaterialsHeader)
        for x in range(self.__numberOfMaterials):
            materialHeader = struct.unpack('<HHHHqqq', file.read(32))
            restore = file.tell()
            nameIndex = materialHeader[0]
            numVectorParams = materialHeader[1]
            numTextureParams = materialHeader[2]
            numMatrixParams = materialHeader[3]

            offsetVectorParams = materialHeader[4]
            offsetTextureParams = materialHeader[5]
            offsetMatrixParams = materialHeader[6]

            vectorParams = []
            textureParams = []
            matrixParams = []

            if numVectorParams > 0:
                file.seek(offsetVectorParams)
                for _ in range(numVectorParams):
                    vectorData = struct.unpack('<Hxxffff',file.read(20))
                    vectorParams.append(PapaVectorParameter(vectorData[0],Vector([vectorData[1],vectorData[2],vectorData[3],vectorData[4]])))

            if numTextureParams > 0:
                file.seek(offsetTextureParams)
                for _ in range(numTextureParams):
                    textureData = struct.unpack('<HH',file.read(4))
                    textureParams.append(PapaTextureParameter(textureData[0],textureData[1]))

            if numMatrixParams > 0:
                file.seek(offsetMatrixParams)
                for _ in range(numMatrixParams):
                    matrixData = struct.unpack('<Hxxffffffffffffffff',file.read(68))
                    A =(matrixData[1],matrixData[5],matrixData[9],matrixData[13])
                    B =(matrixData[2],matrixData[6],matrixData[10],matrixData[14])
                    C =(matrixData[3],matrixData[7],matrixData[11],matrixData[15])
                    D =(matrixData[4],matrixData[8],matrixData[12],matrixData[16])
                    mat = (A,B,C,D)
                    matrixParams.append(PapaMatrixParameter(matrixData[0],Matrix(mat)))
            mat = PapaMaterial(nameIndex, vectorParams,textureParams,matrixParams)
            self.__materialTable.append(mat)
            self.logv(str(mat) + " (shader = " + self.getString(mat.getShaderNameIndex())+")")
            file.seek(restore)



    def __readMeshes(self, file):
        if(self.__offsetMeshHeader < 0):
            return
        
        self.logv("Loading Meshes...")
        file.seek(self.__offsetMeshHeader)
        for _ in range(self.__numberOfMeshes):
            meshHeader = struct.unpack('<HHHxxq', file.read(16))
            restore = file.tell()
            vbuf = meshHeader[0]
            ibuf = meshHeader[1]
            numMatGroups = meshHeader[2]
            offset = meshHeader[3]

            matGroups = []

            if(numMatGroups > 0):
                file.seek(offset)
                for _ in range(numMatGroups):
                    header = struct.unpack('<HHIIBxxx',file.read(16))
                    matGroups.append(PapaMaterialGroup(header[0],header[1],header[2],header[3],header[4]))

            self.__meshTable.append(PapaMesh(vbuf,ibuf,matGroups))
            self.logv(self.__meshTable[len(self.__meshTable) - 1])
            file.seek(restore)

    

    def __readSkeletons(self, file):
        if (self.__offsetSkeletonHeader < 0):
            return
        
        self.logv("Loading Skeletons...")
        file.seek(self.__offsetSkeletonHeader)
        papaSkeletonHeader = []
        for x in range(self.__numberOfSkeletons):
            papaSkeletonHeader.append(struct.unpack('<Hxxxxxxq', file.read(16)))
        for x in range(self.__numberOfSkeletons):
            numBones = papaSkeletonHeader[x][0]
            offsetBoneTable = papaSkeletonHeader[x][1]
            bones = []
            #PapaSkeletonSegment
            file.seek(offsetBoneTable)
            for _ in range(0, numBones):
                currentSegment = struct.unpack('<hhffffffffffffffffffffffffffffffff', file.read(132))
                nameIndex = currentSegment[0]
                parentIndex = currentSegment[1]

                # 2 - 4 = translation relative
                #  5 - 8 = rotation relative
                # 9 - 17 = shear scale (unused)
                # 18 - 33 = bind2bone (convert global position to bone's local position)

                offset = Vector([currentSegment[2],currentSegment[3],currentSegment[4]])
                rotation = Quaternion([currentSegment[5],currentSegment[6],currentSegment[7],currentSegment[8]])

                sA = (currentSegment[9],currentSegment[12],currentSegment[15])
                sB = (currentSegment[10],currentSegment[13],currentSegment[16])
                sC = (currentSegment[11],currentSegment[14],currentSegment[17])
                sMat = (sA,sB,sC)
                shearScale = Matrix(sMat) # unused

                A =(currentSegment[18],currentSegment[22],currentSegment[26],currentSegment[30])
                B =(currentSegment[19],currentSegment[23],currentSegment[27],currentSegment[31])
                C =(currentSegment[20],currentSegment[24],currentSegment[28],currentSegment[32])
                D =(currentSegment[21],currentSegment[25],currentSegment[29],currentSegment[33])
                mat = (A,B,C,D)
                bindToBone = Matrix(mat)
                bones.append(PapaBone(nameIndex,parentIndex,offset,rotation,shearScale,bindToBone))

            self.__skeletonTable.append(PapaSkeleton(bones))
            self.logv(self.__skeletonTable[len(self.__skeletonTable) - 1])


    
    def __readModels(self, file):
        if (self.__offsetModelHeader < 0):
            return
        
        self.logv("Loading Models...")
        file.seek(self.__offsetModelHeader)
        papaModelHeader = []
        for x in range(self.__numberOfModels):
            papaModelHeader.append(struct.unpack('<hhHxxffffffffffffffffq', file.read(80)))
        for x in range(self.__numberOfModels):
            modelNameIndex = papaModelHeader[x][0]
            skeletonIndex = papaModelHeader[x][1]
            numMeshBindings = papaModelHeader[x][2]
            A =(papaModelHeader[x][3],papaModelHeader[x][7],papaModelHeader[x][11],papaModelHeader[x][15])
            B =(papaModelHeader[x][4],papaModelHeader[x][8],papaModelHeader[x][12],papaModelHeader[x][16])
            C =(papaModelHeader[x][5],papaModelHeader[x][9],papaModelHeader[x][13],papaModelHeader[x][17])
            D =(papaModelHeader[x][6],papaModelHeader[x][10],papaModelHeader[x][14],papaModelHeader[x][18])
            mat = (A,B,C,D)
            modelToScene = Matrix(mat)
            offsetMeshBindings = papaModelHeader[x][19]

            meshBindings = []
            # PapaMeshBinding
            if(numMeshBindings>0):
                file.seek(offsetMeshBindings)
                for _ in range(0, numMeshBindings):
                    currentSegment = struct.unpack('<HHHxxffffffffffffffffq', file.read(80))

                    boneMappings = []

                    nameIndex = currentSegment[0]
                    meshIndex = currentSegment[1]
                    numBoneMappings = currentSegment[2]
                    A =(currentSegment[3],currentSegment[7],currentSegment[11],currentSegment[15])
                    B =(currentSegment[4],currentSegment[8],currentSegment[12],currentSegment[16])
                    C =(currentSegment[5],currentSegment[9],currentSegment[13],currentSegment[17])
                    D =(currentSegment[6],currentSegment[10],currentSegment[14],currentSegment[18])
                    mat = (A,B,C,D)
                    meshToModel = Matrix(mat)
                    offsetBoneMap = currentSegment[19]

                    restore = file.tell()
                    if(numBoneMappings>0):
                        file.seek(offsetBoneMap)
                        boneMappings = list(struct.unpack('<' + 'H' * numBoneMappings, file.read(2 * numBoneMappings)))
                    file.seek(restore)

                    meshBindings.append(PapaMeshBinding(nameIndex,meshIndex,meshToModel,boneMappings))
            self.__modelTable.append(PapaModel(modelNameIndex,skeletonIndex,modelToScene,meshBindings))
            self.logv(self.__modelTable[len(self.__modelTable) - 1])

    def __readAnimations(self, file):
        if(self.__offsetAnimationHeader < 0):
            return
        self.logv("Loading Animations...")
        file.seek(self.__offsetAnimationHeader)
        papaAnimationHeader = []
        for x in range(self.__numberOfAnimations):
            papaAnimationHeader.append(struct.unpack('<hHIIIqq', file.read(32)))
        for x in range(self.__numberOfAnimations):
            nameIndex = papaAnimationHeader[x][0]
            numBones = papaAnimationHeader[x][1]
            numFrames = papaAnimationHeader[x][2]
            fpsNumerator = papaAnimationHeader[x][3]
            fpsDenominator = papaAnimationHeader[x][4]
            boneTableOffset = papaAnimationHeader[x][5]
            transformsOffset = papaAnimationHeader[x][6]

            # set up variables
            boneNameIndexes = []
            translations = []
            rotations = []
            for x in range(numBones):
                translations.append([])
                rotations.append([])
            
            # load bone names
            if boneTableOffset >= 0:
                file.seek(boneTableOffset)
            currentSegment = struct.unpack('<' + 'H' * numBones, file.read(2 * numBones))
            for x in range(numBones):
                boneNameIndexes.append(currentSegment[x])
            
            if transformsOffset >= 0:
                file.seek(transformsOffset)
            for i in range(numFrames):
                for k in range(numBones): # (frame1 --> bone1, bone2), (frame2 -->bone1, bone2) ...
                    currentSegment = struct.unpack('<fffffff', file.read(28))
                    translations[k].append(Vector((currentSegment[0],currentSegment[1],currentSegment[2])))
                    rotations[k].append(Quaternion((currentSegment[3],currentSegment[4], currentSegment[5], currentSegment[6])))
            
            animationBones = []
            for i in range(numBones):
                animationBones.append(AnimationBone(boneNameIndexes[i], self.getString(boneNameIndexes[i]),translations[i],rotations[i]))

            self.__animationTable.append(PapaAnimation(nameIndex, numBones, numFrames, fpsNumerator, fpsDenominator, animationBones))
            self.logv(self.__animationTable[len(self.__animationTable) - 1])

    def getSignature(self):
        return self.__signature
    
    def getNumStrings(self) -> int:
        return len(self.__stringTable)
    
    def getNumTextures(self) -> int:
        return len(self.__textureTable)

    def getNumVertexBuffers(self) -> int:
        return len(self.__vertexBufferTable)

    def getNumIndexBuffers(self) -> int:
        return len(self.__indexBufferTable)

    def getNumMaterials(self) -> int:
        return len(self.__materialTable)

    def getNumMeshes(self) -> int:
        return len(self.__meshTable)

    def getNumSkeletons(self) -> int:
        return len(self.__skeletonTable)

    def getNumModels(self) -> int:
        return len(self.__modelTable)

    def getNumAnimations(self) -> int:
        return len(self.__animationTable)

    def getString(self, index:int) -> str:
        if(index < 0 or index >= len(self.__stringTable)):
            return ""
        return self.__stringTable[index].getString()

    def getPapaString(self, index: int):
        return self.__stringTable[index]

    def getTexture(self, index:int) -> PapaTexture:
        return self.__textureTable[index]

    def getVertexBuffer(self, index:int) -> PapaVertexBuffer:
        return self.__vertexBufferTable[index]

    def getIndexBuffer(self, index:int) -> PapaIndexBuffer:
        return self.__indexBufferTable[index]

    def getMaterial(self, index:int) -> PapaMaterial:
        return self.__materialTable[index]

    def getMesh(self, index:int) -> PapaMesh:
        return self.__meshTable[index]

    def getSkeleton(self, index:int) -> PapaSkeleton:
        return self.__skeletonTable[index]

    def getModel(self, index:int) -> PapaModel:
        return self.__modelTable[index]

    def getAnimation(self, index:int) -> PapaAnimation:
        return self.__animationTable[index]

    def addString(self, obj: PapaString) -> int:
        idx = self.getStringIndex(obj.getString())
        if idx != -1:
            return idx
        self.__stringTable.append(obj)
        return len(self.__stringTable) - 1

    def addTexture(self, obj:PapaTexture):
        if obj in self.__textureTable:
            return self.__textureTable.index(obj)
        self.__textureTable.append(obj)
        return len(self.__textureTable) - 1

    def addVertexBuffer(self, obj:PapaVertexBuffer):
        if obj in self.__vertexBufferTable:
            return self.__vertexBufferTable.index(obj)
        self.__vertexBufferTable.append(obj)
        return len(self.__vertexBufferTable) - 1

    def addIndexBuffer(self, obj:PapaIndexBuffer):
        if obj in self.__indexBufferTable:
            return self.__indexBufferTable.index(obj)
        self.__indexBufferTable.append(obj)
        return len(self.__indexBufferTable) - 1

    def addMaterial(self, obj:PapaMaterial):
        if obj in self.__materialTable:
            return self.__materialTable.index(obj)
        self.__materialTable.append(obj)
        return len(self.__materialTable) - 1

    def addMesh(self, obj:PapaMesh):
        if obj in self.__meshTable:
            return self.__meshTable.index(obj)
        self.__meshTable.append(obj)
        return len(self.__meshTable) - 1

    def addSkeleton(self, obj:PapaSkeleton):
        if obj in self.__skeletonTable:
            return self.__skeletonTable.index(obj)
        self.__skeletonTable.append(obj)
        return len(self.__skeletonTable) - 1

    def addModel(self, obj:PapaModel):
        if obj in self.__modelTable:
            return self.__modelTable.index(obj)
        self.__modelTable.append(obj)
        return len(self.__modelTable) - 1

    def addAnimation(self, obj:PapaAnimation):
        if obj in self.__animationTable:
            return self.__animationTable.index(obj)
        self.__animationTable.append(obj)
        return len(self.__animationTable) - 1

    # ---------- compiler portion -------------
    # Note: the compiler is quite simple, it just repacks the data (i.e. calling compile right after opening the file will write the exact same file back). It is
    # up to the programmer to correctly input the data for the compiler to pack

    def compile(self):
        return self.__compileData()
    
    def getStringIndex(self, string: str):
        for x in range(self.getNumStrings()):
            if(self.getString(x) == string):
                return x
        return -1

    def __compileData(self):

        data = bytearray(self.__calcFileSize())

        self.__buildHeader(data)
        headerOffset = 32

        buildOrder = [7,5,4,1,2,3,6,8,0]

        position = 0x68 # the current write pointer

        for index in buildOrder:
            if(len(self.__allComponents[index]) != 0):
                struct.pack_into('<q',data,headerOffset + 8 * index, position)
            else:
                struct.pack_into('<q',data,headerOffset + 8 * index, -1)
            
            position = self.__buildComponent(self.__allComponents[index], data, position)

        return bytes(data)

    def __buildHeader(self, header):
        sigVal = bytearray(self.__signature)
        for _ in range(len(sigVal),6):
            sigVal.append(0)
        struct.pack_into('<IhhhhhhhhhhhBBBBBB',header,0,0x50617061,0,3,self.getNumStrings(), self.getNumTextures(), self.getNumVertexBuffers(),
            self.getNumIndexBuffers(),self.getNumMaterials(), self.getNumMeshes(), self.getNumSkeletons(), self.getNumModels(), self.getNumAnimations(),
            *sigVal)

    def __buildComponent(self, componentList, data, position): # position is the current write position of the byte array
        currentSize = 0 # used to offset from the header
        # calculate the total size of this batch
        for component in componentList:
            component.build()
            currentSize+=component.headerSize() # all headers are aligned to be multiples of 8, so no need to ceilEight
        
        for component in componentList:
            component.applyOffset(currentSize + position)
            currentSize+=ceilEight(component.bodySize())
        
        # write the batch into the file bytes
        for component in componentList:
            data[position: position + len(component.getHeaderBytes())] = component.getHeaderBytes()
            position += component.headerSize()
        
        for component in componentList:
            data[position: position + len(component.getBodyBytes())] = component.getBodyBytes()
            position += component.bodySize()
            position = ceilEight(position)
        
        return position
        
    
    def __calcFileSize(self):
        totalSize = 0x68 # header
        for table in self.__allComponents:
            for component in table:
                totalSize+=component.componentSize()
        return totalSize


def ceilEight(num):
    return ceil(num / 8) * 8

def ceilNextEight(num):
    return ceilEight(num + 1)

PapaFile.loadTextureLibrary()