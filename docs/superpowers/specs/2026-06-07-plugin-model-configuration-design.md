# Design Spec — Resolving Plugin Model Fallback Errors

**Created:** 2026-06-07  
**Status:** Approved by User via Brainstorming Session  
**Topic:** Plugin Model Configuration

---

<section name="problem">

## 1. Problem Statement

Newly installed plugins (such as `micode` and other custom packages) register custom agents (e.g., `commander`, `octto`, `brainstormer`, `planner`, `implementer`, `reviewer`, etc.) instead of standard `plan`/`build` agents. 

When executing these agents, users encounter errors like `gpt-5.2 not init`. 

### Root Cause Analysis
1. In `~/.opencode/plugins/micode/src/utils/config.ts`, `DEFAULT_MODEL` is hardcoded to `"openai/gpt-5.2-codex"`.
2. The plugin's `config-loader` (`src/config-loader.ts`) checks the user's global configuration (`~/.config/opencode/opencode.jsonc`) for a `"model"` or `"provider"` definitions. If none are found, it falls back to the hardcoded `DEFAULT_MODEL` (`"openai/gpt-5.2-codex"`).
3. Since `/Users/barandincoguz/.config/opencode/opencode.jsonc` contains no `"model"` or `"provider"` definitions, and there is no local or global `micode.jsonc` configuration file, all plugin agents default to `"openai/gpt-5.2-codex"`.
4. Because `"openai/gpt-5.2-codex"` is not configured or initialized in the user's OpenCode environment, calling these agents fails with `gpt-5.2 not init`.

</section>

---

<section name="findings">

## 2. Brainstorming Findings

We ran a brainstorming session with the user to explore the best remediation paths:

1. **Fallback Strategy Choice:**
   - **Option A (Selected):** Configure a global default model and provider in `opencode.jsonc`.
   - **Option B (Alternative):** Create a plugin-specific `micode.jsonc` configuration file.
   - **Option C (Alternative):** Modify the plugin's config loader to dynamically detect and auto-fallback to active models.

   *The user selected Option A because defining a global default model is the most robust solution. It ensures that any current or future plugin agents that don't explicitly override their model will automatically fall back to a valid, active model in the environment.*

2. **Default Model Choice:**
   - **Option 1 (Selected):** `google/gemini-3.5-flash` (the active model in this session, known to be initialized and fully functional).
   - **Option 2 (Alternative):** `anthropic/claude-3-5-sonnet`.
   - **Option 3 (Alternative):** A custom model.

   *The user selected `google/gemini-3.5-flash` as the global default model.*

</section>

---

<section name="recommendation">

## 3. Recommended Approach

We will configure `google/gemini-3.5-flash` as the global default model in `/Users/barandincoguz/.config/opencode/opencode.jsonc`.

### Steps to Implement

1. **Read and Parse:** Read the current global config `/Users/barandincoguz/.config/opencode/opencode.jsonc`.
2. **Modify Config:** Add `"model": "google/gemini-3.5-flash"` to the root level of the JSON object.
3. **Save Config:** Write the updated config back to `/Users/barandincoguz/.config/opencode/opencode.jsonc`.
4. **Restart Notice:** Instruct the user to restart OpenCode for the changes to take effect.

</section>
