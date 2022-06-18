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

bl_info = {
    "name": "Planetary Annihilation PAPA Format",
    "author": "Raevn and Luther",
    "version": (1, 2, 0),
    "blender": (3, 0, 0),
    "location": "File > Import/Export",
    "description": "Imports/Exports PAPA meshes, uvs, bones, materials, groups, textures, and animations",
    "warning": "",
    "wiki_url": "http://forums.uberent.com/forums/viewtopic.php?f=72&t=47964",
    "tracker_url": "",
    "category": "Import-Export"}

if "bpy" in locals():
    import imp
    if ("import_papa") in locals():
        imp.reload(import_papa) # type: ignore
    if ("export_papa") in locals():
        imp.reload(export_papa) # type: ignore
    if("papafile" in locals()):
        imp.reload(papafile) # type: ignore
    if("texture_extensions" in locals()):
        imp.reload(texture_extensions) # type: ignore

from .texture_extensions import papa_io_register_texture, papa_io_unregister_texture

import bpy
from copy import copy
from bpy.props import *
from bpy.types import AddonPreferences, OperatorFileListElement, PropertyGroup
import os

from bpy_extras.io_utils import ImportHelper, ExportHelper

class PapaImportProperties:
    def __init__(self, fuzzyMatch: bool, importTextures: bool, convertToQuads: bool, removeDoubles: bool, importNormals: bool, colours: bool,):
        self.__filepath = None
        self.__fuzzyMatch = fuzzyMatch
        self.__importTextures = importTextures
        self.__convertToQuads = convertToQuads
        self.__removeDoubles = removeDoubles
        self.__importNormals = importNormals
        self.__colours = colours
    def getFilepath(self):
        return self.__filepath
    def getFilename(self):
        return os.path.basename(os.path.realpath(self.getFilepath()))
    def nextFile(self):
        self.__filepathIndex += 1
    def isFuzzyMatch(self):
        return self.__fuzzyMatch
    def isImportTextures(self):
        return self.__importTextures
    def isConvertToQuads(self):
        return self.__convertToQuads
    def isRemoveDoubles(self):
        return self.__removeDoubles
    def isImportNormals(self):
        return self.__importNormals
    def getPrimaryColour(self):
        return self.__colours[0]
    def getSecondaryColour(self):
        return self.__colours[1]
    def withFile(self, filepath):
        prop = copy(self)
        prop.__filepath = filepath
        return prop

