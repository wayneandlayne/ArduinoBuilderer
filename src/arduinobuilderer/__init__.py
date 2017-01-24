import logging
import os
import subprocess
import argparse
import multiprocessing
import jinja2
import io
import time
from collections import defaultdict

logger = multiprocessing.log_to_stderr()
logger.setLevel(logging.INFO)

# This is kinda chipKIT specific now, but I want to modify it to be completely generic.

results = []


def run(sketch, board, arduino_path, core_path):
    # This will probably choke if the subprocess makes lots and lots of output.
    logger.info("Starting run.")

    def _build_command(sketch, board, arduino_path, core_path):
        return [os.path.join(arduino_path, "arduino-builder"),
                "-hardware={0}".format(os.path.join(arduino_path, "hardware")),
                "-hardware={0}".format(os.path.join(core_path, "..")),
                "-tools={0}".format(os.path.join(arduino_path, "tools-builder")),
                "-tools={0}".format(os.path.join(core_path, "pic32", "tools")),  # TODO: make core agnostic
                "-fqbn={0}".format(board),
                sketch]

    command = _build_command(sketch, board, arduino_path, core_path)
    logger.info("Going to execute: {0}".format(" ".join(command)))
    logger.info("Starting compile.")
    try:
        output = subprocess.check_output(command,
                                         stderr=subprocess.STDOUT,
                                         shell=False)
        returncode = 0
    except subprocess.CalledProcessError as e:
        returncode = e.returncode
        output = e.output
    logger.info("Finished.")

    r = Result()
    r.sketch = sketch
    r.board = board
    r.output = output
    r.returncode = returncode
    r.command = command
    return r


def parse_args():
    parser = argparse.ArgumentParser(description='Process some integers.')
    parser.add_argument('--boards-file',
                        help='path to boards.txt')
    parser.add_argument('--core-name',
                        required=True,
                        help="chipkit-core for now.  used to build fqbn")
    parser.add_argument('--arduino-path',
                        help="path to the folder that holds arduino-builder")
    parser.add_argument('--core-path',
                        help="path to the chipkit-core folder that holds pic32")
    parser.add_argument('--boards',
                        default=[],
                        nargs="*",
                        help="space delimited fqbns of boards to build. defaults to 'all of them.'")
    parser.add_argument('--sketch-base-paths',
                        default=[],
                        nargs="*",
                        help="space delimited paths to places to recurse for ino files for.")
    parser.add_argument('--sketches',
                        default=[],
                        nargs="*",
                        help="space delimited paths to ino files", )
    parser.add_argument('--output',
                        required=True,
                        help="output file")

    out = parser.parse_args()

    if not out.boards:
        out.boards = get_boards_from_boards_file(out.core_name, out.boards_file)

    if not out.sketches and not out.sketch_base_paths:
        raise argparse.ArgumentError("Must specify either --sketches or --sketch-base-paths")

    if out.sketch_base_paths:
        for sketch_base_path in out.sketch_base_paths:
            out.sketches.extend(get_sketches_from_base_path(sketch_base_path))
    return out


def get_boards_from_boards_file(core_name, boards_file_path):
    boards = []

    with open(boards_file_path) as f:
        for line in f:
            if not line.startswith("#") and ".platform" in line:
                platform = line.strip().split("=")[1]
                name = line.split(".")[0]
                board_name = "{0}:{1}:{2}".format(core_name,
                                                  platform,
                                                  name)
                boards.append(board_name)
    return boards


def get_sketches_from_base_path(base_path):
    sketches = []
    # TODO might need to make this also check if the parent directory matches basename, not sure
    for root, dirs, files in os.walk(base_path):
        for f in files:
            if f.endswith('.ino'):
                sketches.append(os.path.join(root, f))
    return sketches


class Result:
    pass


def log_result(arg):
    results.append(arg)


def main():
    logger.info("Hello world.")
    args = parse_args()

    logger.info("Going to build for {0} boards:".format(len(args.boards)))
    for board in args.boards:
        logger.info("\t{0}".format(board))

    logger.info("Going to build {0} sketches:".format(len(args.sketches)))
    for sketch in args.sketches:
        logger.info("\t{0}".format(sketch))

    pool = multiprocessing.Pool(processes=1)  # sigh, what isn't safe here?

    start_time = time.time()

    for board in args.boards:
        for sketch in args.sketches:
            pool.apply_async(run,
                             args=(sketch, board, args.arduino_path, args.core_path),
                             callback=log_result)
    logger.info("Done spinning up jobs.")

    pool.close()
    pool.join()
    logger.info("Finished running jobs.")
    end_time = time.time()
    logger.info("Duration: {0}".format(end_time - start_time))

    output = process_output(results, html_template)
    with io.open(args.output, 'w', encoding='utf-8') as f:
        f.write(output)

    logger.info("Finished writing output.")


