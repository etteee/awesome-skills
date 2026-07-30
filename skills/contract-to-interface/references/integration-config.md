# Integration configuration

Edit `integration-config.json` once for the local MCP, generator, and build environment.

## Replacement rules

- Replace every static token written as `<UPPERCASE_PLACEHOLDER>`.
- Keep runtime variables written as `{{runtime_variable}}`; the skill resolves them for each request.
- Add or remove entries in `mcp.arguments_template` to match the real MCP schema.
- Use repository-relative paths when practical. Absolute paths are allowed only when they are intentionally machine-specific.
- Quote runtime path variables inside command templates because paths may contain spaces.
- Do not store access tokens, passwords, or other secrets in this file.

Run the checker after editing:

```bash
python3 <skill-directory>/scripts/check_integration_config.py \
  <skill-directory>/references/integration-config.json
```

## Static placeholders

| Placeholder | Purpose | Example shape |
|---|---|---|
| `<MCP_TOOL_NAME>` | Exact callable MCP tool that returns the authoritative contract. | `contract_registry_get_interface` |
| `<MCP_ARGUMENT_NAME>` | One real argument name accepted by the MCP tool. Replace the example object with all required arguments. | `serviceName` |
| `<MCP_RESPONSE_MODE>` | How contract data is returned: `inline`, `url`, or `path`. | `inline` |
| `<MCP_RESPONSE_CONTRACT_SELECTOR>` | Field or selector locating the content, URL, or path in the MCP response. Use `$` when the whole response is the contract. | `result.contract` |
| `<CONTRACT_FORMAT>` | Contract syntax used for validation and the generated file extension. | `openapi-yaml` |
| `<CONTRACT_LOCAL_PATH_TEMPLATE>` | Destination for the fetched contract, relative to `{{repo_root}}` unless absolute. | `contracts/{{service_id}}/{{interface_id}}.yaml` |
| `<CODEGEN_WORKING_DIRECTORY_TEMPLATE>` | Directory from which the generator CLI must run. | `{{service_dir}}` |
| `<CODEGEN_COMMAND_TEMPLATE>` | Complete CLI invocation. It should consume `{{contract_file}}` and write to `{{output_directory}}`. | `generator create --contract "{{contract_file}}" --output "{{output_directory}}"` |
| `<GENERATED_CODE_DIRECTORY_TEMPLATE>` | Directory owned by the generator. | `{{service_dir}}/src/generated` |
| `<BUILD_WORKING_DIRECTORY_TEMPLATE>` | Directory from which compilation must run. | `{{service_dir}}` |
| `<BUILD_COMMAND_TEMPLATE>` | Exact compilation command, including required module or profile arguments. | `mvn -pl {{service_id}} -DskipTests compile` |

## Runtime variables

| Variable | Meaning |
|---|---|
| `{{repo_root}}` | Absolute repository root discovered from the current checkout. |
| `{{service_dir}}` | Absolute directory of the service that owns the interface. |
| `{{service_id}}` | Service identifier expected by the MCP or build tool. |
| `{{interface_id}}` | External interface or operation identifier from the request. |
| `{{contract_version}}` | Requested or discovered contract version. |
| `{{contract_file}}` | Absolute path of the locally persisted contract. |
| `{{output_directory}}` | Absolute generated-code directory. |

An MCP argument can use any runtime variable. For example:

```json
"arguments_template": {
  "serviceName": "{{service_id}}",
  "operationId": "{{interface_id}}",
  "version": "{{contract_version}}"
}
```

The checker rejects unknown runtime variables so spelling errors fail before any external tool is called.
