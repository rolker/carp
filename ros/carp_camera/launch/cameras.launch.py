"""Both Pivariety cameras -> H.264 FFMPEGPacket, optionally recorded.

One component container holds, per camera, a camera_ros node and an
image_transport republisher (raw -> ffmpeg). Intra-process comms hand the
raw 1080p frames to the encoder without a copy through DDS; only the H.264
packets leave the process.

Topics, per camera N in {0, 1} (N = CAM/DISP port on the Pi 5):
    /cameras/camN/image_raw            raw bgr8 (only while subscribed)
    /cameras/camN/image_raw/ffmpeg     ffmpeg_image_transport_msgs/FFMPEGPacket
    /cameras/camN/camera_info

Needs: source ~/opt/libcamera/env.sh && source ~/ros2_ws/install/setup.bash
Defaults are 1280x720 at 10 fps: the most two software x264 encodes sustain
on an uncooled Pi 5 with headroom (~20% CPU, 65 C; 1080p30 saturated the CPU
at ~10 fps per camera and throttled at 85 C). See ADR-015.

Usage: ros2 launch carp_camera cameras.launch.py [record:=true] [fps:=10] ...
"""

import os
import time

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess, OpaqueFunction
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import ComposableNodeContainer
from launch_ros.descriptions import ComposableNode

# libcamera camera ids are device-tree paths, stable across boots
# (/dev/video* and /dev/media* numbering is not).
CAMERAS = {
    'cam0': '/base/axi/pcie@120000/rp1/i2c@88000/arducam_pivariety@c',
    'cam1': '/base/axi/pcie@120000/rp1/i2c@80000/arducam_pivariety@c',
}
NAMESPACE = 'cameras'


def pipeline(context):
    arg = lambda name: LaunchConfiguration(name).perform(context)  # noqa: E731
    fps = float(arg('fps'))
    frame_us = int(round(1e6 / fps))
    gop = max(1, int(round(fps * float(arg('keyframe_s')))))

    nodes = []
    for name, camera_id in CAMERAS.items():
        nodes.append(ComposableNode(
            package='camera_ros',
            plugin='camera::CameraNode',
            namespace=NAMESPACE,
            name=name,
            parameters=[{
                'camera': camera_id,
                'width': int(arg('width')),
                'height': int(arg('height')),
                # libcamera RGB888 = ROS bgr8, which the encoder takes
                # directly; YUYV costs an extra cv_bridge conversion.
                'format': 'RGB888',
                'frame_id': f'{name}_optical_frame',
                'FrameDurationLimits': [frame_us, frame_us],
            }],
            extra_arguments=[{'use_intra_process_comms': True}],
        ))
        nodes.append(ComposableNode(
            package='image_transport',
            plugin='image_transport::Republisher',
            namespace=NAMESPACE,
            name=f'{name}_encoder',
            parameters=[{
                'in_transport': 'raw',
                'out_transport': 'ffmpeg',
                'out.ffmpeg.encoder': 'libx264',
                'out.ffmpeg.pixel_format': 'yuv420p',
                'out.ffmpeg.gop_size': gop,
                'out.ffmpeg.bit_rate': int(arg('bit_rate')),
                'out.ffmpeg.max_b_frames': 0,
                'out.ffmpeg.encoder_av_options':
                    f"preset:{arg('preset')},tune:zerolatency",
            }],
            remappings=[
                ('in', f'{name}/image_raw'),
                ('out/ffmpeg', f'{name}/image_raw/ffmpeg'),
            ],
            extra_arguments=[{'use_intra_process_comms': True}],
        ))

    actions = [ComposableNodeContainer(
        name='camera_container',
        namespace=NAMESPACE,
        package='rclcpp_components',
        executable='component_container_mt',
        composable_node_descriptions=nodes,
        output='screen',
    )]

    bag = os.path.join(os.path.expanduser(arg('bag_dir')),
                       time.strftime('cameras_%Y-%m-%dT%H.%M.%S'))
    topics = [f'/{NAMESPACE}/{n}/{t}' for n in CAMERAS
              for t in ('image_raw/ffmpeg', 'camera_info')]
    actions.append(ExecuteProcess(
        cmd=['ros2', 'bag', 'record', '-s', 'mcap', '-o', bag, *topics],
        condition=IfCondition(arg('record')),
        output='screen',
    ))
    return actions


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument('fps', default_value='10'),
        DeclareLaunchArgument('width', default_value='1280'),
        DeclareLaunchArgument('height', default_value='720'),
        DeclareLaunchArgument('bit_rate', default_value='1500000',
                              description='per camera, bits/s'),
        DeclareLaunchArgument('keyframe_s', default_value='1.5',
                              description='keyframe interval (ADR-015: 1-2 s)'),
        DeclareLaunchArgument('preset', default_value='ultrafast',
                              description='x264 preset'),
        DeclareLaunchArgument('record', default_value='false'),
        DeclareLaunchArgument('bag_dir', default_value='~/bags'),
        OpaqueFunction(function=pipeline),
    ])
