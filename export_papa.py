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

import bpy
from mathutils import * # has vectors and quaternions
from os import path
from .papafile import *
import time

class PapaBuildException(Exception): # used as a filter
    pass

# used to hold nonfatal errors until export is done (this way nonfatal errors won't clutter the fatal one)
class PapaExportNotifications:
    __instance = None

    def __init__(self):
        self.__notifications = []

    def addNotification(self, notificationType, notif=None):
        if notif == None:
            notif = notificationType
            notificationType = {"WARNING"}

        print(next(iter(notificationType))+":",notif)
        self.__notifications.append( (notificationType,notif) )
    
    def getNumNotifications(self):
        return len(self.__notifications)

    def getNotification(self,idx):
        return self.__notifications[idx]

    @classmethod
    def getInstance(cls):
        return cls.__instance

    @classmethod
    def setup(cls):
        cls.__instance = PapaExportNotifications()

class PapaExportCache:
    __instance = None

    def __init__(self):
        self.__skeletonCache = {}
    
    def addSkeleton(self, key, skeleton):
        self.__skeletonCache[key] = skeleton
    
    def getSkeleton(self, key):
        return self.__skeletonCache.get(key, None)

    @classmethod
    def getInstance(cls):
        return cls.__instance

    @classmethod
    def setup(cls):
        cls.__instance = PapaExportCache()

def write_papa(properties, context, operator):
    filepath = properties.getFilepath()
    file_name=path.splitext(path.basename(filepath))[0]
    print("Starting export of "+file_name)
    PapaExportNotifications.setup()
    PapaExportCache.setup()

    selected = []
    for obj in bpy.context.selected_objects:
        selected.append(obj)
    activeObject = bpy.context.active_object
    activeMode = bpy.context.active_object.mode if activeObject else None
    
    targetObjects = properties.getTargets()
    papaFile = PapaFile() # make the papafile container

    try:
        for obj in targetObjects:
            if(obj.type == "MESH"):
                writeMesh(obj, properties, papaFile)
            else:
                writeAnimation(obj, properties, papaFile)
    except PapaBuildException as e:
        return 'ERROR', str(e)
    
    print("Writing Data...")
    data = papaFile.compile()

    file = open(filepath, 'wb')
    file.write(data)
    file.close()

    for obj in bpy.context.selected_objects:
        obj.select_set(False)
    for obj in selected:
        obj.select_set(True)
    if activeObject:
        bpy.context.view_layer.objects.active = activeObject
        bpy.ops.object.mode_set(mode=activeMode)

    notifications = PapaExportNotifications.getInstance()
    if notifications.getNumNotifications() != 0:
        for x in range(notifications.getNumNotifications()):
            notif = notifications.getNotification(x)
            operator.report(notif[0],notif[1])

def selectObject(obj):
    for i in bpy.context.selected_objects: 
        i.select_set(False) #deselect all objects
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj

def vectorToImmutableMapping(vector):
    return (round(vector[0] * 100), round(vector[1] * 100), round(vector[2] * 100))

