# The MIT License
# 
# Copyright (c) 2013, 2014  Raevn
# Copyright (c) 2021, 2022  Marcus Der      marcusder@hotmail.com
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
from bpy_extras import mesh_utils;
from mathutils import Vector
from bpy.props import *
from math import pi, radians, log2, ceil, floor
from array import array
from os import path
import ctypes

TEX_SIZE_INT = "__PAPA_IO_TEXTURE_SIZE"
OBJ_NAME_STRING = "__PAPA_IO_MESH_NAME"
OBJ_TYPE_STRING = "__PAPA_IO_MESH_TYPE"
TEX_NAME_STRING = "__PAPA_IO_TEXTURE_NAME"
TEX_SHOULD_BAKE = "__PAPA_IO_TEXTURE_BAKE"
TEX_SHOULD_SUPERSAMPLE = "__PAPA_IO_TEXTURE_SUPERSAMPLE"
EDGE_HIGHLIGHT_TEXTURE = "__PAPA_IO_EDGE_HIGHLIGHTS"
EDGE_HIGHLIGHT_DILATE = "__PAPA_IO_EDGE_HIGHLIGHTS_DILATE"
EDGE_HIGHLIGHT_BLUR = "__PAPA_IO_EDGE_HIGHLIGHTS_BLUR"
EDGE_HIGHLIGHT_MULTIPLIER = "__PAPA_IO_EDGE_HIGHLIGHTS_MULTIPLIER"
DISTANCE_FIELD_TEXTURE = "__PAPA_IO_DISTANCE_FIELD"
DISTANCE_FIELD_MATERIAL = "__PAPA_IO_DISTANCE_FIELD_MATERIAL"
DISTANCE_FIELD_TEXEL_INFO = "__PAPA_IO_DISTANCE_FIELD_TEXEL_INFO"

class OBJ_TYPES:
    DIFFUSE = "DIFFUSE"
    MATERIAL = "MATERIAL"
    MASK = "MASK"
    AO = "AO"
    EDGE_HIGHLIGHT = "EDGE_HIGHLIGHT"
    DISTANCE_FIELD = "DISTANCE_FIELD"

def selectObject(obj):
    for i in bpy.context.selected_objects: 
        i.select_set(False) #deselect all objects
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj

def duplicateObject(obj, newName, prepend = True):
    n = obj.copy()
    n.data = obj.data.copy()
    n.name = newName
    if prepend:
        if not OBJ_NAME_STRING in obj:
            print("Warning: Duplicated object target has no name string")
        else:
            n.name = obj[OBJ_NAME_STRING] + "_" + n.name
    for prop in dict(n):
        if str(prop).startswith("__PAPA_IO_"):
            del n[str(prop)]
    return n

def getObjectType(obj):
    if not OBJ_TYPE_STRING in obj:
        return ""
    return obj[OBJ_TYPE_STRING]

# https://blender.stackexchange.com/a/158902
def srgbToLinearRGB(c):
    if   c < 0:       return 0
    elif c < 0.04045: return c/12.92
    else:             return ((c+0.055)/1.055)**2.4

def createMaterial(name: str, colour: tuple, blenderImage, attach=False):
    try:
        return bpy.data.materials[name]
    except:
        pass
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = tuple([srgbToLinearRGB(c/0xff) for c in colour] + [1])
    if blenderImage == None:
        return mat
    tex = mat.node_tree.nodes.new("ShaderNodeTexImage")
    tex.image = blenderImage
    tex.location[0] = -300
    tex.location[1] = 200
    tex.select = True
    if attach:
        mat.node_tree.links.new(bsdf.inputs["Base Color"], tex.outputs["Color"])
    return mat

def createHazardStripesMaterial(name: str, colour1: tuple, colour2:tuple, blenderImage, invert=False):
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    out = mat.node_tree.nodes["Material Output"]
    bsdf1 = mat.node_tree.nodes["Principled BSDF"]
    bsdf1.inputs["Base Color"].default_value = tuple([srgbToLinearRGB(c/0xff) for c in colour1] + [1])

    bsdf2 = mat.node_tree.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf2.inputs["Base Color"].default_value = tuple([srgbToLinearRGB(c/0xff) for c in colour2] + [1])

    mix = mat.node_tree.nodes.new("ShaderNodeMixShader")

    geometry = mat.node_tree.nodes.new("ShaderNodeNewGeometry")

    separate = mat.node_tree.nodes.new("ShaderNodeSeparateXYZ")

    mathAdd1 = mat.node_tree.nodes.new("ShaderNodeMath")
    mathAdd2 = mat.node_tree.nodes.new("ShaderNodeMath")
    if invert:
        mathAdd1.operation = "SUBTRACT"
        mathAdd2.operation = "SUBTRACT"
    mathAdd3 = mat.node_tree.nodes.new("ShaderNodeMath")

    mathInput = mat.node_tree.nodes.new("ShaderNodeMath")
    mathInput.inputs[0].default_value = 0
    mathInput.inputs[1].default_value = 2
    mathInput.location[0] = -300
    mathInput.location[1] = 500

    mathMod = mat.node_tree.nodes.new("ShaderNodeMath")
    mathMod.operation = "MODULO"
    mathDiv = mat.node_tree.nodes.new("ShaderNodeMath")
    mathDiv.operation = "DIVIDE"
    mathRound = mat.node_tree.nodes.new("ShaderNodeMath")
    mathRound.operation = "ROUND"

    mat.node_tree.links.new(separate.inputs["Vector"], geometry.outputs["Position"])

    # add1
    mat.node_tree.links.new(mathAdd1.inputs[0], separate.outputs["X"])
    mat.node_tree.links.new(mathAdd1.inputs[1], separate.outputs["Y"])

    # add2
    mat.node_tree.links.new(mathAdd2.inputs[0], mathAdd1.outputs["Value"])
    mat.node_tree.links.new(mathAdd2.inputs[1], separate.outputs["Z"])

    # add3
    mat.node_tree.links.new(mathAdd3.inputs[0], mathAdd2.outputs["Value"])
    mathAdd3.inputs[1].default_value=10000 # make sure our number is positive

    # modulo
    mat.node_tree.links.new(mathMod.inputs[0], mathAdd3.outputs["Value"])
    mat.node_tree.links.new(mathMod.inputs[1], mathInput.outputs["Value"])
    
    # divide
    mat.node_tree.links.new(mathDiv.inputs[0], mathMod.outputs["Value"])
    mat.node_tree.links.new(mathDiv.inputs[1], mathInput.outputs["Value"])

    # round
    mat.node_tree.links.new(mathRound.inputs[0], mathDiv.outputs["Value"])

    #combine into mix
    mat.node_tree.links.new(mix.inputs[0], mathRound.outputs["Value"])
    mat.node_tree.links.new(mix.inputs[1], bsdf1.outputs[0])
    mat.node_tree.links.new(mix.inputs[2], bsdf2.outputs[0])

    mat.node_tree.links.new(out.inputs["Surface"], mix.outputs[0])

    tex = mat.node_tree.nodes.new("ShaderNodeTexImage")
    tex.image = blenderImage
    tex.location[0] = -300
    tex.location[1] = 200
    tex.select = True
    return mat

def createEdgeHightlightMaterial(name:str, diffuseObj, aoObj, blenderImage):
    diffuse = None
    ao = None
    if diffuseObj:
        diffuse = getOrCreateImage(diffuseObj[TEX_NAME_STRING])
    if aoObj:
        ao = getOrCreateImage(aoObj[TEX_NAME_STRING])
    
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]

    edgeTex = mat.node_tree.nodes.new("ShaderNodeTexImage")
    edgeTex.image = blenderImage
    edgeTex.location[0] = -300
    edgeTex.location[1] = 200

    if diffuse:
        diffuseTex = mat.node_tree.nodes.new("ShaderNodeTexImage")
        diffuseTex.image = diffuse

        mixRGB1 = mat.node_tree.nodes.new("ShaderNodeMixRGB")
        mixRGB1.blend_type = 'OVERLAY'

        # overlay the edge highlights on the diffuse
        mat.node_tree.links.new(mixRGB1.inputs["Color1"], diffuseTex.outputs["Color"])
        mat.node_tree.links.new(mixRGB1.inputs["Color2"], edgeTex.outputs["Color"])
        mat.node_tree.links.new(mixRGB1.inputs["Fac"], edgeTex.outputs["Alpha"])
        mat.node_tree.links.new(bsdf.inputs["Base Color"], mixRGB1.outputs["Color"])

        if ao:
            aoTex = mat.node_tree.nodes.new("ShaderNodeTexImage")
            aoTex.image = ao

            mixRGB2 = mat.node_tree.nodes.new("ShaderNodeMixRGB")
            mixRGB2.blend_type = 'MULTIPLY'
            mixRGB2.inputs['Fac'].default_value = 1

            # mix ao and diffuse
            mat.node_tree.links.new(mixRGB2.inputs["Color1"], diffuseTex.outputs["Color"])
            mat.node_tree.links.new(mixRGB2.inputs["Color2"], aoTex.outputs["Color"])
            mat.node_tree.links.new(mixRGB1.inputs["Color1"], mixRGB2.outputs["Color"]) # link this as "diffuse"
    else:
        mat.node_tree.links.new(bsdf.inputs["Base Color"], edgeTex.outputs["Color"])
    
    return mat

