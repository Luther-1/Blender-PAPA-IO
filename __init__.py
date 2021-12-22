bl_info = {
    "name": "Planetary Annihilation Legion Utils",
    "author": "Luther",
    "version": (1, 0, 0),
    "blender": (3, 0, 0),
    "location": "Search",
    "description": "Various utility functions",
    "warning": "",
    "wiki_url": "",
    "tracker_url": "",
    "category": "Utility"
}

import bpy
from bpy_extras import mesh_utils;
from mathutils import Vector
from bpy.props import *
from math import inf, radians, log2
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
DISTANCE_FIELD_TEXTURE = "__PAPA_IO_DISTANCE_FIELD"
DISTANCE_FIELD_MATERIAL = "__PAPA_IO_DISTANCE_FIELD_MATERIAL"
DISTANCE_FIELD_TEXEL_INFO = "__PAPA_IO_DISTANCE_FIELD_TEXEL_INFO"

def selectObject(obj):
    for i in bpy.context.selected_objects: 
        i.select_set(False) #deselect all objects
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj

def duplicateObject(obj, newName):
    n = obj.copy()
    n.data = obj.data.copy()
    n.name = newName
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

class SetupDiffuse(bpy.types.Operator):
    """Copies a mesh and creates only the diffuse details of it"""
    bl_idname = "setup_diffuse.legion_utils"
    bl_label = "Legion Setup Diffuse"
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
        diffuse = duplicateObject(obj,"diffuse")
        diffuse.data.materials.clear()
        diffuse.location[0]+=diffuse.dimensions.x * 2
        diffuse[OBJ_NAME_STRING] = obj[OBJ_NAME_STRING]
        diffuse[OBJ_TYPE_STRING] = "DIFFUSE"
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

        

class SetupBake(bpy.types.Operator):
    """Copies a mesh and creates all the bake details of it"""
    bl_idname = "setup_bake.legion_utils"
    bl_label = "Legion Setup Bake"
    bl_options = {'UNDO'}
    
    def execute(self, context):
        diffuse = None
        for obj in bpy.context.selected_objects:
            if getObjectType(obj) == "DIFFUSE":
                diffuse = obj
                break

        if not diffuse:
            self.report({'ERROR'},"Diffuse object not given")

        try:
            size = diffuse[TEX_SIZE_INT]
            name = diffuse[OBJ_NAME_STRING]
        except:
            self.report({'ERROR'},"Selected object must have been previously created by \"setup diffuse\"")
            return {'CANCELLED'}

        self.setupObject(diffuse, size, name)

        return {'FINISHED'}
    
    def invoke(self, context, event):
        return self.execute(context)

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

    def setupObject(self, obj, texSize, name):
        materialMap = self.getMaterialMap(obj)

        # create the material object
        texname = name+"_material_bake"
        materialTex = getOrCreateImage(texname,texSize)
        material = duplicateObject(obj,"material")
        material.data.materials.clear()
        material.location[0]+=material.dimensions.x * 2
        material[OBJ_NAME_STRING] = obj[OBJ_NAME_STRING]
        material[OBJ_TYPE_STRING] = "MATERIAL"
        material[TEX_NAME_STRING] = texname
        material[TEX_SHOULD_BAKE] = True
        material[TEX_SHOULD_SUPERSAMPLE] = True
        material[TEX_SIZE_INT] = obj[TEX_SIZE_INT]
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
        mask = duplicateObject(obj,"mask")
        mask.data.materials.clear()
        mask.location[0]+=mask.dimensions.x * 4
        mask[OBJ_NAME_STRING] = obj[OBJ_NAME_STRING]
        mask[OBJ_TYPE_STRING] = "MASK"
        mask[TEX_NAME_STRING] = texname
        mask[TEX_SHOULD_BAKE] = True
        mask[TEX_SHOULD_SUPERSAMPLE] = True
        mask[TEX_SIZE_INT] = obj[TEX_SIZE_INT]
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
        ao = duplicateObject(obj,"ao")
        ao.data.materials.clear()
        ao.location[0]+=ao.dimensions.x * 6
        ao[OBJ_NAME_STRING] = obj[OBJ_NAME_STRING]
        ao[OBJ_TYPE_STRING] = "AO"
        ao[TEX_NAME_STRING]=texname
        ao[TEX_SHOULD_BAKE] = True
        ao[TEX_SHOULD_SUPERSAMPLE] = True
        ao[TEX_SIZE_INT] = obj[TEX_SIZE_INT]
        if ao.dimensions.x < 10:
            ao.location[0]+= ao.dimensions.x
        bpy.context.collection.objects.link(ao)

        matData = ao.data.materials
        matData.append(createMaterial("ao_bake",(0xff,0xff,0xff),aoTex,attach=True))
        matData.append(createMaterial("ao_bake_ignore",(0xff,0xff,0xff),aoTex,attach=False))

        self.assignFacesAO(materialMap,ao,"ao_bake_ignore")


