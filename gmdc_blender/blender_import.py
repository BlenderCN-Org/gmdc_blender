'''
Copyright (C) 2018 SmugTomato

Created by SmugTomato

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <http://www.gnu.org/licenses/>.
'''
import bpy, math
import bmesh
from mathutils import Vector, Matrix, Quaternion
from bpy_extras.io_utils import ImportHelper
from bpy.props import StringProperty, BoolProperty, EnumProperty
from bpy.types import Operator

from .rcol.gmdc import GMDC
from .rcol.rcol_data import Rcol
from .rcol.data_helper import DataHelper
from . import blender_model
from .bone_data import BoneData

class ImportGMDC(Operator, ImportHelper):
    """Sims 2 GMDC Importer"""
    bl_idname = "import.gmdc_import"
    bl_label = "Sims 2 GMDC (.5gd)"
    bl_options = {'REGISTER', 'UNDO'}

    # ImportHelper mixin class uses this
    filename_ext = ".5gd"

    filter_glob = StringProperty(
            default="*.5gd",
            options={'HIDDEN'},
            maxlen=255,  # Max internal buffer length, longer would be clamped.
            )

    def execute(self, context):
        gmdc_data = GMDC.from_file_data(self.filepath)
        if gmdc_data.load_header() == False:
            print ('Unsupported GMDC version', hex(gmdc_data.header.file_type))
            return False

        gmdc_data.load_data()
        b_models = blender_model.BlenderModel.groups_from_gmdc(gmdc_data)

        armature = self.import_skeleton(gmdc_data)

        if b_models != False:
            for model in b_models:
                print( self.do_import(model, armature) )

        return {'FINISHED'}


    def parse_data(self, context, filepath):
        gmdc_data = GMDC.from_file_data(context, filepath)

        if gmdc_data.load_header() == False:
            print ('Unsupported GMDC version', hex(gmdc_data.header.file_type))
            return False

        gmdc_data.load_data()
        b_models = blender_model.BlenderModel.groups_from_gmdc(gmdc_data)
        return b_models


    def import_skeleton(self, data):
        skeldata = BoneData.build_bones(data)

        # Create armature and object
        name = 'Armature'
        bpy.ops.object.add(
            type='ARMATURE',
            enter_editmode=True,
            location=(0,0,0))
        # Armature object
        ob = bpy.context.object
        ob.show_x_ray = True
        ob.name = name
        # Armature
        amt = ob.data
        amt.draw_type = 'STICK'

        # Create bones from skeldata
        for bonedata in skeldata:
            bone = amt.edit_bones.new(bonedata.name)
            trans = Vector(bonedata.position)
            rot = Quaternion(bonedata.rotation)
            bone.tail = rot * trans
            if bonedata.parent != None:
                parent = amt.edit_bones[bonedata.parent]
                bone.parent = parent
                bone.head = parent.tail
            if bone.tail == bone.head:
                # Blender does not support 0 length bones
                bone.tail += Vector((0,0.00001,0))

            # Enter custom properties for exporting later
            # # Translate Vector
            bone['tX'] = bonedata.position[0]
            bone['tY'] = bonedata.position[1]
            bone['tZ'] = bonedata.position[2]
            # # Rotation Quaternion
            bone['rW'] = bonedata.rotation[0]
            bone['rX'] = bonedata.rotation[1]
            bone['rY'] = bonedata.rotation[2]
            bone['rZ'] = bonedata.rotation[3]


        # Go back to Object mode, scale the armature -1 along Z and apply the transform
        bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.transform.resize(value=(1, 1, -1))
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

        # Return the Armature object
        return ob


    def do_import(self, b_model, armature):
        print('Importing group:', b_model.name)

        # Create object and mesh
        mesh = bpy.data.meshes.new(b_model.name)
        object = bpy.data.objects.new(b_model.name, mesh)
        bpy.context.scene.objects.link(object)

        # Load vertices and faces
        mesh.from_pydata(b_model.vertices, [], b_model.faces)

        # Load normals
        for i, vert in enumerate(mesh.vertices):
            vert.normal = b_model.normals[i]
            pass

        # Create UV layer and load UV coordinates
        mesh.uv_textures.new('UVMap')
        for i, polygon in enumerate(mesh.polygons):
            for j, loopindex in enumerate(polygon.loop_indices):
                meshuvloop = mesh.uv_layers.active.data[loopindex]

                vertex_index = b_model.faces[i][j]
                meshuvloop.uv = b_model.uvs[vertex_index]

        # Create vertex groups for bone assignments
        for val in BoneData.bone_parent_table:
            object.vertex_groups.new(val[0])

        # Load bone assignments and weights
        # Check for mismatches in index counts
        if len(b_model.vertices) != len(b_model.bone_assign) or \
            len(b_model.vertices) != len(b_model.bone_weight):
            print(len(b_model.vertices), len(b_model.bone_assign), len(b_model.bone_weight))
            error = 'ERROR: Group ' + b_model.name + '\'s vertex index counts don\'t match.'
            return error

        for i in range(len(mesh.vertices)):
            test = mesh.vertices[i].co == Vector(b_model.vertices[i])
            if test != True:
                print(mesh.vertices[i].co, Vector(b_model.vertices[i]))

        print('Applying bone weights')
        for i in range(len(b_model.bone_assign)):
            remainder = 1.0     # Used for an implied 4th bone weight
            print(i, b_model.bone_assign[i])
            for j in range(len(b_model.bone_assign[i])):
                grpname = BoneData.bone_parent_table[ b_model.bone_assign[i][j] ][0]
                vertgroup = object.vertex_groups[grpname]
                print(grpname)

                if j != 3:
                    weight = b_model.bone_weight[i][j]
                    remainder -= weight
                    vertgroup.add( [i], weight, 'ADD' )
                else:
                    vertgroup.add( [i], remainder, 'ADD' )

        return 'Group ' + b_model.name + ' imported.\n'
