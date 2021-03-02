v1.2.0 - 2021-03-02
-------------------

* Support pyarrow~=3.0.

v1.1.0 - 2020-11-17
-------------------

* Nix warning when dictionary-encoding.
* Support pyarrow~=2.0.

v1.0.1 - 2020-10-16
-------------------

* On xlnt exception, show the user an error that suggests opening and re-saving
  the file in Excel. (Many automated tools out there write invalid Excel files
  that Microsoft Excel can open. Workbench is unlikely to achieve feature parity
  with Microsoft Excel's file-repair subsystem.)

v1.0.0 - 2020-09-22
-------------------

* bump arrow-tools to Arrow 1.0

This is a major version change because files written by Arrow 1 aren't
always readable by Arrow 0.16.

v0.0.8 - 2020-07-23
-------------------

* bump arrow-tools, to support more .xlsx files.

v0.0.7 - 2020-06-16
-------------------

* csv: fix typo in the "truncated value" message.

v0.0.6 - 2020-06-03
-------------------

* csv: don't auto-convert "NaN" or "Inf" to Number

v0.0.5 - 2020-06-03
-------------------

* csv: don't auto-convert huge strings of digits to Number

v0.0.4 - 2020-03-31
-------------------

* i18n.en: pluralize warnings correctly.
* i18n.el: first Greek translations.

v0.0.3 - 2020-03-08
-------------------

* Relax cjwmodule dep version.

v0.0.2 - 2020-03-04
-------------------

* Fix CSV parsing.

v0.0.1 - 2020-03-03
-------------------

* Initial release, with `cjwparse.parse_file()`.