def createDistanceFieldMaterial(name:str, blenderImage):

    mat = bpy.data.materials.new(name=name)
    mat.blend_method = "CLIP"
    mat.alpha_threshold= 0.5
    mat.use_backface_culling = True
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]

    edgeTex = mat.node_tree.nodes.new("ShaderNodeTexImage")
    edgeTex.image = blenderImage
    edgeTex.location[0] = -1150
    edgeTex.location[1] = 0

    cameraData = mat.node_tree.nodes.new("ShaderNodeCameraData")
    cameraData.location[0] = -800
    cameraData.location[1] = 200

    mathDiv = mat.node_tree.nodes.new("ShaderNodeMath")
    mathDiv.operation = "DIVIDE"
    mathDiv.inputs[1].default_value = 1200
    mathDiv.location[0] = -600
    mathDiv.location[1] = 250
    mat.node_tree.links.new(mathDiv.inputs[0],cameraData.outputs["View Z Depth"])

    mathMax = mat.node_tree.nodes.new("ShaderNodeMath")
    mathMax.operation = "MAXIMUM"
    mathMax.inputs[1].default_value = 0.25
    mathMax.location[0] = -400
    mathMax.location[1] = 250
    mat.node_tree.links.new(mathMax.inputs[0],mathDiv.outputs["Value"])

    mathSub = mat.node_tree.nodes.new("ShaderNodeMath")
    mathSub.operation = "SUBTRACT"
    mathSub.inputs[0].default_value = 0.9864
    mathSub.location[0] = -800
    mathSub.location[1] = 50
    mat.node_tree.links.new(mathSub.inputs[1],edgeTex.outputs["Color"])

    mathMul = mat.node_tree.nodes.new("ShaderNodeMath")
    mathMul.label = "TEMP_texelinfo"
    mathMul.operation = "MULTIPLY"
    mathMul.location[0] = -600
    mathMul.location[1] = 50
    mat.node_tree.links.new(mathMul.inputs[0],mathSub.outputs["Value"])

    mathMul2 = mat.node_tree.nodes.new("ShaderNodeMath")
    mathMul2.operation = "MULTIPLY"
    mathMul2.inputs[1].default_value = 0.25 # don't question it, this is a copy of the PA shader
    mathMul2.location[0] = -400
    mathMul2.location[1] = 50
    mat.node_tree.links.new(mathMul2.inputs[0],mathMul.outputs["Value"])

    mathCmp = mat.node_tree.nodes.new("ShaderNodeMath")
    mathCmp.operation = "LESS_THAN"
    mathCmp.location[0] = -200
    mathCmp.location[1] = 150
    mat.node_tree.links.new(mathCmp.inputs[0],mathMul2.outputs["Value"])
    mat.node_tree.links.new(mathCmp.inputs[1],mathMax.outputs["Value"])


    mat.node_tree.links.new(bsdf.inputs["Alpha"], mathCmp.outputs["Value"])
    bsdf.inputs["Base Color"].default_value = (1,1,1,1)
    
    return mat
        
def getOrCreateImage(imageName, size=-1):
    try:
        img = bpy.data.images[imageName]
        if size!=-1 and img.size != size**2:
            img.scale(size, size)
        return img
    except:
        if size==-1:
            raise
        img = bpy.data.images.new(imageName, size, size,alpha=True)
        img.pack() # by packing the data, we can edit the colour space name
        return img

def createFaceMapping(fromMesh, toMesh, hashFactor=50): # polyIdx -> polyIdx
    fromData = []
    toData = []
    spatialHashmap = {}

    selectObject(fromMesh)

    # set up hashmap
    for x in range(-1, hashFactor + 1):
        for y in range(-1, hashFactor + 1):
            for z in range(-1, hashFactor + 1):
                spatialHashmap[(x,y,z)] = set()

    rangeX = toMesh.dimensions.x / hashFactor
    rangeY = toMesh.dimensions.y / hashFactor
    rangeZ = toMesh.dimensions.z / hashFactor

    startX = 1<<32 - 1
    startY = 1<<32 - 1
    startZ = 1<<32 - 1

    for vertex in toMesh.data.vertices:
        startX = min(startX, vertex.co.x)
        startY = min(startY, vertex.co.y)
        startZ = min(startZ, vertex.co.z)
    
    def hashIndices(startX, startY, startZ, rangeX, rangeY, rangeZ, vertices, off=0):
        maxX = vertices[0].x
        maxY = vertices[0].y
        maxZ = vertices[0].z
        minX = maxX
        minY = maxY
        minZ = maxZ
        for x in range(1, len(vertices)):
            v = vertices[x]
            maxX = max(maxX, v.x)
            maxY = max(maxY, v.y)
            maxZ = max(maxZ, v.z)
            minX = min(minX, v.x)
            minY = min(minY, v.y)
            minZ = min(minZ, v.z)
        
        maxX = ceil(((maxX - startX) / rangeX) + off)
        maxY = ceil(((maxY - startY) / rangeY) + off)
        maxZ = ceil(((maxZ - startZ) / rangeZ) + off)
        minX = floor(((minX - startX) / rangeX) - off)
        minY = floor(((minY - startY) / rangeY) - off)
        minZ = floor(((minZ - startZ) / rangeZ) - off)

        indices = []
        for x in range(minX, maxX):
            for y in range(minY, maxY):
                for z in range(minZ, maxZ):
                    indices.append( (x,y,z) )

        return indices
    
    def distance(dataBlock1, dataBlock2, angleFactor=1):
        dist = dataBlock1[0].angle(dataBlock2[0], 90) * angleFactor
        sameVertices = 0
        epsilon = 0.01
        sameAxis = 0
        for v1 in dataBlock1[1]:
            minDist = 1<<32 - 1
            for x in range(len(dataBlock2[1])):
                v = v1 - dataBlock2[1][x]
                ls = v.length_squared
                if ls < minDist:
                    minDist = ls
                    sameAxis = sum( [abs(x) < epsilon for x in v.xyz] )

            dist+=minDist
            if minDist <= epsilon:
                sameVertices+=1
        
        return dist, sameVertices, sameAxis

    # setup fromMesh
    fromVertices = fromMesh.data.vertices
    fromLoops = fromMesh.data.loops

    for poly in fromMesh.data.polygons:
        dataVertices = []
        for loopIdx in poly.loop_indices:
            dataVertices.append(Vector(fromVertices[fromLoops[loopIdx].vertex_index].co))
        fromData.append( (Vector(poly.normal), dataVertices) )


    # setup toMesh
    selectObject(toMesh)
    toVertices = toMesh.data.vertices
    toLoops = toMesh.data.loops

    for poly in toMesh.data.polygons:
        dataVertices = []
        for loopIdx in poly.loop_indices:
            dataVertices.append(Vector(toVertices[toLoops[loopIdx].vertex_index].co))

        dataBlock = (Vector(poly.normal), dataVertices)

        toData.append(dataBlock)

        for index in hashIndices(startX, startY, startZ, rangeX, rangeY, rangeZ, dataVertices):
            spatialHashmap[index].add(poly.index)
    
    # build the mapping

    mapping = []
    allIndices = list(range(len(toData)))

    for fromPolyData in fromData:

        candidateIndices = set()
        candidateIndicesList = []
        candidates = []
        
        for index in hashIndices(startX, startY, startZ, rangeX, rangeY, rangeZ, fromPolyData[1], 0.25):
            candidateIndices = candidateIndices.union(spatialHashmap.get(index, set()))

        for index in candidateIndices:
            candidates.append(toData[index])
            candidateIndicesList.append(index)
        
        if len(candidates) == 0:
            candidates = toData
            candidateIndicesList = allIndices

        minDist, bestSame, bestAxis = distance(fromPolyData, candidates[0])
        bestMatch = candidateIndicesList[0]
        
        for x in range(1, len(candidates)):
            toPolyData = candidates[x]
            dist, sameVertices, sameAxis = distance(fromPolyData, toPolyData)
            # if a face shares more verticies, then it clearly should map back to that face even if dist is larger
            if (dist < minDist and sameVertices >= bestSame and sameAxis >= bestAxis) or sameVertices > bestSame:
                minDist = dist
                bestMatch = candidateIndicesList[x]
                bestSame = sameVertices
                bestAxis = sameAxis
                if len(fromPolyData[1]) == sameVertices: # all are the same
                    break
        mapping.append(bestMatch)

    return mapping

