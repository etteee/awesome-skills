---
name: contract-to-interface
description: Convert an externally defined service contract into generated interface and DTO code, verify that the owning service compiles, and enforce that Apache ServiceComb contract code is not handwritten or committed. Use during implementation when adding or changing a service's externally exposed HTTP/API interface requires fetching its authoritative contract through MCP, invoking a custom Swagger Codegen CLI, compiling generated sources, or configuring commit-time checks for ServiceComb providers, consumers, and DTOs.
---

# Contract to Interface

Turn an authoritative interface contract into compilable service code through one traceable workflow: acquire, persist, generate, and compile.

## Integration configuration

Choose the execution path first:

- For contract acquisition, code generation, or compilation, follow the generation workflow and validate the integration configuration below.
- For commit-policy installation or source checking only, skip the integration configuration and go directly to [Commit enforcement](#commit-enforcement).

For the generation path, read [references/integration-config.md](references/integration-config.md), then load `references/integration-config.json`.

Before doing any work, validate the configuration:

```bash
python3 <skill-directory>/scripts/check_integration_config.py \
  <skill-directory>/references/integration-config.json
```

Stop the generation path if the checker reports unresolved `<PLACEHOLDER>` values. Report each unresolved value and its purpose. Do not invent MCP names, CLI commands, directories, or build commands. Unresolved generation placeholders do not block an independent commit-policy check.

Treat `{{runtime_variable}}` values as per-request inputs. Resolve them from the user's request and the repository. Ask only for values that cannot be safely discovered.

## Workflow

### 1. Establish scope

Identify:

- the repository root and owning service directory;
- the service, interface, and requested contract version;
- whether the request adds, changes, or regenerates an interface;
- the files already modified before this workflow starts.

Read applicable `AGENTS.md` or `CLAUDE.md` instructions and inspect the service build files. Preserve unrelated and pre-existing changes. Do not widen the task to other services.

Resolve the configured path and command templates. Normalize local paths before execution. Confirm that the contract file and generated-code directory belong to the intended repository and service.

### 2. Acquire the authoritative contract

Resolve the configured MCP tool. If it is not currently callable, search the available tools for the exact configured name. Do not replace the configured MCP source with web search, a guessed schema, or a manually written contract.

Render `mcp.arguments_template` with the runtime values and invoke the tool. Never print credentials or secret-valued arguments.

Extract the contract according to `mcp.response_mode` and `mcp.contract_selector`:

- `inline`: select contract content from the response;
- `url`: select a contract URL and download its content;
- `path`: select a returned local path and read its content.

Verify that the response identifies the requested service and interface when that metadata is available. Reject empty, malformed, or ambiguous results.

### 3. Persist and validate the contract

Write the exact contract content to the resolved `contract.local_path_template`. Create only the required parent directory. Do not rewrite formatting or semantics unless the generator requires a documented normalization.

Validate the contract according to `contract.format`:

- parse JSON or YAML contracts;
- run the appropriate syntax checker for IDL or schema formats when available;
- ensure the selected operation/interface exists;
- ensure the local file is non-empty.

Record the MCP source, requested identifiers, contract path, and any version metadata returned by the source.

### 4. Generate interface code

Render `generation.command_template` with shell-quoted runtime values, including the absolute contract path and generated-code directory. Run it from the resolved `generation.working_directory_template`.

Before execution:

- inspect the target directory and current Git status;
- show the exact rendered command with secrets redacted;
- stop if it can write outside the intended service or overwrite unrelated files;
- use the generator's dry-run or preview option when the configured command provides one.

Run the existing CLI and require a zero exit status. Verify that it produced or updated files in the configured generated-code directory. Inspect the diff for unexpected deletions, unrelated changes, unresolved template markers, or generated files outside the target.

Do not hand-edit generated files to hide a generator or contract problem. Fix the contract selection, generator configuration, or non-generated integration seam and regenerate.

### 5. Compile the service

Render `build.command_template` and run it from `build.working_directory_template`. Require a zero exit status.

If compilation fails:

1. classify the failure as contract, generation, service-integration, dependency, or environment related;
2. preserve the original compiler output;
3. fix only in-scope, durable sources of the failure;
4. regenerate when generated output is affected;
5. rerun the same build command until it passes or a genuine external blocker is established.

Compilation is the completion gate. Do not report success merely because the MCP call or code generator succeeded.

### 6. Report the result

Return a concise handoff containing:

- MCP contract source and requested interface identifiers;
- local contract path;
- generator working directory, command, and output directory;
- generated and integration files changed;
- build working directory, command, and final result;
- warnings, assumptions, or remaining blockers.

## Commit enforcement

Keep generated interface and DTO sources out of Git. Use `scripts/check_servicecomb_contract_code.py` as a repository-owned policy engine behind both a pre-commit hook and a required CI check.

Read [references/servicecomb-interface-patterns.md](references/servicecomb-interface-patterns.md) before changing detection rules. Read [references/commit-enforcement.md](references/commit-enforcement.md) when installing or configuring the checker in a service repository.

Before commit, run the checker against the Git index:

```bash
python3 <checker-path>/check_servicecomb_contract_code.py \
  --repo-root <repo-root> \
  --config <checker-path>/servicecomb-contract-policy.json \
  --staged
```

Require CI to call the same script with `--base <base-revision> --head <head-revision>`. Do not duplicate rule logic in hook wrappers, CI YAML, Agent instructions, or this skill.

The checker must treat contract DTOs as a transitive type closure rooted in published provider methods, RPC consumer interfaces, RestOperations request/response types, and explicit Swagger/OpenAPI response types. Do not classify DTOs by filename, suffix, or package name alone.

## Invariants

- Treat the MCP contract as authoritative.
- Keep contract acquisition, code generation, and compilation as distinct observable stages.
- Preserve user changes and never clear an output directory destructively.
- Never commit credentials or embed MCP secrets in the configuration.
- Reuse the same inputs when retrying so failures remain reproducible.
- Stop at the failing stage when required configuration or external systems are unavailable; retain successful earlier artifacts.

## Resources

- `references/integration-config.md`: placeholder meanings and replacement rules.
- `references/integration-config.json`: environment-specific integration template.
- `references/servicecomb-interface-patterns.md`: official-source recognition rules for providers, consumers, and DTOs.
- `references/servicecomb-contract-policy.json`: configurable ServiceComb annotation and path policy.
- `references/commit-enforcement.md`: hook and CI integration instructions.
- `scripts/check_integration_config.py`: validates structure and detects unresolved placeholders.
- `scripts/check_servicecomb_contract_code.py`: scans staged, changed, selected, or all Java sources.
- `scripts/test_check_servicecomb_contract_code.py`: dependency-free regression tests for the checker.
