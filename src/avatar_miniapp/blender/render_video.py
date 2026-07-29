"""Render a validated Mini App recipe from a project-owned .blend file."""

import argparse
import json
import sys
from pathlib import Path

import bpy
from mathutils import Vector

ALLOWED_ANIMATIONS = {"idle", "turntable", "photo_pose", "dance_lite"}
CAMERAS = {
    "front": (0, -4.3, 1.15, (0, 0, 0.95)),
    "side": (4.3, 0, 1.15, (0, 0, 0.95)),
    "back": (0, 4.3, 1.15, (0, 0, 0.95)),
    "full_body": (2.5, -3.3, 1.35, (0, 0, 0.95)),
    "half_body": (1.5, -2.4, 1.55, (0, 0, 1.35)),
    "portrait": (0.75, -1.7, 1.68, (0, 0, 1.62)),
}
BACKGROUNDS = {
    "light": (0.72, 0.78, 0.86),
    "dark": (0.012, 0.018, 0.032),
    "studio": (0.025, 0.035, 0.055),
    "transparent": (0.0, 0.0, 0.0),
}


def arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument("--recipe", required=True)
    parser.add_argument("--frames", required=True)
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    return parser.parse_args(argv)


def point_camera(camera, target):
    direction = Vector(target) - camera.location
    camera.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def main():
    args = arguments()
    recipe = json.loads(Path(args.recipe).read_text(encoding="utf-8"))
    animation_id = recipe["animation_id"]
    if animation_id not in ALLOWED_ANIMATIONS:
        raise ValueError("INVALID_ANIMATION")
    resolution = recipe["resolution"].split("x")
    width, height = int(resolution[0]), int(resolution[1])
    if (width, height) not in {(720, 1280), (1280, 720), (1024, 1024)}:
        raise ValueError("INVALID_RESOLUTION")
    fps = int(recipe["fps"])
    duration = int(recipe["duration_seconds"])
    if fps not in {24, 30} or not 3 <= duration <= 10:
        raise ValueError("INVALID_TIMING")
    armature = bpy.data.objects["AvatarRig"]
    armature.animation_data_create()
    armature.animation_data.action = bpy.data.actions[animation_id]
    camera = bpy.data.objects["StudioCamera"]
    camera_values = CAMERAS[recipe["camera_preset"]]
    camera.location = camera_values[:3]
    point_camera(camera, camera_values[3])
    world = bpy.context.scene.world
    background = recipe["background"]
    world.color = BACKGROUNDS[background]
    scene = bpy.context.scene
    scene.render.film_transparent = background == "transparent"
    try:
        scene.render.engine = "BLENDER_EEVEE_NEXT"
    except TypeError:
        scene.render.engine = "BLENDER_EEVEE"
    scene.eevee.taa_render_samples = 8
    scene.render.resolution_x = width
    scene.render.resolution_y = height
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.fps = fps
    scene.frame_start = 1
    scene.frame_end = fps * duration
    scene.render.filepath = str(Path(args.frames) / "frame_")
    bpy.ops.render.render(animation=True)


if __name__ == "__main__":
    main()
