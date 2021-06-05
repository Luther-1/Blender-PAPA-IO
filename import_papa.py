# Copyright (c) 2013, 2014  Raevn
# Copyright (c) 2021        Marcus Der      marcusder@hotmail.com
#
# ##### BEGIN GPL LICENSE BLOCK #####
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
# ##### END GPL LICENSE BLOCK #####

import bpy
from os import path
from mathutils import * # has vectors and quaternions
from bpy.props import * 
from bpy import ops
from math import ceil
from .papafile import *
from . import PapaExportMaterial
import time

def load_papa(properties, context):
    filepath = properties.getFilepath()
    file_name=path.splitext(path.basename(filepath))[0]
    print("Starting import of "+file_name)

    papaFile = PapaFile(filepath, verbose = True, readLinked = properties.isImportTextures()) # parse the file

    bpy.context.view_layer.objects.active = None  # if something is selected in blender then deselect it
    textureMap = {} # maps a string name to the texture that was made

    # import textures in the file itself
    if(papaFile.getNumTextures() > 0):
        for x in range(papaFile.getNumTextures()):
            texture = papaFile.getTexture(x)
            if not texture:
                continue # some textures may be omitted by the importer as to keep indices correct
            name = papaFile.getString(texture.getNameIndex())
            createImageFromData(name,texture.getImageData(),texture.getWidth(),texture.getHeight(), texture.getSRGB(), texture.getFilepath(), texMap=textureMap)

    # try to import the textures in the same directory that match to the model, if the files are found, override the material with it
    importedTexture = None
    importedMask = None
    importedMaterial = None
    if(properties.isImportTextures() and papaFile.getNumModels() > 0):
        importedTexture = extractTexture(filepath,"_diffuse", textureMap)
        importedMask = extractTexture(filepath,"_mask", textureMap) if importedTexture else None # skip if we missed the texture
        importedMaterial = extractTexture(filepath,"_material", textureMap) if importedMask else None # skip if we missed the mask or the texture

    # Import each model in the file
    if(papaFile.getNumModels() > 0):
        for x in range(papaFile.getNumModels()):

            model = papaFile.getModel(x)

            collection = bpy.data.collections.new(papaFile.getString(model.getNameIndex()))
            bpy.context.scene.collection.children.link(collection)
            meshGroups = []
            currentMeshes = []
            # meshes
            for m in range(model.getNumMeshBindings()):
                meshBinding = model.getMeshBinding(m)
                mesh = papaFile.getMesh(meshBinding.getMeshIndex())
                vBuffer = papaFile.getVertexBuffer(mesh.getVertexBufferIndex())
                iBuffer = papaFile.getIndexBuffer(mesh.getIndexBufferIndex())
                # model to scene or mesh to model often cause CSGs to be imported far off of the center.
                blenderMesh = createMeshFromData(papaFile.getString(meshBinding.getNameIndex()),vBuffer,iBuffer, model.getModelToScene() @ meshBinding.getMeshToModel()) 

                meshGroups.append((vBuffer, blenderMesh))
                currentMeshes.append(blenderMesh)

                if(vBuffer.getNumVertices()==0):
                    continue

                vertex = vBuffer.getVertex(0)
                if(vertex.getTexcoord1()!=None):
                    uv = blenderMesh.data.uv_layers.new(name="UVMap")
                    uvLayer = uv.data
                    for i in range(iBuffer.getNumIndices()):
                        vertexUV = vBuffer.getVertex(iBuffer.getIndex(i)).getTexcoord1()
                        uvLayer[i].uv = vertexUV
                
                if(vertex.getTexcoord2()!=None):
                    uv = blenderMesh.data.uv_layers.new(name="Shadow Map")
                    uvLayer = uv.data
                    for i in range(iBuffer.getNumIndices()):
                        vertexUV = vBuffer.getVertex(iBuffer.getIndex(i)).getTexcoord2()
                        uvLayer[i].uv = vertexUV

                if(properties.isImportNormals() and vertex.getNormal()!=None):
                    normals = []
                    for i in range(vBuffer.getNumVertices()):
                        normals.append(vBuffer.getVertex(i).getNormal())
                    blenderMesh.data.use_auto_smooth = True
                    blenderMesh.data.normals_split_custom_set_from_vertices(normals)

                # create the material groups

                materialCount = 0 # the amount of materials that actually are assigned to vertices
                materialMap = {}
                for i in range(mesh.getNumMaterialGroups()):
                    mat = mesh.getMaterialGroup(i)
                    material = papaFile.getMaterial(mat.getMaterialIndex())
                    name = papaFile.getString(mat.getNameIndex())

                    if name == "":
                        name = papaFile.getString(model.getNameIndex())+"_Material_"+str(i) # default name if it does not exist

                    blenderMaterial = createMaterial(name, papaFile, material)
                    blenderMesh.data.materials.append(blenderMaterial)
                    
                    if not materialMap.get(material, False):
                        materialMap[material] = len(blenderMesh.data.materials) - 1

                    if mat.getPrimitiveType()!=2: # not triangle
                        print("Cannot apply material group " + str(name)+" (mesh binding index = "+str(m)+", index = "+str(i)+")")
                        continue

                    ind = materialMap[material]
                    for i in range(mat.getFirstIndex()//3, mat.getFirstIndex()//3 + mat.getNumPrimitives()):
                        blenderMesh.data.polygons[i].material_index = ind
                    
                    if mat.getNumPrimitives() != 0: # some materials have no vertices mapped to them
                        materialCount+=1
                
                if papaFile.getNumTextures() > 0: # textures in the file itself, try to find them
                    for i in range(mesh.getNumMaterialGroups()):
                        matGroup = mesh.getMaterialGroup(i)
                        mat = papaFile.getMaterial(matGroup.getMaterialIndex())
                        if mat.getNumTextureParams() == 0:
                            continue # no mapping
                        diffuse = blenderTextureFromMaterial(papaFile, mat, "DiffuseTexture", textureMap)
                        normal = blenderTextureFromMaterial(papaFile, mat, "NormalTexture", textureMap)
                        material = blenderTextureFromMaterial(papaFile, mat, "MaterialTexture", textureMap)
                        isUnitShader = papaFile.getString(mat.getShaderNameIndex()) == "solid"
                        
                        blenderMaterial = blenderMesh.data.materials[materialMap[papaFile.getMaterial(matGroup.getMaterialIndex())]]
                        if isUnitShader:
                            print("Warning: Data implies CSG shader but actual shader was unit shader.")
                        applyTexture(blenderMaterial, diffuse, None, material, normal, isUnitShader)
                elif importedTexture != None: # Auto apply the diffuse, mask, and specular textures
                    blenderMaterial = None
                    isUnitShader = True
                    
                    if materialCount == 1: # only one material with assigned faces, use that
                        for i in range(mesh.getNumMaterialGroups()):
                            mat = mesh.getMaterialGroup(i)
                            if mat.getNumPrimitives == 0:
                                continue
                            blenderMaterial = blenderMesh.data.materials[materialMap[papaFile.getMaterial(mat.getMaterialIndex())]]
                            isUnitShader = papaFile.getString(papaFile.getMaterial(mat.getMaterialIndex()).getShaderNameIndex()) == "solid" # should always be true
                            break
                    else: # Unknown state, just make a new material and override
                        blenderMaterial = bpy.data.materials.new(name=papaFile.getString(model.getNameIndex())+"_Material")
                        blenderMesh.data.materials.append(blenderMaterial)
                        idx = len(blenderMesh.data.materials) - 1

                        for poly in blenderMesh.data.polygons:
                            poly.material_index = idx
                        print("Warning: Unit mesh has multiple materials with faces assigned. This is not known behaviour.")
                    if not isUnitShader:
                        print("Warning: Data implies unit shader but actual shader was CSG shader.")
                    applyTexture(blenderMaterial, importedTexture, importedMask, importedMaterial, None, isUnitShader)
                # Smooth shading
                # If two faces are connected, PA will smooth shade them. Before we remove doubles, we need to respect smooth shading info
                # In blender, the best we can do is guess this, connection data is destroyed when we remove doubles
                # We can assume the original modelers worked in this same environment, so in theory we will get the same result back
                vertexMap = {}
                connectionMap = {}

                # map every vertex to every face that touches it
                for i in range(iBuffer.getNumIndices()):
                    vertex = iBuffer.getIndex(i)
                    face = i // 3
                    if not vertexMap.get(vertex,False):
                        vertexMap[vertex] = []
                    vertexMap[vertex].append(face)

                for i in range(0,iBuffer.getNumIndices(),3):
                    connectionMap[i//3] = set()
                
                # now, using the vertex map we will build a map that maps every face to it's neighbours
                for i in range(iBuffer.getNumIndices()):
                    vertex = iBuffer.getIndex(i)
                    face = i // 3
                    for connectedFace in vertexMap[vertex]:
                        if connectedFace != face:
                            connectionMap[face].add(connectedFace)

                blenderMesh.data.calc_normals() # needed the smooth shade function
                viewedFaces = set()
                edgeKeyMap = {key:i for i,key in enumerate(blenderMesh.data.edge_keys)}
                for face in connectionMap:

                    currentSet = set()
                    shadeSmoothFindConnections(connectionMap, viewedFaces, currentSet, face)
                    shadeSmoothFromData(blenderMesh, currentSet, iBuffer, edgeKeyMap)
                

            # armatures
            if(model.getSkeletonIndex()>=0):
                blenderArmature = createArmatureFromData(papaFile.getString(model.getNameIndex())+"_Armature")
                armatureName = blenderArmature.name
                blenderArmatureData = blenderArmature.data
                editBones = blenderArmatureData.edit_bones
                
                bpy.ops.object.mode_set(mode='OBJECT')
                bpy.context.scene.cursor.location = (0.0,0.0,0.0)  
                bpy.ops.object.origin_set(type='ORIGIN_CURSOR')
                bpy.ops.object.mode_set(mode='EDIT')

                skeleton = papaFile.getSkeleton(model.getSkeletonIndex())
                for b in range(skeleton.getNumBones()):
                    bone = skeleton.getBone(b)
                    boneName = papaFile.getString(bone.getNameIndex())
                    editBones.new(boneName)
                    aBone = editBones[boneName]
                    aBone.use_inherit_rotation = True
                    aBone.use_local_location = False
                    if (bone.getParentBoneIndex() >= 0):
                        parentBone = skeleton.getBone(bone.getParentBoneIndex())
                        aBone.parent = editBones[papaFile.getString(parentBone.getNameIndex())]
                        aBone.head = (0,0,0)
                        aBone.tail = (0,1,0) # head and tail required, but are overwritten

                        # Apply a correction to convert to blender coords
                        q = bone.getRotation()
                        q2 = Quaternion((q[3],q[0],q[1],q[2]))
                        rotationMatrix = q2.to_matrix().to_4x4()

                        # parentBone.getBindToBone().inverted()
                        aBone.matrix = aBone.parent.matrix @ Matrix.Translation(bone.getTranslation()) @ rotationMatrix
                    else:
                        aBone.head = (0,0,0)
                        aBone.tail = (0,1,0) # head and tail required, but are overwritten
                        aBone.matrix = bone.getBindToBone()

                    # for each bone, loop through all vertices in all meshes and check their weight
                    # TODO: bone mappings!
                    for m in range(len(meshGroups)):
                        bufferMeshPair = meshGroups[m]
                        vertexGroup = bufferMeshPair[1].vertex_groups.new(name=boneName)
                        for v in range(bufferMeshPair[0].getNumVertices()):
                            weight = bufferMeshPair[0].getVertex(v).getWeight(b)
                            if(weight!=0):
                                vertexGroup.add([v],weight,"ADD")
                
                # move armature to new collection
                bpy.context.view_layer.objects.active = blenderArmature
                bpy.ops.object.mode_set(mode='OBJECT')
                currentCollection = getCollection(context,blenderArmature)
                currentCollection.objects.unlink(blenderArmature)
                collection.objects.link(blenderArmature)

                # apply parenting and create an armature deform
                for i in range(len(currentMeshes)):
                    currentMeshes[i].parent = blenderArmature

                    modifierName = blenderArmature.name+"_modifier"
                    currentMeshes[i].modifiers.new(name = modifierName, type = "ARMATURE")
                    currentMeshes[i].modifiers[modifierName].object = blenderArmature

            if properties.isConvertToQuads():
                for m in range(len(meshGroups)):
                    bufferMeshPair = meshGroups[m]
                    bpy.context.view_layer.objects.active = bufferMeshPair[1]

                    ops.object.mode_set(mode='EDIT')
                    bpy.ops.mesh.tris_convert_to_quads()
                    ops.object.mode_set(mode='OBJECT')

            # remove doubles
            if properties.isRemoveDoubles():
                for m in range(len(meshGroups)):
                    bufferMeshPair = meshGroups[m]
                    bpy.context.view_layer.objects.active = bufferMeshPair[1]
                    
                    ops.object.mode_set(mode='EDIT')
                    ops.mesh.remove_doubles(threshold=0.0001)
                    ops.object.mode_set(mode='OBJECT')
                    
                    # move mesh to new collection
                    currentCollection = getCollection(context,blenderMesh)
                    currentCollection.objects.unlink(blenderMesh)
                    collection.objects.link(blenderMesh)
        
    if(papaFile.getNumAnimations() > 0):

        if(papaFile.getNumAnimations() > 1):
            print("Warn: Importer does not support multiple animations in a single file.\nOnly the first animation will be imported.")

        animation = papaFile.getAnimation(0)

        if(animation.getAnimationSpeed() != bpy.context.scene.render.fps):
            bpy.context.scene.render.fps=animation.getAnimationSpeed() 
            print("Scene FPS changed to:", animation.getAnimationSpeed())
        
        bpy.context.scene.frame_start = 0
        bpy.context.scene.frame_end = animation.getNumFrames() - 1
        print("Scene length set to:", animation.getNumFrames() - 1)

        animTargetArmature = None
        if('armatureName' in locals()): # armature was made above, pick the armature
            animTargetArmature = bpy.data.objects[armatureName]
            print("Target armature "+str(armatureName)+" bundled in file... Selecting")
        else:
            animTargetArmature = findFirstValidArmature(animation, properties)
            if(not animTargetArmature):
                return 'ERROR','Failed to find valid armature for animation'
            else:
                print("Found target armature: "+animTargetArmature.name)

        # create action for armature
        action = bpy.data.actions.new(name=file_name)
        if not animTargetArmature.animation_data:
            animTargetArmature.animation_data_create() # create animation_data if it doesn't exist yet
        animTargetArmature.animation_data.action = action # link to action

        # correct each bone to a format that blender accepts
        for bone in animTargetArmature.pose.bones:
            processBone(bone, animation)

        # apply the transforms
        for i in range(animation.getNumBones()):
            currentBone = animation.getAnimationBone(i)
            try:
                bone = animTargetArmature.data.bones[currentBone.getName()]
            except KeyError as e:
                continue # we allow some misses with fuzzy
            
            group = action.groups.new(name=currentBone.getName())
            boneString = "pose.bones[\""+currentBone.getName()+"\"]."
            curvesLoc = []
            curvesRot = []
            
            for i in range(3): # set up groups for location
                curve = action.fcurves.new(data_path=boneString + "location",index=i)
                curve.group = group
                curvesLoc.append(curve)
            for i in range(4): # set up groups for rotation
                curve = action.fcurves.new(data_path=boneString + "rotation_quaternion",index=i)
                curve.group = group
                curvesRot.append(curve)

            # apply bone positions and rotations
            for frame in range(animation.getNumFrames()):
                for i in range(3):
                    curvesLoc[i].keyframe_points.insert(frame=frame,value=currentBone.getTranslation(frame)[i])
                for i in range(4):
                    curvesRot[i].keyframe_points.insert(frame=frame,value=currentBone.getRotation(frame)[i])


def blenderTextureFromMaterial(papaFile: PapaFile, material: PapaMaterial, paramName: str, textureMap=None):
    try:
        param = material.getTextureParamByName(papaFile, paramName)
        if param:
            texture = papaFile.getTexture(param.getTextureIndex())
            if texture:
                name = papaFile.getString(texture.getNameIndex())
                if textureMap == None:
                    return bpy.data.images[name]
                return textureMap[name]
    except Exception as e:
        print("Error finding texture for parameter "+paramName+". Skipping. ("+str(e)+")")

def shadeSmoothFindConnections(map: set, viewed: set, connections: set, startFace: int):
    openList = [startFace] # Python's stack is small, so we implement this iteratively instead of recursively
    tempList = []

    while len(openList)!=0:

        for i in range(len(openList)):
            face = openList[i]
            if(face in viewed):
                continue
            viewed.add(face)
            connections.add(face)

            if not face in map:
                continue # has no connections
            
            for p in map[face]:
                tempList.append(p)
        
        openList = tempList # swap lists
        tempList = []

def shadeSmoothFromData(blenderMesh, currentSet: set, iBuffer: PapaIndexBuffer, edgeKeyMap: dict):
    if(len(currentSet) <= 2): # preliminary check, skip quad-triangulated faces
        return

    triangulated = False
    items = list(currentSet)

    ib = iBuffer.getIndex
    vb = blenderMesh.data.vertices
    n = vb[ib(items[0] * 3)].normal # we can't use the vertex normals from the file as they are calculated before the mesh is broken apart, so normals may differ
    triangulated = True

    cmp = vectorsEqualWithinTolerance
    # determine if it was just a triangulation, or if it was actually connected
    for face in items:
        idx = face * 3
        
        # 100% unreadable but 100% worth it for the one line
        if(not cmp(vb[ib(idx)].normal, n, 0.01) or not cmp(vb[ib(idx + 1)].normal, n, 0.01) or not cmp(vb[ib(idx + 2)].normal, n, 0.01)): 
            triangulated = False
            break

    # create the edge seams (fix for if two smooth shaded sections are next to eachother)
    if not triangulated:
        for p in items:
            blenderMesh.data.polygons[p].use_smooth = True

        edgeMap = {}
        for face in currentSet:
            for edgeKey in blenderMesh.data.polygons[face].edge_keys:
                if not edgeKeyMap.get(edgeKey, False): # weird case where the edge doesn't actually exist?
                    continue
                if not edgeMap.get(edgeKey, False):
                    edgeMap[edgeKey] = 0
                edgeMap[edgeKey] += 1
        
        for edge in edgeMap:
            if edgeMap[edge] < 2:
                blenderMesh.data.edges[edgeKeyMap[edge]].use_edge_sharp = True

def vectorsEqualWithinTolerance(v1, v2, tolerance):
    return abs(v1[0]-v2[0]) < tolerance and abs(v1[1]-v2[1]) < tolerance and abs(v1[2]-v2[2]) < tolerance

def extractTexture(filepath, append, textureMap):
    idx = filepath.rfind('.')
    if(idx==-1):
        idx = len(filepath)
    left = filepath[:idx]
    right = filepath[idx:]

    target = left + append + right
    if not path.isfile(target): # couldn't find the texture
        return None

    textureFile = PapaFile(target)
    print("Auto imported texture file "+target)

    if(textureFile.getNumTextures()>0):
        texture = textureFile.getTexture(0) # only import the first
        name = textureFile.getString(texture.getNameIndex())
        return createImageFromData(name,texture.getImageData(),texture.getWidth(),texture.getHeight(), texture.getSRGB(), texture.getFilepath(), texMap=textureMap)
    return None

def applyTexture(blenderMaterial, diffuse, mask, material, normal, unit):
    if unit:
        applyTextureSolid(blenderMaterial, diffuse, mask, material) # Unit shader
    else:
        applyTextureTextured(blenderMaterial, diffuse, material, normal) # CSG shader
    
    if diffuse:
        blenderMaterial[PapaExportMaterial.TEXTURE_EXTENSTION] = diffuse[PapaExportMaterial.PAPAFILE_SOURCE_EXTENSION]
    if mask:
        blenderMaterial[PapaExportMaterial.MASK_EXTENSION] = mask[PapaExportMaterial.PAPAFILE_SOURCE_EXTENSION]
    if material:
        blenderMaterial[PapaExportMaterial.MATERIAL_EXTENSION] = material[PapaExportMaterial.PAPAFILE_SOURCE_EXTENSION]
    if normal:
        blenderMaterial[PapaExportMaterial.NORMAL_EXTENSTION] = normal[PapaExportMaterial.PAPAFILE_SOURCE_EXTENSION]
    
    # set the shading to be material preview if it's not already
    # https://blender.stackexchange.com/a/124427
    areas = bpy.context.workspace.screens[0].areas
    for area in areas:
        for space in area.spaces:
            if space.type == "VIEW_3D":
                space.shading.type = "MATERIAL"
        
def applyTextureTextured(blenderMaterial, diffuse, material, normal):
    if diffuse:
        blenderMaterial.use_nodes = True
        out = blenderMaterial.node_tree.nodes["Material Output"]

        bsdf = blenderMaterial.node_tree.nodes["Principled BSDF"]
        bsdf.inputs["Specular"].default_value = 0
        bsdf.inputs["Metallic"].default_value = 0
        bsdf.location.x = out.location.x - 570
        bsdf.location.y = out.location.y + 650

        texImage = blenderMaterial.node_tree.nodes.new("ShaderNodeTexImage")
        texImage.image = diffuse
        blenderMaterial.node_tree.links.new(bsdf.inputs["Base Color"], texImage.outputs["Color"])
        texImage.location.x = bsdf.location.x - 350
        texImage.location.y = bsdf.location.y - 400

        if material: # r = specular, g = sharpness, b = emissive
            texmaterial = blenderMaterial.node_tree.nodes.new("ShaderNodeTexImage")
            texmaterial.image = material
            texmaterial.location.x = texImage.location.x - 600
            texmaterial.location.y = texImage.location.y + 300

            sepRGBmaterial = blenderMaterial.node_tree.nodes.new("ShaderNodeSeparateRGB")
            blenderMaterial.node_tree.links.new(sepRGBmaterial.inputs[0], texmaterial.outputs["Color"]) # link inverted material to separate
            sepRGBmaterial.location.x = bsdf.location.x - 650
            sepRGBmaterial.location.y = bsdf.location.y
            blenderMaterial.node_tree.links.new(bsdf.inputs["Specular"], sepRGBmaterial.outputs["R"]) # link red to material on bsdf

            invert = blenderMaterial.node_tree.nodes.new("ShaderNodeInvert")
            blenderMaterial.node_tree.links.new(invert.inputs["Color"], texmaterial.outputs["Color"]) # invert the blenderMaterial
            invert.inputs[0].default_value = 1
            invert.location.x = bsdf.location.x - 650
            invert.location.y = bsdf.location.y - 150

            sepRGBmaterialInv = blenderMaterial.node_tree.nodes.new("ShaderNodeSeparateRGB")
            blenderMaterial.node_tree.links.new(sepRGBmaterialInv.inputs[0], invert.outputs["Color"]) # link inverted material to separate
            sepRGBmaterialInv.location.x = bsdf.location.x - 400
            sepRGBmaterialInv.location.y = bsdf.location.y - 150

            blenderMaterial.node_tree.links.new(bsdf.inputs["Roughness"], sepRGBmaterialInv.outputs["G"]) # link inverted green to roughness on bsdf

            # the glow is not inverted
            sepRGBRawmaterial = blenderMaterial.node_tree.nodes.new("ShaderNodeSeparateRGB")
            blenderMaterial.node_tree.links.new(sepRGBRawmaterial.inputs[0], texmaterial.outputs["Color"]) # link inverted material to separate
            sepRGBRawmaterial.location.x = bsdf.location.x - 650
            sepRGBRawmaterial.location.y = bsdf.location.y - 250

            # add mix
            mix = blenderMaterial.node_tree.nodes.new("ShaderNodeMixShader")
            mix.location.x = out.location.x - 225
            mix.location.y = out.location.y
            blenderMaterial.node_tree.links.new(mix.inputs["Fac"], sepRGBRawmaterial.outputs["B"]) # link the blue channel into emission strength

            # add emission
            emission = blenderMaterial.node_tree.nodes.new("ShaderNodeEmission")
            emission.location.x = mix.location.x - 300
            emission.location.y = mix.location.y - 150
            blenderMaterial.node_tree.links.new(emission.inputs["Color"], texImage.outputs["Color"]) # link the colour into the emission shader

            blenderMaterial.node_tree.links.new(mix.inputs[1], bsdf.outputs[0]) # link BSDF to mix Shader 1
            blenderMaterial.node_tree.links.new(mix.inputs[2], emission.outputs[0]) # link Emission to mix shader 2

            # link the mix shader to the output
            blenderMaterial.node_tree.links.new(out.inputs["Surface"], mix.outputs["Shader"]) # link Emission to shader 2

        if normal:
            texNormal = blenderMaterial.node_tree.nodes.new("ShaderNodeTexImage")
            texNormal.image = normal
            normal.colorspace_settings.name = "Non-Color"
            blenderMaterial.node_tree.links.new(bsdf.inputs["Normal"], texNormal.outputs["Color"])
            texNormal.location.x = bsdf.location.x - 1800
            texNormal.location.y = bsdf.location.y - 875

            # normal in PA is a dual channel normal.
            # Alpha -> X
            # Green -> Y
            # solve for Z
            # https://blender.stackexchange.com/questions/105032/trying-to-convert-a-dxt5nm-normal-map-for-use-in-my-scene

            # add searate node
            sepRGB = blenderMaterial.node_tree.nodes.new("ShaderNodeSeparateRGB")
            blenderMaterial.node_tree.links.new(sepRGB.inputs[0], texNormal.outputs["Color"]) # link normal to separate
            sepRGB.location.x = bsdf.location.x - 1450
            sepRGB.location.y = bsdf.location.y - 750

            # Green ^ 2
            multiplyGreen = blenderMaterial.node_tree.nodes.new("ShaderNodeMath")
            multiplyGreen.operation = "MULTIPLY"
            blenderMaterial.node_tree.links.new(multiplyGreen.inputs[0], sepRGB.outputs["G"])
            blenderMaterial.node_tree.links.new(multiplyGreen.inputs[1], sepRGB.outputs["G"])
            multiplyGreen.location.x = bsdf.location.x - 1200
            multiplyGreen.location.y = bsdf.location.y - 950

            # Alpha ^ 2
            multiplyAlpha = blenderMaterial.node_tree.nodes.new("ShaderNodeMath")
            multiplyAlpha.operation = "MULTIPLY"
            blenderMaterial.node_tree.links.new(multiplyAlpha.inputs[0], texNormal.outputs["Alpha"])
            blenderMaterial.node_tree.links.new(multiplyAlpha.inputs[1], texNormal.outputs["Alpha"])
            multiplyAlpha.location.x = bsdf.location.x - 1200
            multiplyAlpha.location.y = bsdf.location.y - 1150

            # Combine terms
            addGreenAlpha = blenderMaterial.node_tree.nodes.new("ShaderNodeMath")
            addGreenAlpha.operation = "ADD"
            blenderMaterial.node_tree.links.new(addGreenAlpha.inputs[0], multiplyGreen.outputs["Value"])
            blenderMaterial.node_tree.links.new(addGreenAlpha.inputs[1], multiplyAlpha.outputs["Value"])
            addGreenAlpha.location.x = bsdf.location.x - 1000
            addGreenAlpha.location.y = bsdf.location.y - 1050

            # 1 - (G^2 + A^2)
            subtract = blenderMaterial.node_tree.nodes.new("ShaderNodeMath")
            subtract.operation = "SUBTRACT"
            subtract.inputs[0].default_value = 1
            blenderMaterial.node_tree.links.new(subtract.inputs[1], addGreenAlpha.outputs["Value"])
            subtract.location.x = bsdf.location.x - 850
            subtract.location.y = bsdf.location.y - 1050

            # sqrt(1 - (G^2 + A^2))
            power = blenderMaterial.node_tree.nodes.new("ShaderNodeMath")
            power.operation = "POWER"
            blenderMaterial.node_tree.links.new(power.inputs[0], subtract.outputs["Value"])
            power.inputs[1].default_value = 0.5
            power.location.x = bsdf.location.x - 700
            power.location.y = bsdf.location.y - 1050

            # recombine back into vector data
            combineXYZ = blenderMaterial.node_tree.nodes.new("ShaderNodeCombineXYZ")
            blenderMaterial.node_tree.links.new(combineXYZ.inputs["X"], texNormal.outputs["Alpha"])
            blenderMaterial.node_tree.links.new(combineXYZ.inputs["Y"], sepRGB.outputs["G"])
            blenderMaterial.node_tree.links.new(combineXYZ.inputs["Z"], power.outputs["Value"])
            combineXYZ.location.x = bsdf.location.x - 550
            combineXYZ.location.y = bsdf.location.y - 850

            # Turn into normal map
            normalMap = blenderMaterial.node_tree.nodes.new("ShaderNodeNormalMap")
            blenderMaterial.node_tree.links.new(normalMap.inputs["Color"], combineXYZ.outputs["Vector"])
            normalMap.location.x = bsdf.location.x - 300
            normalMap.location.y = bsdf.location.y - 850

            blenderMaterial.node_tree.links.new(bsdf.inputs["Normal"], normalMap.outputs["Normal"]) # link inverted green to roughness on bsdf

def applyTextureSolid(blenderMaterial, diffuse, mask, material): # Unit shader
    if diffuse and mask:
        blenderMaterial.use_nodes = True
        out = blenderMaterial.node_tree.nodes["Material Output"]

        bsdf = blenderMaterial.node_tree.nodes["Principled BSDF"]
        bsdf.inputs["Specular"].default_value = 0
        bsdf.inputs["Metallic"].default_value = 0.5
        bsdf.location.x = out.location.x - 570
        bsdf.location.y = out.location.y + 650

        # add mix
        mix = blenderMaterial.node_tree.nodes.new("ShaderNodeMixShader")
        mix.location.x = out.location.x - 225
        mix.location.y = out.location.y

        # add emission
        emission = blenderMaterial.node_tree.nodes.new("ShaderNodeEmission")
        emission.location.x = mix.location.x - 300
        emission.location.y = mix.location.y - 150

        blenderMaterial.node_tree.links.new(mix.inputs[1], bsdf.outputs[0]) # link BSDF to mix Shader 1
        blenderMaterial.node_tree.links.new(mix.inputs[2], emission.outputs[0]) # link Emission to mix shader 2

        # link the mix shader to the output
        blenderMaterial.node_tree.links.new(out.inputs["Surface"], mix.outputs["Shader"]) # link Emission to shader 2

        # add diffuse
        texImage = blenderMaterial.node_tree.nodes.new("ShaderNodeTexImage")
        texImage.image = diffuse
        texImage.location.x = bsdf.location.x - 1050
        texImage.location.y = bsdf.location.y - 400

        # Contradicatory to the documentation, Blender will premultiply the alpha unless the alpha channel is used
        discard = blenderMaterial.node_tree.nodes.new("ShaderNodeMath")
        discard.label = "Discard"
        discard.hide = True
        discard.inputs[1].default_value = 0
        blenderMaterial.node_tree.links.new(discard.inputs[0], texImage.outputs["Alpha"])
        discard.location.x = bsdf.location.x - 800
        discard.location.y = bsdf.location.y - 475

        # add mask
        texMask = blenderMaterial.node_tree.nodes.new("ShaderNodeTexImage")
        texMask.image = mask
        texMask.location.x = bsdf.location.x - 1450
        texMask.location.y = bsdf.location.y - 1000

        # add searate node
        sepRGB = blenderMaterial.node_tree.nodes.new("ShaderNodeSeparateRGB")
        blenderMaterial.node_tree.links.new(sepRGB.inputs[0], texMask.outputs["Color"]) # link Mask to separate
        sepRGB.location.x = mix.location.x - 1450
        sepRGB.location.y = mix.location.y - 300

        # link blue of mask to mix shader factor
        blenderMaterial.node_tree.links.new(mix.inputs[0], sepRGB.outputs[2]) 

        # recombine red and green to act as a factor
        combineRGB = blenderMaterial.node_tree.nodes.new("ShaderNodeCombineRGB")
        blenderMaterial.node_tree.links.new(combineRGB.inputs[0], sepRGB.outputs[0])
        blenderMaterial.node_tree.links.new(combineRGB.inputs[1], sepRGB.outputs[1])
        combineRGB.location.x = mix.location.x - 1150
        combineRGB.location.y = mix.location.y - 150

        # remap R and G to be the PA default colours (blue and yellow respecitvely)
        colourRampRed = blenderMaterial.node_tree.nodes.new("ShaderNodeValToRGB")
        blenderMaterial.node_tree.links.new(colourRampRed.inputs[0], sepRGB.outputs[0])
        colourRampRed.color_ramp.elements[1].color = (0,0.486,1,1)
        colourRampRed.location.x = mix.location.x - 1150
        colourRampRed.location.y = mix.location.y - 400

        colourRampGreen = blenderMaterial.node_tree.nodes.new("ShaderNodeValToRGB")
        blenderMaterial.node_tree.links.new(colourRampGreen.inputs[0], sepRGB.outputs[1])
        colourRampGreen.color_ramp.elements[1].color = (1,0.394,0,1)
        colourRampGreen.location.x = colourRampRed.location.x
        colourRampGreen.location.y = colourRampRed.location.y - 250
        
        # combine the remapped colours
        mixRGBLighten = blenderMaterial.node_tree.nodes.new("ShaderNodeMixRGB")
        mixRGBLighten.blend_type = "ADD"
        mixRGBLighten.inputs["Fac"].default_value = 1
        blenderMaterial.node_tree.links.new(mixRGBLighten.inputs["Color1"], colourRampRed.outputs["Color"]) # apply our initial colours
        blenderMaterial.node_tree.links.new(mixRGBLighten.inputs["Color2"], colourRampGreen.outputs["Color"]) # apply our mapped mask values
        mixRGBLighten.location.x = mix.location.x - 800
        mixRGBLighten.location.y = mix.location.y - 350

        # add colour ramp
        colourRamp = blenderMaterial.node_tree.nodes.new("ShaderNodeValToRGB")
        blenderMaterial.node_tree.links.new(colourRamp.inputs[0], combineRGB.outputs[0])
        colourRamp.color_ramp.elements[0].position = (0.095) # remap the node
        colourRamp.color_ramp.elements[1].position = (0.1)
        colourRamp.location.x = bsdf.location.x - 600
        colourRamp.location.y = bsdf.location.y - 500

        # add mix RGB node
        mixRGB = blenderMaterial.node_tree.nodes.new("ShaderNodeMixRGB")
        mixRGB.blend_type = "OVERLAY"
        blenderMaterial.node_tree.links.new(mixRGB.inputs["Color1"], texImage.outputs["Color"]) # apply our initial colours
        blenderMaterial.node_tree.links.new(mixRGB.inputs["Color2"], mixRGBLighten.outputs["Color"]) # apply our mapped mask values
        blenderMaterial.node_tree.links.new(mixRGB.inputs["Fac"], colourRamp.outputs["Color"]) # set the factor to be the color ramp
        mixRGB.location.x = bsdf.location.x - 250
        mixRGB.location.y = bsdf.location.y - 350

        blenderMaterial.node_tree.links.new(bsdf.inputs["Base Color"], mixRGB.outputs["Color"]) # link the mixed colour into the BSDF shader
        blenderMaterial.node_tree.links.new(emission.inputs["Color"], mixRGB.outputs["Color"]) # link the mixed colour into the emission shader
        if material: # add material components
            texmaterial = blenderMaterial.node_tree.nodes.new("ShaderNodeTexImage")
            texmaterial.image = material
            texmaterial.location.x = texImage.location.x
            texmaterial.location.y = texImage.location.y + 300

            sepRGBmaterial = blenderMaterial.node_tree.nodes.new("ShaderNodeSeparateRGB")
            blenderMaterial.node_tree.links.new(sepRGBmaterial.inputs[0], texmaterial.outputs["Color"]) # link inverted material to separate
            sepRGBmaterial.location.x = bsdf.location.x - 650
            sepRGBmaterial.location.y = bsdf.location.y
            blenderMaterial.node_tree.links.new(bsdf.inputs["Specular"], sepRGBmaterial.outputs["R"]) # link red to material on bsdf

            invert = blenderMaterial.node_tree.nodes.new("ShaderNodeInvert")
            blenderMaterial.node_tree.links.new(invert.inputs["Color"], texmaterial.outputs["Color"]) # invert the blenderMaterial
            invert.inputs[0].default_value = 1
            invert.location.x = bsdf.location.x - 650
            invert.location.y = bsdf.location.y - 150

            sepRGBmaterialInv = blenderMaterial.node_tree.nodes.new("ShaderNodeSeparateRGB")
            blenderMaterial.node_tree.links.new(sepRGBmaterialInv.inputs[0], invert.outputs["Color"]) # link inverted material to separate
            sepRGBmaterialInv.location.x = bsdf.location.x - 400
            sepRGBmaterialInv.location.y = bsdf.location.y - 150

            blenderMaterial.node_tree.links.new(bsdf.inputs["Roughness"], sepRGBmaterialInv.outputs["G"]) # link inverted green to roughness on bsdf
    elif diffuse: # try just diffuse if we missed all components
        blenderMaterial.use_nodes = True
        bsdf = blenderMaterial.node_tree.nodes["Principled BSDF"]
        bsdf.inputs["Specular"].default_value = 0
        bsdf.inputs["Metallic"].default_value = 0.5

        texImage = blenderMaterial.node_tree.nodes.new("ShaderNodeTexImage")
        texImage.image = diffuse
        blenderMaterial.node_tree.links.new(bsdf.inputs["Base Color"], texImage.outputs["Color"])
        texImage.location.x = bsdf.location.x - 1000
        texImage.location.y = bsdf.location.y - 400
 
def findFirstValidArmature(animation: PapaAnimation, properties):
    for obj in bpy.context.scene.objects: 
        if(obj.type != "ARMATURE"):
            continue
        if(hasAllBones(obj, animation, properties, True)):
            return obj
    return None

def hasAllBones(armature, animation, properties, log):
    maxMisses = ceil(animation.getNumBones() / 10) # must be at least 90% accurate for fuzzy
    currentMisses = 0
    for x in range(animation.getNumBones()):
        name = animation.getAnimationBone(x).getName()
        if not armature.data.bones.get(name):

            if(properties.isFuzzyMatch()): # allow some inaccuracy (PA is weird)
                currentMisses += 1
                if(log):
                    print("Failed to find bone \""+animation.getAnimationBone(x).getName()+"\" in armatue \""+armature.name+"\" (ignored)")
                if(currentMisses < maxMisses):
                    continue
            
            if(log):
                print("Failed to find bone \""+animation.getAnimationBone(x).getName()+"\" in armatue \""+armature.name+"\"")
            return False
    return True

def processBone(poseBone, animation):
    animBone = animation.getAnimationBone(poseBone.name)
    if not animBone: # no data for this bone.
        return
    
    if poseBone.parent:
        # locations in blender are all relative to the edit bone position, however our numbers are relative to the parent bone.
        # we must translate our data into global space by multiplying by the parent matrix and then
        # transform into local space multiply by our bone's inverse matrix
        commonMatrix = poseBone.matrix.inverted() @ poseBone.parent.matrix

        # However, in applying the transformation to the location we correctly move the bones into place,
        # but we apply an unnecessary rotation which causes the axis to be rotated strangely. This means offsets will be mapped incorrectly
        # in order to fix this, we must perform our matrix operations in reverse to build a correction matrix
        _,cr,_ = (poseBone.parent.matrix.inverted() @ poseBone.matrix).decompose()
        locationCorrectionMatrix = cr.to_matrix().to_4x4()

        for x in range(animation.getNumFrames()): # both rotation and translation processed here.

            # The rotation component can be applied like normal
            q = animBone.getRotation(x)
            correctedRotation = Quaternion((q[3],q[0],q[1],q[2]))
            matrix = commonMatrix @ correctedRotation.to_matrix().to_4x4()
            _,r,_ = matrix.decompose()

            # apply our correction matrix to just the location to fix it
            matrix = locationCorrectionMatrix @ commonMatrix @ Matrix.Translation(animBone.getTranslation(x))
            l,_,_ = matrix.decompose()
            

            animBone.setTranslation(x,l)
            animBone.setRotation(x,r)
    else:
        for x in range(animation.getNumFrames()):
            # positions are already in global space.
            q = animBone.getRotation(x)
            correctedRotation = Quaternion((q[3],q[0],q[1],q[2]))
            matrix = poseBone.matrix.inverted() @ Matrix.Translation(animBone.getTranslation(x)) @ correctedRotation.to_matrix().to_4x4()
            
            l,r,_ = (matrix).decompose()

            animBone.setTranslation(x,l)
            animBone.setRotation(x,r)

def createMaterial(name: str, papaFile: PapaFile, material: PapaMaterial):
    mat = bpy.data.materials.new(name=name)

    col = material.getVectorParamByName(papaFile,"DiffuseColor")
    if(col):
        mat.diffuse_color = list(col.getVector().to_tuple())
        mat.diffuse_color[3] = 1 - mat.diffuse_color[3] # opacity to alpha
        if(mat.diffuse_color[3] == 0):
            mat.diffuse_color[3] = 1
            print("Transparent colour for material \""+papaFile.getString(material.getShaderNameIndex())+"\", Ignoring.")

    knownParameters = {
        "DiffuseColor":True,
        "DiffuseTexture":True, # handled in import phase
        "NormalTexture":True, # handled in import phase
        "MaterialTexture":True, # handled in import phase
    }

    for x in range(material.getNumVectorParams()):
        shaderName = papaFile.getString(material.getVectorParam(x).getNameIndex())
        if not knownParameters.get(shaderName, False):
            print("Unknown Vector Parameter: " + shaderName)

    for x in range(material.getNumTextureParams()):
        shaderName = papaFile.getString(material.getTextureParam(x).getNameIndex())
        if not knownParameters.get(shaderName, False):
            print("Unknown Texture Parameter: " + shaderName)

    for x in range(material.getNumMatrixParams()):
        shaderName = papaFile.getString(material.getMatrixParam(x).getNameIndex())
        if not knownParameters.get(shaderName, False):
            print("Unknown Matrix Parameter: " + shaderName)
    
    return mat

def createMeshFromData(name: str, vBuffer: PapaVertexBuffer, iBuffer: PapaIndexBuffer, transform: Matrix):
    # Create mesh and object
    me = bpy.data.meshes.new(name)
    ob = bpy.data.objects.new(name, me)
 
    # Link object to scene and make active
    scn = bpy.context.scene
    scn.collection.objects.link(ob)
    for i in bpy.context.selected_objects: 
        i.select_set(False) #deselect all objects
    ob.select_set(True)

    verts = []
    faces = []
    for i in range(vBuffer.getNumVertices()):
        verts.append(vBuffer.getVertex(i).getPosition().to_tuple())

    for i in range(0, iBuffer.getNumIndices(), 3):
        faces.append((iBuffer.getIndex(i),iBuffer.getIndex(i + 1),iBuffer.getIndex(i + 2)))
    
    components = transform.decompose()

    ob.location=list(components[0].to_tuple())
    ob.rotation_quaternion = components[1]
    ob.scale = list(components[2].to_tuple())

    # Create mesh from given verts, faces.
    me.from_pydata(verts, [], faces)
    # Update mesh with new data
    me.update()
    
    return ob

def createArmatureFromData(name):
    # Create armature and object
    #amt = bpy.data.armatures.new(name+'Amt')
    bpy.ops.object.add(type='ARMATURE', location=(0,0,0))
    ob = bpy.context.object
    ob.name = name
    amt = ob.data
    amt.name = name+'Amt'
    ob.show_name = True
 
    # Link object to scene and make active
    for i in bpy.context.selected_objects: 
        i.select_set(False) #deselect all objects
    ob.select_set(True)
 
    return ob

def getCollection(context, item):
    collections = item.users_collection
    if len(collections) > 0:
        return collections[0]
    return context.scene.collection

# https://blender.stackexchange.com/questions/643/is-it-possible-to-create-image-data-and-save-to-a-file-from-a-script
def createImageFromData(imageName, pixels, width, height, srgb, filepath, texMap = None): # assumed data is in RGBA byte array (as floats)
    img = bpy.data.images.new(imageName, width, height,alpha=True)
    img.pixels = pixels
    img.pack() # by packing the data, we can edit the name colour space
    if not srgb:
        img.colorspace_settings.name = "Linear"
    img[PapaExportMaterial.PAPAFILE_SOURCE_EXTENSION] = filepath
    if texMap != None:
        texMap[imageName] = img # workaround for name clashes and 63 character name limit
    return img

def load(operator,context,properties):
    t = time.time()
    result = load_papa(properties,context)
    t = time.time() - t
    print("Done in "+str(int(t*1000)) + "ms")
    if result:
        operator.report({result[0]}, result[1])
        return {'CANCELLED'}

    return {'FINISHED'}