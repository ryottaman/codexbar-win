"""コンソール窓を出さずに起動するためのランチャー。

pythonw.exe / .pyw で実行、または PyInstaller の exe エントリとして使う。
main をモジュールとして import して起動する（exe 化でも動くようにするため、
run_path でのファイル読込はしない）。

想定外の例外は error.log に記録する（exe 化時は exe と同じ場所）。
"""
import os
import sys
import traceback

if getattr(sys, "frozen", False):
    BASE = os.path.dirname(sys.executable)
else:
    BASE = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, BASE)

try:
    import main

    main.CodexBarApp().run()
except Exception:
    try:
        with open(os.path.join(BASE, "error.log"), "w", encoding="utf-8") as f:
            traceback.print_exc(file=f)
    except OSError:
        pass
    raise
