"""Completion candidates and a menu that never submits input."""

from __future__ import annotations

from dataclasses import dataclass, field
import re


KEYWORDS = tuple("""
ALTER AND AS ASC BY CALL CASE COMMIT CREATE DELETE DESC DISTINCT DROP ELSE END
EXISTS FROM GROUP HAVING IN INSERT INTO IS JOIN LEFT LIMIT NOT NULL ON OR ORDER
RIGHT ROLLBACK SELECT SET TABLE THEN UNION UPDATE VALUES VIEW WHEN WHERE
""".split())


@dataclass(frozen=True)
class Candidate:
  text: str
  detail: str = "keyword"


@dataclass(frozen=True)
class Suggestions:
  start: int
  end: int
  candidates: tuple[Candidate, ...]
  message: str = ""


def suggest(text: str, cursor: int) -> Suggestions:
  match = re.search(r"[\w]+$", text[:cursor])
  start = match.start() if match else cursor
  prefix = text[start:cursor].casefold()
  candidates = tuple(Candidate(word) for word in KEYWORDS if word.casefold().startswith(prefix))
  return Suggestions(start, cursor, candidates)


@dataclass
class CompletionMenu:
  active: bool = False
  original_text: str = ""
  original_cursor: int = 0
  suggestions: Suggestions = field(default_factory=lambda: Suggestions(0, 0, ()))
  selected: int = 0

  def open(self, text: str, cursor: int, suggestions: Suggestions) -> None:
    self.active = True
    self.original_text = text
    self.original_cursor = cursor
    self.suggestions = suggestions
    self.selected = 0

  def move(self, direction: int) -> None:
    if self.suggestions.candidates:
      self.selected = (self.selected + direction) % len(self.suggestions.candidates)

  def accept(self) -> tuple[str, int]:
    candidate = self.suggestions.candidates[self.selected]
    start, end = self.suggestions.start, self.suggestions.end
    self.active = False
    return (
      self.original_text[:start] + candidate.text + self.original_text[end:],
      start + len(candidate.text),
    )
