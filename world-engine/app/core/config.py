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
import yaml

# Default models
FLASH_MODEL = os.getenv("WORLD_ENGINE_FLASH_MODEL", "gemini-3.5-flash")
PRO_MODEL = os.getenv("WORLD_ENGINE_PRO_MODEL", "gemini-2.5-pro")

# Policy config path
ORIGINAL_POLICY_PATH = os.getenv("WORLD_ENGINE_POLICY_PATH", "policy.yaml")

# Dynamic resolution of model names to work around 404/quota issues on AI Studio free tier
POLICY_PATH = ORIGINAL_POLICY_PATH
if os.path.exists(ORIGINAL_POLICY_PATH):
    try:
        with open(ORIGINAL_POLICY_PATH) as f:
            config = yaml.safe_load(f) or {}
        
        # Intercept models section and map to gemini-2.5-flash
        if "models" in config:
            for k, v in config["models"].items():
                if v in ["gemini-flash", "gemini-pro", "gemini-flash-lite", "gemini-3.5-flash", "gemini-2.5-pro"]:
                    config["models"][k] = "gemini-2.5-flash"
        
        resolved_path = ORIGINAL_POLICY_PATH.replace(".yaml", "_resolved.yaml")
        with open(resolved_path, "w") as f:
            yaml.dump(config, f)
        
        POLICY_PATH = resolved_path
    except Exception as e:
        import sys
        print(f"Failed to pre-resolve policy configuration: {e}", file=sys.stderr)