def createFaceShadingIslands(mesh, properties):
    # in PA, smooth shading is defined by whether or not two faces share the same vertices
    # we must construct a map that tells us which faces are connected and which are not by assigning each face index to a shading index
    vertices = mesh.data.vertices
    edges = mesh.data.edges
    polygons = mesh.data.polygons

    edgeKeyToIndex = {}
    for edge in edges:
        edgeKeyToIndex[edge.key] = edge.index
    
    edgeKeyToFaces = {}
    for x in range(len(polygons)):
        for edgeKey in polygons[x].edge_keys:
            if not edgeKeyToFaces.get(edgeKey):
                edgeKeyToFaces[edgeKey] = []
            edgeKeyToFaces[edgeKey].append(x) # map this face to this edge key
    seenFaces = {}
    currentIndex = 0

    # maps each face to it's shading group
    faceMap = {}
    # we can safely combine faces with the same normal even if they're not smooth shaded
    compressionMap = {}

    # for each face, perform a search and set all faces that you find to be the same index
    # the search is limited only by smooth shading borders or mark sharp borders
    for polyIdx in range(len(polygons)):
        if seenFaces.get(polyIdx, False):
            continue

        faceMap[polyIdx] = currentIndex
        seenFaces[polyIdx] = True

        if polygons[polyIdx].use_smooth == False:

            # try to find any face with the same normal vector so we can combine data
            if properties.isCompress():
                norm = vectorToImmutableMapping(polygons[polyIdx].normal)
                mapping = compressionMap.get(norm, -1)

                # not found, add new entry
                if mapping == -1:
                    compressionMap[norm] = currentIndex
                    currentIndex+=1
                else:
                    faceMap[polyIdx] = mapping
            else:
                currentIndex+=1
            
            continue
        
        openList = [polyIdx]
        while len(openList) != 0:
            currentFace = openList.pop()
            faceMap[currentFace] = currentIndex

            # lookup faces that have this edge
            for edgeKey in polygons[currentFace].edge_keys:
                edgeIndex = edgeKeyToIndex.get(edgeKey,None)
                edge = edges[edgeIndex]

                # Respect the sharp of the model, also PA cannot store smooth shading data and split UVs together. We handle this edge case with the connection map
                # (Smooth shading requires shared vertices but split UVs require split vertices)
                if edge.use_edge_sharp or edge.use_seam:
                    continue
                
                faces = edgeKeyToFaces[edgeKey]
                for faceKey in faces:
                    if seenFaces.get(faceKey,False) or polygons[faceKey].use_smooth == False:
                        continue
                    seenFaces[faceKey] = True
                    openList.append(faceKey)
        
        currentIndex+=1

    if not properties.isRespectMarkSharp():
        return faceMap, {}, {}

    connectionMap = [] # [faceIndex][vertexIndex] -> all connected faces (sharp aware)
    vertexShadingMap = [] # [faceIndex][vertexIndex] -> unique index to separate out local connection
    tempShadingMap = {} # [uniqueIndex] -> maps the vertexShadingMap back to the connection map
    currentIndex = 0

    for _ in range(len(polygons)):
        vertexShadingMap.append({})
    
    for polyIdx in range(len(polygons)):

        faceConnections = {}
        connectionMap.append(faceConnections)
        for vertexIdx in polygons[polyIdx].vertices:

            if not polygons[polyIdx].use_smooth:
                # only connected to itself
                faceConnections[vertexIdx] = [polyIdx]
                continue

            testVal = vertexShadingMap[polyIdx].get(vertexIdx, -1)
            if testVal != -1:
                # already computed, use that instead
                faceConnections[vertexIdx] = tempShadingMap[testVal]
                continue

            openList = [polyIdx]
            seenFaces = {polyIdx: True}
            connections = [polyIdx]
            faceConnections[vertexIdx] = connections

            while len(openList) != 0:
                poly = openList.pop()
                for key in polygons[poly].edge_keys:
                    edge = edges[edgeKeyToIndex[key]]
                    if edge.use_edge_sharp or not vertexIdx in edge.vertices:
                        continue

                    faces = edgeKeyToFaces[key]
                    for faceIdx in faces:
                        if seenFaces.get(faceIdx, False):
                            continue
                        seenFaces[faceIdx] = True
                        openList.append(faceIdx)
                        connections.append(faceIdx)
                        vertexShadingMap[faceIdx][vertexIdx] = currentIndex

            tempShadingMap[currentIndex] = connections
            currentIndex+=1

    angleMap = [] # [faceIndex][vertexIndex] -> angle in radians between the edges that connect to this vertex
    for _ in range(len(polygons)):
        angleMap.append({})

    for polyIdx in range(len(polygons)):
        polyEdges = []
        for key in polygons[polyIdx].edge_keys:
            polyEdges.append(edges[edgeKeyToIndex[key]])

        for vertexIdx in polygons[polyIdx].vertices:
            # find the two edges that make up this face
            currentEdges = []
            for edge in polyEdges:
                if vertexIdx in edge.vertices:
                    currentEdges.append(edge)
            
            # every face must have at exactly 2 edges that touch a vertex, or else it is not a face.
            v1 = currentEdges[0].vertices[0]
            v2 = currentEdges[0].vertices[1]
            v3 = currentEdges[1].vertices[0]
            v4 = currentEdges[1].vertices[1]

            if v1 == vertexIdx:
                vec1 = Vector(vertices[v2].co) - Vector(vertices[v1].co)
            else:
                vec1 = Vector(vertices[v1].co) - Vector(vertices[v2].co)

            if v3 == vertexIdx:
                vec2 = Vector(vertices[v4].co) - Vector(vertices[v3].co)
            else:
                vec2 = Vector(vertices[v3].co) - Vector(vertices[v4].co)

            angleMap[polyIdx][vertexIdx] = vec1.angle(vec2)

    return faceMap, connectionMap, angleMap

def createFaceMaterialIslands(mesh):
    # faces that use a material must be laid out sequentially in the data
    # we build a map that maps each material to a list of faces that use it

    polygons = mesh.data.polygons
    materialMap = []
    for _ in mesh.data.materials:
        materialMap.append([])
    if len(materialMap) == 0:
        materialMap.append([])

    for x in range(len(polygons)):
        face = polygons[x]
        idx = face.material_index
        materialMap[idx].append(x)
    return materialMap

