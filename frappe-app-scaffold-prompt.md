# Frappe App Scaffolding Prompt

Use this prompt when hand-scaffolding a new Frappe app without access to `bench new-app`/`bench new-doctype` (e.g. on a machine without a bench environment). It encodes every real bug hit while building `entre_mc`, verified against a known-working reference app and against Frappe's own source where relevant.

---

I'm building a new Frappe app called `<app_name>` by hand (no local bench available to scaffold it). Follow these rules exactly — they come from a previous app where violating each one caused a real, hard-to-diagnose install failure.

## 1. Directory depth — verify, don't assume

Structure must be exactly:

```
<app_name>/                        <- repo root (= apps/<app_name> once cloned by bench)
  pyproject.toml
  README.md
  <app_name>/                      <- Python package, ONE level below repo root
    __init__.py                    <- contains __version__ = "0.0.1"
    hooks.py
    modules.txt
    config/__init__.py
    public/js/, public/css/
    templates/
    fixtures/
    tasks.py, utils/, etc.         <- package-level helper modules (NOT inside the module folder below)
    <module_name>/                 <- Frappe module folder, TWO levels below repo root
                                       (module_name = app name scrubbed, from modules.txt, usually same as app_name)
      __init__.py                  <- MUST exist, even if empty — easy to forget
      doctype/
        <doctype_folder>/
          __init__.py
          <doctype>.json
          <doctype>.py
          <doctype>.js             (optional)
```

After creating every file, verify the depth explicitly — do not eyeball `find` output and count slashes by hand (I did this twice and miscounted both times). Instead run, from the repo root:

```bash
find "$(pwd)" -iname "hooks.py" -not -path "*/.git/*"
find "$(pwd)" -type d -iname "doctype" -not -path "*/.git/*"
```

`hooks.py` must be at exactly repo_root/`<app_name>`/hooks.py (one segment). `doctype/` must be at exactly repo_root/`<app_name>`/`<app_name>`/doctype (two segments). If you have another working Frappe app locally, run the same two commands against it and diff the segment counts — this catches off-by-one nesting errors that pure counting misses.

## 2. pyproject.toml — use flit_core, not setuptools

```toml
[project]
name = "<app_name>"
authors = [{ name = "...", email = "..." }]
description = "..."
requires-python = ">=3.10"
readme = "README.md"
dynamic = ["version"]

[build-system]
requires = ["flit_core >=3.4,<4"]
build-backend = "flit_core.buildapi"

[tool.bench.dev-dependencies]
```

- `dynamic = ["version"]` + flit_core reads `__version__` from `<app_name>/__init__.py` via static AST parsing — this works reliably. Do NOT switch to setuptools "to fix" an install error without first seeing the actual underlying pip error (run pip manually, not through `bench`, and drop the `--quiet` flag — it hides the real error). setuptools' package auto-discovery has a known ambiguity bug when the project directory and the package directory share the same name (which they will, since bench apps are named after themselves), causing it to register the package as a broken namespace package.
- No `package.json` needed. No MANIFEST.in needed. Don't add either unless a real working reference app has one.

## 3. hooks.py asset includes

```python
app_include_css = "/assets/<app_name>/css/<file>.css"
app_include_js = [
    "/assets/<app_name>/js/<file>.js",
]
```

Use the full `/assets/<app>/...` built-output path, pointing at plain files under `public/js/` and `public/css/` with **no** `.bundle.js`/`.bundle.css` suffix. Don't use a bare filename or an `"<app>/<file>"` form — both are wrong conventions for this hook (confirmed against Frappe's esbuild source and a working reference app).

## 4. DocType `"name"` field — two hard constraints

Every DocType JSON has a `"name"` field that is its *internal identity* — this is completely separate from field `"label"` values, which can be anything.

**a) ASCII only, no diacritics.** Frappe's module-file resolution (`frappe.scrub()`-based) does not strip accents. If the doctype is called "Situação da Fatura", Frappe will look for a Python module literally named `situação_da_fatura` and fail. Use `Situacao da Fatura` for the `name` field; keep the accented version only in a `label` field if you want it displayed. Field labels, print format names, Role names, Workflow State names — none of those have this constraint, only the DocType's own `name`.

**b) Every word capitalized, matching the Python class name exactly.** Frappe derives the expected controller class name via literally `doctype.replace(" ", "").replace("-", "")` — no re-capitalization of any word. So a DocType named `"Pedido de Credito"` (lowercase "de") produces the expected class name `PedidodeCredito`, which will NOT match a Python class written as `class PedidoDeCredito(Document):` (capital "De", the natural PascalCase convention). This mismatch doesn't error immediately — it fails silently during `bench migrate`'s orphan-doctype cleanup, which treats the unloadable doctype as "orphaned" and **deletes it** with no obvious error pointing at the real cause.

  Rule: for any multi-word DocType name (including connector words like "de"/"do"/"da"/"of"/"and"), write it as strict PascalCase-with-spaces (`"Pedido De Credito"`), and make sure the Python class name matches exactly after removing spaces (`class PedidoDeCredito(Document):`). Verify this for every doctype before shipping:

  ```bash
  python -c "
  import json, glob
  for f in glob.glob('<app_name>/<app_name>/<app_name>/doctype/*/*.json'):
      d = json.load(open(f, encoding='utf-8'))
      if d.get('istable'): continue
      expected_class = d['name'].replace(' ', '').replace('-', '')
      py_file = f.rsplit('.json', 1)[0] + '.py'
      content = open(py_file, encoding='utf-8').read()
      if f'class {expected_class}(' not in content:
          print(f'MISMATCH: {f} name={d[\"name\"]!r} expected class {expected_class}, not found in {py_file}')
  "
  ```

