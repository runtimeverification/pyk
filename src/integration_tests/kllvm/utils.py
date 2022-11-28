from types import ModuleType

from pyk.kllvm.runtime import compile_runtime, import_runtime

from ..kompiled_test import KompiledTest


class RuntimeTest(KompiledTest):
    KOMPILE_BACKEND = 'llvm'

    runtime: ModuleType

    def setUp(self) -> None:
        super().setUp()
        compile_runtime(self.kompiled_dir)
        self.runtime = import_runtime(self.kompiled_dir)