def createBoneWeightMap(mesh, papaFile:PapaFile, skeleton:PapaSkeleton, hiddenBones:dict):
    # simplifies down the lookup process to be just a vertex index
    boneWeightMap = []
    vertices = mesh.data.vertices
    vertexGroups = mesh.vertex_groups

    invalidVertices = 0
    for x in range(len(vertices)):
        vertex = vertices[x]
        vertexGroupElements = vertex.groups
        boneWeightMap.append([])
        for vertexGroupElement in vertexGroupElements:
            name = vertexGroups[vertexGroupElement.group].name
            weight = vertexGroupElement.weight

            # max 4 weights per bone
            if len(boneWeightMap[x]) >= 4:
                invalidVertices+=1
                break
            
            if weight < 1/255 or hiddenBones.get(name,True):
                continue

            boneWeightMap[x].append( (name, weight) )

    if invalidVertices!=0:
        PapaExportNotifications.getInstance().addNotification(str(invalidVertices)+" vertices have more than 4 weight links. PA does not support this.")
    invalidVertices=0
    
    # report missing weights
    for x in range(len(boneWeightMap)):
        if len(boneWeightMap[x]) == 0:
            invalidVertices+=1
            bone = skeleton.getBone(0)
            boneWeightMap[x].append( (papaFile.getString(bone.getNameIndex()), 1) ) # add implicit data
    if invalidVertices!=0:
        PapaExportNotifications.getInstance().addNotification(str(invalidVertices)+" vertices have no weight links. All vertices must have at least one weight link.")
    return boneWeightMap

