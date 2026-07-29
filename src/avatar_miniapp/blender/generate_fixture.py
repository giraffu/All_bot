"""Generate the project-owned adult female fixture used by the LAN Mini App.

Run only inside Blender:
  blender --background --python generate_fixture.py -- --output /tmp/output
"""

import argparse
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector


def arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    return parser.parse_args(argv)


def material(name, color, metallic=0.0, roughness=0.55):
    value = bpy.data.materials.new(name)
    value.diffuse_color = (*color, 1.0)
    value.use_nodes = True
    principled = value.node_tree.nodes.get("Principled BSDF")
    principled.inputs["Base Color"].default_value = (*color, 1.0)
    principled.inputs["Metallic"].default_value = metallic
    principled.inputs["Roughness"].default_value = roughness
    return value


def add_ellipsoid(
    name,
    location,
    scale,
    mat,
    bone,
    armature,
    rotation=(0, 0, 0),
):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=20, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    obj.rotation_euler = rotation
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.data.materials.append(mat)
    world_matrix = obj.matrix_world.copy()
    obj.parent = armature
    obj.parent_type = "BONE"
    obj.parent_bone = bone
    obj.matrix_world = world_matrix
    return obj


def add_bone(edit_bones, name, head, tail, parent=None):
    bone = edit_bones.new(name)
    bone.head = head
    bone.tail = tail
    if parent:
        bone.parent = edit_bones[parent]
    return bone


def build_armature():
    bpy.ops.object.armature_add(enter_editmode=True, location=(0, 0, 0))
    armature = bpy.context.object
    armature.name = "AvatarRig"
    edit = armature.data.edit_bones
    edit.remove(edit[0])
    add_bone(edit, "hips", (0, 0, 0.92), (0, 0, 1.08))
    add_bone(edit, "spine", (0, 0, 1.08), (0, 0, 1.34), "hips")
    add_bone(edit, "chest", (0, 0, 1.34), (0, 0, 1.53), "spine")
    add_bone(edit, "neck", (0, 0, 1.53), (0, 0, 1.65), "chest")
    add_bone(edit, "head", (0, 0, 1.65), (0, 0, 1.88), "neck")
    for side, sign in (("L", 1), ("R", -1)):
        add_bone(
            edit,
            f"upper_arm.{side}",
            (0.18 * sign, 0, 1.5),
            (0.48 * sign, 0, 1.31),
            "chest",
        )
        add_bone(
            edit,
            f"lower_arm.{side}",
            (0.48 * sign, 0, 1.31),
            (0.71 * sign, 0, 1.1),
            f"upper_arm.{side}",
        )
        add_bone(
            edit,
            f"hand.{side}",
            (0.71 * sign, 0, 1.1),
            (0.81 * sign, 0, 1.01),
            f"lower_arm.{side}",
        )
        add_bone(
            edit,
            f"upper_leg.{side}",
            (0.11 * sign, 0, 0.96),
            (0.11 * sign, 0, 0.54),
            "hips",
        )
        add_bone(
            edit,
            f"lower_leg.{side}",
            (0.11 * sign, 0, 0.54),
            (0.11 * sign, 0, 0.12),
            f"upper_leg.{side}",
        )
        add_bone(
            edit,
            f"foot.{side}",
            (0.11 * sign, 0, 0.12),
            (0.11 * sign, -0.15, 0.06),
            f"lower_leg.{side}",
        )
    bpy.ops.object.mode_set(mode="POSE")
    for bone in armature.pose.bones:
        bone.rotation_mode = "XYZ"
    bpy.ops.object.mode_set(mode="OBJECT")
    armature.show_in_front = True
    return armature