## 5. Import paths — package-level vs module-level

- Files living directly in the package root (`<app_name>/<app_name>/utils.py`, `<app_name>/<app_name>/tasks.py`, or a `utils/` subpackage there) are imported as `<app_name>.utils....` — **one** `<app_name>` segment.
- Files inside the module folder (`doctype/`, `page/`, `report/`, `workspace/`, `print_format/`) are imported as `<app_name>.<app_name>.doctype....` — **two** `<app_name>` segments.
- This applies to real `from X import Y` statements, `hooks.py` string references (`scheduler_events`, `doc_events`), and JS-side `frappe.call({method: "..."})` strings alike. After writing all the code, verify every dotted reference actually resolves to a file on disk (adjust the regex/string list per project):

  ```bash
  python -c "
  import re, os, glob
  pattern = re.compile(r'from (<app_name>(?:\.\w+)+) import')
  for f in glob.glob('<app_name>/**/*.py', recursive=True):
      content = open(f, encoding='utf-8').read()
      for m in pattern.finditer(content):
          path = m.group(1).replace('.', '/') + '.py'
          if not os.path.isfile(path):
              print(f'{f}: {m.group(1)} -> {path} MISSING')
  "
  ```

## 6. Naming series

Use Frappe's standard mechanism, not a custom settings-driven one:

- For real transactional documents: `"autoname": "naming_series:"` at the doctype top level, plus a `naming_series` Select field with a single default option (e.g. `"XX-.YY.-.##"`), editable later via Setup → Naming Series.
- For entity/person-like documents that should be named after a natural identifier: `"autoname": "field:some_field"` (e.g. a person's full name). No Python override needed for either case.

## 7. If installing on a remote bench (server debugging checklist)

If `bench get-app`/`install-app`/`migrate` fails, work through these in order rather than guessing:

1. **Un-quiet the real error.** `bench` often runs pip with `--quiet`, hiding the actual failure. Run the underlying `pip install -e <path>` command directly to see it. When re-running raw commands manually, match the file-ownership user (`ls -la apps/<app>` — if owned by e.g. `daemon` not your login user, run as `sudo -u daemon ...`, since `bench` itself may run under a different user than your interactive shell).
2. **Clean stale state before every retry.** After any failed attempt: `rm -rf apps/<app_name>` before re-cloning, and remove any `*.egg-info` and `__pycache__` directories left behind — these can cause confusing secondary errors (permission/timestamp errors, stale bytecode) unrelated to the real bug.
3. **Check `sites/apps.txt`.** Should contain the app name on its own line. If a manual edit was ever needed, verify with `cat -A` that no line got concatenated without a newline (a common `>>`-without-preceding-newline mistake that silently corrupts the file and breaks unrelated apps in the same file).
4. **If `bench build` fails in esbuild** with a cryptic `path.resolve` / `undefined` error, it's almost always `sites/apps.txt` missing the app, not a hooks.py convention issue — check that file before touching any JS asset config.
5. **If `bench migrate` silently deletes doctypes** ("Orphaned DocType(s) found... Deleting"), don't treat it as harmless cleanup without checking — run `frappe.get_all("DocType", filters={"module": "<Module Name>"}, pluck="name")` in `bench console` before and after to see exactly what's missing, then reproduce the failure directly with `from frappe.model.base_document import get_controller; get_controller(doctype="X")` to get the real traceback instead of inferring from the migrate summary.
6. **If you have another working Frappe app**, diff structure and conventions against it directly (`ls`, `cat hooks.py`, `cat pyproject.toml`) rather than relying on memory of "how Frappe apps usually look" — this caught the majority of the real bugs faster than reasoning from first principles did.

## 8. Before ever pushing to test on a server

Run all of these locally and only proceed once they're all clean:

```bash
# JSON syntax
python -c "import json, glob; [json.load(open(f, encoding='utf-8')) for f in glob.glob('<app_name>/**/*.json', recursive=True)]"

# Python syntax
python -m py_compile $(find <app_name> -name "*.py")

# TOML syntax + backend sanity
python -c "import tomllib; d = tomllib.load(open('pyproject.toml','rb')); print(d['build-system'])"

# Every doctype class name matches its "name" field (see section 4)
# Every dotted import resolves to a real file (see section 5)
```

None of these catch the *specific* bugs in this document (they're about depth/naming conventions, not syntax) — but they're cheap, and set a baseline so remaining failures are more likely to be a convention issue covered above rather than a typo.