def createPapaModelData(papaFile:PapaFile, mesh, shadingMap, materialMap, boneWeightMap, papaSkeleton:PapaSkeleton, uvMap:dict, vertexData:dict, properties):
    print("Generating Vertex Buffers...")
    polygons = mesh.data.polygons
    vertices = mesh.data.vertices

    vertexList = [] # the PapaVerticies to be compiled
    vertexFaceMap = [] # maps each vertex on each face to it's position in the vertex buffer
    shadingBuckets = [] # each shading region gets a unique bucket (doesn't need to be a map because it's sequential)

    # Given any vertex and a shading region and face, we need to know what the index in the vertex buffer it maps to is
    # i.e. vertexFaceMap[vertexIndex][face] = vertexBufferIndex
    # To accomplish this, we need an intermediate which recognizes the shading regions. This is done by the vertexFaceMap list

    for x in range(len(vertices)):
        vertexFaceMap.append({})

    for x in range(len(shadingMap)):
        shadingBuckets.append({}) # each slot of the bucket maps to a list of tuples (bufferIdx, uv)

    boneNameToIndex = {}
    if papaSkeleton:
        for x in range(papaSkeleton.getNumBones()):
            bone = papaSkeleton.getBone(x)
            boneNameToIndex[papaFile.getString(bone.getNameIndex())] = x

    # build the vertex map
    for poly in polygons:
        for idx in poly.vertices:
            shadingRegion = shadingMap[poly.index]

            # for each vertex, check if it's shading region claims to have the same vertex already
            bucket = shadingBuckets[shadingRegion]
            knownVertices = bucket.get(idx,False)

            if knownVertices:
                # this region claims to have vertex data for this location,
                # however, there is also the possibility of UVs not aligning, so now we need to check if UVs align
                normal = vectorToImmutableMapping(vertexData[0][poly.index][idx])
                uv1 = uvMap[0][poly.index][idx]
                foundVertex = False
                if properties.isCSG(): # respect shadow map as well
                    uv2 = uvMap[1][poly.index][idx]
                    for x in knownVertices:
                        if(x[1] == uv1 and x[2] == uv2 and x[3] == normal): # found a match, select it
                            vertexFaceMap[idx][poly.index] = x[0]
                            foundVertex = True
                            break
                else:
                    for x in knownVertices:
                        if(x[1] == uv1 and x[3] == normal):
                            vertexFaceMap[idx][poly.index] = x[0]
                            foundVertex = True
                            break
                if foundVertex:
                    continue
            
            # if we didn't find a matching UV, or there exists no data for this vertex, make a new vertex and register it
            if properties.isCSG():
                # Position3Normal3Tan3Bin3TexCoord4
                loc = Vector(vertices[idx].co)
                normal = vertexData[0][poly.index][idx]
                tangent = vertexData[1][poly.index][idx]
                binormal = vertexData[2][poly.index][idx]
                texCoord1 = uvMap[0][poly.index][idx]
                texCoord2 = uvMap[1][poly.index][idx]
                v = PapaVertex(pos=loc,norm=normal,binorm=binormal,tan=tangent,texcoord1=texCoord1,texcoord2=texCoord2)
            else:
                loc = Vector(vertices[idx].co)
                weightList = [0] * 4
                boneList = [0] * 4
                if papaSkeleton:
                    # normalize the weights (if they're combined > 1 PA refuses to load them)
                    total = 0
                    for i in range(len(boneWeightMap[idx])):
                        total+=boneWeightMap[idx][i][1]

                    for i in range(len(boneWeightMap[idx])):
                        boneData = boneWeightMap[idx][i]
                        # if the bone is hidden, don't include the data
                        if not boneData[0] in boneNameToIndex:
                            continue
                        boneList[i] = boneNameToIndex[boneData[0]]
                        weightList[i] = round(boneData[1] / total * 255)

                normal = vertexData[0][poly.index][idx]
                texCoord1 = uvMap[0][poly.index][idx]
                texCoord2 = None # required for buckets
                v = PapaVertex(pos=loc, norm=normal, texcoord1=texCoord1, bones=boneList, weights=weightList)
            vertexIndex = len(vertexList)
            vertexFaceMap[idx][poly.index] = vertexIndex
            vertexList.append(v)

            # register in the bucket
            if not bucket.get(idx,False):
                bucket[idx] = []
            bucket[idx].append( (vertexIndex, texCoord1, texCoord2, vectorToImmutableMapping(normal)) )
    vertexFormat = 10 if properties.isCSG() else 8
    vBuffer = PapaVertexBuffer(vertexFormat,vertexList)
    print(vBuffer)


    seenVertices = [False] * len(vertices)
    vertexCount = 0
    print("Generating Index Buffers...")
    # build a lookup from face to triangle
    triangleTable = {}
    for tri in mesh.data.loop_triangles:
        if not triangleTable.get(tri.polygon_index):
            triangleTable[tri.polygon_index] = []
        triangleTable[tri.polygon_index].append(tri)
        for x in range(3):
            if not seenVertices[tri.vertices[x]]:
                seenVertices[tri.vertices[x]] = True
                vertexCount+=1
    
    if vertexCount != len(vertices):
        PapaExportNotifications.getInstance().addNotification("1D geometry on model (loose edge or vertex). "
            + str(len(vertices)-vertexCount)+" unaccounted for vertice(s)")

    materialGroupIndices = [] # map list of tuples
    indices = []
    currentCount = 0


    # now, create the index buffer
    for x in range(len(materialMap)):
        startCount = currentCount
        for polyIndex in materialMap[x]:
            shadingRegion = shadingMap[polyIndex]
            for tri in triangleTable[polyIndex]: # add all the triangulated faces of the ngon into the index buffer
                currentCount += 1 # triangle primitive
                for x in range(3): # 1d geometry will work but will cause weird effects
                    indices.append(vertexFaceMap[tri.vertices[x]][polyIndex])
        materialGroupIndices.append( (startCount, currentCount) )

                

    fmt = 0 if len(indices) < 65536 else 1
    iBuffer = PapaIndexBuffer(fmt, indices)
    print(iBuffer)


    print("Generating Material Groups...")
    # finally, create the material groups
    materialGroups = []
    materialIndex = 0
    for x in range(len(materialMap)): # traverse the material map in order
        materialData = materialGroupIndices[x]
        mat = mesh.material_slots[x]
        nameIndex = papaFile.addString(PapaString(mat.name))
        numPrimitives = materialData[1] - materialData[0]
        startLocation = materialData[0] * 3 
        matGroup = PapaMaterialGroup(nameIndex,materialIndex,startLocation,numPrimitives,PapaMaterialGroup.TRIANGLES)
        print(matGroup)
        materialGroups.append(matGroup)
        materialIndex+=1

    return vBuffer, iBuffer, materialGroups

def getOrMakeTexture(papaFile:PapaFile, textureMap:dict, path: str):
    texIdx = textureMap.get(path, None)
    if texIdx == None:
        nameIndex = papaFile.addString(PapaString(path))
        texture = PapaTexture(nameIndex,0,0,0,0,[]) # write a linked texture
        texIdx = papaFile.addTexture(texture)
        textureMap[path] = texIdx
    return texIdx