def build_character(armature):
    skin = material("Skin", (0.62, 0.34, 0.25), roughness=0.62)
    suit = material("StudioSuit", (0.09, 0.12, 0.18), metallic=0.08, roughness=0.42)
    accent = material("SuitAccent", (0.08, 0.48, 0.56), metallic=0.2, roughness=0.3)
    hair = material("Hair", (0.035, 0.022, 0.018), roughness=0.48)
    add_ellipsoid("Head", (0, 0, 1.75), (0.115, 0.105, 0.145), skin, "head", armature)
    add_ellipsoid(
        "Hair", (0, 0.025, 1.81), (0.123, 0.112, 0.13), hair, "head", armature
    )
    add_ellipsoid("Neck", (0, 0, 1.59), (0.065, 0.06, 0.1), skin, "neck", armature)
    add_ellipsoid("Torso", (0, 0, 1.34), (0.245, 0.135, 0.30), suit, "chest", armature)
    add_ellipsoid("Waist", (0, 0, 1.11), (0.18, 0.115, 0.19), accent, "spine", armature)
    add_ellipsoid("Hips", (0, 0, 0.94), (0.235, 0.145, 0.18), suit, "hips", armature)
    for side, sign in (("L", 1), ("R", -1)):
        add_ellipsoid(
            f"UpperArm.{side}",
            (0.33 * sign, 0, 1.405),
            (0.18, 0.072, 0.072),
            suit,
            f"upper_arm.{side}",
            armature,
            (0, 0.56 * sign, 0),
        )
        add_ellipsoid(
            f"LowerArm.{side}",
            (0.595 * sign, 0, 1.205),
            (0.16, 0.06, 0.06),
            skin,
            f"lower_arm.{side}",
            armature,
            (0, 0.74 * sign, 0),
        )
        add_ellipsoid(
            f"Hand.{side}",
            (0.76 * sign, 0, 1.055),
            (0.075, 0.055, 0.045),
            skin,
            f"hand.{side}",
            armature,
            (0, 0.74 * sign, 0),
        )
        add_ellipsoid(
            f"UpperLeg.{side}",
            (0.11 * sign, 0, 0.73),
            (0.105, 0.115, 0.24),
            suit,
            f"upper_leg.{side}",
            armature,
        )
        add_ellipsoid(
            f"LowerLeg.{side}",
            (0.11 * sign, 0, 0.32),
            (0.085, 0.095, 0.23),
            suit,
            f"lower_leg.{side}",
            armature,
        )
        add_ellipsoid(
            f"Foot.{side}",
            (0.11 * sign, -0.09, 0.07),
            (0.09, 0.17, 0.07),
            accent,
            f"foot.{side}",
            armature,
        )


def key(armature, frame, rotations=None, location=None):
    rotations = rotations or {}
    bpy.context.scene.frame_set(frame)
    if location is not None:
        armature.pose.bones["hips"].location = location
        armature.pose.bones["hips"].keyframe_insert("location", frame=frame)
    for name, rotation in rotations.items():
        bone = armature.pose.bones[name]
        bone.rotation_euler = rotation
        bone.keyframe_insert("rotation_euler", frame=frame)


def action(armature, name, frames):
    value = bpy.data.actions.new(name)
    value.use_fake_user = True
    armature.animation_data_create()
    armature.animation_data.action = value
    for frame, rotations, location in frames:
        key(armature, frame, rotations, location)
    return value


def build_actions(armature):
    idle = action(
        armature,
        "idle",
        [
            (1, {}, (0, 0, 0)),
            (24, {"chest": (0.018, 0, 0)}, (0, 0, 0.008)),
            (48, {}, (0, 0, 0)),
        ],
    )
    action(
        armature,
        "turntable",
        [
            (1, {"hips": (0, 0, 0)}, None),
            (48, {"hips": (0, 0, math.pi)}, None),
            (96, {"hips": (0, 0, math.tau)}, None),
        ],
    )
    action(
        armature,
        "photo_pose",
        [
            (
                1,
                {
                    "upper_arm.L": (0, -0.18, 0.2),
                    "lower_arm.L": (0, 0.15, 0.55),
                    "upper_arm.R": (0, 0.2, -0.3),
                    "lower_arm.R": (0, -0.15, -0.75),
                    "upper_leg.L": (0.08, 0, 0.08),
                    "head": (0.03, 0.08, -0.08),
                },
                (0, 0, 0),
            ),
            (72, {"head": (-0.02, -0.05, 0.08)}, (0, 0, 0.012)),
        ],
    )
    action(
        armature,
        "dance_lite",
        [
            (1, {}, (0, 0, 0)),
            (
                12,
                {
                    "upper_arm.L": (0, 0, 0.65),
                    "upper_arm.R": (0, 0, -0.65),
                    "spine": (0, 0, 0.12),
                },
                (0.04, 0, 0.035),
            ),
            (
                24,
                {
                    "upper_arm.L": (0, 0, -0.45),
                    "upper_arm.R": (0, 0, 0.45),
                    "spine": (0, 0, -0.12),
                },
                (-0.04, 0, 0),
            ),
            (
                36,
                {
                    "upper_arm.L": (0, 0, 0.65),
                    "upper_arm.R": (0, 0, -0.65),
                    "spine": (0, 0, 0.12),
                },
                (0.04, 0, 0.035),
            ),
            (48, {}, (0, 0, 0)),
        ],
    )
    armature.animation_data.action = idle


