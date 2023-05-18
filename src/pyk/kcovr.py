from __future__ import annotations

import glob
import os
import sys
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping


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
    sources = [os.path.abspath(path) for path in files]
    rule_map = create_rule_map(kompiled_dirs)
    cover_map = create_cover_map(kompiled_dirs)

    all_lines: set[tuple[str, str]] = set()
    for _, value in rule_map.items():
        all_lines.add((value[0], value[1]))

    def lines_covered(coverage_of_component: Mapping[str, int]) -> int:
        covered_lines = set()
        for rule_id in coverage_of_component:
            rule = rule_map[rule_id]
            covered_lines.add((rule[0], rule[1]))
        return len(covered_lines)

    def rules_covered(coverage_of_component: Mapping[str, int]) -> int:
        return len(coverage_of_component)

    num_rules_global = len(rule_map)  # should be the same as len(all_rules)
    num_lines = len(all_lines)
    line_rate_global = float(lines_covered(cover_map)) / num_lines
    rule_rate_global = float(rules_covered(cover_map)) / num_rules_global
    timestamp = int(time.time())

    template = """
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

    source = os.path.dirname(os.path.commonprefix(sources))

    class_template = """
    <class name="{filename}" filename="{filename}" line-rate="{line_rate}" branch-rate="{rule_rate}" complexity="{num_rules}.0">
      <lines>
        {lines_elem}
      </lines>
    </class>
    """

    line_template_no_branch = """
    <line number="{line_num}" hits="{hits}" branch="false"/>
    """

    line_template_branch = """
    <line number="{line_num}" hits="{hits}" branch="true" condition-coverage="{rule_rate}% ({rules_covered}/{num_rules})">
      <conditions>
        <condition number="0" type="jump" coverage="{rule_rate}%"/>
      </conditions>
    </line>
    """

    rule_map_by_file: dict[str, dict[str, tuple[str, str]]] = {}

    for id, loc in rule_map.items():
        if not loc[0] in rule_map_by_file:
            rule_map_by_file[loc[0]] = {}
        file_map = rule_map_by_file[loc[0]]
        file_map[id] = (loc[1], loc[2])

    classes = []

    for filename in sources:
        if not filename in rule_map_by_file:
            continue

        relative_file = os.path.relpath(filename, source)
        all_lines = set()

        all_rules_2 = rule_map_by_file[filename]  # TODO naming
        rule_map_by_line = {}
        for key, value_2 in all_rules_2.items():  # TODO naming
            all_lines.add((value_2[0], value_2[1]))
            if not value_2[0] in rule_map_by_line:
                rule_map_by_line[value_2[0]] = [key]
            else:
                rule_map_by_line[value_2[0]].append(key)

        file_coverage = {rule: num for rule, num in cover_map.items() if rule in all_rules_2}

        num_rules_file = len(all_rules_2)
        num_lines = len(all_lines)
        line_rate_file = float(lines_covered(file_coverage)) / num_lines
        rule_rate_file = float(rules_covered(file_coverage)) / num_rules_file

        lines = []

        for line_num, rules in rule_map_by_line.items():
            line_coverage = {rule: num for rule, num in file_coverage.items() if rule in rules}
            hits = sum(line_coverage.values())
            num_covered = len(line_coverage)
            num_rules_line = len(rules)
            rule_rate_line = float(num_covered) / num_rules_line
            if num_rules_line == 1:
                lines.append(line_template_no_branch.format(line_num=line_num, hits=hits))
            else:
                lines.append(
                    line_template_branch.format(
                        line_num=line_num,
                        hits=hits,
                        rule_rate=int(rule_rate_line * 100),
                        rules_covered=num_covered,
                        num_rules=num_rules_line,
                    )
                )
        lines_elem = ''.join(lines)
        classes.append(
            class_template.format(
                filename=relative_file,
                line_rate=line_rate_file,
                rule_rate=rule_rate_file,
                num_rules=num_rules_file,
                lines_elem=lines_elem,
            )
        )

    classes_elem = ''.join(classes)
    xml = template.format(
        line_rate=line_rate_global,
        rule_rate=rule_rate_global,
        timestamp=timestamp,
        num_rules=num_rules_global,
        source=source,
        classes_elem=classes_elem,
    )

    return xml


def create_rule_map(kompiled_dirs: Iterable[str]) -> dict[str, tuple[str, str, str]]:
    all_rules: set[str] = set()

    for kompiled_dir in kompiled_dirs:
        filename = kompiled_dir + '/allRules.txt'
        with open(filename) as f:
            all_rules.update(f.readlines())

    rule_map: dict[str, tuple[str, str, str]] = {}
    for line in all_rules:
        parts = line.split(' ')
        id = parts[0].strip()
        location = ' '.join(parts[1:])
        parts = location.split(':')
        rule_map[id] = (os.path.abspath(':'.join(parts[:-2])), parts[-2], parts[-1])

    assert len(all_rules) == len(rule_map)
    return rule_map


def create_cover_map(kompiled_dirs: Iterable[str]) -> dict[str, int]:
    cover_map: dict[str, int] = {}

    def add_cover(rule: str) -> None:
        rule = rule.strip()
        if not rule in cover_map:
            cover_map[rule] = 0
        cover_map[rule] += 1

    for kompiled_dir in kompiled_dirs:
        filename = kompiled_dir + '/coverage.txt'
        with open(filename) as f:
            for line in f:
                add_cover(line)
        for filename in glob.glob(kompiled_dir + '/*_coverage.txt'):
            with open(filename) as f:
                for line in f:
                    add_cover(line)

    return cover_map


if __name__ == '__main__':
    main()
