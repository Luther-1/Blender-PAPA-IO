bl_info = {
    "name": "Planetary Annihilation Legion Utils",
    "author": "Luther",
    "version": (1, 0, 0),
    "blender": (2, 90, 0),
    "location": "Search",
    "description": "Various utility functions",
    "warning": "",
    "wiki_url": "",
    "tracker_url": "",
    "category": "Utility"
}

import bpy
from mathutils import Vector
from bpy.props import *
from math import radians, log2
from array import array
from os import path
import ctypes

TEX_SIZE_STRING = "__PAPA_IO_TEXTURE_SIZE"
OBJ_NAME_STRING = "__PAPA_IO_MESH_NAME"
TEX_NAME_STRING = "__PAPA_IO_TEXTURE_NAME"
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
    return n

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
    tex = mat.node_tree.nodes.new("ShaderNodeTexImage")
    bsdf.inputs["Base Color"].default_value = tuple([srgbToLinearRGB(c/0xff) for c in colour] + [1])
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
        obj[TEX_SIZE_STRING] = texSize
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
        diffuse[TEX_NAME_STRING] = texname
        bpy.context.collection.objects.link(diffuse)

        matData = diffuse.data.materials
        colourNameTuples = (
            ("dark_diffuse",(0x1d,0x27,0x28)),
            ("medium_diffuse",(0x6b,0x6b,0x6b)),
            ("light_diffuse",(0x7d,0x7d,0x7d)),
            ("green_glow_diffuse",(0x60,0xf0,0x00)),
            ("red_glow_diffuse",(0xff,0x00,0x00)),
            ("engine_glow_diffuse",(0xe3,0xad,0x00)),
            ("black_diffuse",(0x00,0x00,0x00)),
            ("white_glow_diffuse",(0xff,0xff,0xff)),
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

        

class SetupBake(bpy.types.Operator):
    """Copies a mesh and creates all the bake details of it"""
    bl_idname = "setup_bake.legion_utils"
    bl_label = "Legion Setup Bake"
    bl_options = {'UNDO'}
    
    def execute(self, context):
        obj = bpy.context.active_object
        if not obj:
            self.report({'ERROR'},"No Object given")

        try:
            size = obj[TEX_SIZE_STRING]
            name = obj[OBJ_NAME_STRING]
        except:
            self.report({'ERROR'},"Selected object must have been previously created by \"setup diffuse\"")
            return {'CANCELLED'}

        self.setupObject(obj, size, name)

        return {'FINISHED'}
    
    def invoke(self, context, event):
        return self.execute(context)

    def getMaterialMap(self, mesh):
        polygons = mesh.data.polygons
        materialMap = {}
        materialMap['dark']=[]
        materialMap['light']=[]
        materialMap['glow']=[]
        materialMap['none']=[]
        materialMap['default']=[]

        for x in range(len(polygons)):
            face = polygons[x]
            idx = face.material_index
            matName = mesh.data.materials[idx].name
            if matName=="dark_diffuse":
                materialMap['dark'].append(x)
            elif matName=="black_diffuse":
                materialMap['none'].append(x)
            elif matName=="medium_diffuse" or matName=="light_diffuse" or matName=="hazard_stripe" or matName == "hazard_stripe_inverted":
                materialMap['light'].append(x)
            elif matName=="red_glow_diffuse" or matName=="engine_glow_diffuse" or matName=="white_glow_diffuse" or matName=="green_glow_diffuse":
                materialMap['glow'].append(x)
            else:
                materialMap['default'].append(x)
        return materialMap
    
    def assignFacesMaterial(self, materialMap, mesh, dark, light, none, glow):
        polygons = mesh.data.polygons
        materialDict = {mat.name: i for i, mat in enumerate(mesh.data.materials)}
        darkIdx = materialDict[dark]
        lightIdx = materialDict[light]
        noneIdx = materialDict[none]
        glowIdx = materialDict[glow]

        for faceIdx in materialMap["dark"]:
            polygons[faceIdx].material_index = darkIdx
        for faceIdx in materialMap["light"]:
            polygons[faceIdx].material_index = lightIdx
        for faceIdx in materialMap["glow"]:
            polygons[faceIdx].material_index = glowIdx
        for faceIdx in materialMap["none"]:
            polygons[faceIdx].material_index = noneIdx
        for faceIdx in materialMap["default"]:
            polygons[faceIdx].material_index = noneIdx
    
    def assignFacesMask(self, materialMap, mesh, glow):
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
        material[TEX_NAME_STRING] = texname
        bpy.context.collection.objects.link(material)

        matData = material.data.materials
        colourNameTuples = (
            ("dark_material",(0xc0,0xc0,0xff)),
            ("light_material",(0xf0,0xcc,0xff)),
            ("glow_material",(0x00,0x00,0xff)),
            ("tread_material",(0x28,0xc5,0xff)),
            ("shiny_material",(0x00,0xff,0x00)),
            ("shiny_lesser_material",(0x08,0xB9,0x00)),
        )
        for value in colourNameTuples:
            matData.append(createMaterial(value[0],value[1],materialTex))
        
        self.assignFacesMaterial(materialMap, material, "dark_material", "light_material", "glow_material", "glow_material")

        # create the mask object
        texname = name+"_mask_bake"
        maskTex = getOrCreateImage(texname,texSize)
        mask = duplicateObject(obj,"mask")
        mask.data.materials.clear()
        mask.location[0]+=mask.dimensions.x * 4
        mask[TEX_NAME_STRING] = texname
        bpy.context.collection.objects.link(mask)

        matData = mask.data.materials
        colourNameTuples = (
            ("primary",(0xff,0x00,0x00)),
            ("secondary",(0x00,0xff,0x00)),
            ("glow_mask",(0x00,0x00,0xff)),
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
        aoTex = getOrCreateImage(texname,texSize * 2)
        ao = duplicateObject(obj,"ao")
        ao.data.materials.clear()
        ao.location[0]+=ao.dimensions.x * 6
        ao[TEX_NAME_STRING]=texname
        if ao.dimensions.x < 10:
            ao.location[0]+= ao.dimensions.x
        bpy.context.collection.objects.link(ao)

        matData = ao.data.materials
        matData.append(createMaterial("ao_bake",(0xff,0xff,0xff),aoTex,attach=True))

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
            size = obj[TEX_SIZE_STRING]
            for obj in bpy.context.selected_objects:
                if obj.name=="diffuse":
                    diffuseObj = obj
                if obj.name=="ao":
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

        edgeHighlight[EDGE_HIGHLIGHT_TEXTURE] = edgeHighlightTex
        edgeHighlight[TEX_NAME_STRING] = edgeHighlightTex.name
        matData = edgeHighlight.data.materials
        matData.append(createEdgeHightlightMaterial("edge highlights", diffuse, ao, edgeHighlightTex))
        

class CalulateEdgeSharp(bpy.types.Operator):
    """Freestyle marks edges which separate faces with an angle greater than the specified angle."""
    bl_idname = "calculate_edges.legion_utils"
    bl_label = "Legion Calculate Edges"
    bl_options = {'REGISTER','UNDO'}

    angleLimit: FloatProperty(name="Max Angle",description="The max angle before being marked", min=0, max=radians(180), default=radians(10), subtype='ANGLE')
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

    lineThickness: IntProperty(name="Width", description="The thickness to draw the edge highlights at",min=1,max=50,default=1)
    blurAmount: FloatProperty(name="Blur",description="The amount to blur the edge highlights", min=0, max=50, default=1)
    
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

    def processObject(self, obj, tex, thickness, blur):

        if not textureLibrary:
            self.report({'ERROR'},"TEXTURE LIBRARY NOT LOADED")
            return

        obj[EDGE_HIGHLIGHT_DILATE] = thickness
        obj[EDGE_HIGHLIGHT_BLUR] = blur
        
        imgWidth = tex.size[0]
        imgHeight = tex.size[0]
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

        if len(uvs) == 0:
            self.report({"ERROR"},"Model has no freestyle marked edges.")
            return

        uvPointer = uvs.buffer_info()[0]
        numUvCoords = len(uvs)
        textureLibrary.generateEdgeHighlights(ctypes.cast(uvPointer,ctypes.POINTER(ctypes.c_float)),
                    ctypes.c_int(numUvCoords), ctypes.c_int(imgWidth), ctypes.c_int(imgHeight), ctypes.c_int(thickness), ctypes.c_float(blur), 
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
            size = obj[TEX_SIZE_STRING]
            for obj in bpy.context.selectable_objects:
                if obj.name=="diffuse":
                    diffuseObj = obj
                if obj.name=="ao":
                    aoObj = obj
                if obj.name == "edge highlights":
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

        distanceField[DISTANCE_FIELD_TEXTURE] = distanceFieldTex
        distanceField[TEX_NAME_STRING] = distanceFieldTex.name
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
            imgHeight = tex.size[0]
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

            # note: image is saved to SRGB, but this value is linear.
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

        area = bpy.context.workspace.screens[0].areas[0]
        prevType = area.type
        area.type = "IMAGE_EDITOR"
        prevImage = area.spaces[0].image

        for obj in objects:
            try:
                texname = obj[TEX_NAME_STRING]
                tex = getOrCreateImage(texname)
            except:
                self.report({"ERROR"},"Object "+str(obj.name)+" has no texture associated with it")
                continue
            area.spaces[0].image = tex
            bpy.ops.image.save_as({'area': area},'INVOKE_DEFAULT',copy=True,filepath = bpy.path.abspath("//")+"/"+str(texname)+".png")
            success+=1
        
        if success !=0:
            self.report({"INFO"},"Saved "+str(success)+" images")
        
        area.spaces[0].image = prevImage
        area.type = prevType
        
        return {'FINISHED'}

class UpdateLegacy(bpy.types.Operator):
    """Updates any legacy naming conventions used by previous versions of this tool, allowing for modern functions to work properly"""
    bl_idname = "update_legacy.legion_utils"
    bl_label = "Legion Update Legacy Data"
    bl_options = {'REGISTER','UNDO'}
    
    def execute(self, context):
        objects = []
        for obj in bpy.context.selected_objects:
            objects.append(obj)
        if len(objects)==0:
            self.report({'ERROR'},"No Object given")
            return {'CANCELLED'}

        success = 0

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
                obj[TEX_SIZE_STRING] = texsize
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
                edgehighlights = obj["__LEGION_EDGE_HIGHLIGHTS"]
                obj[EDGE_HIGHLIGHT_TEXTURE] = edgehighlights
                del obj["__LEGION_EDGE_HIGHLIGHTS"]
                obj[TEX_NAME_STRING] = edgehighlights.name
                success+=1
            except:
                pass
            
        
        self.report({"INFO"},"Updated "+str(success)+" properties")
        
        return {'FINISHED'}

libPath = path.dirname(path.abspath(__file__)) + path.sep + "ETex.dll"
textureLibrary = None
if path.exists(libPath):
    try:
        textureLibrary = ctypes.CDLL(libPath,winmode=0)
        textureLibrary.generateEdgeHighlights.argTypes = (ctypes.POINTER(ctypes.c_float), ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                ctypes.c_float, ctypes.POINTER(ctypes.c_float))
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
