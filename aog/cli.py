"""AOG CLI 진입점.

현재는 독립 러너 스크립트로 인자를 그대로 위임하는 얇은 래퍼 역할만 한다.
"""

import sys


def main() -> int:
    """패키지 경로를 유지한 채 실제 러너의 main 함수를 실행한다.

    Returns:
        러너가 반환한 종료 코드.
    """
    from custom_nodes.ComfyUI_AOG.run_aog_audio_pipeline import main as runner_main
    old_argv = sys.argv
    try:
        sys.argv = [old_argv[0], *old_argv[1:]]
        return int(runner_main())
    finally:
        sys.argv = old_argv


if __name__ == "__main__":
    raise SystemExit(main())
