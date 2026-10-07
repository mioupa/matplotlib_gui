"""生成したスクリプトを CPython で実行し、図の要約（runner.figure_summary）を JSON で出力する小さな補助。

使い方: python run_script_summary.py SCRIPT.py   （MPLBACKEND=Agg、PYTHONPATH に py/ を足す。cwd はデータのあるフォルダ）
"""
import json
import runpy
import sys

from mplgui.runner import figure_summary

namespace = runpy.run_path(sys.argv[1])
print("FIGURE_SUMMARY:" + json.dumps(figure_summary(namespace["fig"])))
