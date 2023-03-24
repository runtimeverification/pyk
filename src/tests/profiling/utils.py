from cProfile import Profile
from pathlib import Path
from pstats import SortKey, Stats
from typing import Any, ContextManager, Final, Iterable, Optional, Tuple, Union

TEST_DATA_DIR: Final = (Path(__file__).parent / 'test-data').resolve(strict=True)


class Profiler:
    _tmp_path: Path

    def __init__(self, tmp_path: Path):
        self._tmp_path = tmp_path

    def __call__(
        self,
        file_name: str = 'profile.txt',
        *,
        sort_keys: Iterable[Union[str, SortKey]] = (),
        patterns: Iterable[str] = (),
        limit: Optional[Union[int, float]] = None,
    ) -> ContextManager[None]:
        return ProfileContext(
            self._tmp_path / file_name,
            sort_keys=tuple(SortKey(key) for key in sort_keys),
            patterns=tuple(patterns),
            limit=limit,
        )


class ProfileContext(ContextManager[None]):
    _profile: Profile
    _profile_path: Path
    _sort_keys: Tuple[SortKey, ...]
    _patterns: Tuple[str, ...]
    _limit: Optional[Union[int, float]]

    def __init__(
        self,
        profile_path: Path,
        *,
        sort_keys: Tuple[SortKey, ...],
        patterns: Tuple[str, ...],
        limit: Optional[Union[int, float]],
    ):
        self._profile = Profile()
        self._profile_path = profile_path
        self._sort_keys = sort_keys
        self._patterns = patterns
        self._limit = limit

    def __enter__(self) -> None:
        self._profile.__enter__()

    def __exit__(self, *args: Any, **kwargs: Any) -> None:
        self._profile.__exit__(*args, **kwargs)
        with self._profile_path.open('w') as stream:
            stats = Stats(self._profile, stream=stream)
            stats.sort_stats(*self._sort_keys)
            restrictions = self._patterns + ((self._limit,) if self._limit is not None else ())
            stats.print_stats(*restrictions)