def createPapaMaterials(papaFile:PapaFile, mesh, properties):
    print("Generating Materials...")
    materials = []
    if properties.isCSG(): #
        if(len(mesh.material_slots) == 0):
            raise PapaBuildException("No materials present on CSG")

        shaderLevel = 0 # textured
        diffuseStringIndex = papaFile.addString(PapaString("DiffuseTexture"))
        if "normal" in properties.getShader():
            shaderLevel+=1 # textured_normal
            normalStringIndex = papaFile.addString(PapaString("NormalTexture"))
        if "material" in properties.getShader():
            shaderLevel+=1 # textured_normal_material
            materialStringIndex = papaFile.addString(PapaString("MaterialTexture"))
        
        shaderNameIndex = papaFile.addString(PapaString(properties.getShader()))

        textureMap = {} # maps the path to a texture index
        for x in range(len(mesh.material_slots)):
            material = mesh.material_slots[x]
            exportMaterial = properties.getMaterialForName(material.name)
            textureParams = []
            if shaderLevel >= 0: # diffuse
                texIdx = getOrMakeTexture(papaFile, textureMap, exportMaterial.getTexturePath())
                textureParams.append(PapaTextureParameter(diffuseStringIndex,texIdx))
            if shaderLevel >= 1: # normal
                texIdx = getOrMakeTexture(papaFile, textureMap, exportMaterial.getNormalPath())
                textureParams.append(PapaTextureParameter(normalStringIndex,texIdx))
            if shaderLevel >= 2: # material
                texIdx = getOrMakeTexture(papaFile, textureMap, exportMaterial.getMaterialPath())
                textureParams.append(PapaTextureParameter(materialStringIndex,texIdx))
            mat = PapaMaterial(shaderNameIndex,[],textureParams,[])
            print(mat)
            materials.append(mat)
    else:
        nameIndex = papaFile.addString(PapaString("solid"))

        if(len(mesh.material_slots) == 0): # guarantee at least one material, doesn't matter for units
            mesh.data.materials.append(bpy.data.materials.new(name=mesh.name+"_implicit"))
            PapaExportNotifications.getInstance().addNotification({"INFO"},"No materials on object \""+mesh.name+"\". New material generated: "+mesh.name+"_implicit")

        for _ in mesh.material_slots:
            mat = PapaMaterial(nameIndex,[PapaVectorParameter(papaFile.addString(PapaString("DiffuseColor")),Vector([0.5,0.5,0.5,0]))],[],[])
            print(mat)
            materials.append(mat)
    return materials

def isDefaultRotation(quat):
    # (1,0,0,0)
    epsilon = 0.0001
    return abs(quat[0]-1) < epsilon and abs(quat[1]) < epsilon and abs(quat[2]) < epsilon and abs(quat[3]) < epsilon

# gets the parent bone, hide aware
def editBoneParent(properties, editBone):
    if not properties.isIgnoreHidden():
        return editBone.parent
    while editBone.parent:
        editBone = editBone.parent
        if not editBone.hide:
            return editBone
    return None

def createSkeleton(papaFile: PapaFile, mesh, properties):
    lastMode = bpy.context.object.mode
    
    armature = None

    for modifier in mesh.modifiers:
        if modifier.type == "ARMATURE":
            armature = modifier.object
            break
    if armature == None:
        return None, None

    selectObject(armature)
    bpy.ops.object.mode_set(mode='EDIT')

    print("Generating Skeletons...")

    if PapaExportCache.getInstance().getSkeleton(armature):
        print("Found skeleton in cache.")
        return PapaExportCache.getInstance().getSkeleton(armature)

    boneList = []
    boneMap = {}
    hiddenBones = {}
    numRootBones = 0
    for bone in armature.data.edit_bones:
        hiddenBones[bone.name] = False
        # ignore hidden bones. Mostly for IK animation
        if properties.isIgnoreHidden() and bone.hide:
            hiddenBones[bone.name] = True
            continue

        mat = bone.matrix
        if editBoneParent(properties, bone):
            loc, q, _ = (editBoneParent(properties, bone).matrix.inverted() @ mat).decompose()
        else:
            loc, q, _ = mat.decompose()
            numRootBones+=1
            if numRootBones != 1:
                PapaExportNotifications.getInstance().addNotification("Skeleton \""+armature.name+"\" has more than one root bone. ("+bone.name+" has no parent)")
            if not isDefaultRotation(q):
                PapaExportNotifications.getInstance().addNotification("Root bone ("+bone.name+") is not rotated -90 degrees on x axis from bind pose.")
        rot = Quaternion((q[1],q[2],q[3],q[0]))

        
        papaBone = PapaBone(papaFile.addString(PapaString(bone.name)),-1,loc,rot,Matrix(),mat.inverted())

        boneMap[bone.name] = len(boneList)
        boneList.append(papaBone)

    if len(boneList) > 32:
        PapaExportNotifications.getInstance().addNotification("Skeleton \""+armature.name+"\" exceeds maximum bone count. ("+str(len(boneList))+" > 32)")
    
    # map parents
    for bone in boneList:
        editBone = armature.data.edit_bones[papaFile.getString(bone.getNameIndex())]
        if not editBoneParent(properties, editBone) or (properties.isIgnoreHidden() and editBone.hide):
            continue

        parentIndex = boneMap[editBoneParent(properties, editBone).name]
        bone.setParentIndex(parentIndex)

    bpy.ops.object.mode_set(mode=lastMode)
    skeleton = PapaSkeleton(boneList)
    PapaExportCache.getInstance().addSkeleton(armature, (skeleton, hiddenBones))
    print(skeleton)
    return skeleton, hiddenBones