class SetupTextureInitial(bpy.types.Operator):
    """Copies a mesh and creates only the diffuse details of it"""
    bl_idname = "setup_diffuse.papa_utils"
    bl_label = "PAPA Setup Texture Initial"
    bl_options = {'UNDO'}

    size: StringProperty(name="Texture Size",description="The size of the texture to use.",subtype="NONE",default="512")
    extras: BoolProperty(name="Add Extra Shaders",description="Adds extra shaders to the mesh",default=False)
    
    def execute(self, context):
        obj = bpy.context.active_object
        if not obj:
            self.report({'ERROR'},"No Object given")
            return {'CANCELLED'}

        texSize = int(self.size)
        obj[TEX_SIZE_INT] = texSize
        obj[OBJ_NAME_STRING] = obj.name.lower()
        self.setupObject(obj, texSize)

        return {'FINISHED'}
    
    def invoke(self, context, event):
        wm = context.window_manager
        return wm.invoke_props_dialog(self)

    def setupObject(self, obj, texSize):
        loc,rot,sca = obj.matrix_world.decompose()

        epsilon = 0.0001
        if sca[0] != 1 or sca[1] != 1 or sca[2] != 1:
            self.report({'ERROR'},obj.name +" has a scale transform! Make sure that yor UV was unwrapped with this transform applied")
        if abs(rot[0]-1) > epsilon or abs(rot[1]) > epsilon or abs(rot[2]) > epsilon or abs(rot[3]) > epsilon:
            self.report({'ERROR'},obj.name +" has a rotation transform. Use of non applied transformations is discouraged.")
        if abs(loc[0]) > epsilon or abs(loc[1]) > epsilon or abs(loc[2]) > epsilon:
            self.report({'ERROR'},obj.name +" has a location transform. Use of non applied transformations is discouraged.")

        texname = obj[OBJ_NAME_STRING]+"_diffuse_bake"
        diffuseTex = getOrCreateImage(obj[OBJ_NAME_STRING]+"_diffuse_bake",texSize)
        diffuse = duplicateObject(obj, OBJ_TYPES.DIFFUSE.lower())
        diffuse.data.materials.clear()
        diffuse.location[0]+=diffuse.dimensions.x * 2
        diffuse[OBJ_NAME_STRING] = obj[OBJ_NAME_STRING]
        diffuse[OBJ_TYPE_STRING] = OBJ_TYPES.DIFFUSE
        diffuse[TEX_NAME_STRING] = texname
        diffuse[TEX_SHOULD_BAKE] = True
        diffuse[TEX_SHOULD_SUPERSAMPLE] = True
        diffuse[TEX_SIZE_INT] = obj[TEX_SIZE_INT]
        bpy.context.collection.objects.link(diffuse)

        matData = diffuse.data.materials
        colourNameTuples = (
            ("dark_diffuse",(0x1d,0x27,0x28)),
            ("medium_diffuse",(0x4e,0x4e,0x4e)),
            ("light_alt_diffuse",(0x6b,0x6b,0x6b)),
            ("light_diffuse",(0x7d,0x7d,0x7d)),
            ("green_glow_diffuse",(0x60,0xf0,0x00)),
            ("red_glow_diffuse",(0xff,0x00,0x00)),
            ("engine_glow_diffuse",(0xe3,0xad,0x00)),
            ("black_diffuse",(0x00,0x00,0x00)),
            ("white_glow_diffuse",(0xff,0xff,0xff)),
            ("socket_diffuse",(0x07,0x07,0x0b)),
        )
        for value in colourNameTuples:
            matData.append(createMaterial(value[0],value[1],diffuseTex))
        
        if self.extras:
            matData.append(createHazardStripesMaterial("hazard_stripe",(0xf0,0xb8,0x00),(0x00,0x00,0x00),diffuseTex))
            matData.append(createHazardStripesMaterial("hazard_stripe_inverted",(0xf0,0xb8,0x00),(0x00,0x00,0x00),diffuseTex,invert=True))

        areas = bpy.context.workspace.screens[0].areas
        for area in areas:
            for space in area.spaces:
                if space.type == "VIEW_3D":
                    space.shading.type = "MATERIAL"

        bpy.context.scene.render.engine = 'CYCLES'