class SetupMaterialbake(bpy.types.Operator):
    """Creates a material bake for the material object which incorporates the edge highlights"""
    bl_idname = "setup_materialbake.legion_utils"
    bl_label = "Legion Setup Material Bake"
    bl_options = {'UNDO'}
    
    def execute(self, context):
        obj = bpy.context.active_object
        if not obj:
            self.report({'ERROR'},"No Object given")

        material = None
        edgeHighlights = None

        for obj in bpy.context.selected_objects:
            t = getObjectType(obj)
            if t == "MATERIAL":
                material = obj
            if t == "EDGE_HIGHLIGHT":
                edgeHighlights = obj

        if not material or not edgeHighlights:
            self.report({'ERROR'},"Selected objects should contain the material object and edge highlight object")
            return {'CANCELLED'}


        self.setupObject(material, edgeHighlights)

        return {'FINISHED'}
    
    def setupObject(self, materialObj, edgeHighlight):
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
            return

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

        self.report({"INFO"},"Material successfully updated")

class BakeSelectedObjects(bpy.types.Operator):
    """Bakes all selected objects' textures."""
    bl_idname = "bake_objects.legion_utils"
    bl_label = "Legion Bake Objects"
    bl_options = {'REGISTER','UNDO'}

    def alterUvs(self, mesh, idx, move):

        bpy.ops.object.mode_set(mode='OBJECT')
        uvData = mesh.data.uv_layers[0].data
        for poly in mesh.data.polygons:
            if poly.material_index == idx:
                for loopIdx in poly.loop_indices:
                    uvData[loopIdx].uv[0]+=move
    
    def execute(self, context):
        success= 0
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

                if getObjectType(obj) == "AO":
                    bpy.ops.object.bake(type="AO",margin=128)
                    self.alterUvs(obj,0,1)
                    bpy.ops.object.bake(pass_filter={"COLOR"},type="DIFFUSE",margin=0,use_clear=False)
                    self.alterUvs(obj,0,-1)
                else:
                    bpy.ops.object.bake(pass_filter={"COLOR"},type="DIFFUSE",margin=128)

                if shouldSupersample:
                    tex.scale(texSize[0],texSize[1])

                if getObjectType(obj) == "DIFFUSE": # add magic pixel TODO remove
                    idx = texSize[0] * texSize[1] * 4 - 4
                    tex.pixels[idx] = 1.0
                    tex.pixels[idx + 1] = 0.0
                    tex.pixels[idx + 2] = 1.0
                    tex.pixels[idx + 3] = 1.0
                elif getObjectType(obj) == "AO":
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