def computeUVData(mesh, properties):
    uvMap = {}
    uvMap[0] = {} # main UV
    uvMap[1] = {} # shadow map
    hasUV1 = len(mesh.data.uv_layers) > 0
    hasUV2 = len(mesh.data.uv_layers) > 1

    uv0 = None if not hasUV1 else mesh.data.uv_layers[0].data
    uv1 = None if not hasUV2 else mesh.data.uv_layers[1].data

    if not hasUV1:
        raise PapaBuildException("Model is missing UV data.")

    if properties.isCSG():
        if not hasUV2:
            raise PapaBuildException("CSG requires two UV maps. The first UV map is the texture UV map while the second is the shadow map.")
        for poly in mesh.data.polygons:
            shadowMapUV = {}
            textureMapUV = {}
            uvMap[0][poly.index] = textureMapUV
            uvMap[1][poly.index] = shadowMapUV
            for vIdx, loopIdx in zip(poly.vertices, poly.loop_indices):
                # referencing the data causes weirdness, copy it directly
                textureMapUV[vIdx] = (uv0[loopIdx].uv[0], uv0[loopIdx].uv[1])
                shadowMapUV[vIdx] = (uv1[loopIdx].uv[0], uv1[loopIdx].uv[1])
    else:
        for poly in mesh.data.polygons:
            textureMapUV = {}
            uvMap[0][poly.index] = textureMapUV
            for vIdx, loopIdx in zip(poly.vertices, poly.loop_indices):
                textureMapUV[vIdx] = (uv0[loopIdx].uv[0], uv0[loopIdx].uv[1])
    
    return uvMap

def computeVertexData(mesh, connectionMap, angleMap, properties):
    # calculate the normal of each vertex in the mesh. if the face is flat shaded, the normal is the same as the
    # polygon. If it is flat shaded, the normal is the average of all similar shaded touching faces' normals
    polygons = mesh.data.polygons
    vertices = mesh.data.vertices
    loops = mesh.data.loops

    # build a vertex -> face map
    vertexFaceMap = {} # [vertex] -> all faces

    for vertex in vertices:
        vertexFaceMap[vertex.index] = []

    for poly in polygons:
        for idx in poly.vertices:
            vertexFaceMap[idx].append(poly)

    # build the normal data
    vertexData = {}
    vertexData[0] = {} # normal
    vertexData[1] = {} # tangent
    vertexData[2] = {} # binormal

    for poly in polygons:
        nMap = {}
        vertexData[0][poly.index] = nMap
        for idx in poly.vertices:
            if not poly.use_smooth: 
                nMap[idx] = Vector(poly.normal)
            elif properties.isRespectMarkSharp():
                normal = Vector([0,0,0])
                for faceIdx in connectionMap[poly.index][idx]: # use the connection map to build a normal (respects sharp)
                    normal+=Vector(polygons[faceIdx].normal) * angleMap[faceIdx][idx]
                nMap[idx] = normal.normalized()
            else:
                nMap[idx] = Vector(vertices[idx].normal)
    if properties.isCSG():
        # calculate the tangents and bitangents
        
        # https://blender.stackexchange.com/questions/26116/script-access-to-tangent-and-bitangent-per-face-how
        for poly in polygons:
            tMap = {}
            bMap = {}
            vertexData[1][poly.index] = tMap
            vertexData[2][poly.index] = bMap
            
            for loopIndex in poly.loop_indices:
                loop = loops[loopIndex]
                idx = loop.vertex_index
                # convert to tuples so the data stays after we free it
                tMap[idx] = (loop.tangent[0], loop.tangent[1], loop.tangent[2])
                bMap[idx] = (loop.bitangent[0], loop.bitangent[1], loop.bitangent[2])

    return vertexData

