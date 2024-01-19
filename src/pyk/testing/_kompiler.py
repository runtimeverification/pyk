from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import TYPE_CHECKING

import pytest

from ..kast.outer import read_kast_definition
from ..kcfg import KCFGExplore
from ..kllvm.compiler import compile_runtime
from ..kllvm.importer import import_runtime
from ..kore.pool import KoreServerPool
from ..kore.rpc import BoosterServer, KoreClient, KoreServer
from ..ktool import TypeInferenceMode
from ..ktool.kompile import DefinitionInfo, Kompile
from ..ktool.kprint import KPrint
from ..ktool.kprove import KProve
from ..ktool.krun import KRun

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from pathlib import Path
    from typing import Any, ClassVar

    from pytest import FixtureRequest, TempPathFactory

    from ..kast.outer import KDefinition
    from ..kcfg.semantics import KCFGSemantics
    from ..kllvm.runtime import Runtime
    from ..ktool.kprint import SymbolTable
    from ..utils import BugReport


class Kompiler:
    _path: Path
    _cache: dict[Kompile, Path]

    def __init__(self, tmp_path_factory: TempPathFactory):
        self._path = tmp_path_factory.mktemp('kompiled')
        self._cache = {}

    def __call__(self, main_file: str | Path, **kwargs: Any) -> Path:
        kwargs['main_file'] = main_file
        kompile = Kompile.from_dict(kwargs)
        if kompile not in self._cache:
            output_dir = self._path / self._uid(kompile)
            self._cache[kompile] = kompile(output_dir=output_dir, type_inference_mode=TypeInferenceMode.CHECKED)

        return self._cache[kompile]

    def _uid(self, kompile: Kompile) -> str:
        return f'{kompile.base_args.main_file.stem}-{kompile.backend.value}-{len(self._cache)}'


class KompiledTest:
    KOMPILE_MAIN_FILE: ClassVar[str | Path]
    KOMPILE_BACKEND: ClassVar[str | None] = None
    KOMPILE_ARGS: ClassVar[dict[str, Any]] = {}

    @pytest.fixture(scope='class')
    def definition_dir(self, kompile: Kompiler) -> Path:
        kwargs = dict(self.KOMPILE_ARGS)
        kwargs['main_file'] = self.KOMPILE_MAIN_FILE
        kwargs['backend'] = self.KOMPILE_BACKEND
        return kompile(**kwargs)

    @pytest.fixture(scope='class')
    def definition(self, definition_dir: Path) -> KDefinition:
        return read_kast_definition(definition_dir / 'compiled.json')

    @pytest.fixture(scope='class')
    def definition_info(self, definition_dir: Path) -> DefinitionInfo:
        return DefinitionInfo(definition_dir)


class KPrintTest(KompiledTest):
    @pytest.fixture
    def kprint(self, definition_dir: Path, tmp_path: Path) -> KPrint:
        use_directory = tmp_path / 'kprint'
        use_directory.mkdir()

        return KPrint(
            definition_dir,
            use_directory=use_directory,
            patch_symbol_table=self._update_symbol_table,
        )

    @staticmethod
    def _update_symbol_table(symbol_table: SymbolTable) -> None:
        pass


class KRunTest(KompiledTest):
    @pytest.fixture
    def krun(self, definition_dir: Path, tmp_path: Path) -> KRun:
        use_directory = tmp_path / 'krun'
        use_directory.mkdir()

        return KRun(
            definition_dir,
            use_directory=use_directory,
            patch_symbol_table=self._update_symbol_table,
        )

    @staticmethod
    def _update_symbol_table(symbol_table: SymbolTable) -> None:
        pass


class KProveTest(KompiledTest):
    KOMPILE_BACKEND = 'haskell'

    @pytest.fixture
    def kprove(self, definition_dir: Path, tmp_path: Path, bug_report: BugReport | None) -> KProve:
        use_directory = tmp_path / 'kprove'
        use_directory.mkdir()

        return KProve(
            definition_dir,
            use_directory=use_directory,
            bug_report=bug_report,
            patch_symbol_table=self._update_symbol_table,
        )

    @staticmethod
    def _update_symbol_table(symbol_table: SymbolTable) -> None:
        pass


class KCFGExploreTest(KPrintTest):
    @abstractmethod
    def semantics(self, definition: KDefinition) -> KCFGSemantics:
        ...

    @pytest.fixture
    def kcfg_explore(self, kprint: KProve, bug_report: BugReport | None) -> Iterator[KCFGExplore]:
        definition_dir = kprint.definition_dir
        main_module_name = kprint.main_module
        semantics = self.semantics(kprint.definition)
        with KoreServer(definition_dir, main_module_name, bug_report=bug_report) as server:
            with KoreClient('localhost', server.port, bug_report=bug_report) as client:
                yield KCFGExplore(kprint, client, kcfg_semantics=semantics)


class UseServer(Enum):
    LEGACY = 'legacy'
    BOOSTER = 'booster'
    BOTH = 'both'
    NONE = 'none'