class ImportPapa(bpy.types.Operator, ImportHelper):
    """Import from PAPA file format (.papa)"""
    bl_idname = "import_scene.uberent_papa"
    bl_label = "Import PAPA"
    bl_options = {'UNDO'}
    
    filename_ext = ".papa"
    filter_glob: StringProperty(default="*.papa", options={'HIDDEN'})

    files: CollectionProperty(name="PAPA import files", type=OperatorFileListElement)
    directory: StringProperty(subtype="DIR_PATH")

    # filepath: bpy.props.StringProperty(
    #     name="File Path", 
    #     description="File path used for importing the PAPA file", 
    #     maxlen= 1024, default= "")
       
    fuzzyMatch : BoolProperty(name="Fuzzy Match Animation Targets",description="Don't require all bones to match to import an animation.", default=True)
    importTextures : BoolProperty(name="Auto Import Texture Files",description="Automatically import the "
        + "diffuse, mask, and specular textures from the same folder or linked destinations if they exist", default=True)
    convertToQuads : BoolProperty(name="Convert to Quads",description="Perform a tris to quads conversion before removing doubles", default=True)
    removeDoubles : BoolProperty(name="Remove Doubles",description="Removes double vertices on each mesh", default=True)
    importNormals : BoolProperty(name="Import Vertex Normals",description="Sets custom normals from the model data", default=True)
    
    def execute(self, context):
        from . import import_papa

        pref = context.preferences.addons[__name__].preferences

        colours = self.__getColours(pref)

        files = []
        for file in self.properties.files:
            files.append(os.path.join(self.properties.directory, file.name))

        prop = PapaImportProperties(self.properties.fuzzyMatch, self.properties.importTextures,
            self.properties.convertToQuads, self.properties.removeDoubles, self.properties.importNormals,colours)
        return import_papa.load(self, context, prop, files)

    def __getColours(self, pref):

        if pref.colourScheme=="MLA":
            return ((0,0.486,1,1),(1,0.394,0,1))

        if pref.colourScheme=="LEGION":
            return ((1,0,0,1),(0,0,0,1))

        if pref.colourScheme=="CUSTOM":
            fvp1 = pref.customColour1
            fvp2 = pref.customColour2

            return ((fvp1[0], fvp1[1], fvp1[2], 1), (fvp2[0], fvp2[1], fvp2[2], 1))
    
    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}
    
    def draw(self, context):
        l = self.layout

        row = l.row()
        row.prop(self,"fuzzyMatch")

        row = l.row()
        row.prop(self,"importTextures")

        row = l.row()
        row.prop(self,"convertToQuads")

        row = l.row()
        row.prop(self,"removeDoubles")

        row = l.row()
        row.prop(self,"importNormals")

        pref = context.preferences.addons[__name__].preferences
        row = l.row()
        row.prop(pref,"colourScheme", expand=True)

        colourType = pref.colourScheme
        if colourType == "CUSTOM":
            row = l.row()
            row.prop(pref,"customColour1")

            row = l.row()
            row.prop(pref,"customColour2")

class PapaAddonPreferences(AddonPreferences):
    bl_idname = __name__

    colourOptions = [
        ("MLA", "MLA", "Uses the default colours of the MLA (standard faction)", "", 0),
        ("LEGION", "Legion", "Uses the default colours of the Legion Expansion faction", "", 1),
        ("CUSTOM", "Custom", "Uses custom colours", "", 2),
    ]

    colourScheme: EnumProperty(name="Colour Scheme",description="Determines what unit colours should be used",items=colourOptions)

    customColour1: FloatVectorProperty(name="Primary",min=0,max=1, subtype='COLOR', description="The primary custom colour.")
    customColour2: FloatVectorProperty(name="Secondary",min=0,max=1, subtype='COLOR', description="The secondary custom colour.")

    textureExtensionsConfig: StringProperty(name="Texture Extensions Configuration", description="The configuration section to use in texture_config.json")

class PapaExportMaterialListItem(PropertyGroup):
    exportIndex: IntProperty()

    texturePath: StringProperty(name= "Texture", description="Path to the texture file. Leave blank to omit in the shader",default="",maxlen=1024)
    normalPath: StringProperty(name= "Normal", description="Path to the normal file. Leave blank to omit in the shader",default="",maxlen=1024)
    materialPath: StringProperty(name= "Material", description="Path to the material file. Leave blank to omit in the shader",default="",maxlen=1024)

