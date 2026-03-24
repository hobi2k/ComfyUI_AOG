"""Handle frame extraction, ffmpeg assembly, and final media outputs."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Sequence


class MediaError(RuntimeError):
    """
    프레임 인코딩이나 ffmpeg 후처리가 실패했을 때 발생한다.
    """


def copy_last_frame(frame_paths: Sequence[Path], destination: str | Path) -> Path:
    """
    렌더된 프레임 시퀀스의 마지막 프레임을 별도 산출물로 복사한다.

    Args:
        frame_paths: 저장된 프레임 파일 목록이다.
        destination: 마지막 프레임을 저장할 경로다.

    Returns:
        복사된 마지막 프레임 경로다.
    """
    if not frame_paths:
        raise MediaError("No rendered frames were produced for the shot")
    destination_path = Path(destination)
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(frame_paths[-1], destination_path)
    return destination_path


def encode_frames_to_video(
    *,
    frame_dir: str | Path,
    fps: int,
    output_path: str | Path,
) -> Path:
    """
    번호가 매겨진 PNG 프레임을 중간 영상 파일로 인코딩한다.

    Args:
        frame_dir: 입력 프레임 디렉터리다.
        fps: 출력 프레임레이트다.
        output_path: 생성할 중간 영상 경로다.

    Returns:
        생성된 중간 영상 경로다.
    """
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    _run_ffmpeg(
        [
            "ffmpeg",
            "-y",
            "-framerate",
            str(fps),
            "-i",
            str(Path(frame_dir) / "frame_%05d.png"),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(output),
        ]
    )
    return output


def concatenate_videos(
    *,
    video_paths: Sequence[str | Path],
    output_path: str | Path,
) -> Path:
    """
    shot 단위 중간 영상을 순서대로 이어 붙인다.

    Args:
        video_paths: 합칠 영상 파일 목록이다.
        output_path: 이어 붙인 결과를 저장할 경로다.

    Returns:
        연결된 중간 영상 경로다.
    """
    if not video_paths:
        raise MediaError("At least one video path is required for concatenation")
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    concat_file = output.parent / "concat_inputs.txt"
    concat_file.write_text(
        "\n".join(f"file '{Path(path).resolve()}'" for path in video_paths),
        encoding="utf-8",
    )
    _run_ffmpeg(
        [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_file),
            "-c",
            "copy",
            str(output),
        ]
    )
    return output


def mux_video_and_audio(
    *,
    video_path: str | Path,
    audio_path: str | Path,
    output_path: str | Path,
    video_codec: str,
    audio_codec: str,
    pixel_format: str,
    upscale_scale: int | None = None,
    target_fps: int | None = None,
) -> Path:
    """
    생성된 영상과 오디오를 최종 결과물로 묶는다.

    Args:
        video_path: 중간 영상 경로다.
        audio_path: 생성된 오디오 경로다.
        output_path: 최종 출력 경로다.
        video_codec: 출력 비디오 코덱이다.
        audio_codec: 출력 오디오 코덱이다.
        pixel_format: 출력 픽셀 포맷이다.
        upscale_scale: 선택적 업스케일 배율이다.
        target_fps: 선택적 보간 목표 fps다.

    Returns:
        최종 출력 파일 경로다.
    """
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    filters: list[str] = []
    if upscale_scale and upscale_scale > 1:
        filters.append(f"scale=iw*{upscale_scale}:ih*{upscale_scale}:flags=lanczos")
    if target_fps and target_fps > 0:
        filters.append(f"minterpolate=fps={target_fps}")

    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(video_path),
        "-i",
        str(audio_path),
    ]
    if filters:
        command.extend(["-vf", ",".join(filters)])
    command.extend(
        [
            "-c:v",
            video_codec,
            "-pix_fmt",
            pixel_format,
            "-c:a",
            audio_codec,
            "-shortest",
            str(output),
        ]
    )
    _run_ffmpeg(command)
    return output


def _run_ffmpeg(command: list[str]) -> None:
    """
    ffmpeg 명령을 실행하고 실패 이유를 그대로 노출한다.

    Args:
        command: 실행할 ffmpeg 명령 토큰 목록이다.
    """
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise MediaError(
            "ffmpeg command failed.\n"
            f"Command: {' '.join(command)}\n"
            f"stderr:\n{result.stderr}"
        )