def writeMesh(mesh, properties, papaFile: PapaFile):
    selectObject(mesh)
    lastMode = bpy.context.object.mode
    bpy.ops.object.mode_set(mode='OBJECT') # must be in object mode to get UV data

    # set up data
    print("Preparing Data...")

    # shadingMap[polygonIndex] -> shading index, connectionMap[polygonIndex][vertex] -> all connected faces (inclues the input face, aware of mark sharp)
    # note the connection map is not necessarily the faces that are literally connected in the model, it is the faces that should be connected
    shadingMap, connectionMap, angleMap = createFaceShadingIslands(mesh, properties) 
    materialMap = createFaceMaterialIslands(mesh) # materialIndex -> list of polygons that use that material

    uvMap = computeUVData(mesh, properties) # [mapIndex (0 for main UV, 1 for shadow map)][face][vertex] -> UV coord

    bpy.ops.object.mode_set(mode='EDIT') # swap to edit to get the triangles and normals
    mesh.data.calc_loop_triangles()
    mesh.data.calc_normals_split()

    if properties.isCSG():
        mapName = mesh.data.uv_layers[0].name # use texture UV map
        mesh.data.calc_tangents(uvmap=mapName)

    vertexData = computeVertexData(mesh, connectionMap, angleMap, properties) # [normal=0, tangent=1, binormal=2][face][vertex] -> normal direction

    papaSkeleton, hiddenBones = createSkeleton(papaFile, mesh, properties)
    # map each vertex index to a list of tupes (bone_name: str, bone_weight: float)
    boneWeightMap = {} if papaSkeleton == None else createBoneWeightMap(mesh, papaFile, papaSkeleton, hiddenBones)
    skeletonIndex = -1
    if papaSkeleton:
        skeletonIndex = papaFile.addSkeleton(papaSkeleton)

    # create the list of materials
    # the traversal of all materials is always guaranteed to be the same order as in blender
    # i.e. the 4th material and the 4th material group both map to the 4th Blender Material
    papaMaterials = createPapaMaterials(papaFile, mesh, properties)
    for mat in papaMaterials:
        papaFile.addMaterial(mat)

    # create the vertex buffer, index buffer, and material
    vBuffer, iBuffer, materialGroups = createPapaModelData(papaFile, mesh, shadingMap, materialMap, boneWeightMap, papaSkeleton, uvMap, vertexData, properties)

    vBufferIndex = papaFile.addVertexBuffer(vBuffer)
    iBufferIndex = papaFile.addIndexBuffer(iBuffer)

    # create the mesh
    print("Generating Meshes...")
    papaMesh = PapaMesh(vBufferIndex, iBufferIndex, materialGroups)
    print(papaMesh)
    meshIndex = papaFile.addMesh(papaMesh)

    # generate the mesh binding
    boneMap = []
    if papaSkeleton:
        for x in range(papaSkeleton.getNumBones()):
            boneMap.append(x)
    
    nameIndex = papaFile.addString(PapaString(mesh.name))
    print("Generating Mesh Bindings...")
    meshBinding = PapaMeshBinding(nameIndex,meshIndex,Matrix(),boneMap)
    print(meshBinding)
    papaMeshBindings = [meshBinding]

    print("Generating Models...")
    papaModel = PapaModel(nameIndex,skeletonIndex,mesh.matrix_world,papaMeshBindings)
    print(papaModel)
    papaFile.addModel(papaModel)

    # set the mode back
    selectObject(mesh)
    bpy.ops.object.mode_set(mode=lastMode)

    if properties.isCSG():
        mesh.data.free_tangents()


def processBone(poseBone, animation, properties):
    # this is an inverted form of processBone in import_papa.
    # The code does all the operations in reverse to turn the blender formatted data back into PA formatted data
    animBone = animation.getAnimationBone(poseBone.name)
    bone = poseBone.bone
    parent = poseBoneParent(properties, poseBone)
    
    if parent:
        parent = parent.bone
        commonMatrix = bone.matrix_local.inverted() @ parent.matrix_local
        _,cr,_ = (parent.matrix_local.inverted() @ bone.matrix_local).decompose()
        locationCorrectionMatrix = cr.to_matrix().to_4x4()

        for x in range(animation.getNumFrames()): # both rotation and translation processed here.
            
            l = animBone.getTranslation(x)
            r = animBone.getRotation(x)

            matrix = commonMatrix.inverted() @ locationCorrectionMatrix.inverted() @ Matrix.Translation(l)
            loc, _, _ = matrix.decompose()
            animBone.setTranslation(x,loc)

            matrix = commonMatrix.inverted() @ r.to_matrix().to_4x4()
            _, q, _ = matrix.decompose()
            cr = Quaternion((q[1],q[2],q[3],q[0]))
            animBone.setRotation(x,cr)
    else:
        for x in range(animation.getNumFrames()):
            # positions are already in global space.
            l = animBone.getTranslation(x)
            r = animBone.getRotation(x)

            cl, cr, _ = (bone.matrix_local @ Matrix.Translation(l) @ r.to_matrix().to_4x4()).decompose()
            cr = Quaternion((cr[1],cr[2],cr[3],cr[0]))

            animBone.setTranslation(x,cl)
            animBone.setRotation(x,cr)