class SetupEdgeHighlights(bpy.types.Operator):
    """Copies the object and sets it up for edge highlights."""
    bl_idname = "setup_edges.legion_utils"
    bl_label = "Legion Setup Edge Highlights"
    bl_options = {'REGISTER','UNDO'}
    
    def execute(self, context):
        obj = bpy.context.active_object
        if not obj and len(bpy.context.selected_objects) != 0:
            obj = bpy.context.selected_objects[0]
        if not obj:
            self.report({'ERROR'},"No Object given")
            return {'CANCELLED'}

        diffuseObj = None
        aoObj = None
    
        try:
            name = obj[OBJ_NAME_STRING]
            size = obj[TEX_SIZE_INT]
            for obj in bpy.context.selected_objects:
                t = getObjectType(obj)
                if t == "DIFFUSE":
                    diffuseObj = obj
                if t == "AO":
                    aoObj = obj

        except:
            self.report({'ERROR'},"Selected object must have been previously created by \"setup diffuse\" or \"setup bake\"")
            return {'CANCELLED'}

        self.setupObject(diffuseObj, aoObj, name, size)

        return {'FINISHED'}
    

    def setupObject(self, diffuse, ao, name, texSize):
        target = None
        
        edgeHighlightTex = getOrCreateImage(name+"_edge_highlights",texSize)
        target = ao
        if not target:
            target = diffuse
        if not target:
            target = bpy.context.active_object
        edgeHighlight = duplicateObject(target,"edge highlights")
        edgeHighlight.data.materials.clear()
        if ao:
            edgeHighlight.location[0]+=edgeHighlight.dimensions.x * 2
            if ao.dimensions.x < 10:
                edgeHighlight.location[0]+= ao.dimensions.x
        else:
            edgeHighlight.location[1]+=edgeHighlight.dimensions.y * 2
        bpy.context.collection.objects.link(edgeHighlight)

        edgeHighlight[OBJ_NAME_STRING] = diffuse[OBJ_NAME_STRING]
        edgeHighlight[OBJ_TYPE_STRING] = "EDGE_HIGHLIGHT"
        edgeHighlight[EDGE_HIGHLIGHT_TEXTURE] = edgeHighlightTex
        edgeHighlight[TEX_NAME_STRING] = edgeHighlightTex.name
        edgeHighlight[TEX_SHOULD_BAKE] = False
        edgeHighlight[TEX_SHOULD_SUPERSAMPLE] = False
        edgeHighlight[TEX_SIZE_INT] = diffuse[TEX_SIZE_INT]
        matData = edgeHighlight.data.materials
        matData.append(createEdgeHightlightMaterial("edge highlights", diffuse, ao, edgeHighlightTex))
        

