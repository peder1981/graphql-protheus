# -*- coding: utf-8 -*-
"""Configuracao pytest dos testes TIR do servico GraphQL Protheus.

- Garante que `tests/` esteja no sys.path para `from contrib.tir import Webapp`.
- Coleta arquivos *.tir como modulos de teste Python (compile + exec, sem tocar
  nos arquivos .tir originais).
"""

import sys
import types
from pathlib import Path

TESTS_DIR = Path(__file__).parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from _pytest.python import Module  # noqa: E402


class TirModule(Module):
    """Module collector que executa arquivos .tir como codigo Python."""

    def _getobj(self):
        source = self.path.read_text(encoding="utf-8")
        code = compile(source, str(self.path), "exec")
        modname = "tir_" + self.path.stem
        mod = types.ModuleType(modname)
        mod.__file__ = str(self.path)
        sys.modules[modname] = mod
        exec(code, mod.__dict__)
        return mod


def pytest_collect_file(file_path, parent):
    if file_path.suffix == ".tir" and file_path.name.startswith("test_"):
        return TirModule.from_parent(parent, path=file_path)
    return None