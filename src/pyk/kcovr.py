from __future__ import annotations

import glob
import os
import sys
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping
    from typing import Final


TEMPLATE: Final = """
<coverage line-rate="{line_rate}" branch-rate="{rule_rate}" version="1.9" timestamp="{timestamp}">
  <sources>
    <source>{source}</source>
  </sources>
  <packages>
    <package name="" line-rate="{line_rate}" branch-rate="{rule_rate}" complexity="{num_rules}.0">
      <classes>
        {classes_elem}
      </classes>
    </package>
  </packages>
</coverage>
"""

CLASS_TEMPLATE: Final = """
<class name="{filename}" filename="{filename}" line-rate="{line_rate}" branch-rate="{rule_rate}" complexity="{num_rules}.0">
  <lines>
    {lines_elem}
  </lines>
</class>
"""

LINE_TEMPLATE_NO_BRANCH: Final = """
<line number="{line_num}" hits="{hits}" branch="false"/>
"""

LINE_TEMPLATE_BRANCH: Final = """
<line number="{line_num}" hits="{hits}" branch="true" condition-coverage="{rule_rate}% ({rules_covered}/{num_rules})">
  <conditions>
    <condition number="0" type="jump" coverage="{rule_rate}%"/>
  </conditions>
</line>
"""


def main() -> None:
    if len(sys.argv) < 4:
        print('usage: ' + sys.argv[0] + ' <kompiled-dir>... -- <files>...')
        exit(1)

    def split_at_dashes(xs: list[str]) -> tuple[list[str], list[str]]:
        for i, x in enumerate(xs):
            if x == '--':
                return xs[:i], xs[i + 1 :]
        return xs, []

    kompiled_dirs, files = split_at_dashes(sys.argv[1:])

    xml = render_coverage_xml(kompiled_dirs, files)
    print(xml)


def render_coverage_xml(kompiled_dirs: Iterable[str], files: Iterable[str]) -> str:
    rule_map = create_rule_map(kompiled_dirs)
    cover_map = create_cover_map(kompiled_dirs)
    sources = [os.path.abspath(path) for path in files]
    source = os.path.dirname(os.path.commonprefix(sources))

    classes = render_classes(rule_map, cover_map, sources, source)
    classes_elem = ''.join(classes)

    num_rules_covered_global = count_rules_covered(cover_map)
    num_rules_global = len(rule_map)
    rule_rate_global = float(num_rules_covered_global) / num_rules_global

    lines_covered_global = count_lines_covered(rule_map, cover_map)
    num_lines_global = count_lines_global(rule_map)
    line_rate_global = float(lines_covered_global) / num_lines_global

    timestamp = int(time.time())

    xml = TEMPLATE.format(
        line_rate=line_rate_global,
        rule_rate=rule_rate_global,
        timestamp=timestamp,
        num_rules=num_rules_global,
        source=source,
        classes_elem=classes_elem,
    )

    return xml