class SetupTextureComplete(bpy.types.Operator):
    """Copies a mesh and creates several new objects for baking"""
    bl_idname = "setup_bake.papa_utils"
    bl_label = "PAPA Setup Texture Complete"
    bl_options = {'UNDO'}

    def findDiffuse(self, context):
        for obj in bpy.context.selected_objects:
            if getObjectType(obj) == OBJ_TYPES.DIFFUSE:
                self.__builtObjects.append(obj)
                return True
    
        self.report({'ERROR'},"Selected object must have been previously set up using Setup Texture Initial")
        return False

    def getMaterialMap(self, mesh):
        polygons = mesh.data.polygons
        materialMap = {}
        materialMap['dark']=[]
        materialMap['light']=[]
        materialMap['glow']=[]
        materialMap['vent']=[]
        materialMap['default']=[]

        for x in range(len(polygons)):
            face = polygons[x]
            idx = face.material_index
            matName = mesh.data.materials[idx].name
            if matName=="dark_diffuse" or matName=="medium_diffuse" or matName=="socket_diffuse":
                materialMap['dark'].append(x)
            elif matName=="black_diffuse":
                materialMap['vent'].append(x)
            elif matName=="light_diffuse" or matName=="light_alt_diffuse" or matName=="hazard_stripe" or matName == "hazard_stripe_inverted":
                materialMap['light'].append(x)
            elif matName=="red_glow_diffuse" or matName=="engine_glow_diffuse" or matName=="white_glow_diffuse" or matName=="green_glow_diffuse":
                materialMap['glow'].append(x)
            else:
                materialMap['default'].append(x)
        return materialMap
    
    def assignFacesMaterial(self, materialMap, mesh, dark, light, vent, glow):
        polygons = mesh.data.polygons
        materialDict = {mat.name: i for i, mat in enumerate(mesh.data.materials)}
        darkIdx = materialDict[dark]
        lightIdx = materialDict[light]
        ventIdx = materialDict[vent]
        glowIdx = materialDict[glow]

        for faceIdx in materialMap["dark"]:
            polygons[faceIdx].material_index = darkIdx
        for faceIdx in materialMap["light"]:
            polygons[faceIdx].material_index = lightIdx
        for faceIdx in materialMap["glow"]:
            polygons[faceIdx].material_index = glowIdx
        for faceIdx in materialMap["vent"]:
            polygons[faceIdx].material_index = ventIdx
        for faceIdx in materialMap["default"]:
            polygons[faceIdx].material_index = ventIdx
    
    def assignFacesMask(self, materialMap, mesh, glow):
        polygons = mesh.data.polygons
        materialDict = {mat.name: i for i, mat in enumerate(mesh.data.materials)}
        glowIdx = materialDict[glow]

        for faceIdx in materialMap["glow"]:
            polygons[faceIdx].material_index = glowIdx

    def assignFacesAO(self, materialMap, mesh, glow):
        polygons = mesh.data.polygons
        materialDict = {mat.name: i for i, mat in enumerate(mesh.data.materials)}
        glowIdx = materialDict[glow]

        for faceIdx in materialMap["glow"]:
            polygons[faceIdx].material_index = glowIdx

    def setupObjectBake(self, obj, texSize, name):
        materialMap = self.getMaterialMap(obj)

        # create the material object
        texname = name+"_material_bake"
        materialTex = getOrCreateImage(texname,texSize)
        material = duplicateObject(obj, OBJ_TYPES.MATERIAL.lower())
        material.data.materials.clear()
        material.location[0]+=material.dimensions.x * 2
        material[OBJ_NAME_STRING] = obj[OBJ_NAME_STRING]
        material[OBJ_TYPE_STRING] = OBJ_TYPES.MATERIAL
        material[TEX_NAME_STRING] = texname
        material[TEX_SHOULD_BAKE] = True
        material[TEX_SHOULD_SUPERSAMPLE] = True
        material[TEX_SIZE_INT] = obj[TEX_SIZE_INT]
        self.__builtObjects.append(material)
        bpy.context.collection.objects.link(material)

        matData = material.data.materials
        colourNameTuples = (
            ("dark_material",(0xc0,0xc0,0xff)),
            ("light_material",(0xf0,0xcc,0xff)),
            ("glow_material",(0x00,0x00,0xff)),
            ("vent_material",(0x00,0xc5,0xff)),
            ("tread_material",(0x28,0xc5,0xff)),
            ("shiny_material",(0x00,0xff,0x00)),
            ("shiny_lesser_material",(0x08,0xB9,0x00)),
        )
        for value in colourNameTuples:
            matData.append(createMaterial(value[0],value[1],materialTex))
        
        self.assignFacesMaterial(materialMap, material, "dark_material", "light_material", "vent_material", "glow_material")

        # create the mask object
        texname = name+"_mask_bake"
        maskTex = getOrCreateImage(texname,texSize)
        mask = duplicateObject(obj, OBJ_TYPES.MASK.lower())
        mask.data.materials.clear()
        mask.location[0]+=mask.dimensions.x * 4
        mask[OBJ_NAME_STRING] = obj[OBJ_NAME_STRING]
        mask[OBJ_TYPE_STRING] = OBJ_TYPES.MASK
        mask[TEX_NAME_STRING] = texname
        mask[TEX_SHOULD_BAKE] = True
        mask[TEX_SHOULD_SUPERSAMPLE] = True
        mask[TEX_SIZE_INT] = obj[TEX_SIZE_INT]
        self.__builtObjects.append(mask)
        bpy.context.collection.objects.link(mask)

        matData = mask.data.materials
        colourNameTuples = (
            ("primary",(0xff,0x00,0x00)),
            ("secondary",(0x00,0xff,0x00)),
            ("glow_mask",(0x00,0x00,0xff)),
            ("glow_primary_mask",(0xff,0x00,0xff)),
            ("black_mask",(0x00,0x00,0x00)),
        )
        for value in colourNameTuples:
            matData.append(createMaterial(value[0],value[1],maskTex))

        lastIdx = len(mask.data.materials) - 1
        polygons = mask.data.polygons
        for poly in polygons:
            poly.material_index = lastIdx

        self.assignFacesMask(materialMap, mask, "glow_mask")
    
        # create the AO object
        texname = name+"_ao_bake"
        aoTex = getOrCreateImage(texname,texSize)
        ao = duplicateObject(obj, OBJ_TYPES.AO.lower())
        ao.data.materials.clear()
        ao.location[0]+=ao.dimensions.x * 6
        ao[OBJ_NAME_STRING] = obj[OBJ_NAME_STRING]
        ao[OBJ_TYPE_STRING] = OBJ_TYPES.AO
        ao[TEX_NAME_STRING]=texname
        ao[TEX_SHOULD_BAKE] = True
        ao[TEX_SHOULD_SUPERSAMPLE] = True
        ao[TEX_SIZE_INT] = obj[TEX_SIZE_INT]
        self.__builtObjects.append(ao)
        if ao.dimensions.x < 10:
            ao.location[0]+= ao.dimensions.x
        bpy.context.collection.objects.link(ao)

        matData = ao.data.materials
        matData.append(createMaterial("ao_bake",(0xff,0xff,0xff),aoTex,attach=True))
        matData.append(createMaterial("ao_bake_ignore",(0xff,0xff,0xff),aoTex,attach=False))

        self.assignFacesAO(materialMap,ao,"ao_bake_ignore")

    def setupBake(self, context):
        diffuse = None
        for obj in bpy.context.selected_objects:
            if getObjectType(obj) == OBJ_TYPES.DIFFUSE:
                diffuse = obj
                break
        if diffuse == None:
            self.report({'ERROR'}, "Selected object must have been created with setup texture initial")
            return False

        self.__builtObjects.append(diffuse)
        size = diffuse[TEX_SIZE_INT]
        name = diffuse[OBJ_NAME_STRING]

        self.setupObjectBake(diffuse, size, name)

        return True

    # ------------------------------------------

    def setupObjectEdgeHighlights(self, diffuse, ao, name, texSize):
        target = None
        
        edgeHighlightTex = getOrCreateImage(name+"_edge_highlights",texSize)
        target = ao
        edgeHighlight = duplicateObject(target, OBJ_TYPES.EDGE_HIGHLIGHT.lower())
        edgeHighlight.data.materials.clear()
        if ao:
            edgeHighlight.location[0]+=edgeHighlight.dimensions.x * 2
            if ao.dimensions.x < 10:
                edgeHighlight.location[0]+= ao.dimensions.x
        else:
            edgeHighlight.location[1]+=edgeHighlight.dimensions.y * 2
        bpy.context.collection.objects.link(edgeHighlight)

        edgeHighlight[OBJ_NAME_STRING] = diffuse[OBJ_NAME_STRING]
        edgeHighlight[OBJ_TYPE_STRING] = OBJ_TYPES.EDGE_HIGHLIGHT
        edgeHighlight[EDGE_HIGHLIGHT_TEXTURE] = edgeHighlightTex
        edgeHighlight[TEX_NAME_STRING] = edgeHighlightTex.name
        edgeHighlight[TEX_SHOULD_BAKE] = False
        edgeHighlight[TEX_SHOULD_SUPERSAMPLE] = False
        edgeHighlight[TEX_SIZE_INT] = diffuse[TEX_SIZE_INT]
        self.__builtObjects.append(edgeHighlight)
        matData = edgeHighlight.data.materials
        matData.append(createEdgeHightlightMaterial("edge highlights", diffuse, ao, edgeHighlightTex))

    def setupEdgeHighlights(self, context):
        obj = self.__builtObjects[0]

        diffuseObj = None
        aoObj = None
    
        name = obj[OBJ_NAME_STRING]
        size = obj[TEX_SIZE_INT]
        for obj in self.__builtObjects:
            t = getObjectType(obj)
            if t == OBJ_TYPES.DIFFUSE:
                diffuseObj = obj
            if t == OBJ_TYPES.AO:
                aoObj = obj

        self.setupObjectEdgeHighlights(diffuseObj, aoObj, name, size)

        return True

    # ------------------------------------------

    def setupObjectDistanceField(self, locObj, diffuse, ao, edgeObj, name, texSize):

        target = None
        
        distanceFieldTex = getOrCreateImage(name+"_distance_field",texSize)
        target = edgeObj
        if not target:
            target = ao
        if not target:
            target = diffuse
        if not target:
            target = bpy.context.active_object
        distanceField = duplicateObject(target,OBJ_TYPES.DISTANCE_FIELD.lower())
        distanceField.data.materials.clear()
        if edgeObj and edgeObj.location[0]>=locObj.location[0]:
            distanceField.location[0]+=distanceField.dimensions.x * 2
            if ao.dimensions.x < 10:
                distanceField.location[0]+= ao.dimensions.x
        else:
            distanceField.location[0]=locObj.location[0] + locObj.dimensions.x * 2
            distanceField.location[1]=locObj.location[1]
            distanceField.location[2]=locObj.location[2]
        bpy.context.collection.objects.link(distanceField)

        distanceField[OBJ_NAME_STRING] = diffuse[OBJ_NAME_STRING]
        distanceField[OBJ_TYPE_STRING] = OBJ_TYPES.DISTANCE_FIELD
        distanceField[DISTANCE_FIELD_TEXTURE] = distanceFieldTex
        distanceField[TEX_NAME_STRING] = distanceFieldTex.name
        distanceField[TEX_SHOULD_BAKE] = False
        distanceField[TEX_SHOULD_SUPERSAMPLE] = False
        distanceField[TEX_SIZE_INT] = diffuse[TEX_SIZE_INT]
        self.__builtObjects.append(distanceField)
        matData = distanceField.data.materials
        df = createDistanceFieldMaterial("distance field", distanceFieldTex)
        matData.append(df)
        matData.append(createMaterial("distance field ignore",(0xff,0xff,0xff),distanceFieldTex))
        distanceField[DISTANCE_FIELD_MATERIAL] = df

    def setupDistanceField(self, context):
        obj = self.__builtObjects[0]

        locObj = None
        diffuseObj = None
        aoObj = None
        edgeObj = None
        maxLocation = -999999
    
        name = obj[OBJ_NAME_STRING]
        size = obj[TEX_SIZE_INT]
        for obj in self.__builtObjects:
            t = getObjectType(obj)
            if t == OBJ_TYPES.DIFFUSE:
                diffuseObj = obj
            if t == OBJ_TYPES.AO:
                aoObj = obj
            if t == OBJ_TYPES.EDGE_HIGHLIGHT:
                edgeObj = obj
            if(obj.location[0] > maxLocation):
                locObj = obj
                maxLocation = obj.location[0]

        self.setupObjectDistanceField(locObj, diffuseObj, aoObj, edgeObj, name, size)

        return True

    # ------------------------------------------

    def setupObjectMaterialBake(self, materialObj, edgeHighlight):
        darkMat = None
        lightMat = None
        for slot in materialObj.material_slots:
            if not slot.material:
                continue
            mat = slot.material
            if mat.name == "dark_material":
                darkMat = mat
            if mat.name == "light_material":
                lightMat = mat
            
        if not darkMat or not lightMat:
            self.report({"ERROR"},"Material object missing dark or light material.")
            return False

        lightCol = lightMat.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value
        
        tree = darkMat.node_tree
        bsdf = tree.nodes["Principled BSDF"]

        col = tree.nodes.new("ShaderNodeMixRGB")
        col.inputs["Fac"].default_value = 0
        col.inputs["Color1"].default_value=bsdf.inputs["Base Color"].default_value

        mixRGB = tree.nodes.new("ShaderNodeMixRGB")
        mixRGB.blend_type = "SOFT_LIGHT"

        colourRamp = tree.nodes.new("ShaderNodeValToRGB")
        colourRamp.color_ramp.elements[1].color = lightCol

        edgeBake = tree.nodes.new("ShaderNodeTexImage")
        edgeBake.image = edgeHighlight[EDGE_HIGHLIGHT_TEXTURE]
        edgeBake.select=False

        tree.links.new(mixRGB.inputs["Color1"], col.outputs["Color"])
        tree.links.new(mixRGB.inputs["Color2"], colourRamp.outputs["Color"])
        tree.links.new(mixRGB.inputs["Fac"], edgeBake.outputs["Alpha"])
        tree.links.new(colourRamp.inputs["Fac"], edgeBake.outputs["Color"])
        tree.links.new(bsdf.inputs["Base Color"], mixRGB.outputs["Color"])

    def setupMaterialBake(self, context):
        obj = self.__builtObjects[0]

        material = None
        edgeHighlights = None

        for obj in self.__builtObjects:
            t = getObjectType(obj)
            if t == OBJ_TYPES.MATERIAL:
                material = obj
            if t == OBJ_TYPES.EDGE_HIGHLIGHT:
                edgeHighlights = obj


        self.setupObjectMaterialBake(material, edgeHighlights)

        return True

    def clearEdgeSharp(self, context):
        for obj in self.__builtObjects:
            t = getObjectType(obj)
            if t == OBJ_TYPES.EDGE_HIGHLIGHT or t == OBJ_TYPES.DISTANCE_FIELD:
                continue

            for edge in obj.data.edges:
                edge.use_edge_sharp = False


    def execute(self, context):

        methods = [self.setupBake, self.setupEdgeHighlights, self.setupDistanceField, self.setupMaterialBake, self.clearEdgeSharp]
        self.__builtObjects = []

        for method in methods:
            retVal = method(context)
            if not retVal:
                return {'CANCELLED'}

        return {'FINISHED'}

