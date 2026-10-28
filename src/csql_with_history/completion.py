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
  allowed: bool = True


@dataclass(frozen=True)
class Relation:
  owner: str
  name: str
  kind: str
  columns: tuple[str, ...] = ()


@dataclass(frozen=True)
class Schema:
  user: str = ""
  relations: tuple[Relation, ...] = ()


@dataclass(frozen=True)
class Token:
  text: str
  start: int
  end: int
  kind: str
  depth: int
  closed: bool = True

  @property
  def name(self) -> str:
    return unquote(self.text, self.closed)

  @property
  def keyword(self) -> str:
    return self.text.upper() if self.kind == "word" else ""


def unquote(value: str, closed: bool = True) -> str:
  if value and value[0] in '["`':
    closer = ']' if value[0] == '[' else value[0]
    return value[1:-1 if closed else None].replace(closer * 2, closer)
  return value


def identifier(value: str, quote: str = "") -> str:
  if not quote and re.fullmatch(r"[^\W\d]\w*", value, re.UNICODE) and value.upper() not in KEYWORDS:
    return value
  quote = quote or '['
  closer = ']' if quote == '[' else quote
  return quote + value.replace(closer, closer * 2) + closer


def tokenize(text: str) -> list[Token]:
  """Keep source spans and tolerate incomplete comments, strings, and names."""
  tokens = []
  index, depth = 0, 0
  while index < len(text):
    start = index
    character = text[index]
    if character.isspace():
      index += 1
      continue
    kind, closed = "symbol", True
    if text.startswith('--', index):
      end = text.find('\n', index)
      index = len(text) if end < 0 else end
      kind, closed = "comment", end >= 0
    elif text.startswith('/*', index):
      end = text.find('*/', index + 2)
      index = len(text) if end < 0 else end + 2
      kind, closed = "comment", end >= 0
    elif character in "'\"`[":
      closer = ']' if character == '[' else character
      kind = "string" if character == "'" else "identifier"
      index += 1
      closed = False
      while index < len(text):
        if text[index] == closer:
          index += 1
          if index < len(text) and text[index] == closer:
            index += 1
            continue
          closed = True
          break
        index += 1
    elif character.isalnum() or character in '_$':
      index += 1
      while index < len(text) and (text[index].isalnum() or text[index] in '_$'):
        index += 1
      kind = "word"
    else:
      index += 1
    if character == ')' and kind == "symbol":
      depth = max(0, depth - 1)
    tokens.append(Token(text[start:index], start, index, kind, depth, closed))
    if character == '(' and kind == "symbol":
      depth += 1
  return tokens


def statement_scope(tokens: list[Token], cursor: int) -> list[Token]:
  """Use the current statement and innermost parenthesized scope only."""
  stack = []
  start, depth = 0, 0
  for token in tokens:
    if token.start >= cursor:
      break
    if token.text == '(' and token.kind == "symbol":
      stack.append(token.end)
      depth += 1
    elif token.text == ')' and token.kind == "symbol" and stack:
      stack.pop()
      depth -= 1
    elif token.text == ';' and not stack:
      start = token.end
  if stack:
    start = stack[-1]
  end = len(tokens) and tokens[-1].end or cursor
  for token in tokens:
    if token.start >= cursor and token.kind == "symbol":
      if token.text == ')' and token.depth < depth or token.text == ';' and token.depth == depth:
        end = token.start
        break
  return [t for t in tokens if start <= t.start < end and t.depth == depth and t.kind != "comment"]


def table_position(tokens: list[Token]) -> bool:
  if not tokens:
    return False
  if tokens[-1].keyword in ("FROM", "JOIN", "UPDATE", "INTO"):
    return True
  if tokens[-1].text == ',':
    clauses = [t.keyword for t in tokens if t.keyword in ("SELECT", "FROM", "WHERE", "ON", "SET", "ORDER", "GROUP")]
    return bool(clauses and clauses[-1] == "FROM")
  return False


def referenced_relations(tokens: list[Token], schema: Schema) -> list[tuple[str, Relation]]:
  found = []
  for index, token in enumerate(tokens):
    if not table_position(tokens[:index + 1]):
      continue
    index += 1
    if index >= len(tokens) or tokens[index].kind not in ("word", "identifier"):
      continue
    owner, name = "", tokens[index].name
    index += 1
    if index + 1 < len(tokens) and tokens[index].text == '.':
      owner, name = name, tokens[index + 1].name
      index += 2
    matches = [r for r in schema.relations if r.name.casefold() == name.casefold() and (
      r.owner.casefold() == owner.casefold() if owner else r.owner.casefold() in (schema.user.casefold(), 'public')
    )]
    if not owner:
      own = [r for r in matches if r.owner.casefold() == schema.user.casefold()]
      matches = own or matches
    if len(matches) != 1:
      continue
    alias = name
    if index < len(tokens) and tokens[index].keyword == "AS":
      index += 1
    if index < len(tokens) and tokens[index].kind in ("word", "identifier") and tokens[index].keyword not in KEYWORDS:
      alias = tokens[index].name
    found.append((alias, matches[0]))
  return found


def suggest(text: str, cursor: int, schema: Schema = Schema(), message: str = "") -> Suggestions:
  tokens = tokenize(text)
  current = next((t for t in tokens if t.start < cursor <= t.end and (
    t.kind in ("word", "identifier") or t.kind in ("comment", "string") and (
      cursor < t.end or not t.closed or t.text.startswith('--')
    )
  )), None)
  if current and current.kind in ("comment", "string") or text.lstrip().startswith(';'):
    return Suggestions(cursor, cursor, (), allowed=False)
  start, end = (current.start, current.end) if current else (cursor, cursor)
  quote = text[start:start + 1] if current and current.kind == "identifier" else ""
  partial = text[start:cursor]
  prefix = unquote(partial, bool(current and current.closed and cursor == current.end)).casefold()
  scoped = statement_scope(tokens, cursor)
  before = [t for t in scoped if t.end <= start]
  qualifier = ""
  if len(before) >= 2 and before[-1].text == '.':
    qualifier = before[-2].name
    before = before[:-2]
  candidates = []
  if table_position(before):
    for relation in schema.relations:
      if not relation.name.casefold().startswith(prefix) or qualifier and relation.owner.casefold() != qualifier.casefold():
        continue
      own = relation.owner.casefold() in (schema.user.casefold(), 'public')
      if relation.owner.casefold() == 'public' and schema.user.casefold() != 'public':
        own = not any(r.owner.casefold() == schema.user.casefold() and r.name.casefold() == relation.name.casefold()
                      for r in schema.relations)
      rendered = identifier(relation.name, quote)
      if not qualifier and not own:
        rendered = identifier(relation.owner) + '.' + rendered
      kind = "view" if relation.kind == "VCLASS" else "table"
      candidates.append(Candidate(rendered, kind + " " + relation.owner))
  else:
    references = referenced_relations(scoped, schema)
    for alias, relation in references:
      if qualifier and alias.casefold() != qualifier.casefold():
        continue
      for column in relation.columns:
        if column.casefold().startswith(prefix):
          rendered = identifier(column, quote)
          if not qualifier and len(references) > 1:
            rendered = identifier(alias) + '.' + rendered
          candidates.append(Candidate(rendered, "column " + alias))
    if not qualifier and not quote:
      candidates.extend(Candidate(word) for word in KEYWORDS if word.casefold().startswith(prefix))
  unique = {candidate.text: candidate for candidate in candidates}
  ordered = tuple(sorted(unique.values(), key=lambda c: (c.detail == 'keyword', c.text.casefold())))
  return Suggestions(start, end, ordered, message)


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
