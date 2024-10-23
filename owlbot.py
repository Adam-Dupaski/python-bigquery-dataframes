# Copyright 2021 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""This script is used to synthesize generated parts of this library."""

import pathlib
import re
import textwrap

from synthtool import gcp
import synthtool as s
from synthtool.languages import python

REPO_ROOT = pathlib.Path(__file__).parent.absolute()

common = gcp.CommonTemplates()

# ----------------------------------------------------------------------------
# Add templated files
# ----------------------------------------------------------------------------
templated_files = common.py_library(
    unit_test_python_versions=["3.9", "3.10", "3.11", "3.12"],
    system_test_python_versions=["3.9", "3.11", "3.12"],
    cov_level=35,
    intersphinx_dependencies={
        "pandas": "https://pandas.pydata.org/pandas-docs/stable/",
        "pydata-google-auth": "https://pydata-google-auth.readthedocs.io/en/latest/",
    },
)
s.move(
    templated_files,
    excludes=[
        # Multi-processing note isn't relevant, as bigframes is responsible for
        # creating clients, not the end user.
        "docs/multiprocessing.rst",
        "noxfile.py",
        ".pre-commit-config.yaml",
        "README.rst",
        "CONTRIBUTING.rst",
        ".github/release-trigger.yml",
        # BigQuery DataFrames manages its own Kokoro cluster for presubmit & continuous tests.
        ".kokoro/build.sh",
        ".kokoro/continuous/common.cfg",
        ".kokoro/presubmit/common.cfg",
    ],
)

# ----------------------------------------------------------------------------
# Fixup files
# ----------------------------------------------------------------------------

# Encourage sharring all relevant versions in bug reports.
assert 1 == s.replace(
    [".github/ISSUE_TEMPLATE/bug_report.md"],
    re.escape("#### Steps to reproduce\n"),
    textwrap.dedent(
        """
        ```python
        import sys
        import bigframes
        import google.cloud.bigquery
        import ibis
        import pandas
        import pyarrow
        import sqlglot

        print(f"Python: {sys.version}")
        print(f"bigframes=={bigframes.__version__}")
        print(f"google-cloud-bigquery=={google.cloud.bigquery.__version__}")
        print(f"ibis=={ibis.__version__}")
        print(f"pandas=={pandas.__version__}")
        print(f"pyarrow=={pyarrow.__version__}")
        print(f"sqlglot=={sqlglot.__version__}")
        ```

        #### Steps to reproduce
        """,
    ),
)

# Make sure build includes all necessary files.
assert 1 == s.replace(
    ["MANIFEST.in"],
    re.escape("recursive-include google"),
    "recursive-include third_party/bigframes_vendored *\nrecursive-include bigframes",
)

# Even though BigQuery DataFrames isn't technically a client library, we are
# opting into Cloud RAD for docs hosting.
assert 1 == s.replace(
    [".kokoro/docs/common.cfg"],
    re.escape('value: "docs-staging-v2-dev"'),
    'value: "docs-staging-v2"',
)

# Use a custom table of contents since the default one isn't organized well
# enough for the number of classes we have.
assert 1 == s.replace(
    [".kokoro/publish-docs.sh"],
    (
        re.escape("# upload docs")
        + "\n"
        + re.escape(
            'python3.10 -m docuploader upload docs/_build/html/docfx_yaml --metadata-file docs.metadata --destination-prefix docfx --staging-bucket "${V2_STAGING_BUCKET}"'
        )
    ),
    (
        "# Replace toc.yml template file\n"
        + "mv docs/templates/toc.yml docs/_build/html/docfx_yaml/toc.yml\n\n"
        + "# upload docs\n"
        + 'python3.10 -m docuploader upload docs/_build/html/docfx_yaml --metadata-file docs.metadata --destination-prefix docfx --staging-bucket "${V2_STAGING_BUCKET}"'
    ),
)

# Fixup the documentation.
assert 1 == s.replace(
    ["docs/conf.py"],
    re.escape("Google Cloud Client Libraries for bigframes"),
    "BigQuery DataFrames provides DataFrame APIs on the BigQuery engine",
)

# Don't omit `*/core/*.py` when counting test coverages
assert 1 == s.replace(
    [".coveragerc"],
    re.escape("  */core/*.py\n"),
    "",
)

# ----------------------------------------------------------------------------
# Samples templates
# ----------------------------------------------------------------------------

python.py_samples(skip_readmes=True)

# ----------------------------------------------------------------------------
# Final cleanup
# ----------------------------------------------------------------------------

s.shell.run(["nox", "-s", "format"], hide_output=False)
for noxfile in REPO_ROOT.glob("samples/**/noxfile.py"):
    s.shell.run(["nox", "-s", "format"], cwd=noxfile.parent, hide_output=False)
