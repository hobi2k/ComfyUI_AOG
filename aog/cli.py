import sys


def main() -> int:
    from custom_nodes.ComfyUI_AOG.run_aog_audio_pipeline import main as runner_main
    old_argv = sys.argv
    try:
        sys.argv = [old_argv[0], *old_argv[1:]]
        return int(runner_main())
    finally:
        sys.argv = old_argv


if __name__ == "__main__":
    raise SystemExit(main())