class KoreClientTest(KompiledTest):
    DISABLE_LEGACY: ClassVar = False
    DISABLE_BOOSTER: ClassVar = False

    KOMPILE_BACKEND: ClassVar = 'haskell'
    KOMPILE_MAIN_FILE: ClassVar[str | Path]
    KOMPILE_MAIN_MODULE: ClassVar[str]
    KOMPILE_ARGS: ClassVar[dict[str, Any]] = {}

    LLVM_ARGS: ClassVar[dict[str, Any]] = {}

    CLIENT_TIMEOUT: ClassVar = 1000

    class ServerType(Enum):
        LEGACY = 'legacy'
        BOOSTER = 'booster'

        def enabled(self, use_server: UseServer) -> bool:
            match use_server:
                case UseServer.LEGACY:
                    return self is KoreClientTest.ServerType.LEGACY
                case UseServer.BOOSTER:
                    return self is KoreClientTest.ServerType.BOOSTER
                case UseServer.BOTH:
                    return True
                case UseServer.NONE:
                    return False
                case _:
                    raise AssertionError()

    # Should ideally depend on _server_type to avoid triggering kompilation,
    # but it can't due to method signature in superclass.
    # In the parameter list, always put after `kore_client`.
    @pytest.fixture(scope='class')
    def definition_dir(self, kompile: Kompiler) -> Path:
        assert self.KOMPILE_BACKEND == 'haskell'
        kwargs = dict(self.KOMPILE_ARGS)
        kwargs['backend'] = 'haskell'
        kwargs['main_file'] = self.KOMPILE_MAIN_FILE
        kwargs['main_module'] = self.KOMPILE_MAIN_MODULE
        return kompile(**kwargs)

    @pytest.fixture(scope='class', params=['legacy', 'booster'])
    def _server_type(self, request: FixtureRequest, use_server: UseServer) -> ServerType:
        res = self.ServerType(request.param)
        if not res.enabled(use_server):
            pytest.skip(f'Server is disabled globally: {res.value}')
        if (res is self.ServerType.LEGACY and self.DISABLE_LEGACY) or (
            res is self.ServerType.BOOSTER and self.DISABLE_BOOSTER
        ):
            pytest.skip(f'Server is disabled for this test: {res.value}')
        return res

    @pytest.fixture(scope='class')
    def llvm_dir(self, _server_type: ServerType, kompile: Kompiler) -> Path | None:
        if _server_type is not self.ServerType.BOOSTER:
            return None

        kwargs = dict(self.LLVM_ARGS)
        kwargs['backend'] = 'llvm'
        kwargs['main_file'] = self.KOMPILE_MAIN_FILE
        kwargs['main_module'] = self.KOMPILE_MAIN_MODULE
        kwargs['llvm_kompile_type'] = 'c'
        return kompile(**kwargs)

    @pytest.fixture
    def _kore_server(
        self,
        _server_type: ServerType,
        definition_dir: Path,
        llvm_dir: Path | None,
        bug_report: BugReport | None,
    ) -> Iterator[KoreServer]:
        match _server_type:
            case self.ServerType.LEGACY:
                assert not llvm_dir
                with KoreServer(
                    definition_dir,
                    self.KOMPILE_MAIN_MODULE,
                    bug_report=bug_report,
                ) as server:
                    yield server
            case self.ServerType.BOOSTER:
                assert llvm_dir
                with BoosterServer(
                    definition_dir,
                    llvm_dir,
                    self.KOMPILE_MAIN_MODULE,
                    bug_report=bug_report,
                    command=None,
                ) as server:
                    yield server
            case _:
                raise AssertionError

    @pytest.fixture
    def kore_client(self, _kore_server: KoreServer, bug_report: BugReport) -> Iterator[KoreClient]:
        with KoreClient('localhost', _kore_server.port, timeout=self.CLIENT_TIMEOUT, bug_report=bug_report) as client:
            yield client


class KoreServerPoolTest(KompiledTest, ABC):
    KOMPILE_BACKEND = 'haskell'

    POOL_MODULE_NAME: ClassVar[str]
    POOL_MAX_WORKERS: ClassVar[int | None] = None

    @pytest.fixture
    def create_server(self, definition_dir: Path) -> Callable[[], KoreServer]:
        def _create_server() -> KoreServer:
            return KoreServer(definition_dir, self.POOL_MODULE_NAME)

        return _create_server

    @pytest.fixture
    def server_pool(self, create_server: Callable[[], KoreServer]) -> Iterator[KoreServerPool]:
        with KoreServerPool(create_server, max_workers=self.POOL_MAX_WORKERS) as pool:
            yield pool


class RuntimeTest(KompiledTest):
    KOMPILE_BACKEND = 'llvm'

    @pytest.fixture(scope='class')
    def runtime(self, definition_dir: Path) -> Runtime:
        compile_runtime(definition_dir)
        return import_runtime(definition_dir)
