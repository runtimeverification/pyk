from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from typing import final

from .project import Project


@final
@dataclass(frozen=True)
class Package:
    project: Project

    @staticmethod
    def create(project_file: str | Path) -> Package:
        project = Project.load(project_file)
        return Package(project)

    @property
    def name(self) -> str:
        return self.project.name

    @property
    def source(self) -> Path:
        return self.project.path

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
        return tuple(Package(project) for project in self.project.dependencies)

    @cached_property
    def sub_packages(self) -> tuple[Package, ...]:
        res: tuple[Package, ...] = (self,)
        for package in self.deps_packages:
            res += package.sub_packages
        return res