class PapaExportMaterial:
    TEXTURE_EXTENSTION = "__PAPA_EXPORT_TEXTURE"
    MASK_EXTENSION = "__PAPA_EXPORT_MASK" # unused, but here for consistency
    NORMAL_EXTENSTION = "__PAPA_EXPORT_NORMAL"
    MATERIAL_EXTENSION = "__PAPA_EXPORT_MATERIAL"
    PAPAFILE_SOURCE_EXTENSION = "__PAPAFILE_SOURCE_LOCATION"

    def __init__(self, material, UIIndex = -1):
        self.__materialObject = material
        self.__materialName = material.name
        self.__texture = ""
        self.__normal = ""
        self.__material = ""
        self.__UIIndex = UIIndex

        if material == None:
            raise ValueError("Source material must be defined")
        if PapaExportMaterial.TEXTURE_EXTENSTION in material:
            self.__texture = material[PapaExportMaterial.TEXTURE_EXTENSTION]
        if PapaExportMaterial.NORMAL_EXTENSTION in material:
            self.__normal = material[PapaExportMaterial.NORMAL_EXTENSTION]
        if PapaExportMaterial.MATERIAL_EXTENSION in material:
            self.__material = material[PapaExportMaterial.MATERIAL_EXTENSION]

    def getTexturePath(self):
        return self.__texture

    def getNormalPath(self):
        return self.__normal

    def getMaterialPath(self):
        return self.__material

    def getMaterialName(self):
        return self.__materialName

    def getMaterialObject(self):
        return self.__materialObject

    def getIndexUI(self):
        return self.__UIIndex

    def updateMaterial(self, paramName, path):
        if len(path) == 0 or path == ExportPapa.NO_TEXTURE_STRING:
            if paramName in self.__materialObject:
                del self.__materialObject[paramName]
        else:
            self.__materialObject[paramName] = path
    
    def setTexturePath(self, path):
        self.__texture = path
        

    def setNormalPath(self, path):
        self.__normal = path

    def setMaterialPath(self, path):
        self.__material = path

class PapaExportMaterialGetPath(bpy.types.Operator):
    """Sets the path of the texture to be the currently selected file"""
    bl_idname = "export_scene_grab_path.uberent_papa"
    bl_label = "Set path from current selected file"
    bl_options = {"INTERNAL"}

    propertyName: StringProperty(name="target_name", options={"HIDDEN"})
    propertyIndex: IntProperty()

    def execute(self, context):
        exporter = ExportPapa.getInstance()
        filepath = exporter.filepath
        collection = exporter.materialUIList[self.propertyIndex]
        setattr(collection,self.propertyName,filepath)
        return {"FINISHED"}
        
class PapaExportMaterialList(bpy.types.UIList):
    bl_idname = "PAPA_EXPORT_UL_MATERIAL_LIST"
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        properties = bpy.context.scene.SCENE_PAPA_EXPORT_SETTINGS
        mat = ExportPapa.materialList[item.exportIndex] # i hate this so much why can't i just tell blender to make empty list objects
        
        shader = int(properties.CSGExportShader) # gets the identifier property

        layout.use_property_split = True
        column = layout.column()
        column.label(text=mat.getMaterialName(),icon="MATERIAL")
        if shader >= 1:
            r = column.row()
            r.alert = not self.isPathValid(item["texturePath"])
            r.prop(item,"texturePath")
            operatorProps = r.operator(PapaExportMaterialGetPath.bl_idname,icon="FILE_TICK",text="")
            operatorProps.propertyIndex = item.exportIndex
            operatorProps.propertyName = "texturePath"
        if shader >= 2:
            r = column.row()
            r.alert = not self.isPathValid(item["normalPath"])
            r.prop(item,"normalPath")
            operatorProps = r.operator(PapaExportMaterialGetPath.bl_idname,icon="FILE_TICK",text="")
            operatorProps.propertyIndex = item.exportIndex
            operatorProps.propertyName = "normalPath"
        if shader >= 3:
            r = column.row()
            r.alert = not self.isPathValid(item["materialPath"])
            r.prop(item,"materialPath")
            operatorProps = r.operator(PapaExportMaterialGetPath.bl_idname,icon="FILE_TICK",text="")
            operatorProps.propertyIndex = item.exportIndex
            operatorProps.propertyName = "materialPath"

    def isPathValid(self, path):
        path = path.replace("\\","/")
        # either it is an absolute path and exists, or it's a relative path (assumes it exists)
        return (os.path.isfile(path) and ("/pa/" in path or "/pa_ex1/" in path)) or path.startswith("/pa/")