def render_classes(
    rule_map: Mapping[str, tuple[str, int, int]],
    cover_map: Mapping[str, int],
    sources: Iterable[str],
    source: str,
) -> list[str]:
    classes = []

    rule_map_by_file = create_rule_map_by_file(rule_map)
    for filename in sources:
        if not filename in rule_map_by_file:
            continue

        relative_file = os.path.relpath(filename, source)
        all_lines = set()

        rule_map_file = rule_map_by_file[filename]
        cover_map_file = {rule: cnt for rule, cnt in cover_map.items() if rule in rule_map_file}

        rule_map_by_line = {}
        for rule_id, (line, pos) in rule_map_file.items():
            all_lines.add((line, pos))
            if not line in rule_map_by_line:
                rule_map_by_line[line] = [rule_id]
            else:
                rule_map_by_line[line].append(rule_id)

        num_rules_covered_file = count_rules_covered(cover_map_file)
        num_rules_file = len(rule_map_file)
        rule_rate_file = float(num_rules_covered_file) / num_rules_file

        num_lines_covered_file = count_lines_covered(rule_map, cover_map_file)
        num_lines_file = len(all_lines)
        line_rate_file = float(num_lines_covered_file) / num_lines_file

        lines = []

        for line_num, rules in rule_map_by_line.items():
            line_coverage = {rule: cnt for rule, cnt in cover_map_file.items() if rule in rules}
            hits = sum(line_coverage.values())
            num_covered = len(line_coverage)
            num_rules_line = len(rules)
            rule_rate_line = float(num_covered) / num_rules_line
            if num_rules_line == 1:
                lines.append(LINE_TEMPLATE_NO_BRANCH.format(line_num=line_num, hits=hits))
            else:
                lines.append(
                    LINE_TEMPLATE_BRANCH.format(
                        line_num=line_num,
                        hits=hits,
                        rule_rate=int(rule_rate_line * 100),
                        rules_covered=num_covered,
                        num_rules=num_rules_line,
                    )
                )
        lines_elem = ''.join(lines)
        classes.append(
            CLASS_TEMPLATE.format(
                filename=relative_file,
                line_rate=line_rate_file,
                rule_rate=rule_rate_file,
                num_rules=num_rules_file,
                lines_elem=lines_elem,
            )
        )

    return classes


def create_rule_map(kompiled_dirs: Iterable[str]) -> dict[str, tuple[str, int, int]]:
    all_rules: set[str] = set()

    for kompiled_dir in kompiled_dirs:
        filename = kompiled_dir + '/allRules.txt'
        with open(filename) as f:
            all_rules.update(line.strip() for line in f.readlines())

    rule_map: dict[str, tuple[str, int, int]] = {}
    for line in all_rules:
        parts = line.split(' ')
        rule_id = parts[0]
        location = ' '.join(parts[1:])
        parts = location.split(':')
        rule_map[rule_id] = (os.path.abspath(':'.join(parts[:-2])), int(parts[-2]), int(parts[-1]))

    assert len(all_rules) == len(rule_map)
    return rule_map


def create_cover_map(kompiled_dirs: Iterable[str]) -> dict[str, int]:
    cover_map: dict[str, int] = {}

    def add_cover(rule_id: str) -> None:
        if not rule_id in cover_map:
            cover_map[rule_id] = 0
        cover_map[rule_id] += 1

    for kompiled_dir in kompiled_dirs:
        filename = kompiled_dir + '/coverage.txt'
        with open(filename) as f:
            for line in f:
                rule_id = line.strip()
                add_cover(rule_id)
        for filename in glob.glob(kompiled_dir + '/*_coverage.txt'):
            with open(filename) as f:
                for line in f:
                    rule_id = line.strip()
                    add_cover(rule_id)

    return cover_map


def create_rule_map_by_file(rule_map: Mapping[str, tuple[str, int, int]]) -> dict[str, dict[str, tuple[int, int]]]:
    rule_map_by_file: dict[str, dict[str, tuple[int, int]]] = {}

    for rule_id, (path, line, pos) in rule_map.items():
        if not path in rule_map_by_file:
            rule_map_by_file[path] = {}
        rule_map_by_file[path][rule_id] = (line, pos)

    return rule_map_by_file


def count_lines_global(rule_map: dict[str, tuple[str, int, int]]) -> int:
    return len({(src, line) for src, line, _pos in rule_map.values()})


def count_lines_covered(rule_map: Mapping[str, tuple[str, int, int]], cover_map: Mapping[str, int]) -> int:
    covered_lines = set()
    for rule_id in cover_map:
        rule = rule_map[rule_id]
        covered_lines.add((rule[0], rule[1]))
    return len(covered_lines)


def count_rules_covered(cover_map: Mapping[str, int]) -> int:
    return len(cover_map)


if __name__ == '__main__':
    main()