class Results:
    def __init__(self):
        self.results = []

    def get_successes(self):
        return [result for result in self.results if result.returncode == 0]

    def get_failures(self):
        return [result for result in self.results if result.returncode != 0]

    def get_sorted_by_board(self):
        return sorted(self.results, key=lambda result: result.board)


text_template = jinja2.Template("""
Number of sketches tested: {{ results_by_sketch|length }}
Number of boards tested: {{ results_by_board|length }}
Total number of compiles: {{ num_compiles }}
Total number of successful compiles: {{ num_success }}
Total number of failed compiles: {{ num_failure }}

Sketch Summary
{% for sketch_name in results_by_sketch %}
Sketch {{ sketch_name }}
Number of successful compiles: {{ results_by_sketch[sketch_name].get_successes()|length }}
Number of failed compiles: {{ results_by_sketch[sketch_name].get_failures()|length }}
{% if results_by_sketch[sketch_name].get_successes() -%}
Successes:
{% for result in results_by_sketch[sketch_name].get_successes() -%}
{{ result.board }}
{% endfor %}
{%- endif %}
{% if results_by_sketch[sketch_name].get_failures() -%}
Failures:
{% for result in results_by_sketch[sketch_name].get_failures() -%}
{{ result.board }}
{% endfor %}
{%- endif %}
{% endfor %}

Board Summary
{% for board_name in results_by_board %}
Board {{ board_name }}
Number of successful compiles: {{ results_by_board[board_name].get_successes()|length }}
Number of failed compiles: {{ results_by_board[board_name].get_failures()|length }}
{% if results_by_board[board_name].get_successes() -%}
Successes:
{% for result in results_by_board[board_name].get_successes() -%}
{{ result.sketch }}
{%- endfor %}
{%- endif %}
{% if results_by_board[board_name].get_failures() -%}
Failures:
{% for result in results_by_board[board_name].get_failures() -%}
{{ result.sketch }}
{%- endfor %}
{%- endif %}
{% endfor %}

All Results
{% for result in all_results.results %}
Sketch: {{ result.sketch }}
Board: {{ result.board }}
Status: {% if result.returncode == 0 %}pass{% else %}FAIL (Return code: {{result.returncode}}){% endif %}
Output: {{ result.output }}
{% endfor %}
""")

