# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
import sys
import google.auth
from google.auth.credentials import AnonymousCredentials

# Mock GCP credentials and set dummy project/location to satisfy client instantiation
google.auth.default = lambda *args, **kwargs: (AnonymousCredentials(), "dummy-project")
os.environ["GOOGLE_CLOUD_PROJECT"] = "dummy-project"
os.environ["GOOGLE_CLOUD_LOCATION"] = "us-east1"

from google.agents.cli.eval.cmd_grade import cmd_grade

if __name__ == "__main__":
    sys.argv = [
        "run_grade.py",
        "--traces",
        "artifacts/traces/generated_traces.json",
        "--config",
        "tests/eval/eval_config.yaml",
        "--output",
        "artifacts/grade_results/"
    ]
    try:
        cmd_grade()
    except SystemExit as e:
        sys.exit(e.code)