class PapaExportProperties:
    def __init__(self, filepath:str, target:object, isCSG: bool, markSharp:bool, shader: str, materialList: list, compressData: bool,
                        ignoreRoot:bool, ignoreHidden:bool,ignoreNoData:bool,merge:bool, signature:str):
        self.__filepath = filepath
        self.__targetObject = target
        self.__isCSG = isCSG
        self.__markSharp = markSharp
        self.__shader = shader
        self.__materialMap = {}
        for material in materialList:
            self.__materialMap[material.getMaterialName()] = material
        self.__compressData = compressData
        self.__ignoreRoot = ignoreRoot
        self.__ignoreHidden = ignoreHidden
        self.__ignoreNoData = ignoreNoData
        self.__merge = merge
        self.__signature = signature

    def getFilepath(self) -> str:
        return self.__filepath
    
    def getTargets(self) -> object:
        return self.__targetObject

    def isCSG(self):
        return self.__isCSG

    def isRespectMarkSharp(self):
        return self.__markSharp

    def getShader(self):
        return self.__shader
    
    def getMaterialForName(self, name: str):
        return self.__materialMap[name]
    
    def isCompress(self):
        return self.__compressData

    def isIgnoreRoot(self):
        return self.__ignoreRoot

    def isIgnoreHidden(self):
        return self.__ignoreHidden

    def isIgnoreNoData(self):
        return self.__ignoreNoData
    
    def isMerge(self):
        return self.__merge

    def getSignature(self):
        return self.__signature

class ExportPapaUISettings(PropertyGroup):

    markSharp: BoolProperty(name="Respect Mark Sharp", description="Causes the compiler to consider adjacent smooth"
        + " shaded faces which are marked sharp as disconnected",default=True)
    compress: BoolProperty(name="Join Similar Polygons", description="Joins the data of any faces that have the same normals to reduce file size."
        + " Does nothing if the face is smooth shaded",default=True)
    merge: BoolProperty(name="Multi-Mesh", description="Causes selected meshes with the same skeleton to be written to the"
        + " file as one model instead of many. Creates support for >32 bones", default=True)
    isCSG : BoolProperty(name="Export as CSG",description="Exports the selected mesh as a CSG instead of a unit. Cannot be used if multiple meshes are selected")

    shaderOptions = [
        ("1", "textured", "PA shader with just a texture", "", 0),
        ("2", "textured_normal", "PA shader with texture and a normal map (encoded in the Green and Alpha channels, G -> G, A -> R)", "", 1),
        ("3", "textured_normal_material", "PA shader with texture, a normal map "
            + "(encoded in the Green and Alpha channels, G -> G, A -> R), and an emission + specular material", "", 2),
    ]

    CSGExportShader: EnumProperty(name="",description="Export shader type",items=shaderOptions)

    ignoreRoot: BoolProperty(name="Ignore Root Movement", description="Any bones with no parent will have all transforms removed",default=True)
    ignoreHidden: BoolProperty(name="Ignore Hidden Bones", description="Hidden bones will not be written to the file"
        + " (Edit bones for model export, pose bones for animation export)",default=True)
    ignoreNoData: BoolProperty(name="Skip Bones With No Data", description="Bones that have no animation data associated with them will not be written",default=True)

    signature: StringProperty(name="Signature",description="A six letter or less string to embed into the file that for purposes of crediting",maxlen=6,subtype='BYTE_STRING')