class CalulateEdgeSharp(bpy.types.Operator):
    """Freestyle marks edges which separate faces with an angle greater than the specified angle."""
    bl_idname = "calculate_edges.legion_utils"
    bl_label = "Legion Calculate Edges"
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
    bl_idname = "tweak_edges.legion_utils"
    bl_label = "Legion Tweak Edge Highlights"
    bl_options = {'REGISTER','UNDO'}

    lineThickness: FloatProperty(name="Width", description="The thickness to draw the edge highlights at",min=0,max=50,default=1.5)
    blurAmount: FloatProperty(name="Blur",description="The amount to blur the edge highlights", min=0, max=50, default=0)

    lineThickness2: FloatProperty(name="Redraw Width", description="The thickness to draw the edge highlights at for the second pass",min=0,max=50,default=1)
    blurAmount2: FloatProperty(name="Redraw Blur",description="The amount to blur the edge highlights for the second pass", min=0, max=50, default=0)

    maxTaper: FloatProperty(name="Max Taper Angle",description="The largest angle that tapering is applied", min=0, max=radians(90), default=radians(45), subtype='ANGLE')
    minTaper: FloatProperty(name="Min Taper Angle",description="The smallest angle that tapering is applied", min=0, max=radians(90), default=CalulateEdgeSharp.DEFAULT_ANGLE, subtype='ANGLE')
    taperFactor: FloatProperty(name="Taper Factor",description="The amount to taper at min", min=0, max=1, default=0.25)
    
    def execute(self, context):
        obj = bpy.context.active_object

        try:
            tex = obj[EDGE_HIGHLIGHT_TEXTURE]
        except:
            self.report({'ERROR'},"Selected object must have been previously created by \"setup edge highlights\"")
            return {'CANCELLED'}
        

        self.processObject(obj, tex, self.lineThickness, self.blurAmount)

        return {'FINISHED'}
    
    def invoke(self, context, event):
        obj = bpy.context.active_object
        if not obj:
            self.report({'ERROR'},"No Object given")
            return {'CANCELLED'}

        try:
            self.lineThickness = obj[EDGE_HIGHLIGHT_DILATE]
        except:
            pass
        
        try:
            self.blurAmount = obj[EDGE_HIGHLIGHT_BLUR]
        except:
            pass
        return self.execute(context)


    def getLines(self, mesh, islands, baseThickness, baseBlur):
        selectObject(mesh)
        bpy.ops.object.mode_set(mode='OBJECT')
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
            for poly in islands[islandIdx]:
                polygon = polygons[poly]
                l = len(polygon.loop_indices)
                for x in range(l):
                    loopIdx = polygon.loop_indices[x]
                    edge = edges[loops[loopIdx].edge_index]
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
                    lines.append(baseThickness)
                    lines.append(baseBlur)
                    count+=1
            lines[arrIdx] = count
        return lines

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


    def processObject(self, obj, tex, thickness, blur):
        # the following are converted into arrays of structs in C
        # lineData: array of floats [num_lines, mask_idx, [start, end, thickness, blur...]...] ends when start has a value of -infinity
        # triangulatedUVData: ordered list of float indices as follows [num_triangles, <triangulated UV data>...] ends when num_triangles has a value of -infinity

        if not textureLibrary:
            self.report({'ERROR'},"TEXTURE LIBRARY NOT LOADED")
            return

        obj[EDGE_HIGHLIGHT_DILATE] = thickness
        obj[EDGE_HIGHLIGHT_BLUR] = blur

        islands, islandMap = self.getIslandMap(obj)

        lines = self.getLines(obj, islands, thickness, blur)
        lines = array('f',lines)
        linePointer = lines.buffer_info()[0]

        if len(lines) == 0:
            self.report({"ERROR"},"Model has no freestyle marked edges.")
            return

        triangulatedUvs = self.getOrderedUvsTriangulated(obj, islandMap)
        tuvs = array('f',triangulatedUvs)
        tuvPointer = tuvs.buffer_info()[0]

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

        textureLibrary.generateEdgeHighlights(  ctypes.cast(linePointer,ctypes.POINTER(ctypes.c_float)),
                                                ctypes.cast(tuvPointer,ctypes.POINTER(ctypes.c_float)),
                                                ctypes.c_int(dataLen),
                                                ctypes.c_int(imgWidth), ctypes.c_int(imgHeight),
                                                ctypes.cast(outPointer,ctypes.POINTER(ctypes.c_float)))

        tex.pixels = outData

class SetupDistanceField(bpy.types.Operator):
    """Copies the object and sets it up for distance field."""
    bl_idname = "setup_distance.legion_utils"
    bl_label = "Legion Setup Distance Field"
    bl_options = {'REGISTER','UNDO'}
    
    def execute(self, context):
        obj = bpy.context.active_object
        if not obj and len(bpy.context.selected_objects) != 0:
            obj = bpy.context.selected_objects[0]
        if not obj:
            self.report({'ERROR'},"No Object given")
            return {'CANCELLED'}

        locObj = None
        diffuseObj = None
        aoObj = None
        edgeObj = None
        maxLocation = -999999
    
        try:
            name = obj[OBJ_NAME_STRING]
            size = obj[TEX_SIZE_INT]
            for obj in bpy.context.selectable_objects:
                t = getObjectType(obj)
                if t == "DIFFUSE":
                    diffuseObj = obj
                if t == "AO":
                    aoObj = obj
                if t == "EDGE_HIGHLIGHT":
                    edgeObj = obj
                if(obj.location[0] > maxLocation):
                    locObj = obj
                    maxLocation = obj.location[0]
        except:
            self.report({'ERROR'},"Selected object must have been previously created by \"setup diffuse\" or \"setup bake\"")
            return {'CANCELLED'}

        self.setupObject(locObj, diffuseObj, aoObj, edgeObj, name, size)

        return {'FINISHED'}
    

    def setupObject(self, locObj, diffuse, ao, edgeObj, name, texSize):

        target = None
        
        distanceFieldTex = getOrCreateImage(name+"_distance_field",texSize)
        target = edgeObj
        if not target:
            target = ao
        if not target:
            target = diffuse
        if not target:
            target = bpy.context.active_object
        distanceField = duplicateObject(target,"distance field")
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
        distanceField[OBJ_TYPE_STRING] = "DISTANCE_FIELD"
        distanceField[DISTANCE_FIELD_TEXTURE] = distanceFieldTex
        distanceField[TEX_NAME_STRING] = distanceFieldTex.name
        distanceField[TEX_SHOULD_BAKE] = False
        distanceField[TEX_SHOULD_SUPERSAMPLE] = False
        distanceField[TEX_SIZE_INT] = diffuse[TEX_SIZE_INT]
        matData = distanceField.data.materials
        df = createDistanceFieldMaterial("distance field", distanceFieldTex)
        matData.append(df)
        matData.append(createMaterial("distance field ignore",(0xff,0xff,0xff),distanceFieldTex))
        distanceField[DISTANCE_FIELD_MATERIAL] = df

