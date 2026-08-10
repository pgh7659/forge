# Hermes, Discord, and Codex Reference Deployment

## Purpose

This directory preserves the first concrete Forge deployment as public
conformance evidence. It records one selected stack without making its
components, host layout, or operational rules requirements of Forge core.

## Selected Components

The reference selection includes an OCI host, Hermes and Discord for the
personal-assistant gateway, Codex CLI for engineering execution, Tailscale for
private dashboard access, systemd host services, GitHub handoff, and the
deployment's selected secret integration.

## Evidence Level

These documents record design decisions, templates, and proposed operating
procedures. They are not evidence that any live host is reconciled, secure, or
currently conforms. Version-dependent commands require verification against the
installed implementation before use.

## Operations

[Operations runbooks](operations/) describe the selected deployment's audit,
migration, routing, handoff, and incident procedures. They remain
approval-gated and do not authorize infrastructure mutation by themselves.

## Decisions

[Historical decisions](decisions/) retain their original rationale and each
applies only to this named reference deployment.

## Contracts

[Example task and result envelopes](contracts/) show the first deployment's
Codex handoff shapes. Portable contract ownership remains in Forge core.

## Not Core Requirements

OCI, Hermes, Discord, Tailscale, Codex, systemd, GitHub, and any selected
secret provider are replaceable deployment choices. Other implementations may
conform to Forge contracts with different adapters and operational controls.
