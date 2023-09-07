from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from typing import final

from .project import Project


class Package(ABC):
    @staticmethod
    def create(project_file: str | Path) -> Package:
        project = Project.load(project_file)
        return _RootPackage(project)

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @property
    @abstractmethod
    def source(self) -> Path:
        ...

    @property
    @abstractmethod
    def project(self) -> Project:
        ...

    @property
    def path(self) -> Path:
        return Path(self.name)

    @property
    def target_dir(self) -> Path:
        return self.path / 'target'

    @property
    def resource_dir(self) -> Path:
        return self.path / 'resource'

    @property
    def include_dir(self) -> Path:
        return self.path / 'include'

    @cached_property
    def deps_packages(self) -> tuple[Package, ...]:
        return tuple(_RootPackage(project) for project in self.project.dependencies)

    @cached_property
    def sub_packages(self) -> tuple[Package, ...]:
        res: tuple[Package, ...] = (self,)
        for package in self.deps_packages:
            res += package.sub_packages
        return res


@final
@dataclass(frozen=True)
class _RootPackage(Package):
    _project: Project

    @property
    def name(self) -> str:
        return self.project.name

    @property
    def source(self) -> Path:
        return self.project.path

    @property
    def project(self) -> Project:
        return self._project
