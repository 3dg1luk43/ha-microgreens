# Microgreens - Home Assistant integration for planning and tracking microgreen trays.
# Copyright (C) 2026 Lukas Bandura
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Today's tasks as a to-do list. Checking an item off does the task.

Items cannot be added, edited or deleted here: the list is derived from the
grow schedule (schedule.tasks), the same list the panel and the notifications
show. A completed task simply leaves the list.
"""
from __future__ import annotations

from homeassistant.components.todo import (
    TodoItem,
    TodoItemStatus,
    TodoListEntity,
    TodoListEntityFeature,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import MicrogreensConfigEntry
from .const import DOMAIN
from .entity import MicrogreensEntity
from .manager import MicrogreensManager
from .models import MicrogreensError


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MicrogreensConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([TasksTodoList(entry.runtime_data)])


class TasksTodoList(MicrogreensEntity, TodoListEntity):
    _attr_supported_features = TodoListEntityFeature.UPDATE_TODO_ITEM

    def __init__(self, manager: MicrogreensManager) -> None:
        super().__init__(manager, "tasks")

    @property
    def todo_items(self) -> list[TodoItem]:
        return [
            TodoItem(
                uid=task.id,
                summary=self.manager.task_summary(task),
                status=TodoItemStatus.NEEDS_ACTION,
                due=task.due_on,
            )
            for task in self.manager.tasks()
        ]

    async def async_update_todo_item(self, item: TodoItem) -> None:
        if item.status != TodoItemStatus.COMPLETED or not item.uid:
            return
        try:
            self.manager.complete_task(item.uid)
        except MicrogreensError as err:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key=err.key,
                translation_placeholders=err.placeholders,
            ) from err
