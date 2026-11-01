# Custom User Automation Skill Template

## Overview
Serves as an extensible boilerplate for user-defined automations, domain-specific instructions, or custom webhook handlers.

## Guidelines for Authoring New Skills
1. Create a dedicated subdirectory in `skills/<your-skill-name>/`.
2. Define `manifest.json` with unique ID, type (`instruction_only`, `tool_based`, `script_enabled`), and permissions required.
3. Provide `SKILL.md` detailing purpose and parameters.
4. If script-enabled, provide `scripts/main.py` that reads JSON from `sys.stdin` and outputs JSON to `sys.stdout`.
5. Install or sync through the Skill Manager interface.