class ExportPapa(bpy.types.Operator, ExportHelper):
    """Export to PAPA file format (.papa)"""
    bl_idname = "export_scene.uberent_papa"
    bl_label = "Export PAPA"
    
    target_object_string: StringProperty(name="target_object", options={"HIDDEN"}) # assigned from the menu

    materialList = []
    materialUIList = []
    currentInstance = None

    NO_TEXTURE_STRING = "NO_TEXTURE"
    
    filename_ext = ".papa"
    filter_glob: StringProperty(default="*.papa", options={"HIDDEN"})
    

    filepath: bpy.props.StringProperty(
        name="File Path", 
        description="File path used for exporting the PAPA file", 
        maxlen=1024, default="")

    def draw(self, context):
        l = self.layout

        properties = bpy.context.scene.SCENE_PAPA_EXPORT_SETTINGS

        if self.__isAnimation:
            row = l.row()
            row.prop(properties,"ignoreRoot")

            row = l.row()
            row.prop(properties,"ignoreHidden")

            row = l.row()
            row.prop(properties,"ignoreNoData")

            row = l.row()
            row.prop(properties,"signature")
            return

        row = l.row()
        row.prop(properties,"markSharp") # this is so needlessly hard blender why

        row = l.row()
        row.prop(properties,"compress")

        row = l.row()
        row.prop(properties,"ignoreHidden")

        row = l.row()
        row.prop(properties,"merge")

        row = l.row()
        row.prop(properties,"isCSG")
        row.enabled = self.__isCSGCompatible

        col = l.column()
        col.label(text="CSG Export Shader:")
        col.prop(properties,"CSGExportShader")
        col.enabled = properties.isCSG
        
        row = l.row()
        row.template_list(PapaExportMaterialList.bl_idname,"",bpy.context.scene,"SCENE_PAPA_MATERIALS_LIST",
            bpy.context.scene,"SCENE_PAPA_MATERIALS_LIST_ACTIVE",rows = len(ExportPapa.materialList))
        row.enabled = properties.isCSG

        row = l.row()
        row.prop(properties,"signature")
    
    def getObject(self): # takes the source string and turns it into a blender object
        if self.target_object_string == ExportPapaMenu.EXPORT_SELECTED_STRING:
            return ExportPapaMenu.getValidSelectedObjects()
        for object in bpy.context.scene.objects:
            if object.name == self.target_object_string:
                return [object]

    def __toLocalDirectory(self, path):
        if len(path) == 0:
            return ExportPapa.NO_TEXTURE_STRING

        path = path.replace("\\","/")
        directory = "/pa/"

        if path.startswith("/pa/"): # local path already
            return path

        idx = path.find(directory)
        if idx == -1:
            print("Warning: Path \""+path+"\" is not in a subdirectory of "+directory+". Assuming the path is meant to be blank")
            return ExportPapa.NO_TEXTURE_STRING
        return path[idx:]
        
    def __correctPaths(self):
        for mat in ExportPapa.materialList: # update the material path to be local to PA
            mat.setTexturePath(self.__toLocalDirectory(mat.getTexturePath()))
            mat.setNormalPath(self.__toLocalDirectory(mat.getNormalPath()))
            mat.setMaterialPath(self.__toLocalDirectory(mat.getMaterialPath()))

    def __updatePaths(self):
        for x in range(len(ExportPapa.materialUIList)): # update the materials
            exportMaterial = ExportPapa.materialList[x]
            item = ExportPapa.materialUIList[x]
            exportMaterial.setTexturePath(item.texturePath)
            exportMaterial.setNormalPath(item.normalPath)
            exportMaterial.setMaterialPath(item.materialPath)

            exportMaterial.updateMaterial(PapaExportMaterial.TEXTURE_EXTENSTION,exportMaterial.getTexturePath())
            exportMaterial.updateMaterial(PapaExportMaterial.NORMAL_EXTENSTION,exportMaterial.getNormalPath())
            exportMaterial.updateMaterial(PapaExportMaterial.MATERIAL_EXTENSION,exportMaterial.getMaterialPath())
    
    def execute(self, context):
        from . import export_papa

        properties = bpy.context.scene.SCENE_PAPA_EXPORT_SETTINGS

        self.__updatePaths() # update data to match UI
        self.__correctPaths() 
        shader = ExportPapaUISettings.shaderOptions[int(properties.CSGExportShader)-1][1] # get the shader by name. bit spaghetti
        prop = PapaExportProperties(self.properties.filepath, self.__objectsList, 
            properties.isCSG,properties.markSharp, shader, ExportPapa.materialList, properties.compress,
            properties.ignoreRoot, properties.ignoreHidden, properties.ignoreNoData, properties.merge, properties.signature)
        return export_papa.write(self, context, prop)
    
    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        self.__objectsList = self.getObject()
        self.__isCSGCompatible = False
        self.__isAnimation = False
        ExportPapa.materialList = [] # holds the backend
        ExportPapa.materialUIList = [] # holds the UI frontend
        ExportPapa.currentInstance = self

        collection = bpy.context.scene.SCENE_PAPA_MATERIALS_LIST 
        collection.clear()

        highestShaderLevel = 1

        if len(self.__objectsList) == 1 and self.__objectsList[0].type == "ARMATURE":
            self.__isAnimation = True

        if len(self.__objectsList) == 1 and self.__objectsList[0].type == "MESH":
            self.__isCSGCompatible = True
            obj = self.__objectsList[0]
            idx = 0
            for slot in obj.material_slots:
                material = slot.material
                if not material:
                    continue
                mat = PapaExportMaterial(material)
                ExportPapa.materialList.append(mat)
                prop = collection.add()
                prop.exportIndex = idx
                prop.texturePath = mat.getTexturePath()
                prop.normalPath = mat.getNormalPath()
                prop.materialPath = mat.getMaterialPath()
                ExportPapa.materialUIList.append(prop)
                idx+=1

                if len(mat.getTexturePath()):
                    highestShaderLevel = max(highestShaderLevel, 1)
                if len(mat.getNormalPath()):
                    highestShaderLevel = max(highestShaderLevel, 2)
                if len(mat.getMaterialPath()):
                    highestShaderLevel = max(highestShaderLevel, 3)

        bpy.context.scene.SCENE_PAPA_EXPORT_SETTINGS.CSGExportShader = str(highestShaderLevel)
        
        if not self.__isCSGCompatible:
            bpy.context.scene.SCENE_PAPA_EXPORT_SETTINGS.isCSG = False
        return {'RUNNING_MODAL'}
    
    @classmethod
    def getInstance(cls):
        return ExportPapa.currentInstance