class BakeSelectedObjects(bpy.types.Operator):
    """Bakes all selected objects' textures."""
    bl_idname = "bake_objects.papa_utils"
    bl_label = "PAPA Bake Objects"
    bl_options = {'REGISTER','UNDO'}

    def alterUvs(self, mesh, idx, move):

        bpy.ops.object.mode_set(mode='OBJECT')
        uvData = mesh.data.uv_layers[0].data
        for poly in mesh.data.polygons:
            if poly.material_index == idx:
                for loopIdx in poly.loop_indices:
                    uvData[loopIdx].uv[0]+=move
    
    def execute(self, context):
        success = 0
        objects = []
        for obj in bpy.context.selected_objects:
            try:
                shouldBake = obj[TEX_SHOULD_BAKE]
                shouldSupersample = obj[TEX_SHOULD_SUPERSAMPLE]
                texSize = obj[TEX_SIZE_INT]
            except:
                continue

            if shouldBake:
                tex = getOrCreateImage(obj[TEX_NAME_STRING])

                if shouldSupersample:
                    texSize = (tex.size[0], tex.size[1])
                    tex.scale(texSize[0]*2,texSize[1]*2)
                
                selectObject(obj)

                if getObjectType(obj) == OBJ_TYPES.AO:
                    bpy.ops.object.bake(type="AO",margin=128)
                    self.alterUvs(obj,0,1)
                    bpy.ops.object.bake(pass_filter={"COLOR"},type="DIFFUSE",margin=0,use_clear=False)
                    self.alterUvs(obj,0,-1)
                else:
                    bpy.ops.object.bake(pass_filter={"COLOR"},type="DIFFUSE",margin=128)

                if shouldSupersample:
                    tex.scale(texSize[0],texSize[1])

                if getObjectType(obj) == OBJ_TYPES.DIFFUSE: # add magic pixel TODO remove
                    idx = texSize[0] * texSize[1] * 4 - 4
                    tex.pixels[idx] = 1.0
                    tex.pixels[idx + 1] = 0.0
                    tex.pixels[idx + 2] = 1.0
                    tex.pixels[idx + 3] = 1.0
                elif getObjectType(obj) == OBJ_TYPES.AO:
                    idx = texSize[0] * texSize[1] * 4 - 4
                    tex.pixels[idx] = 1.0
                    tex.pixels[idx + 1] = 1.0
                    tex.pixels[idx + 2] = 1.0
                    tex.pixels[idx + 3] = 1.0
                else:
                    tex.pixels[0] = tex.pixels[0] # force a reload, sometimes the texture won't update automatically after a bake
                
                success+=1

        self.report({"INFO"},"Successfully baked "+str(success)+" texture(s).")
        return {'FINISHED'}

class DissolveTo(bpy.types.Operator):
    """Attempts to dissolve all vertices on the selected meshes that do not correspond to vertices on the active mesh"""
    bl_idname = "dissolve_to.papa_utils"
    bl_label = "PAPA Dissolve To"
    bl_options = {'UNDO'}

    def execute(self, context):
        obj = bpy.context.active_object
        others = []
        for x in bpy.context.selected_objects:
            if x != obj:
                others.append(x)

        if not obj:
            self.report({'ERROR'}, "No object given")
            return {'FINISHED'}
        
        vertexMap = self.calculateVertexMap(obj)

        total = 0

        for x in others:
            total += self.dissolve(vertexMap, x)

        selectObject(obj)
        self.report({'INFO'}, "Dissolved "+str(total)+" edge(s) from " + str(len(others)) + "object(s)")
        return {'FINISHED'}

    def calculateVertexMap(self, obj):
        selectObject(obj)
        bpy.ops.object.mode_set(mode='EDIT')

        vertexMap = {}
        for vertex in obj.data.vertices:
            vertexMap[Vector(vertex.co).freeze()] = True

        return vertexMap
    
    def dissolve(self, vertexMap, obj):
        selectObject(obj)
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_mode(type='EDGE')
        bpy.ops.mesh.select_all(action='DESELECT')
        bpy.ops.object.mode_set(mode='OBJECT')

        vertices = obj.data.vertices

        count = 0

        frozenVertices = []
        for v in vertices:
            frozenVertices.append(Vector(v.co).freeze())

        for edge in obj.data.edges:
            v = edge.vertices
            v1 = frozenVertices[v[0]]
            v2 = frozenVertices[v[1]]
            if not v1 in vertexMap and not v2 in vertexMap:
                edge.select = True
                count += 1
    
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.dissolve_edges()
        return count
        
class AssignFrom(bpy.types.Operator):
    """Attempts to assign material slots from one mesh to another"""
    bl_idname = "assign_from.papa_utils"
    bl_label = "PAPA Assign From"
    bl_options = {'REGISTER','UNDO'}

    hashFactor: IntProperty(name="Search Quadrants",description="The amount of zones to break the mesh up in to.", default=50, min=1, max=256)

    def execute(self, context):
        applyTo = None
        materialSource = bpy.context.active_object
        for x in bpy.context.selected_objects:
            if x != materialSource:
                applyTo = x

        if not materialSource:
            self.report({'ERROR'}, "No active object")
            return {'CANCELLED'}

        if len(bpy.context.selected_objects) != 2:
            self.report({'ERROR'}, "Incorrect amount of objects given. Exactly two must be selected.")
            return {'CANCELLED'}
        
        self.assign(createFaceMapping(applyTo, materialSource, self.hashFactor), applyTo, materialSource)

        applyToSlots = len(applyTo.data.materials)
        materialSourceSlots = len(materialSource.data.materials)
        if applyToSlots != materialSourceSlots:
            self.report({'WARNING'}, "Material slot count differs between objects ("+str(applyToSlots) + " != "+str(materialSourceSlots)+").")
        else:
            self.report({'INFO'}, "Finished assigning material slots")

        selectObject(applyTo)
        return {'FINISHED'}
    
    def assign(self, mapping, applyTo, materialSource):
        selectObject(materialSource)
        bpy.ops.object.mode_set(mode='OBJECT')
        materialMapping = []
        for poly in materialSource.data.polygons:
            materialMapping.append(poly.material_index)

        selectObject(applyTo)
        bpy.ops.object.mode_set(mode='OBJECT')
        for x in range(len(mapping)):
            poly = applyTo.data.polygons[x]
            poly.material_index = materialMapping[mapping[x]]

class CalulateEdgeSharp(bpy.types.Operator):
    """Freestyle marks edges which separate faces with an angle greater than the specified angle."""
    bl_idname = "calculate_edges.papa_utils"
    bl_label = "PAPA Calculate Edges"
    bl_options = {'REGISTER','UNDO'}
    DEFAULT_ANGLE = radians(10)

    angleLimit: FloatProperty(name="Max Angle",description="The max angle before being marked", min=0, max=radians(180), default=DEFAULT_ANGLE, subtype='ANGLE')
    markLoose: BoolProperty(name="Mark Loose", description="Marks loose edges with freestyle mark", default=True)
    
    def execute(self, context):
        obj = bpy.context.active_object
        if not obj:
            self.report({'ERROR'},"No Object given")
            return {'CANCELLED'}

        self.processObject(obj, self.angleLimit)

        return {'FINISHED'}
    

    def createEdgeFaceMap(self, obj):
        edges = obj.data.edges
        polygons = obj.data.polygons

        edgeKeyToIndex = {}
        for edge in edges:
            edgeKeyToIndex[edge.key] = edge.index
        
        edgeKeyToFaces = {}
        for x in range(len(polygons)):
            for edgeKey in polygons[x].edge_keys:
                if not edgeKeyToFaces.get(edgeKey):
                    edgeKeyToFaces[edgeKey] = []
                edgeKeyToFaces[edgeKey].append(x) # map this face to this edge key
        return edgeKeyToFaces


    def processObject(self, obj, angleLimit):
        selectObject(obj)
        bpy.ops.object.mode_set(mode='OBJECT')
        edgeKeyToFaces = self.createEdgeFaceMap(obj)
        edges = obj.data.edges
        polygons = obj.data.polygons
        for edge in edges:
            faces = edgeKeyToFaces[edge.key]
            if len(faces) >= 2:
                v1 = Vector(polygons[faces[0]].normal)
                v2 = Vector(polygons[faces[1]].normal)
                diff = v1.angle(v2,0)
                edge.use_freestyle_mark = diff>=angleLimit
            else:
                edge.use_freestyle_mark = self.markLoose

        bpy.ops.object.mode_set(mode='EDIT')

