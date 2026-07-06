"""Workflow configuration for metrics and analysis."""

from __future__ import annotations

from pydantic import BaseModel, Field


class WorkflowConfig(BaseModel):
    """
    Defines how statuses are classified for TL engineering metrics.

    Terminal statuses represent workflow completion.
    Reopen is detected only on terminal → non-terminal transitions.
  Cycle time starts at first In Progress entry.
    """

    terminal_statuses: list[str] = Field(
        default_factory=lambda: ["Post Deployment", "Done"],
    )
    cancelled_statuses: list[str] = Field(default_factory=lambda: ["Cancelled"])
    queue_statuses: list[str] = Field(
        default_factory=lambda: ["Backlog", "To Do", "Ready for QA", "Ready for Deployment"],
    )
    active_statuses: list[str] = Field(default_factory=lambda: ["In Progress"])
    review_statuses: list[str] = Field(default_factory=lambda: ["Review"])
    qa_statuses: list[str] = Field(default_factory=lambda: ["QA IN PROGRESS"])
    deployment_queue_statuses: list[str] = Field(
        default_factory=lambda: ["Ready for Deployment"],
    )
    waiting_statuses: list[str] = Field(
        default_factory=lambda: ["Waiting", "Blocked"],
    )
    bug_issue_types: list[str] = Field(default_factory=lambda: ["Bug", "HOT-FIX"])

    def _normalized_set(self, names: list[str]) -> set[str]:
        return {name.strip().lower() for name in names if name.strip()}

    @property
    def terminal(self) -> set[str]:
        return self._normalized_set(self.terminal_statuses)

    @property
    def cancelled(self) -> set[str]:
        return self._normalized_set(self.cancelled_statuses)

    @property
    def buffer(self) -> set[str]:
        return self._normalized_set(self.queue_statuses)

    @property
    def active(self) -> set[str]:
        return self._normalized_set(
            self.active_statuses + self.review_statuses + self.qa_statuses
        )

    @property
    def waiting(self) -> set[str]:
        return self._normalized_set(self.waiting_statuses)

    @property
    def review(self) -> set[str]:
        return self._normalized_set(self.review_statuses)

    @property
    def qa(self) -> set[str]:
        return self._normalized_set(self.qa_statuses)

    @property
    def active_only(self) -> set[str]:
        return self._normalized_set(self.active_statuses)

    @property
    def bugs(self) -> set[str]:
        return self._normalized_set(self.bug_issue_types)

    def is_terminal(self, status_name: str | None) -> bool:
        if not status_name:
            return False
        normalized = status_name.strip().lower()
        return normalized in self.terminal or normalized in self.cancelled

    def is_cancelled(self, status_name: str | None) -> bool:
        if not status_name:
            return False
        return status_name.strip().lower() in self.cancelled

    def is_buffer(self, status_name: str | None) -> bool:
        if not status_name:
            return False
        return status_name.strip().lower() in self.buffer

    def is_work_active(self, status_name: str | None, status_category: str | None = None) -> bool:
        """True for In Progress, Review, and QA IN PROGRESS."""
        return self.is_active(status_name, status_category)

    def is_active(self, status_name: str | None, status_category: str | None = None) -> bool:
        if not status_name:
            return False
        normalized = status_name.strip().lower()
        if normalized in self.active:
            return True
        if not self.active_statuses and not self.review_statuses and not self.qa_statuses:
            return status_category == "indeterminate"
        return False

    def is_cycle_start(self, status_name: str | None) -> bool:
        """Cycle time starts at first In Progress entry."""
        if not status_name:
            return False
        return status_name.strip().lower() in self.active_only

    def is_review(self, status_name: str | None) -> bool:
        if not status_name:
            return False
        return status_name.strip().lower() in self.review

    def is_qa(self, status_name: str | None) -> bool:
        if not status_name:
            return False
        return status_name.strip().lower() in self.qa

    def is_active_only(self, status_name: str | None) -> bool:
        if not status_name:
            return False
        return status_name.strip().lower() in self.active_only

    def is_bug_type(self, issue_type: str | None) -> bool:
        if not issue_type:
            return False
        return issue_type.strip().lower() in self.bugs

    def status_category_label(self, status_name: str | None) -> str:
        """Category for metric inspector highlighting."""
        if not status_name:
            return "other"
        if self.is_terminal(status_name):
            return "terminal"
        if self.is_work_active(status_name):
            return "active"
        if self.is_buffer(status_name):
            return "buffer"
        return "other"

    def queue_category(self, status_name: str | None) -> str:
        """Classify a status into queue analysis buckets."""
        if not status_name:
            return "other"
        if self.is_terminal(status_name):
            return "done"
        if self.is_review(status_name):
            return "review"
        if self.is_qa(status_name):
            return "qa"
        if self.is_active_only(status_name):
            return "active"
        if self.is_buffer(status_name):
            return "queue"
        if status_name.strip().lower() in self.waiting:
            return "waiting"
        return "other"

    def workflow_type(self, status_name: str | None) -> str:
        return self.queue_category(status_name)

    def is_waiting(self, status_name: str | None, status_category: str | None = None) -> bool:
        if not status_name:
            return False
        normalized = status_name.strip().lower()
        if normalized in self.waiting:
            return True
        if self.is_terminal(status_name) or self.is_active(status_name, status_category):
            return False
        return status_category == "new" or status_category == "undefined"
