"""コンソール窓を出さずに起動するためのランチャー。

pythonw.exe / .pyw で実行、または PyInstaller の exe エントリとして使う。
main をモジュールとして import して起動する（exe 化でも動くようにするため、
run_path でのファイル読込はしない）。

想定外の例外は error.log に記録する（exe 化時は %APPDATA%\\CodexBar）。
"""
import os
import sys
import traceback

if not getattr(sys, "frozen", False):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    import main

    if main.acquire_single_instance():
        main.CodexBarApp().run()
except Exception:
    try:
        from paths import APP_DIR

        log_dir = APP_DIR
    except Exception:
        log_dir = os.path.dirname(os.path.abspath(__file__))
    try:
        with open(os.path.join(log_dir, "error.log"), "w", encoding="utf-8") as f:
            traceback.print_exc(file=f)
    except OSError:
        pass
    raise
