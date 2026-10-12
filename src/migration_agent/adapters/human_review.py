"""Trusted local console review adapter; no automatic or piped approval channel."""

import getpass
import sys

from migration_agent.domain.apply_approval import HumanDecision, ReviewRequestPayload
from migration_agent.domain.execution import NativeExecutionConsent
from migration_agent.domain.planning import AssuranceLevel


class ConsoleHumanReview:
    def __init__(self, key_fingerprint: str | None = None) -> None:
        self.key_fingerprint = key_fingerprint

    def confirm(self, review: ReviewRequestPayload) -> HumanDecision:
        if not sys.stdin.isatty() or not sys.stdout.isatty():
            raise ValueError(
                "HUMAN_CONSOLE_REQUIRED: run approval yourself in an interactive terminal."
            )
        print(review.model_dump_json(indent=2))
        key = self.key_fingerprint or (
            review.signer_key_fingerprint
            if review.required_assurance == AssuranceLevel.MODE_A
            else None
        )
        if review.required_assurance == AssuranceLevel.MODE_A and not key:
            raise ValueError(
                "SIGNING_KEY_REQUIRED: enroll your public key for independent review/apply handoff."
            )
        phrase = f"APPROVE {review.changeset_digest[-12:]}"
        answer = input(f"Review the exact diff above. Type '{phrase}' to authorize apply: ")
        assurance = AssuranceLevel.MODE_A if key else AssuranceLevel.MODE_B
        return HumanDecision(
            confirmed=answer == phrase,
            actor=getpass.getuser(),
            assurance=assurance,
            key_fingerprint=key,
        )

    def confirm_native(
        self, consent: NativeExecutionConsent, diff: str, templates: tuple[str, ...]
    ) -> HumanDecision:
        if not sys.stdin.isatty() or not sys.stdout.isatty():
            raise ValueError(
                "HUMAN_CONSOLE_REQUIRED: authorize native execution yourself in "
                "an interactive terminal."
            )
        print(
            "Native code executes with your local account's filesystem and "
            "network permissions. Job Objects supervise processes; they are "
            "not a security sandbox."
        )
        print(consent.model_dump_json(indent=2))
        key = self.key_fingerprint or (
            consent.key_fingerprint if consent.assurance_level == AssuranceLevel.MODE_A else None
        )
        if consent.assurance_level == AssuranceLevel.MODE_A and not key:
            raise ValueError(
                "SIGNING_KEY_REQUIRED: enroll your public key for team execution consent."
            )
        print("Fixed templates: " + "; ".join(templates))
        print(
            "The repair budget covers only in-scope changes; scripts, "
            "dependency/configuration and toolchain changes require renewed "
            "consent."
        )
        print(diff)
        phrase = f"EXECUTE {consent.signing_digest[-12:]}"
        answer = input(
            f"Review this scope and trust the code above. Type '{phrase}' "
            "to authorize native execution: "
        )
        return HumanDecision(
            confirmed=answer == phrase,
            actor=getpass.getuser(),
            assurance=AssuranceLevel.MODE_A if key else AssuranceLevel.MODE_B,
            key_fingerprint=key,
        )