class ExportPapaMenu(bpy.types.Menu):
    bl_idname = "PAPA_MT_UBERENT_PAPA"
    bl_label = "Export PAPA"

    EXPORT_SELECTED_STRING = "\t~ExportSelected"

    def draw(self, context):
        l = self.layout
        l.operator_context = 'INVOKE_DEFAULT' # invoke the export routine from the button
        
        exportables = list(ExportPapaMenu.getAvailableExports())
        if(len(exportables)==0):
            row = l.row()
            row.operator(ExportPapa.bl_idname, text="No exportables found.", icon="ERROR")
            row.enabled = False
            return

        # add exportables
        for obj in exportables:
            row = l.row()
            icon = "none"
            name = "undefined"
            if(obj.type == "MESH"):
                icon = "GROUP"
                name = "Model"
                for modifier in obj.modifiers:
                    if modifier.type == "ARMATURE" and modifier.object:
                        name = "Model + Armature"
                        break
            if(obj.type == "ARMATURE"):
                icon = "ACTION"
                name = "Animation"
            row.operator(ExportPapa.bl_idname, text=obj.name+" ("+name+")", icon=icon).target_object_string = obj.name

        # special export selected mode
        selectedString = ""
        hasModel = False
        hasArmature = False
        hasAnimation = False
        numTargets = len(ExportPapaMenu.getValidSelectedObjects())
        for obj in ExportPapaMenu.getValidSelectedObjects():
            if(obj.type == "MESH"):
                hasModel = True
                for modifier in obj.modifiers:
                    if modifier.type == "ARMATURE" and modifier.object:
                        hasArmature = True
            
            if(obj.type == "ARMATURE"): # invalid unless it has animation data
                hasAnimation = True

        if hasModel:
            selectedString+="Model + "
        if hasArmature:
            selectedString+="Armature + "
        if hasAnimation:
            selectedString+="Animation + "
        if len(selectedString) != 0:
            selectedString = "("+selectedString[:-3]+")"

        exportAllRow = l.row()
        exportAllRow.operator(ExportPapa.bl_idname, text="Export Selected "+selectedString+" ("+str(numTargets) + (" target)" if numTargets == 1 else " targets)"),
            icon="SCENE_DATA").target_object_string = ExportPapaMenu.EXPORT_SELECTED_STRING
        if len(ExportPapaMenu.getValidSelectedObjects()) == 0:
            exportAllRow.enabled = False

    @classmethod
    def testCanExport(cls, obj):
        if(obj.type == "MESH"):
            return True
        if(obj.type == "ARMATURE" and obj.animation_data and obj.animation_data.action):
            return True
        return False

    @classmethod
    def getValidSelectedObjects(cls):
        selected = []
        for obj in bpy.context.selected_objects:
            if ExportPapaMenu.testCanExport(obj):
                selected.append(obj)
        return selected

    @classmethod
    def getTotalAvailableExports(cls):
        return len(ExportPapaMenu.getAllAvailableExports())

    @classmethod
    def getAllAvailableExports(cls):
        exportables = []
        for obj in bpy.context.scene.objects:
            if(cls.testCanExport(obj)):
                exportables.append(obj)
        return exportables

    @classmethod
    def getAvailableExports(cls):
        exportables = []
        for obj in bpy.context.selected_objects: # first, try selected objects
            if(cls.testCanExport(obj)):
                exportables.append(obj)
        if len(exportables) == 0 and bpy.context.active_object: # otherwise, try active
            if(cls.testCanExport(bpy.context.active_object)):
                exportables.append(bpy.context.active_object)
        if len(exportables) == 0 or len(bpy.context.scene.objects) < 5: # finally, show all if we found none OR there are less than 5 objects
            for obj in bpy.context.scene.objects:
                if(cls.testCanExport(obj) and not obj in exportables):
                    exportables.append(obj)

        return exportables