class TweakDistanceField(bpy.types.Operator):
    """Draws the distance field of the specified object"""
    bl_idname = "tweak_distance.legion_utils"
    bl_label = "Legion Tweak Distance Field"
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
    bl_idname = "pack_underside.legion_utils"
    bl_label = "Legion Pack Underside UVs"
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
    bl_idname = "save_textures.legion_utils"
    bl_label = "Legion Save Images"
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
    """Updates any legacy naming conventions used by previous versions of this tool, allowing for modern functions to work properly"""
    bl_idname = "update_legacy.legion_utils"
    bl_label = "Legion Update Legacy Data"
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
                objname = obj["__LEGION_MESH_NAME"]
                obj[OBJ_NAME_STRING] = objname
                del obj["__LEGION_MESH_NAME"]
                success+=1
            except:
                pass
            try:
                texsize = obj["__LEGION_TEXTURE_SIZE"]
                obj[TEX_SIZE_INT] = texsize
                del obj["__LEGION_TEXTURE_SIZE"]
                success+=1
            except:
                pass
            try:
                texname = obj["__LEGION_TEXTURE_NAME"]
                obj[TEX_NAME_STRING] = texname
                del obj["__LEGION_TEXTURE_NAME"]
                success+=1
            except:
                pass
            try:
                edgeHighlightTex = obj["__LEGION_EDGE_HIGHLIGHTS"]
                obj[EDGE_HIGHLIGHT_TEXTURE] = edgeHighlightTex
                del obj["__LEGION_EDGE_HIGHLIGHTS"]
                obj[TEX_NAME_STRING] = edgeHighlightTex.name
                success+=1
            except:
                pass
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
            if obj.name=="diffuse":
                if not TEX_SHOULD_BAKE in obj:
                    obj[TEX_SHOULD_BAKE]=True
                    success+=1
                if not TEX_SHOULD_SUPERSAMPLE in obj:
                    obj[TEX_SHOULD_SUPERSAMPLE]=True
                    success+=1
                if not OBJ_TYPE_STRING in obj:
                    obj[OBJ_TYPE_STRING] = "DIFFUSE"
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
                if obj.name=="ao":
                    if not "ao_bake_ignore" in obj.data.materials and TEX_NAME_STRING in obj:
                        obj.data.materials.append(createMaterial("ao_bake_ignore",(0xff,0xff,0xff),getOrCreateImage(obj[TEX_NAME_STRING],obj[TEX_SIZE_INT]*2),attach=False))
                        success+=1


            if obj.name=="material":
                if not TEX_SHOULD_BAKE in obj:
                    obj[TEX_SHOULD_BAKE]=True
                    success+=1
                if not TEX_SHOULD_SUPERSAMPLE in obj:
                    obj[TEX_SHOULD_SUPERSAMPLE]=True
                    success+=1
                if not OBJ_TYPE_STRING in obj:
                    obj[OBJ_TYPE_STRING] = "MATERIAL"
                    success+=1
            if obj.name=="mask":
                if not TEX_SHOULD_BAKE in obj:
                    obj[TEX_SHOULD_BAKE]=True
                    success+=1
                if not TEX_SHOULD_SUPERSAMPLE in obj:
                    obj[TEX_SHOULD_SUPERSAMPLE]=True
                    success+=1
                if not OBJ_TYPE_STRING in obj:
                    obj[OBJ_TYPE_STRING] = "MASK"
                    success+=1
            if obj.name=="ao":
                if not TEX_SHOULD_BAKE in obj:
                    obj[TEX_SHOULD_BAKE]=True
                    success+=1
                if not TEX_SHOULD_SUPERSAMPLE in obj:
                    obj[TEX_SHOULD_SUPERSAMPLE]=False
                    success+=1
                if not OBJ_TYPE_STRING in obj:
                    obj[OBJ_TYPE_STRING] = "AO"
                    success+=1
            if obj.name=="distance field":
                if not TEX_SHOULD_BAKE in obj:
                    obj[TEX_SHOULD_BAKE]=False
                    success+=1
                if not TEX_SHOULD_SUPERSAMPLE in obj:
                    obj[TEX_SHOULD_SUPERSAMPLE]=False
                    success+=1
                if not OBJ_TYPE_STRING in obj:
                    obj[OBJ_TYPE_STRING] = "DISTANCE_FIELD"
                    success+=1
                if DISTANCE_FIELD_TEXTURE in obj and not obj[DISTANCE_FIELD_TEXTURE] and TEX_NAME_STRING in obj and TEX_SIZE_INT in obj:
                    texname = obj[TEX_NAME_STRING]
                    img = getOrCreateImage(texname, obj[TEX_SIZE_INT])
                    obj[DISTANCE_FIELD_TEXTURE] = img
                    success+=1
            if obj.name=="edge highlights":
                if not TEX_SHOULD_BAKE in obj:
                    obj[TEX_SHOULD_BAKE]=False
                    success+=1
                if not TEX_SHOULD_SUPERSAMPLE in obj:
                    obj[TEX_SHOULD_SUPERSAMPLE]=False
                    success+=1
                if not OBJ_TYPE_STRING in obj:
                    obj[OBJ_TYPE_STRING] = "EDGE_HIGHLIGHT"
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

