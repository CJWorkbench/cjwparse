Parsers for [CJWorkbench](https://github.com/CJWorkbench/cjworkbench) modules.

Workbench modules may _optionally_ depend on the latest version of this Python
package for its `cjwparse.api.parse_file()` function.

Installation
============

This is meant to be used within a Docker container. It depends on executables
`/usr/bin/(csv|json|xls|xlsx)-to-arrow`.

Your Dockerfile might look something like this:

```
FROM arrow-tools:v0.0.11 AS arrow-tools
FROM python:3.8.1-buster AS main

COPY --from=arrow-tools /usr/bin/csv-to-arrow /usr/bin/csv-to-arrow
COPY --from=arrow-tools /usr/bin/json-to-arrow /usr/bin/json-to-arrow
COPY --from=arrow-tools /usr/bin/xls-to-arrow /usr/bin/xls-to-arrow
COPY --from=arrow-tools /usr/bin/xlsx-to-arrow /usr/bin/xlsx-to-arrow

# And now that these binaries are accessible, you can install cjwparse...
```

Usage
=====

```python
import pyarrow

from cjwparse.api import parse_file

# Convert a CSV file 'input.csv' to Arrow file 'output.arrow'
input_path = Path("input.csv")
input_path.write_bytes(b"A,B\n1,2")
output_path = Path("output.arrow")
parse_file(input_path, output_path=output_path, has_headers=False)

# Read the output
with pyarrow.ipc.open_file(output_path) as reader:
    table = reader.read_all()
```


Developing
==========

1. Run tests: `docker build .`
2. Write a failing unit test in `tests/`
3. Make it pass by editing code in `cjwparse/`
4. `black cjwparse tests && isort --recursive cjwparse tests`
5. Submit a pull request

Be very, very, very careful to preserve a consistent API. Workbench will
upgrade this dependency without module authors' explicit consent. Add new
features; fix bugs. Never change functionality.

I18n
====

### Marking strings for translation

Strings in `cjwparse` can be marked for translation using
`cjwparse.i18n._trans_cjwparse`. Each translation message must have a
(unique) ID. ICU is supported for the content. For example:

```python
from .i18n import _trans_cjwparse

err = "Error 404"

with_arguments = _trans_cjwparse(
    "greatapi.exception.message",
    "Something is wrong: {error}",
    {"error": err}
)

without_arguments = _trans_cjwparse(
    "greatapi.exception.general",
    "Something is wrong",
)
```

Workbench is wired to accept the return value of `_trans_cjwparse`
wherever an error/warning or quick fix is expected.

### Creating `po` catalogs

Calls to `_trans_cjwparse` can (and must) be parsed to create `cjwparse`'s `.po` files.
Update the `.po` files with:

```
./setup.py extract_messages
```

The first time you run this, you'll need to install dependencies: `pip3 install .[maintenance]`

### Unit testing

In case a `_trans_cjwparse` invocation needs to be unit tested, you can use `cjwparse.testing.i18n.cjwparse_i18n_message` 
in a manner similar to the following: 

```python
from cjwparse.testing.i18n import cjwparse_i18n_message
import with_arguments, without_arguments

assert with_arguments == cjwparse_i18n_message("greatapi.exception.message", {"error": "Error 404"})
assert without_arguments == cjwparse_i18n_message("greatapi.exception.general")
```

### Message deprecation

Never delete a `trans()` call: each message ID, once assigned, must be preserved
forever.

When there is no more code path to a `trans()` call, move it to
`cjwparse/i18n/_deprecated_i18n_messages.py`. The file is only read by
extraction code. It is never executed.


Publishing
==========

1. Write a new `__version__` to `cjwparse/__init__.py`. Adhere to
   [semver](https://semver.org). (As changes must be backwards-compatible,
   the version will always start with `1` and look like `1.x.y`.)
2. Prepend notes to `CHANGELOG.md` about the new version
3. `git commit`
4. `git tag v1.x.y`
5. `git push --tags && git push`
6. Wait for Travis to push our changes to PyPI
