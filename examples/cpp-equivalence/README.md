# A C++ implementation, checked equivalent

The claim grammar is language-neutral, and the equivalence relation
(`f =:= g`) accepts any callable for `g`, so a C++ implementation
reached through a ctypes shim participates in the ladder today, with
no special integration.

## Run it

```bash
clang++ -O2 -shared -o libema.dylib ema.cpp   # macOS
# g++ -O2 -shared -fPIC -o libema.so ema.cpp  # Linux
python shim.py
```

Output (the two warnings go to stderr, shown here trimmed):

```text
StateDependenceWarning: mathema: ema_cpp inherits from global scope: _lib; behavior depends on state outside the function
StateDependenceWarning: mathema: ema_cpp inherits from global scope: _lib; behavior depends on state outside the function
verdict: holds  route: probe
note:    96 executed shared points agree within tolerance (sampling, never proof)
```

The 96 is the equivalence ladder's fixed budget of shared, seeded
draws, every one of which executed on both sides and agreed; see
[the ladder](../../docs/multi-function-claims.md).

## Read the result honestly

- **`holds`, never `proven`.** The C++ side has no Python source, so
  the form-hash and symbolic rungs of the equivalence ladder cannot
  run; what remains is code-versus-code sampling on shared draws,
  and sampling is evidence, not proof.
- **The state warning is mathema being right.** The shim's `_lib`
  handle is state outside the walk, and the analyzer says so. A C
  library is exactly that.
- **The binding does not survive the record.** `funcs={"g": ema_cpp}`
  is a live callable with no text spelling, so the recorded claim
  keeps the law but not the binding. Anything meant to persist should
  bind by dotted path (`let g = <module>.<name>`) to an importable
  shim.
- **Safety claims do not transfer.** Equivalence is about the
  mathematics. `is_state_safe`, representation behaviour, and
  overflow are properties of an implementation and a language
  (signed-integer overflow is undefined behaviour in C++, `-ffast-math`
  changes NaN semantics), and each implementation earns its own.