libPath = path.dirname(path.abspath(__file__)) + path.sep + "ETex.dll"
textureLibrary = None
if path.exists(libPath):
    try:
        textureLibrary = ctypes.CDLL(libPath,winmode=0)
        textureLibrary.generateEdgeHighlights.argTypes = (ctypes.POINTER(ctypes.c_float), ctypes.POINTER(ctypes.c_float), ctypes.c_int, ctypes.c_int,
                ctypes.c_int, ctypes.POINTER(ctypes.c_float))
        textureLibrary.generateEdgeHighlights.resType = None

        textureLibrary.generateDistanceField.argTypes = (ctypes.POINTER(ctypes.c_float), ctypes.c_int, ctypes.POINTER(ctypes.c_float), ctypes.c_int, ctypes.c_int, ctypes.c_int,
                ctypes.c_int, ctypes.POINTER(ctypes.c_float))
        textureLibrary.generateDistanceField.resType = None
        print("Legion Utils: Texture Library ETex.dll successfully loaded")
    except Exception as e:
        print("TEXTURE LIBRARY MISSING ("+str(e)+")")



_classes = (
    SetupDiffuse,
    SetupBake,
    SetupMaterialbake,
    BakeSelectedObjects,
    CalulateEdgeSharp,
    SetupEdgeHighlights,
    TweakEdgeHighlights,
    SetupDistanceField,
    TweakDistanceField,
    PackUndersideFaces,
    UpdateLegacy,
    SaveTextures,
)

def register():
    from bpy.utils import register_class
    for cls in _classes:
        register_class(cls)
    
def unregister():
    from bpy.utils import unregister_class
    for cls in reversed(_classes):
        unregister_class(cls)

if __name__ == "__main__":
    register()