html_template = jinja2.Template("""
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <title>Results</title>
    <style>
    /* from https://css-tricks.com/rotated-table-column-headers/ */

.table-header-rotated {
  border-collapse: collapse;
}

.table-header-rotated td {
  width: 30px;
}

.table-header-rotated td {
  text-align: center;
  padding: 10px 5px;
  border: 1px solid #ccc;
}
.table-header-rotated th.rotate {
  height: 140px;
  white-space: nowrap;
}

.table-header-rotated th.rotate > div {
  -webkit-transform: translate(16px, 51px) rotate(315deg);
          transform: translate(16px, 51px) rotate(315deg);
  width: 30px;
}

.table-header-rotated th.rotate > div > span {
  border-bottom: 1px solid #ccc;
  padding: 5px 10px;
}
.table-header-rotated th.row-header {
  padding: 0 10px;
  border-bottom: 1px solid #ccc;
  text-align: right;
}

</style>
  </head>
  <body>
    <h1>Sketch/Board Analysis</h1>
    <h2>Summary</h2>
    Number of compilations: {{ num_compiles }}<br />
    Number of successful compiles: {{ num_success }} <br />
    Number of failed compiles: {{ num_failure }}<br />

    <h2>Table view</h2>
    (The cells are clickable!)<br />
    <table class="table table-header-rotated">
    <thead>
    <tr>
    <th></th>
    {% for board_name in indexed.keys()|sort %}
        <th class="rotate"><div><span><a href="#{{ board_name }}">{{ board_name }}</a></span></div></th>
    {% endfor %}
    </tr>
    </thead>
    <tbody>
    {% for sketch_name in results_by_sketch.keys()|sort %}
    <tr>
        <th class="row-header"><a href="#{{ sketch_name }}">{{ sketch_name }}</a></td>
        {% for board_name in indexed.keys()|sort %}
        {% set r = indexed[board_name][sketch_name] %}
        <td onclick="document.location = '#{{r.board}}-{{r.sketch}}';"
        style="cursor:pointer; background-color:{% if r.returncode == 0 %}lightgreen{% else %}lightcoral{%endif%}">
        </td>
        {% endfor %}
    </tr>
    {% endfor %}
    </tbody>
    </table>

    <h2>Sketch Summary</h2>
    {% for sketch_name in results_by_sketch %}
    <a name="{{sketch_name}}"></a>

<h3>Sketch {{ sketch_name }}</h3>
Number of successful compiles: {{ results_by_sketch[sketch_name].get_successes()|length }}<br />
Number of failed compiles: {{ results_by_sketch[sketch_name].get_failures()|length }}<br />
{% if results_by_sketch[sketch_name].get_successes() %}
<h4>Successes</h4>
<ul>
{% for result in results_by_sketch[sketch_name].get_successes() -%}
<li><a href="#{{result.board}}-{{result.sketch}}">{{ result.board }}</a></li>
{% endfor %}
</ul>
{% endif %}
{% if results_by_sketch[sketch_name].get_failures() -%}
<h4>Failures</h4>
<ul>
{% for result in results_by_sketch[sketch_name].get_failures() -%}
<li><a href="#{{result.board}}-{{result.sketch}}">{{ result.board }}</a></li>
{% endfor %}
</ul>
{%- endif %}
{% endfor %}

<h2>Board Summary</h2>
{% for board_name in results_by_board %}
<a name="{{board_name}}"></a>
<h3>Board {{ board_name }}</h3>
Number of successful compiles: {{ results_by_board[board_name].get_successes()|length }}<br />
Number of failed compiles: {{ results_by_board[board_name].get_failures()|length }}<br />
{% if results_by_board[board_name].get_successes() -%}
<h4>Successes</h4>
<ul>
{% for result in results_by_board[board_name].get_successes() -%}
<li><a href="#{{result.board}}-{{result.sketch}}">{{ result.sketch }}</a></li>
{%- endfor %}
</ul>
{%- endif %}
{% if results_by_board[board_name].get_failures() -%}
<h4>Failures</h4>
<ul>
{% for result in results_by_board[board_name].get_failures() -%}
<li><a href="#{{result.board}}-{{result.sketch}}">{{ result.sketch }}</a></li>
{%- endfor %}
</ul>
{%- endif %}
{% endfor %}

<h2>All Results</h2>
{% for result in all_results.results %}
<a name="{{result.board}}-{{result.sketch}}"></a>
Sketch: {{ result.sketch }}<br />
Board: {{ result.board }}<br />
Status: {% if result.returncode == 0 %}pass{% else %}FAIL (Return code: {{result.returncode}}){% endif %}<br />
Output: <br />
<pre>{{ result.output }}</pre>
<hr />
{% endfor %}


  </body>
</html>
""")

blah = """


Number of sketches tested: {{ results_by_sketch|length }}
Number of boards tested: {{ results_by_board|length }}
Total number of compiles: {{ num_compiles }}
Total number of successful compiles: {{ num_success }}
Total number of failed compiles: {{ num_failure }}

Sketch Summary


Board Summary
{% for board_name in results_by_board %}
Board {{ board_name }}
Number of successful compiles: {{ results_by_board[board_name].get_successes()|length }}
Number of failed compiles: {{ results_by_board[board_name].get_failures()|length }}
{% if results_by_board[board_name].get_successes() -%}
Successes:
{% for result in results_by_board[board_name].get_successes() -%}
{{ result.sketch }}
{%- endfor %}
{%- endif %}
{% if results_by_board[board_name].get_failures() -%}
Failures:
{% for result in results_by_board[board_name].get_failures() -%}
{{ result.sketch }}
{%- endfor %}
{%- endif %}
{% endfor %}

All Results
{% for result in all_results.results %}
Sketch: {{ result.sketch }}
Board: {{ result.board }}
Status: {% if result.returncode == 0 %}pass{% else %}FAIL (Return code: {{result.returncode}}){% endif %}
Output: {{ result.output }}
{% endfor %}
"""


def process_output(results, template):
    by_sketch = defaultdict(Results)
    by_board = defaultdict(Results)
    all_results = Results()
    indexed = {}
    # details = []

    for result in results:
        by_sketch[result.sketch].results.append(result)
        by_board[result.board].results.append(result)
        if result.board not in indexed:
            indexed[result.board] = {}  # *sigh*?
        indexed[result.board][result.sketch] = result
        all_results.results.append(result)

    return template.render(results_by_sketch=by_sketch,
                           results_by_board=by_board,
                           all_results=all_results,
                           indexed=indexed,
                           num_compiles=len(all_results.results),
                           num_success=len(all_results.get_successes()),
                           num_failure=len(all_results.get_failures())
                           )


if __name__ == "__main__":
    main()
