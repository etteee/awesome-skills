# Commit enforcement

Use one repository-owned checker from local hooks, CI, IDE tasks, and Agents. A hook is an early feedback adapter; CI is the authoritative enforcement adapter.

## Install in a service repository

Vendor these files into a stable, tracked directory in the service repository:

```text
tools/contract-interface-check/
├── check_servicecomb_contract_code.py
└── servicecomb-contract-policy.json
```

Do not point a team hook at a developer's personal Codex skill directory. Every developer and Agent must execute the same reviewed checker revision from the repository.

Adjust only these policy fields when necessary:

- `generated_path_globs`: build-time generated-source directories that must never be committed;
- `allowed_path_globs`: reviewed path-level exceptions, preferably temporary;
- `allowed_type_globs`: reviewed fully qualified type exceptions;
- `reserved_contract_type_globs`: generated interface/model package globs; tracked types in these packages are always rejected;
- annotation/type arrays: framework-version FQCNs, not simple-name aliases;
- `service_url_schemes`: current and legacy ServiceComb logical URL schemes.

## Git pre-commit adapter

Track `.githooks/pre-commit`:

```sh
#!/bin/sh
repo_root=$(git rev-parse --show-toplevel) || exit 2
exec python3 "$repo_root/tools/contract-interface-check/check_servicecomb_contract_code.py" \
  --repo-root "$repo_root" \
  --config "$repo_root/tools/contract-interface-check/servicecomb-contract-policy.json" \
  --staged
```

Enable the tracked hook directory once per checkout:

```bash
git config core.hooksPath .githooks
```

The checker reads candidate content from the Git index, so partial staging is handled correctly. Exit status `0` passes, `1` means policy violations, and `2` means the check could not run reliably.

## CI adapter

Run the same checker against the proposed revision:

```bash
python3 tools/contract-interface-check/check_servicecomb_contract_code.py \
  --repo-root . \
  --config tools/contract-interface-check/servicecomb-contract-policy.json \
  --base "$BASE_SHA" \
  --head "$HEAD_SHA"
```

Make this job a required merge check. Local hooks can be absent or bypassed with `--no-verify`; CI must not rely on local Git configuration.

## Rules

| Rule | Blocked condition |
|---|---|
| `SCB000` | Generated Java source is staged or committed. |
| `SCB001` | A tracked Java type occupies a package reserved for generated interfaces or DTOs. |
| `SCB101` | `@RestSchema` or `@RpcSchema` publishes handwritten implementation methods without `schemaInterface`. |
| `SCB102` | `schemaInterface` resolves to a tracked handwritten Java interface. |
| `SCB110` | A confirmed ServiceComb contract root contains handwritten JAX-RS or Spring MVC mappings. |
| `SCB111` | A confirmed ServiceComb contract root contains handwritten Swagger/OpenAPI metadata. |
| `SCB120` | A provider or RPC consumer contract interface is tracked handwritten source. |
| `SCB130` | A tracked consumer directly calls a `servicecomb://` or legacy `cse://` RestOperations endpoint. |
| `SCB131` | `@RpcReference` or `Invoker.createProxy` resolves to a tracked handwritten interface. |
| `SCB200` | A tracked handwritten type belongs to the transitive contract DTO closure. |

## DTO closure

The checker starts from:

- parameters and return types of confirmed provider contract methods;
- parameters and return types of RPC consumer interfaces;
- request construction and response class literals in ServiceComb RestOperations consumers;
- explicit response/implementation class literals in Swagger/OpenAPI annotations.

It then recursively follows concrete generic arguments, arrays, DTO fields, record components, JavaBean getter/setter types, and DTO superclasses. This detects a DTO-only staged change even when the interface file itself is unchanged.

Also configure `reserved_contract_type_globs` for the packages owned by the custom Swagger Codegen templates, for example `com.example.orders.contract.*` and `com.example.orders.contract.model.*`. This second gate detects a handwritten DTO even when its generated interface exists only during compilation and is therefore absent from Git.

The bundled checker intentionally has no parser dependency. It resolves packages, explicit/wildcard imports, balanced declarations, method signatures, fields, records, and local type references. It does not guess ambiguous symbols. For repositories with heavy annotation composition, generated meta-models, inherited provider annotations, or complex Lombok-only properties, replace its parsing implementation with a JavaParser/compiler-based adapter while preserving the CLI, configuration, rule IDs, and hook/CI interface.