def menu_func_import(self, context):
    self.layout.operator(ImportPapa.bl_idname, text="Planetary Annihilation (.papa)")

def menu_func_export(self, context):
    self.layout.menu(ExportPapaMenu.bl_idname, text="Planetary Annihilation  (.papa)")

_classes = (
    ImportPapa,
    ExportPapa,
    ExportPapaMenu,
    PapaExportMaterialListItem,
    ExportPapaUISettings,
    PapaExportMaterialList,
    PapaExportMaterialGetPath,
    PapaAddonPreferences,
)

def register():
    from bpy.utils import register_class
    for cls in _classes:
        register_class(cls)
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import)
    bpy.types.TOPBAR_MT_file_export.append(menu_func_export)
    # bpy.types.IMAGE_MT_image.append(menu_func_texture_export)
    # bpy.types.IMAGE_MT_image.append(menu_func_texture_import)

    bpy.types.Scene.SCENE_PAPA_MATERIALS_LIST = CollectionProperty(type = PapaExportMaterialListItem)
    bpy.types.Scene.SCENE_PAPA_MATERIALS_LIST_ACTIVE = IntProperty()
    bpy.types.Scene.SCENE_PAPA_EXPORT_SETTINGS = PointerProperty(type=ExportPapaUISettings)
    papa_io_register_texture()
    
def unregister():
    from bpy.utils import unregister_class
    for cls in reversed(_classes):
        unregister_class(cls)
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)
    bpy.types.TOPBAR_MT_file_export.remove(menu_func_export)

    del bpy.types.Scene.SCENE_PAPA_MATERIALS_LIST
    del bpy.types.Scene.SCENE_PAPA_MATERIALS_LIST_ACTIVE
    del bpy.types.Scene.SCENE_PAPA_EXPORT_SETTINGS
    papa_io_unregister_texture()

if __name__ == "__main__":
    register()