def hasTransforms(animationBone:AnimationBone, frames:int):
    if frames == 0:
        return False
    bl = animationBone.getTranslation(0)
    br = animationBone.getRotation(0)
    epsilon = 0.0001
    if abs(bl[0]) > epsilon or abs(bl[1]) > epsilon or abs(bl[2]) > epsilon:
        return True
    if abs(br[0]-1) > epsilon or abs(br[1]) > epsilon or abs(br[2]) > epsilon or abs(br[3]) > epsilon:
        return True
    for i in range(1,frames):
        l = animationBone.getTranslation(i)
        r = animationBone.getRotation(i)
        if abs(bl[0]-l[0]) > epsilon or abs(bl[1]-l[1]) > epsilon or abs(bl[2]-l[2]) > epsilon:
            return True
        if abs(br[0]-r[0]) > epsilon or abs(br[1]-r[1]) > epsilon or abs(br[2]-r[2]) > epsilon or abs(br[3]-r[3]) > epsilon:
            return True

def poseBoneParent(properties, poseBone):
    if not properties.isIgnoreHidden():
        return poseBone.parent
    while poseBone.parent:
        poseBone = poseBone.parent
        if not poseBone.bone.hide:
            return poseBone
    return None        

def writeAnimation(armature, properties, papaFile: PapaFile):

    selectObject(armature)
    lastMode = bpy.context.object.mode
    bpy.ops.object.mode_set(mode='EDIT')

    # now, create the animation
    print("Generating Animations...")
    numFrames = bpy.context.scene.frame_end - bpy.context.scene.frame_start + 1
    animationSpeed = round(bpy.context.scene.render.fps)
    savedStartFrame = bpy.context.scene.frame_current

    # create the animation bones
    animationBones = []
    animationBoneMap = {}
    for bone in armature.pose.bones:
        if properties.isIgnoreHidden() and bone.bone.hide:
            continue
        b = AnimationBone(-1,bone.name,[None] * numFrames, [None] * numFrames)
        animationBones.append(b)
        animationBoneMap[bone] = b

    # load the transformations
    bpy.ops.object.mode_set(mode='POSE')
    for frame in range(numFrames):
        bpy.context.scene.frame_set(bpy.context.scene.frame_start + frame)
        for bone in armature.pose.bones:
            if properties.isIgnoreHidden() and bone.bone.hide:
                continue
            animationBone = animationBoneMap[bone]

            if properties.isIgnoreRoot() and not poseBoneParent(properties, bone):
                matrix = armature.convert_space(pose_bone=bone, matrix=bone.bone.matrix_local, from_space='POSE',to_space='LOCAL')
            else:    
                # convert the matrix back into local space for compilation
                matrix = armature.convert_space(pose_bone=bone, matrix=bone.matrix, from_space='POSE',to_space='LOCAL')
            
            loc, rot, _ = matrix.decompose()
            animationBone.setTranslation(frame, loc)
            animationBone.setRotation(frame, rot)

    if properties.isIgnoreNoData():
        newList = []
        for bone in animationBones:
            if hasTransforms(bone,numFrames):
                newList.append(bone)
                bone.setNameIndex(papaFile.addString(PapaString(bone.getName())))
            else:
                print("\""+bone.getName()+"\" has no data. Skipping...")

        animationBones = newList


    # create and put an animation into the file
    animation = PapaAnimation(-1, len(animationBones),numFrames,animationSpeed,1,animationBones)
    print(animation)
    papaFile.addAnimation(animation)

    # check for possible errors
    numRootBones = 0
    for bone in armature.pose.bones:
        if properties.isIgnoreHidden() and bone.bone.hide:
                continue
        if not poseBoneParent(properties, bone):
            numRootBones+=1
            if numRootBones != 1:
                PapaExportNotifications.getInstance().addNotification("Exported animation has more than one root bone. ("+bone.name+" has no parent)")
    
    # correct the transformations from blender data into PA data
    for bone in armature.pose.bones:
        if animation.getAnimationBone(bone.name) != None:
            processBone(bone, animation, properties)

    # put the header back
    bpy.context.scene.frame_current = savedStartFrame

    # set the mode back
    bpy.ops.object.mode_set(mode=lastMode)

def write(operator,context,properties):
    t = time.time()
    result = write_papa(properties, context, operator)
    t = time.time() - t
    print("Done in "+str(int(t*1000)) + "ms")
    if result:
        operator.report({result[0]}, result[1])
        return {'CANCELLED'}
    if not operator.has_reports:
        operator.report({"INFO"},"Done in "+str(int(t*1000)) + "ms")
    return {'FINISHED'}

