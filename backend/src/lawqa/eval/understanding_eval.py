from collections import Counter, defaultdict

from pydantic import BaseModel

from lawqa.eval.dataset import EvalItem


class IntentReport(BaseModel):
    accuracy: float
    confusion: dict[str, dict[str, int]]
    mistakes: list[tuple[str, str, str, str]]  # id, question, expected, predicted


def intent_accuracy(items: list[EvalItem], predicted: dict[str, str]) -> IntentReport:
    confusion: dict[str, Counter[str]] = defaultdict(Counter)
    mistakes = []
    for item in items:
        guess = predicted[item.id]
        confusion[item.intent][guess] += 1
        if guess != item.intent:
            mistakes.append((item.id, item.question, item.intent, guess))
    correct = sum(1 for item in items if predicted[item.id] == item.intent)
    return IntentReport(
        accuracy=correct / len(items) if items else 0.0,
        confusion={expected: dict(row) for expected, row in sorted(confusion.items())},
        mistakes=mistakes,
    )
