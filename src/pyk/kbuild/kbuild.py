import shutil
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from typing import List, Union, final

from ..ktool.kompile import kompile
from .package import Package
from .utils import k_version, sync_files


@final
@dataclass(frozen=True)
class KBuild:
    kbuild_dir: Path

    def __init__(self, kbuild_dir: Union[str, Path]):
        kbuild_dir = Path(kbuild_dir).resolve()
        object.__setattr__(self, 'kbuild_dir', kbuild_dir)

    @cached_property
    def k_version(self) -> str:
        return k_version().text

    def definition_dir(self, package: Package, target_name: str) -> Path:
        return self.kbuild_dir / package.target_dir / self.k_version / target_name

    def resource_dir(self, package: Package) -> Path:
        return self.kbuild_dir / package.resource_dir

    def include_dir(self, package: Package) -> Path:
        return self.kbuild_dir / package.include_dir

    def source_dir(self, package: Package) -> Path:
        return self.include_dir(package) / package.name

    def source_files(self, package: Package) -> List[Path]:
        return [self.source_dir(package) / file_name for file_name in package.project.source_file_names]

    def clean(self, package: Package, target_name: str) -> None:
        shutil.rmtree(self.definition_dir(package, target_name), ignore_errors=True)

    def sync(self, package: Package) -> List[Path]:
        res: List[Path] = []

        # Sync sources
        res += sync_files(
            source_dir=package.project.source_dir,
            target_dir=self.source_dir(package),
            file_names=package.project.source_file_names,
        )

        # Sync resources
        for resource_dir in package.project.resources:
            source_dir = package.project.resources[resource_dir]
            target_dir = self.resource_dir(package) / resource_dir
            file_names = package.project.resource_file_names[source_dir]
            res += sync_files(source_dir, target_dir, file_names)
        return res

    def kompile(self, package: Package, target_name: str) -> Path:
        for sub_package in package.sub_packages:
            self.sync(sub_package)

        output_dir = self.definition_dir(package, target_name)

        if self.up_to_date(package, target_name):
            return output_dir

        target = package.project.get_target(target_name)
        kompile(
            main_file=self.source_dir(package) / target.main_file,
            output_dir=output_dir,
            include_dirs=[self.include_dir(sub_package) for sub_package in package.sub_packages],
            cwd=self.kbuild_dir,
            **target.kompile_args(),
        )

        return output_dir

    def up_to_date(self, package: Package, target_name: str) -> bool:
        definition_dir = self.definition_dir(package, target_name)
        timestamp = definition_dir / 'timestamp'

        if not timestamp.exists():
            return False

        input_files: List[Path] = []
        for sub_package in package.sub_packages:
            input_files.append(sub_package.project.project_file)
            input_files.extend(self.source_files(sub_package))

        input_timestamps = (input_file.stat().st_mtime for input_file in input_files)
        target_timestamp = timestamp.stat().st_mtime
        return all(input_timestamp < target_timestamp for input_timestamp in input_timestamps)
