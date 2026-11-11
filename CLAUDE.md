# bennett-arith

## What this repo is

adders, multipliers, QROM and soft-float as ISA library objects with certificates. The v1 Bennett.jl generators are the reference implementations to port.

Part of the Bennett reboot: many small repositories, two published contracts
(`bennett-dialect-spec`, `bennett-isa-spec`). Depends on: bennett-dialect-spec; bennett-driver as a build tool.

## Where the spec is

The published specs, at the versions in `SPEC_VERSIONS.toml`. Source documents
currently live in the Bennett.jl repo (`Bennett-NorthStar.md`,
`Bennett-ISA-Spec.md`) until the spec repos are split out. The spec wins over
any code, including code in this repo.

## Rules

The one rulebook is bennett/docs/process/COMMON.md; it binds here. Gate: `scripts/pre-push`. Tasks: `bd` (`bd prime` lists its commands).
