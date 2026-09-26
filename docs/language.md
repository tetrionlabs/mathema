# Language domains

A claim over a function of text needs a domain the way a claim over a
function of numbers does. A language is that domain: the set of strings
a name stands for, or of structured values a schema stands for, written
`L[<name>]` where a numeric claim writes `R` or `[0, 1]`.

```
for text in L[unicode], f(f(text)) == f(text)
for text in L[unicode] \ {""}, len(f(text)) >= 1
for text in L[unicode] \ {∅}, len(f(text)) <= len(text)
```

## Three words

An **alphabet** is a set of characters (`ascii`, `latin-1`, `digit`). A
**language** is a set of strings, or more generally of values: `L[ascii]`
is every string over the ascii alphabet, the way a Kleene star reads, so
the empty string is a member and `\ {""}` removes it; `L[json]` is every
string `json.loads` accepts; a schema names the language of its
documents. **Text** is the carrier, Python's `str`, the way the reals are
the carrier of `R`. `L` is rendered in both output alphabets; `𝕃` is
accepted on input.

Union with a finite set of members, exclusion and the missing-value
policy read exactly as they do for a numeric domain, and a finite set of
strings is itself the simplest language, the one mathema always had:

```
for scale in {"info", "linear"}, f(r, scale) >= 0
```

## What mathema does with a language

The probe draws members of the language and never a value outside it:
the language's own hazards first (the empty string, whitespace, NUL and
the other control code points, an alphabet's boundary, a long member, a
lone surrogate, a byte-order mark), then random members. A function that
raises on a member falsifies the claim with that member as the witness,
the rule a numeric domain follows. The derive route has no reading of a
string, so it declines with the reason rather than proving real-only
facts about a symbol standing in for one; a finite language is the
exception, swept point by point and proven or falsified with the member.
`@enforce_domain()` reads a language binding and rejects a non-member at
call time.

Every record states what a name resolved to, in `meta["mathema.language"]`:
the name, its source (an in-process registration, a package's entry
point, a dotted object, an adaptor), its level (finite, alphabet,
regular, predicate, schema) and its persisted form. A claim over a
language is stamped `grammar: mathema/language`, the dialect of the claim
grammar that reads language vocabulary; a claim over a finite set stays
plain `mathema`.

## Installing the languages

mathema itself parses, renders and records `L[...]` and resolves no name.
The names come from the `mathema-language` package:

```bash
pip install "mathema[language]"
```

It provides the alphabets (`ascii`, `latin-1`, `unicode`, `printable`,
`digit`, `alpha`, `alnum`), the predicate languages with an exact
standard-library test behind each (`identifier`, `json`, `uuid`,
`iso_date`, `iso_datetime`, `ipv4`, `ipv6`, `base64`, `hex`, `slug`,
`shell_safe`), the hazard sub-alphabets a probe mixes in (control and
format characters, combining marks, surrogates, the characters whose
NFKC form differs, the astral planes), the hazard families
`is_length_safe` and `is_encoding_safe`, and the schema adaptors that
turn a dataclass, a `TypedDict`, a pydantic model or a JSON Schema into
the language of its rows. Without it, a claim over `L[unicode]` reports
`skipped` with the message naming the package.

## Writing your own

A language is any object satisfying `mathema.languages.Language`: a
`name`, a `kind` (what a member is), a `level` (how far the engine can
decide it), and `contains`, `explain`, `sample`, `members`, `hazards`,
`outside`, `shrink`, `fields`, `render` and `to_json`.
`mathema.languages.StringLanguage` assembles one from a per-character
test or a whole-string predicate, and `language_problems(obj)` says what
an object is missing. Three ways to make it resolvable:

- `register_language("slug", obj)` in the process that checks the claims.
- A `mathema.languages` entry point in your package, the name being the
  language name.
- A dotted path, `L[myapp.text.SLUG]`, to a `Language` object, or to
  anything a `mathema.language_adaptors` adaptor accepts.

[Extending mathema](extending.md) documents the two entry-point groups.