def add_studio():
    world = bpy.context.scene.world or bpy.data.worlds.new("World")
    bpy.context.scene.world = world
    world.color = (0.025, 0.035, 0.055)
    bpy.ops.object.light_add(type="AREA", location=(2.4, -3.0, 3.2))
    bpy.context.object.data.energy = 900
    bpy.context.object.data.shape = "DISK"
    bpy.context.object.data.size = 3.0
    bpy.ops.object.light_add(type="AREA", location=(-2.2, -1.2, 2.3))
    bpy.context.object.data.energy = 600
    bpy.context.object.data.size = 2.0
    bpy.ops.object.light_add(type="AREA", location=(0, 2.2, 2.7))
    bpy.context.object.data.energy = 800
    bpy.context.object.data.size = 2.0
    bpy.ops.mesh.primitive_plane_add(size=12, location=(0, 0, 0))
    floor = bpy.context.object
    floor.name = "StudioFloor"
    floor.data.materials.append(material("Floor", (0.045, 0.06, 0.09), roughness=0.8))


def point_camera(camera, point):
    direction = Vector(point) - camera.location
    camera.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def camera_for(location):
    camera = bpy.data.objects.get("StudioCamera")
    if camera is None:
        bpy.ops.object.camera_add(location=location)
        camera = bpy.context.object
        camera.name = "StudioCamera"
        bpy.context.scene.camera = camera
    camera.location = location
    camera.data.lens = 58
    point_camera(camera, (0, 0, 0.95))
    return camera


def render(path, camera_location, resolution=(768, 1024)):
    camera_for(camera_location)
    scene = bpy.context.scene
    scene.render.resolution_x = resolution[0]
    scene.render.resolution_y = resolution[1]
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = str(path)
    scene.frame_set(1)
    bpy.ops.render.render(write_still=True)


def main():
    args = arguments()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    try:
        scene.render.engine = "BLENDER_EEVEE_NEXT"
    except TypeError:
        scene.render.engine = "BLENDER_EEVEE"
    scene.eevee.taa_render_samples = 16
    scene.render.film_transparent = False
    scene.render.resolution_percentage = 100
    scene.render.image_settings.color_mode = "RGBA"
    armature = build_armature()
    build_character(armature)
    build_actions(armature)
    add_studio()
    render(output / "model_front.png", (0, -4.3, 1.15))
    render(output / "model_back.png", (0, 4.3, 1.15))
    render(output / "model_left.png", (-4.3, 0, 1.15))
    render(output / "model_right.png", (4.3, 0, 1.15))
    render(output / "thumbnail.png", (2.5, -3.3, 1.45), (768, 768))
    scene.frame_start = 1
    scene.frame_end = 96
    bpy.ops.wm.save_as_mainfile(filepath=str(output / "avatar.blend"))
    bpy.ops.object.select_all(action="DESELECT")
    bpy.context.view_layer.objects.active = armature
    armature.select_set(True)
    for child in armature.children:
        child.select_set(True)
    try:
        bpy.ops.export_scene.gltf(
            filepath=str(output / "avatar.glb"),
            export_format="GLB",
            use_selection=True,
            export_animations=True,
            export_animation_mode="ACTIONS",
        )
    except TypeError:
        bpy.ops.export_scene.gltf(
            filepath=str(output / "avatar.glb"),
            export_format="GLB",
            use_selection=True,
            export_animations=True,
        )


if __name__ == "__main__":
    main()
