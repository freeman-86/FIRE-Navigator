import unittest

from core.domain.event import ConditionalEvent
from core.domain.milestone import Milestone, MilestoneType
from core.domain.value_objects import EventCondition


class ConditionalEventProtocolTest(unittest.TestCase):
    def test_milestone_structurally_conforms_to_conditional_event(self) -> None:
        milestone = Milestone(
            milestone_id="milestone_retire_001",
            milestone_type=MilestoneType.RETIREMENT,
            trigger=EventCondition.at_age(60),
        )

        # Milestoneのフィールドは一切変更せず、triggerを持つことでConditionalEventとして構造的に扱える。
        self.assertIsInstance(milestone, ConditionalEvent)

    def test_object_without_trigger_does_not_conform(self) -> None:
        class NotAnEvent:
            pass

        self.assertNotIsInstance(NotAnEvent(), ConditionalEvent)


if __name__ == "__main__":
    unittest.main()
