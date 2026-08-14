from tooldrawer_studio.frozen_runtime import prepare_frozen_runtime

prepare_frozen_runtime()

from tooldrawer_studio.entrypoint import build_main_window, main

__all__ = ["build_main_window", "main"]


if __name__ == "__main__":
    raise SystemExit(main())
