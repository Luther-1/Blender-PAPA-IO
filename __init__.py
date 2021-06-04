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

bl_info = {
    "name": "Planetary Annihilation PAPA Format",
    "author": "Raevn and Luther",
    "version": (0, 9, 1),
    "blender": (2, 90, 0),
    "location": "File > Import/Export",
    "description": "Imports/Exports PAPA meshes, uvs, bones, materials, groups, textures, and animations",
    "warning": "",
    "wiki_url": "http://forums.uberent.com/forums/viewtopic.php?f=72&t=47964",
    "tracker_url": "",
    "category": "Import-Export"}

if "bpy" in locals():
    import imp
    if ("import_papa") in locals():
        imp.reload(import_papa)
    if ("export_papa") in locals():
        imp.reload(export_papa)
    if("papafile" in locals()):
        imp.reload(papafile)
import bpy
from bpy.props import *
from bpy.types import PropertyGroup
from os import path
import os

from bpy_extras.io_utils import ImportHelper, ExportHelper

class PapaImportProperties:
    def __init__(self, filepath: str, fuzzyMatch: bool, importTextures: bool, convertToQuads: bool, removeDoubles: bool, importNormals: bool):
        self.__filepath = filepath
        self.__fuzzyMatch = fuzzyMatch
        self.__importTextures = importTextures
        self.__convertToQuads = convertToQuads
        self.__removeDoubles = removeDoubles
        self.__importNormals = importNormals
    def getFilepath(self):
        return self.__filepath
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

class ImportPapa(bpy.types.Operator, ImportHelper):
    """Import from PAPA file format (.papa)"""
    bl_idname = "import_scene.uberent_papa"
    bl_label = "Import PAPA"
    bl_options = {'UNDO'}
    
    filename_ext = ".papa"
    filter_glob: StringProperty(default="*.papa", options={'HIDDEN'})

    filepath: bpy.props.StringProperty(
        name="File Path", 
        description="File path used for importing the PAPA file", 
        maxlen= 1024, default= "")
       
    fuzzyMatch : BoolProperty(name="Fuzzy Match Animation Targets",description="Don't require all bones to match to import an animation.", default=True)
    importTextures : BoolProperty(name="Auto Import Texture Files (Slow!)",description="Automatically import the " \
        + "diffuse, mask, and specular textures from the same folder or linked destinations if they exist", default=True)
    convertToQuads : BoolProperty(name="Convert to Quads",description="Perform a tris to quads conversion before removing doubles", default=True)
    removeDoubles : BoolProperty(name="Remove Doubles",description="Removes double vertices on each mesh", default=True)
    importNormals : BoolProperty(name="Import Vertex Normals",description="Sets custom normals from the model data", default=False)
    
    def execute(self, context):
        from . import import_papa
        
        prop = PapaImportProperties(self.properties.filepath, self.properties.fuzzyMatch, self.properties.importTextures,
            self.properties.convertToQuads, self.properties.removeDoubles, self.properties.importNormals)
        return import_papa.load(self, context, prop)
    
    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

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
            r.alert = not path.isfile(item["normalPath"])
            r.prop(item,"normalPath")
            operatorProps = r.operator(PapaExportMaterialGetPath.bl_idname,icon="FILE_TICK",text="")
            operatorProps.propertyIndex = item.exportIndex
            operatorProps.propertyName = "normalPath"
        if shader >= 3:
            r = column.row()
            r.alert = not path.isfile(item["materialPath"])
            r.prop(item,"materialPath")
            operatorProps = r.operator(PapaExportMaterialGetPath.bl_idname,icon="FILE_TICK",text="")
            operatorProps.propertyIndex = item.exportIndex
            operatorProps.propertyName = "materialPath"

    def isPathValid(self, path):
        path = path.replace("\\","/")
        return (os.path.isfile(path) and "/media/" in path) or path.startswith("/pa/") # either it is an absolute path and exists, or it's a relative path (assumes it exists)

