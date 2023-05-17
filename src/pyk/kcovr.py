#!/usr/bin/python3
import glob
import os
import sys
import time

if len(sys.argv) < 4:
  print('usage: ' + sys.argv[0] + ' <kompiled-dir>... -- <files>...')
  exit(1)
all_rules = set()
cover_map = {}

def add_cover(rule):
  rule = rule.strip()
  if not rule in cover_map:
    cover_map[rule] = 0
  cover_map[rule] += 1

for idx, dir in enumerate(sys.argv[1:], start=1):
  if dir == '--':
    file_idx = idx + 1
    break
  filename = dir + '/allRules.txt'
  with open(filename) as f:
    all_rules.update(f.readlines())
  filename = dir + '/coverage.txt'
  with open(filename) as f:
    for line in f:
      add_cover(line)
  for filename in glob.glob(dir + '/*_coverage.txt'):
    with open(filename) as f:
      for line in f:
        add_cover(line)

sources = [os.path.abspath(path) for path in  sys.argv[file_idx:]]

rule_map = {}

for line in all_rules:
  parts = line.split(' ')
  id = parts[0].strip()
  location = ' '.join(parts[1:])
  parts = location.split(':')
  rule_map[id] = (os.path.abspath(':'.join(parts[:-2])), parts[-2], parts[-1])

all_lines = set()

for _, value in rule_map.items():
  all_lines.add((value[0], value[1]))

def lines_covered(coverage_of_component):
  covered_lines = set()
  for rule_id in coverage_of_component:
    rule = rule_map[rule_id]
    covered_lines.add((rule[0], rule[1]))
  return len(covered_lines)

def rules_covered(coverage_of_component):
  return len(coverage_of_component)

num_rules_global = len(all_rules)
num_lines = len(all_lines)
line_rate_global = float(lines_covered(cover_map)) / num_lines
rule_rate_global = float(rules_covered(cover_map)) / num_rules_global
timestamp = int(time.time())

template = """
<coverage line-rate="{line_rate}" branch-rate="{ruleRate}" version="1.9" timestamp="{timestamp}">
  <sources>
    <source>{source}</source>
  </sources>
  <packages>
    <package name="" line-rate="{line_rate}" branch-rate="{ruleRate}" complexity="{numRules}.0">
      <classes>
        {classes_elem}
      </classes>
    </package>
  </packages>
</coverage>
"""

source = os.path.dirname(os.path.commonprefix(sources))

class_template = """
<class name="{filename}" filename="{filename}" line-rate="{line_rate}" branch-rate="{ruleRate}" complexity="{numRules}.0">
  <lines>
    {lines_elem}
  </lines>
</class>
"""

line_template_no_branch = """
<line number="{line_num}" hits="{hits}" branch="false"/>
"""

line_template_branch = """
<line number="{line_num}" hits="{hits}" branch="true" condition-coverage="{ruleRate}% ({rules_covered}/{numRules})">
  <conditions>
    <condition number="0" type="jump" coverage="{ruleRate}%"/>
  </conditions>
</line>
"""

rule_map_by_file = {}

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

  all_rules = rule_map_by_file[filename]
  rule_map_by_line = {}
  for key, value in all_rules.items():
    all_lines.add((value[0], value[1]))
    if not value[0] in rule_map_by_line:
      rule_map_by_line[value[0]] = [key]
    else:
      rule_map_by_line[value[0]].append(key)

  file_coverage = {rule: num for rule, num in cover_map.items() if rule in all_rules}

  num_rules_file = len(all_rules)
  num_lines = len(all_lines)
  line_rate_file = float(lines_covered(file_coverage)) / num_lines
  rule_rate_file = float(rules_covered(file_coverage)) / num_rules_file

  lines = []

  for line_num,rules in rule_map_by_line.items():
    line_coverage = {rule: num for rule, num in file_coverage.items() if rule in rules}
    hits = sum(line_coverage.values())
    num_covered = len(line_coverage)
    num_rules_line = len(rules)
    rule_rate_line = float(num_covered) / num_rules_line
    if num_rules_line == 1:
      lines.append(line_template_no_branch.format(line_num=line_num,hits=hits))
    else:
      lines.append(line_template_branch.format(line_num=line_num,hits=hits,ruleRate=int(rule_rate_line*100),rules_covered=num_covered,numRules=num_rules_line))
  lines_elem = ''.join(lines)
  classes.append(class_template.format(filename=relative_file,line_rate=line_rate_file,ruleRate=rule_rate_file,numRules=num_rules_file,lines_elem=lines_elem))

classes_elem = ''.join(classes)
xml = template.format(line_rate=line_rate_global,ruleRate=rule_rate_global,timestamp=timestamp,numRules=num_rules_global,source=source,classes_elem=classes_elem)
print(xml)