class TweakEdgeHighlights(bpy.types.Operator):
    """Draws the edge highlights to the specified texture"""
    bl_idname = "tweak_edges.papa_utils"
    bl_label = "PAPA Tweak Edge Highlights"
    bl_options = {'REGISTER','UNDO'}

    lineThickness: FloatProperty(name="Width", description="The thickness to draw the edge highlights at",min=0,max=50,default=1)
    blurAmount: FloatProperty(name="Blur",description="The amount to blur the edge highlights", min=0, max=50, default=0.5)
    multiplier: FloatProperty(name="Multiplier",description="How much to multiply the values by", min=0, max=10, default=1)

    maxTaper: FloatProperty(name="Max Taper Angle",description="The largest angle that tapering is applied", min=0, max=radians(180), default=radians(90), subtype='ANGLE')
    minTaper: FloatProperty(name="Min Taper Angle",description="The smallest angle that tapering is applied", min=0, max=radians(180), default=CalulateEdgeSharp.DEFAULT_ANGLE, subtype='ANGLE')
    taperFactor: FloatProperty(name="Taper Factor",description="The amount to taper at min", min=0, max=1, default=0.25)

    
    def execute(self, context):
        obj = bpy.context.active_object

        try:
            tex = obj[EDGE_HIGHLIGHT_TEXTURE]
        except:
            self.report({'ERROR'},"Selected object must be an edge highlights object")
            return {'CANCELLED'}
        

        self.processObject(obj, tex, self.lineThickness, self.blurAmount, self.multiplier,
                                        self.minTaper, self.maxTaper, self.taperFactor)

        return {'FINISHED'}
    
    def invoke(self, context, event):
        obj = bpy.context.active_object
        if not obj:
            self.report({'ERROR'},"No Object given")
            return {'CANCELLED'}

        try:
            self.lineThickness = obj[EDGE_HIGHLIGHT_DILATE]
            self.blurAmount = obj[EDGE_HIGHLIGHT_BLUR]
            self.multiplier = obj[EDGE_HIGHLIGHT_MULTIPLIER]
        except:
            pass

        return self.execute(context)

    def getEdgeToAngle(self, mesh):

        edges = mesh.data.edges
        polygons = mesh.data.polygons
        loops = mesh.data.loops

        # build a edge -> polygons map
        edgeMap = []
        for _ in edges:
            edgeMap.append([])
        
        for poly in polygons:
            for loopIdx in poly.loop_indices:
                edgeMap[loops[loopIdx].edge_index].append(Vector(poly.normal))

        for x in range(len(edgeMap)):
            arr = edgeMap[x]
            if len(arr) != 2:
                edgeMap[x] = pi
            else:
                edgeMap[x] = arr[0].angle(arr[1], pi)
        return edgeMap

    def getLines(self, mesh, islands, edgeMap, minAngle, maxAngle, minTaper, islandSizes, baseThickness, baseBlur):
        selectObject(mesh)
        bpy.ops.object.mode_set(mode='OBJECT')

        angleDiff = maxAngle - minAngle
        angleFactor = 1 / angleDiff if angleDiff > 0 else 0
        minThickness = minTaper * baseThickness
        thicknessAngleFactor = (baseThickness - minThickness) * angleFactor

        averageIslandSize = sum(islandSizes) / len(islandSizes)
        averageIslandSizeDiv = averageIslandSize / 2

        lines = [] # [num_lines_in_island, islandIdx, [x1,y1,x2,y2, thickness, blur...]...]

        if len(mesh.data.uv_layers) == 0:
            self.report({'ERROR'},"Mesh has no UV layer")

        uv = mesh.data.uv_layers[0].data

        edges = mesh.data.edges
        polygons = mesh.data.polygons
        loops = mesh.data.loops

        for islandIdx in range(len(islands)):
            lines.append(-1)

            count = 0
            arrIdx = len(lines) - 1

            lines.append(float(islandIdx))

            islandSize = islandSizes[islandIdx]
            for poly in islands[islandIdx]:
                polygon = polygons[poly]
                l = len(polygon.loop_indices)
                for x in range(l):
                    loopIdx = polygon.loop_indices[x]
                    edgeIndex = loops[loopIdx].edge_index
                    edge = edges[edgeIndex]
                    if not edge.use_freestyle_mark:
                        continue
                    loopIdx2 = polygon.loop_indices[(x + 1) % l]
                    c1 = uv[loopIdx].uv[0]
                    c2 = uv[loopIdx].uv[1]
                    c3 = uv[loopIdx2].uv[0]
                    c4 = uv[loopIdx2].uv[1]
                    lines.append(c1)
                    lines.append(c2)
                    lines.append(c3)
                    lines.append(c4)

                    # taper pass
                    edgeAngle = edgeMap[edgeIndex]
                    if edgeAngle >= minAngle and edgeAngle < maxAngle:
                        thickness = (edgeAngle - minAngle) * thicknessAngleFactor + minThickness
                    else:
                        thickness = baseThickness

                    # size pass
                    if islandSize < averageIslandSizeDiv:
                        thickness = thickness * (islandSize / averageIslandSizeDiv)

                    lines.append(thickness)
                    lines.append(baseBlur)
                    count+=1
            lines[arrIdx] = count
        return lines

    def getOrderedIslandSizes(self, triangulatedUvs):
        x = 0
        islandSizes = []
        while x < len(triangulatedUvs):
            islandSize = 0
            numData = triangulatedUvs[x] * 6
            x+=1
            for y in range(x, x + numData,6):
                x1 = triangulatedUvs[y]
                y1 = triangulatedUvs[y + 1]
                x2 = triangulatedUvs[y + 2]
                y2 = triangulatedUvs[y + 3]
                x3 = triangulatedUvs[y + 4]
                y3 = triangulatedUvs[y + 5]
                islandSize += 1 / 2 * (x1 * (y2 - y3) + x2 * (y3 - y1) + x3 * (y1 - y2))
            x += numData
            islandSizes.append(islandSize)
        return islandSizes

    def getOrderedUvsTriangulated(self, mesh, islandMap):
        selectObject(mesh)
        bpy.ops.object.mode_set(mode='OBJECT')

        uv = mesh.data.uv_layers[0].data

        rawData = []
        for x in range(len(islandMap)):
            rawData.append([])

        mesh.data.calc_loop_triangles()
        for tri in mesh.data.loop_triangles:
            arr = rawData[islandMap[tri.polygon_index]]
            for x in range(3):
                uvData = uv[tri.loops[x]].uv
                c1 = uvData[0]
                c2 = uvData[1]
                arr.append(c1)
                arr.append(c2)

        triangulatedUvs = [] # [num_triangles_in_island, x1,y1,x2,y2,...]
        for x in range(len(rawData)):
            triangulatedUvs.append(len(rawData[x]) // 6)

            for u in rawData[x]:
                triangulatedUvs.append(u)
        return triangulatedUvs

    def getIslandMap(self, obj):
        selectObject(obj)
        bpy.ops.object.mode_set(mode='OBJECT')
        islands = mesh_utils.mesh_linked_uv_islands(obj.data)
        islandMap = {} # [polyIdx] -> island idx
        for x in range(len(islands)):
            for poly in islands[x]:
                islandMap[poly] = x

        return islands, islandMap


    def processObject(self, obj, tex, thickness, blur, multiplier, minAngle, maxAngle, minTaper):
        # the following are converted into arrays of structs in C
        # lineData: array of floats [num_lines, mask_idx, [start, end, thickness, blur...]...] ends when start has a value of -infinity
        # triangulatedUVData: ordered list of float indices as follows [num_triangles, <triangulated UV data>...] ends when num_triangles has a value of -infinity


        if not textureLibrary:
            self.report({'ERROR'},"TEXTURE LIBRARY NOT LOADED")
            return

        obj[EDGE_HIGHLIGHT_DILATE] = thickness
        obj[EDGE_HIGHLIGHT_BLUR] = blur
        obj[EDGE_HIGHLIGHT_MULTIPLIER] = multiplier

        islands, islandMap = self.getIslandMap(obj)
        edgeMap = self.getEdgeToAngle(obj)

        triangulatedUvs = self.getOrderedUvsTriangulated(obj, islandMap)
        tuvs = array('f',triangulatedUvs)
        tuvPointer = tuvs.buffer_info()[0]

        if len(triangulatedUvs) == 0:
            self.report({"ERROR"},"Model has no freestyle marked edges.")
            return

        islandSizes = self.getOrderedIslandSizes(triangulatedUvs)

        lines1 = self.getLines(obj, islands, edgeMap, minAngle, maxAngle, minTaper, islandSizes, thickness, blur)
        lines2 = self.getLines(obj, islands, edgeMap, minAngle, maxAngle, minTaper, islandSizes, thickness/3, blur*4)
        lines3 = self.getLines(obj, islands, edgeMap, minAngle, maxAngle, minTaper, islandSizes, thickness/4, blur*12)
        lines1 = array('f',lines1)
        lines2 = array('f',lines2)
        lines3 = array('f',lines3)
        lines = array('Q',[lines1.buffer_info()[0], lines2.buffer_info()[0], lines3.buffer_info()[0]])
        linePointer = lines.buffer_info()[0]

        dataLen = len(islands)
        
        imgWidth = tex.size[0]
        imgHeight = tex.size[1]
        imgSize = imgWidth * imgHeight
        imgDataSize = imgSize * 4
        if imgDataSize & (imgDataSize-1) == 0: # test if the number of values is a power of two
            outData = array('f',[0.0])
            for _ in range(int(log2(imgDataSize))):
                outData.extend(outData)
        else:
            outData = array('f',[0.0] * imgDataSize)
        outPointer = outData.buffer_info()[0]

        extraData = array('f',[multiplier,multiplier/2,multiplier/3])
        extraPointer = extraData.buffer_info()[0]

        textureLibrary.generateEdgeHighlights(  ctypes.cast(linePointer,ctypes.POINTER(ctypes.POINTER(ctypes.c_float))),
                                                ctypes.cast(tuvPointer,ctypes.POINTER(ctypes.c_float)),
                                                ctypes.cast(extraPointer, ctypes.POINTER(ctypes.c_float)),
                                                ctypes.c_int(dataLen),
                                                ctypes.c_int(imgWidth), ctypes.c_int(imgHeight),
                                                ctypes.cast(outPointer,ctypes.POINTER(ctypes.c_float)))

        tex.pixels = outData

class TweakDistanceField(bpy.types.Operator):
    """Draws the distance field of the specified object"""
    bl_idname = "tweak_distance.papa_utils"
    bl_label = "PAPA Tweak Distance Field"
    bl_options = {'REGISTER','UNDO'}

    texelInfo: FloatProperty(name="TEMP_texelinfo",description="The value for TEMP_texelinfo", min=-1, max=4096, default=-1)
    
    def execute(self, context):
        obj = bpy.context.active_object

        try:
            tex = obj[DISTANCE_FIELD_TEXTURE]
            matData = obj[DISTANCE_FIELD_MATERIAL]
        except:
            self.report({'ERROR'},"Selected object must have been previously created by \"setup distance field\"")
            return {'CANCELLED'}
        
        self.processObject(obj, tex, matData, not self.options.is_repeat)

        return {'FINISHED'}
    
    def invoke(self, context, event):
        obj = bpy.context.active_object
        if not obj:
            self.report({'ERROR'},"No Object given")
            return {'CANCELLED'}
        
        try:
            self.texelInfo = obj[DISTANCE_FIELD_TEXEL_INFO]
        except:
            pass
        return self.execute(context)


    def getUvs(self, mesh):
        selectObject(mesh)
        bpy.ops.object.mode_set(mode='OBJECT')
        uvs = [] # [x1,y1,x2,y2,...]

        if len(mesh.data.uv_layers) == 0:
            self.report({'ERROR'},"Mesh has no UV layer")

        uv = mesh.data.uv_layers[0].data

        edges = mesh.data.edges
        polygons = mesh.data.polygons
        loops = mesh.data.loops
        
        for poly in polygons:
            l = len(poly.loop_indices)
            for x in range(l):
                loopIdx = poly.loop_indices[x]
                edge = edges[loops[loopIdx].edge_index]
                if not edge.use_freestyle_mark:
                    continue
                loopIdx2 = poly.loop_indices[(x + 1) % l]
                c1 = uv[loopIdx].uv[0]
                c2 = uv[loopIdx].uv[1]
                c3 = uv[loopIdx2].uv[0]
                c4 = uv[loopIdx2].uv[1]
                uvs.append(c1)
                uvs.append(c2)
                uvs.append(c3)
                uvs.append(c4)
        return uvs

    def getUvsTriangulated(self, mesh):
        selectObject(mesh)
        bpy.ops.object.mode_set(mode='OBJECT')
        uvs = [] # [x1,y1,x2,y2,...]

        uv = mesh.data.uv_layers[0].data

        polygons = mesh.data.polygons

        mesh.data.calc_loop_triangles()
        for tri in mesh.data.loop_triangles:
            if polygons[tri.polygon_index].material_index == 0:
                for x in range(3):
                    uvData = uv[tri.loops[x]].uv
                    uvs.append(uvData[0])
                    uvs.append(uvData[1])
        return uvs
                

    def processObject(self, obj, tex, matData, recalculate):

        if not textureLibrary:
            self.report({'ERROR'},"TEXTURE LIBRARY NOT LOADED")
            return

        tInfo = ctypes.c_float()

        if self.texelInfo == -1 or recalculate:
            imgWidth = tex.size[0]
            imgHeight = tex.size[1]
            imgSize = imgWidth * imgHeight
            imgDataSize = imgSize * 4
            if imgDataSize & (imgDataSize-1) == 0: # test if the number of values is a power of two
                outData = array('f',[0.0])
                for _ in range(int(log2(imgDataSize))):
                    outData.extend(outData)
            else:
                outData = array('f',[0.0] * imgDataSize)
            outPointer = outData.buffer_info()[0]

            uvs = array('f',self.getUvs(obj))
            uvPointer = uvs.buffer_info()[0]
            numUvCoords = len(uvs)

            if len(uvs) == 0:
                self.report({"ERROR"},"Model has no freestyle marked edges.")
                return

            tuvs = array('f',self.getUvsTriangulated(obj))
            tuvPointer = tuvs.buffer_info()[0]
            numTuvCoords = len(tuvs)

            # note: image is saved to SRGB, but this value is linear. it is still WYSIWYG for the shader
            decay = 170 # hard coded, use texelinfo to change the way it looks

            textureLibrary.generateDistanceField(ctypes.cast(uvPointer,ctypes.POINTER(ctypes.c_float)),
                    ctypes.c_int(numUvCoords), ctypes.cast(tuvPointer,ctypes.POINTER(ctypes.c_float)), ctypes.c_int(numTuvCoords),
                    ctypes.c_int(imgWidth), ctypes.c_int(imgHeight), ctypes.c_int(decay), 
                    ctypes.cast(outPointer,ctypes.POINTER(ctypes.c_float)), ctypes.byref(tInfo))
        
            tex.pixels = outData
        
        # only update value when the user requests it to recalculate
        if self.texelInfo == -1:
            self.texelInfo = tInfo.value
        else:
            tInfo.value = self.texelInfo
        
        obj[DISTANCE_FIELD_TEXEL_INFO] = tInfo.value
        for node in matData.node_tree.nodes:
            if node.label == "TEMP_texelinfo":
                node.inputs[1].default_value = tInfo.value
                return


class PackUndersideFaces(bpy.types.Operator):
    """Packs any UVs on faces that point down. Sensitive to hidden faces"""
    bl_idname = "pack_underside.papa_utils"
    bl_label = "PAPA Pack Underside UVs"
    bl_options = {'REGISTER','UNDO'}

    packingFactor: FloatProperty(name="Factor",description="How much to multiply underside UVs by", min=0, max=1, default=0.25)
    maxDeviation: FloatProperty(name="Max Deviation",description="How much of an angle away from straight down the face may point", 
                                min=0, max=radians(180), default=0.1, subtype="ANGLE")
    select: BoolProperty(name="Select Faces", description="Selects the faces that were altered", default=True)
    
    def execute(self, context):
        obj = bpy.context.active_object
        if not obj:
            self.report({'ERROR'},"No Object given")
            return {'CANCELLED'}
        result = self.processObject(obj)

        self.report({"INFO"},"Packed "+str(result) + " UVs")

        return {'FINISHED'}
                

    def processObject(self, mesh):

        selectObject(mesh)
        if self.select:
            bpy.ops.object.mode_set(mode='EDIT')
            bpy.ops.mesh.select_all(action="DESELECT")
        bpy.ops.object.mode_set(mode='OBJECT')
        if len(mesh.data.uv_layers) == 0:
            self.report({'ERROR'},"Mesh has no UV layer")

        uv = mesh.data.uv_layers[0].data

        polygons = mesh.data.polygons

        down = Vector((0,0,-1))
        numPacked = 0
        
        fac = self.packingFactor
        maxAng = self.maxDeviation
        for poly in polygons:
            if poly.hide:
                continue

            if Vector(poly.normal).angle(down, 100) > maxAng:
                continue

            poly.select = True

            l = len(poly.loop_indices)
            numPacked += 1
            # get the UV for this face
            for x in range(l):
                loopIdx = poly.loop_indices[x]
                data = uv[loopIdx].uv
                data[0] *= fac
                data[1] *= fac
        
        bpy.ops.object.mode_set(mode='EDIT')
        
        return numPacked


class SaveTextures(bpy.types.Operator):
    """Saves the textures of the specified object to the local directory"""
    bl_idname = "save_textures.papa_utils"
    bl_label = "PAPA Save Images"
    bl_options = {'REGISTER','UNDO'}
    
    def execute(self, context):
        objects = []
        for obj in bpy.context.selected_objects:
            objects.append(obj)
        if len(objects)==0:
            self.report({'ERROR'},"No Object given")
            return {'CANCELLED'}

        success = 0
        fail = 0

        area = bpy.context.workspace.screens[0].areas[0]
        prevType = area.type
        area.type = "IMAGE_EDITOR"
        prevImage = area.spaces[0].image

        for obj in objects:
            if obj.type != "MESH":
                continue
            try:
                texname = obj[TEX_NAME_STRING]
                tex = getOrCreateImage(texname)
            except:
                fail+=1
                continue
            area.spaces[0].image = tex
            bpy.ops.image.save_as({'area': area},'INVOKE_DEFAULT',copy=True,filepath = bpy.path.abspath("//")+"/"+str(texname)+".png")
            success+=1
        
        if success != 0 or fail != 0:
            if fail != 0:
                self.report({"INFO"},"Saved "+str(success)+" image(s), "+str(fail) + " model(s) had no images associated.")
            else:
                self.report({"INFO"},"Saved "+str(success)+" image(s)")
        
        area.spaces[0].image = prevImage
        area.type = prevType
        
        return {'FINISHED'}

class UpdateLegacy(bpy.types.Operator):
    """Updates properties of an object that were defined previously by the plugin"""
    bl_idname = "update_legacy.papa_utils"
    bl_label = "PAPA Update Legacy Data"
    bl_options = {'REGISTER','UNDO'}

    meshName: StringProperty(name="Mesh Name",description="The mesh name to apply, leave blank to do nothing",default="")
    size: IntProperty(name="Texture Size",description="The texture size to use, set to zero to leave the same", default=0,min=0, max=4096)
    
    def execute(self, context):
        objects = []
        for obj in bpy.context.selected_objects:
            if obj.type != "MESH":
                continue
            objects.append(obj)
        if len(objects)==0:
            self.report({'ERROR'},"No Object given")
            return {'CANCELLED'}

        success = 0

        # change old legacy names
        for obj in objects:
            try:
                supersample = obj["PAPA_IO_TEXTURE_SUPERSAMPLE"]
                obj[TEX_SHOULD_SUPERSAMPLE] = supersample
                del obj["PAPA_IO_TEXTURE_SUPERSAMPLE"]
                success+=1
            except:
                pass
        
        

        # copy the texture name from material if it is not defined already
        for obj in objects:
            if not TEX_NAME_STRING in obj or not obj[TEX_NAME_STRING] in bpy.data.images:
                if len(obj.data.materials) == 0:
                    continue
                if not obj.data.materials[0].node_tree: # not using nodes
                    continue
                for node in obj.data.materials[0].node_tree.nodes:
                    if node.bl_idname == "ShaderNodeTexImage" and node.image:
                        obj[TEX_NAME_STRING] = node.image.name
                        success+=1
                        break

        # update mesh names
        if self.meshName != "":
            for obj in objects:

                if OBJ_NAME_STRING in obj and TEX_NAME_STRING in obj:

                    oldName = obj[OBJ_NAME_STRING]
                    texStr = obj[TEX_NAME_STRING]
                    try:
                        img = getOrCreateImage(texStr)
                    except:
                        continue
                    texname = self.meshName + texStr[len(oldName)::]
                    if img.name == texname and texStr == texname:
                        continue
                    img.name = texname
                    obj[TEX_NAME_STRING] = texname
                    success+=1

                if not OBJ_NAME_STRING in obj or obj[OBJ_NAME_STRING] != self.meshName:
                    success+=1
                    obj[OBJ_NAME_STRING] = self.meshName

                if (getObjectType(obj) != ""):
                    obj.name = self.meshName +"_" + getObjectType(obj).lower()
        
        # link the nodes to textures if they are not already there
        for obj in objects:
            if TEX_NAME_STRING in obj and obj[TEX_NAME_STRING] in bpy.data.images:
                if len(obj.data.materials) == 0:
                    continue
                for mat in obj.data.materials:
                    if not mat.use_nodes:
                        continue
                    for node in mat.node_tree.nodes:
                        if node.bl_idname == "ShaderNodeTexImage" and not node.image:
                            node.image = getOrCreateImage(obj[TEX_NAME_STRING])
                            success+=1
        
        # general update / add properties
        for obj in objects:
            if getObjectType(obj) == OBJ_TYPES.DIFFUSE:
                if not TEX_SHOULD_BAKE in obj:
                    obj[TEX_SHOULD_BAKE]=True
                    success+=1
                if not TEX_SHOULD_SUPERSAMPLE in obj:
                    obj[TEX_SHOULD_SUPERSAMPLE]=True
                    success+=1
                if not OBJ_TYPE_STRING in obj:
                    obj[OBJ_TYPE_STRING] = OBJ_TYPES.DIFFUSE
                    success+=1
                matNames = [x.material.name if x.material else None for x in obj.material_slots]
                matIdx = {}
                selectObject(obj)
                for x in range(len(obj.material_slots)):
                    m = obj.material_slots[x].material
                    if not m:
                        continue
                    matIdx[m.name] = x
                if not "light_alt_diffuse" in matNames and "medium_diffuse" in matNames:
                    mIdx = matIdx["medium_diffuse"]
                    obj.material_slots[mIdx].material.name="light_alt_diffuse"
                    success+=1

                    mat = createMaterial("medium_diffuse",(0x4e,0x4e,0x4e),bpy.data.images[obj[TEX_NAME_STRING]])
                    obj.data.materials.append(mat)
                    obj.active_material_index=len(obj.data.materials)-1
                    for _ in range(7):
                        bpy.ops.object.material_slot_move(direction="UP")
                    success+=1
                if not "socket_diffuse" in matNames:
                    mat = createMaterial("socket_diffuse",(0x07,0x07,0x0b),bpy.data.images[obj[TEX_NAME_STRING]])
                    obj.data.materials.append(mat)
                    obj.active_material_index=len(obj.data.materials)-1
                    for _ in range(9):
                        bpy.ops.object.material_slot_move(direction="UP")
                    success+=1
                if getObjectType(obj)==OBJ_TYPES.AO:
                    if not "ao_bake_ignore" in obj.data.materials and TEX_NAME_STRING in obj:
                        obj.data.materials.append(createMaterial("ao_bake_ignore",(0xff,0xff,0xff),getOrCreateImage(obj[TEX_NAME_STRING],obj[TEX_SIZE_INT]*2),attach=False))
                        success+=1


            if getObjectType(obj)==OBJ_TYPES.MATERIAL:
                if not TEX_SHOULD_BAKE in obj:
                    obj[TEX_SHOULD_BAKE]=True
                    success+=1
                if not TEX_SHOULD_SUPERSAMPLE in obj:
                    obj[TEX_SHOULD_SUPERSAMPLE]=True
                    success+=1
                if not OBJ_TYPE_STRING in obj:
                    obj[OBJ_TYPE_STRING] = OBJ_TYPES.MATERIAL
                    success+=1
            if getObjectType(obj)==OBJ_TYPES.MASK:
                if not TEX_SHOULD_BAKE in obj:
                    obj[TEX_SHOULD_BAKE]=True
                    success+=1
                if not TEX_SHOULD_SUPERSAMPLE in obj:
                    obj[TEX_SHOULD_SUPERSAMPLE]=True
                    success+=1
                if not OBJ_TYPE_STRING in obj:
                    obj[OBJ_TYPE_STRING] = OBJ_TYPES.MASK
                    success+=1
            if getObjectType(obj)==OBJ_TYPES.AO:
                if not TEX_SHOULD_BAKE in obj:
                    obj[TEX_SHOULD_BAKE]=True
                    success+=1
                if not TEX_SHOULD_SUPERSAMPLE in obj:
                    obj[TEX_SHOULD_SUPERSAMPLE]=False
                    success+=1
                if not OBJ_TYPE_STRING in obj:
                    obj[OBJ_TYPE_STRING] = OBJ_TYPES.AO
                    success+=1
            if getObjectType(obj)==OBJ_TYPES.DISTANCE_FIELD:
                if not TEX_SHOULD_BAKE in obj:
                    obj[TEX_SHOULD_BAKE]=False
                    success+=1
                if not TEX_SHOULD_SUPERSAMPLE in obj:
                    obj[TEX_SHOULD_SUPERSAMPLE]=False
                    success+=1
                if not OBJ_TYPE_STRING in obj:
                    obj[OBJ_TYPE_STRING] = OBJ_TYPES.DISTANCE_FIELD
                    success+=1
                if DISTANCE_FIELD_TEXTURE in obj and not obj[DISTANCE_FIELD_TEXTURE] and TEX_NAME_STRING in obj and TEX_SIZE_INT in obj:
                    texname = obj[TEX_NAME_STRING]
                    img = getOrCreateImage(texname, obj[TEX_SIZE_INT])
                    obj[DISTANCE_FIELD_TEXTURE] = img
                    success+=1
            if getObjectType(obj)==OBJ_TYPES.EDGE_HIGHLIGHT:
                if not TEX_SHOULD_BAKE in obj:
                    obj[TEX_SHOULD_BAKE]=False
                    success+=1
                if not TEX_SHOULD_SUPERSAMPLE in obj:
                    obj[TEX_SHOULD_SUPERSAMPLE]=False
                    success+=1
                if not OBJ_TYPE_STRING in obj:
                    obj[OBJ_TYPE_STRING] = OBJ_TYPES.EDGE_HIGHLIGHT
                    success+=1
                if EDGE_HIGHLIGHT_TEXTURE in obj and not obj[EDGE_HIGHLIGHT_TEXTURE] and TEX_NAME_STRING in obj and TEX_SIZE_INT in obj:
                    texname = obj[TEX_NAME_STRING]
                    img = getOrCreateImage(texname, obj[TEX_SIZE_INT])
                    obj[EDGE_HIGHLIGHT_TEXTURE] = img
                    success+=1

        # resize images
        if self.size != 0:
            for obj in objects:
                if not TEX_SIZE_INT in obj or obj[TEX_SIZE_INT] != self.size:
                    obj[TEX_SIZE_INT] = self.size
                    success+=1

            for obj in objects:
                if not TEX_NAME_STRING in obj:
                    continue
                texStr = obj[TEX_NAME_STRING]
                try:
                    img = getOrCreateImage(texStr, self.size)
                except:
                    continue

                if img.size[0]!=self.size or img.size[1]!=self.size:
                    img.scale(self.size,self.size)
                    success+=1
                
        self.report({"INFO"},"Updated "+str(success)+" properties")
        
        return {'FINISHED'}


class TextureFunctions(bpy.types.Menu):
    """Panel for Blender PAPA IO functions"""
    bl_label = "PAPA Texture Tools"
    bl_idname = "PAPA_TEXTURE_MT_UBERENT_PAPA"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'TOOLS'

    options = [
        SetupTextureInitial,
        SetupTextureComplete,
        PackUndersideFaces,
        CalulateEdgeSharp,
        DissolveTo,
        AssignFrom,
        TweakEdgeHighlights,
        TweakDistanceField,
        BakeSelectedObjects,
        SaveTextures,
        UpdateLegacy,
    ]

    def draw(self, context):
        l = self.layout

        for option in self.options:
            row = l.row()
            row.operator(option.bl_idname, text=option.bl_label)


libPath = path.dirname(path.abspath(__file__)) + path.sep + "ETex.dll"
textureLibrary = None
if path.exists(libPath):
    try:
        textureLibrary = ctypes.CDLL(libPath,winmode=0)
        textureLibrary.generateEdgeHighlights.argTypes = (ctypes.POINTER(ctypes.POINTER(ctypes.c_float)), ctypes.POINTER(ctypes.c_float), ctypes.POINTER(ctypes.c_float), 
                ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.POINTER(ctypes.c_float))
        textureLibrary.generateEdgeHighlights.resType = None

        textureLibrary.generateDistanceField.argTypes = (ctypes.POINTER(ctypes.c_float), ctypes.c_int, ctypes.POINTER(ctypes.c_float), ctypes.c_int, ctypes.c_int, ctypes.c_int,
                ctypes.c_int, ctypes.POINTER(ctypes.c_float))
        textureLibrary.generateDistanceField.resType = None
        print("PAPA IO: Texture Library ETex.dll successfully loaded")
    except Exception as e:
        print("TEXTURE LIBRARY MISSING ("+str(e)+")")

_papa_texture_extension_classes = (
    SetupTextureInitial,
    SetupTextureComplete,
    PackUndersideFaces,
    CalulateEdgeSharp,
    DissolveTo,
    AssignFrom,
    TweakEdgeHighlights,
    TweakDistanceField,
    BakeSelectedObjects,
    SaveTextures,
    UpdateLegacy,
    TextureFunctions,
)

def view3d_menu_func_texture(self, context):
    self.layout.menu(TextureFunctions.bl_idname, text="PAPA Texture Extensions")

def papa_io_register_texture():
    from bpy.utils import register_class
    for cls in _papa_texture_extension_classes:
        register_class(cls)
    
    bpy.types.VIEW3D_MT_object.append(view3d_menu_func_texture)
    
def papa_io_unregister_texture():
    from bpy.utils import unregister_class
    for cls in reversed(_papa_texture_extension_classes):
        unregister_class(cls)

    bpy.types.VIEW3D_MT_object.remove(view3d_menu_func_texture)

if __name__ == "__main__":
    papa_io_register_texture()