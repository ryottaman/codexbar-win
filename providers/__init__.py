"""プロバイダー登録。ここに追加すれば UI に自動で反映される。"""
from __future__ import annotations

from . import claude, codex, copilot, gemini

# (キー, 表示名, fetch関数) のタプル。上から順に表示される。
REGISTRY = [
    ("claude", "Claude", claude.fetch),
    ("codex", "Codex", codex.fetch),
    ("copilot", "Copilot", copilot.fetch),
    ("gemini", "Gemini", gemini.fetch),
]
