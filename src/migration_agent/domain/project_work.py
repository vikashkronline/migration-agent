"""Git-owned project work declarations; workflow evidence remains operational truth."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Text = Annotated[str, Field(min_length=1, max_length=1024)]
Identifier = Annotated[str, Field(pattern=r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")]
ROOTS = frozenset({"project", "foundation", "work", "knowledge"})


class ProjectWorkModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class WorkflowEvidenceRef(ProjectWorkModel):
    workflow_id: str = Field(min_length=1, max_length=128)
    task_id: str = Field(min_length=1, max_length=128)


class ProjectWorkItem(ProjectWorkModel):
    item_id: Identifier
    parent_id: Identifier | None = None
    section: Literal["foundation", "work", "knowledge"] = "work"
    kind: Literal["group", "task"]
    title: str = Field(min_length=1, max_length=200)
    summary: str = Field(default="", max_length=4096)
    owner: str = Field(default="", max_length=128)
    acceptance: tuple[Text, ...] = Field(default=(), max_length=20)
    dependencies: tuple[Identifier, ...] = Field(default=(), max_length=20)
    declared_status: Literal["UNKNOWN", "PLANNED", "IN_PROGRESS", "COMPLETE"] = "UNKNOWN"
    workflow: WorkflowEvidenceRef | None = None
    order: int = Field(default=0, ge=0, le=1_000_000)

    @model_validator(mode="after")
    def task_evidence_only(self) -> "ProjectWorkItem":
        if self.workflow is not None and self.kind != "task":
            raise ValueError("PROJECT_WORK_INVALID: only tasks can bind workflow evidence.")
        return self


class ProjectWorkDefinition(ProjectWorkModel):
    schema_version: Literal[1] = 1
    project_name: str = Field(default="", max_length=200)
    objective: str = Field(default="", max_length=8192)
    items: tuple[ProjectWorkItem, ...] = Field(default=(), max_length=1000)

    @model_validator(mode="after")
    def valid_graphs(self) -> "ProjectWorkDefinition":
        indexed = {item.item_id: item for item in self.items}
        if len(indexed) != len(self.items) or indexed.keys() & ROOTS:
            raise ValueError("PROJECT_WORK_INVALID: duplicate or reserved identity.")
        bindings = [(i.workflow.workflow_id, i.workflow.task_id) for i in self.items if i.workflow]
        if len(bindings) != len(set(bindings)):
            raise ValueError("PROJECT_WORK_INVALID: one owner per linked workflow task.")
        for item in self.items:
            parent = item.parent_id
            if parent is not None and (parent not in indexed or indexed[parent].kind != "group"):
                raise ValueError("PROJECT_WORK_INVALID: parent must be a declared group.")
            if any(dependency not in indexed for dependency in item.dependencies):
                raise ValueError("PROJECT_WORK_INVALID: missing dependency identity.")
            seen = {item.item_id}
            while parent:
                if parent in seen or len(seen) > 32:
                    raise ValueError("PROJECT_WORK_INVALID: cyclic or excessively deep ownership.")
                seen.add(parent)
                parent = indexed[parent].parent_id
        done: set[str] = set()

        def check_dependencies(ident: str, visiting: set[str]) -> None:
            if ident in visiting or len(visiting) > 32:
                raise ValueError("PROJECT_WORK_INVALID: cyclic or excessively deep dependencies.")
            if ident in done:
                return
            for dependency in indexed[ident].dependencies:
                check_dependencies(dependency, visiting | {ident})
            done.add(ident)

        for ident in indexed:
            check_dependencies(ident, set())
        return self
