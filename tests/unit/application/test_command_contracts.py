from __future__ import annotations

from dataclasses import dataclass

from backend.application.commands import CommandContext, CommandPreview, UndoPlan


@dataclass(frozen=True, slots=True)
class FakeCompensation:
    action_type: str = "fake_compensation"

    def describe(self) -> dict:
        return {"action_type": self.action_type, "target": "external-resource"}

    def apply(self, _context: CommandContext) -> dict:
        return {"restored": True}


def test_command_preview_is_structural_and_non_mutating() -> None:
    preview = CommandPreview(
        command_type="FakeCommand",
        summary="Preview fake command",
        preview={"would_change": ["external-resource"]},
    )

    assert preview.command_type == "FakeCommand"
    assert preview.preview == {"would_change": ["external-resource"]}


def test_undo_plan_uses_command_supplied_compensation() -> None:
    compensation = FakeCompensation()
    undo_plan = UndoPlan(
        command_type="UndoFakeCommand",
        summary="Undo fake command",
        action=compensation,
        payload=compensation.describe(),
    )

    assert undo_plan.payload["action_type"] == "fake_compensation"
    assert undo_plan.payload["target"] == "external-resource"