class PapaExportProperties:
    def __init__(self, filepath:str, target:object, isCSG: bool, markSharp:bool, shader: str, materialList: list):
        self.__filepath = filepath
        self.__targetObject = target
        self.__isCSG = isCSG
        self.__markSharp = markSharp
        self.__shader = shader
        self.__materialMap = {}
        for material in materialList:
            self.__materialMap[material.getMaterialName()] = material

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

class ExportPapaUISettings(PropertyGroup):

    markSharp: BoolProperty(name="Respect Mark Sharp", description="Causes the compiler to consider adjacent smooth"\
        + " shaded faces which are marked sharp as disconnected",default=True)
    isCSG : BoolProperty(name="Export as CSG",description="Exports the selected object as a CSG instead of as a unit. Cannot be used if multiple meshes are selected")

    shaderOptions = [
        ("1", "textured", "PA shader with just a texture", "", 0),
        ("2", "textured_normal", "PA shader with texture and a normal map (encoded in the Green and Alpha channels, G -> G, A -> R)", "", 1),
        ("3", "textured_normal_material", "PA shader with texture, a normal map "
            + "(encoded in the Green and Alpha channels, G -> G, A -> R), and an emission + specular material", "", 2),
    ]

    CSGExportShader: EnumProperty(name="",description="Export shader type",items=shaderOptions)

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

        row = l.row()
        row.prop(properties,"markSharp") # this is so needlessly hard blender why

        row = l.row()
        row.prop(properties,"isCSG") # this is so needlessly hard blender why
        row.enabled = self.__isCSGCompatible

        col = l.column()
        col.label(text="CSG Export Shader:")
        col.prop(properties,"CSGExportShader")
        col.enabled = properties.isCSG
        
        row = l.row()
        row.template_list(PapaExportMaterialList.bl_idname,"",bpy.context.scene,"SCENE_PAPA_MATERIALS_LIST",
            bpy.context.scene,"SCENE_PAPA_MATERIALS_LIST_ACTIVE",rows = len(ExportPapa.materialList))
        row.enabled = properties.isCSG
    
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
        prop = PapaExportProperties(self.properties.filepath, self.__objectsList, properties.isCSG,properties.markSharp, shader, ExportPapa.materialList)
        return export_papa.write(self, context, prop)
    
    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        self.__objectsList = self.getObject()
        self.__isCSGCompatible = False
        ExportPapa.materialList = [] # holds the backend
        ExportPapa.materialUIList = [] # holds the UI frontend
        ExportPapa.currentInstance = self

        collection = bpy.context.scene.SCENE_PAPA_MATERIALS_LIST 
        collection.clear()

        highestShaderLevel = 1

        if len(self.__objectsList) == 1 and self.__objectsList[0].type == "MESH":
            self.__isCSGCompatible = True
            obj = self.__objectsList[0]
            idx = 0
            for slot in obj.material_slots:
                material = slot.material
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

        for obj in exportables:
            row = l.row()
            icon = "none"
            name = "undefined"
            if(obj.type == "MESH"):
                icon = "GROUP"
                name = "Model"
                for modifier in obj.modifiers:
                    if modifier.type == "ARMATURE":
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
                    if modifier.type == "ARMATURE":
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
)

def register():
    from bpy.utils import register_class
    for cls in _classes:
        register_class(cls)
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import)
    bpy.types.TOPBAR_MT_file_export.append(menu_func_export)

    bpy.types.Scene.SCENE_PAPA_MATERIALS_LIST = CollectionProperty(type = PapaExportMaterialListItem)
    bpy.types.Scene.SCENE_PAPA_MATERIALS_LIST_ACTIVE = IntProperty()
    bpy.types.Scene.SCENE_PAPA_EXPORT_SETTINGS = PointerProperty(type=ExportPapaUISettings)
    
def unregister():
    from bpy.utils import unregister_class
    for cls in reversed(_classes):
        unregister_class(cls)
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)
    bpy.types.TOPBAR_MT_file_export.remove(menu_func_export)

    del bpy.types.Scene.SCENE_PAPA_MATERIALS_LIST
    del bpy.types.Scene.SCENE_PAPA_MATERIALS_LIST_ACTIVE
    del bpy.types.Scene.SCENE_PAPA_EXPORT_SETTINGS

if __name__ == "__main__":
    register()
