"""Feasibility experiment only. Parse fixed fixtures without opening a database.

This uses private CUBRID symbols, not a supported distribution interface.
Run in a bounded child process. See ../feasibility.md for prerequisites.
"""

import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import resource
import sys
import tempfile


def main():
    args = argparse.ArgumentParser(description=__doc__)
    args.add_argument("--library", type=Path, required=True)
    args.add_argument("--prefix", type=Path, required=True)
    args.add_argument("--source-commit", required=True)
    options = args.parse_args()
    library = options.library.resolve(strict=True)
    prefix = options.prefix.resolve(strict=True)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_CPU, (10, 10))
    sys.dont_write_bytecode = True

    # This experiment never invokes a client, registers a DB, or executes SQL.
    ctypes.CDLL("libstdc++.so.6", mode=ctypes.RTLD_GLOBAL)
    lib = ctypes.CDLL(str(library))
    signatures = [
        ("er_init", [ctypes.c_char_p, ctypes.c_int], ctypes.c_int),
        ("lang_init", [], ctypes.c_int),
        ("lang_set_charset_lang", [ctypes.c_char_p], ctypes.c_int),
        ("msgcat_init", [], ctypes.c_int),
        ("sysprm_load_and_init", [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int], ctypes.c_int),
        ("parser_create_parser", [], ctypes.c_void_p),
        ("parser_parse_string_with_escapes", [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_bool], ctypes.c_void_p),
        ("pt_get_errors", [ctypes.c_void_p], ctypes.c_void_p),
        ("pt_get_next_error", [ctypes.c_void_p, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int),
                               ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_char_p)], ctypes.c_void_p),
        ("parser_free_parser", [ctypes.c_void_p], None),
    ]
    for name, inputs, output in signatures:
        function = getattr(lib, name)
        function.argtypes = inputs
        function.restype = output
    version = getattr(lib, "_Z18rel_version_stringv")
    version.argtypes = []
    version.restype = ctypes.c_char_p

    fixtures = [
        ("cubrid-serial-valid", "CREATE SERIAL order_no START WITH 10 INCREMENT BY 2;", True),
        ("cubrid-serial-invalid", "CREATE SERIAL order_no START WITH ;", False),
        ("editor-incomplete", "SELECT e. FROM employees e;", False),
        ("catalog-independent", "SELECT missing_column FROM missing_table;", True),
        ("unicode-crlf", "-- 한글 😀\r\nSELECT '한글 😀';", True),
        ("multiple-statements", "SELECT 1; CREATE SERIAL order_no START WITH 10;", True),
        ("destructive-text-only", "DROP TABLE must_never_be_executed;", True),
    ]
    report = {
        "experiment": "native-parse-only",
        "library": str(library),
        "library_sha256": hashlib.sha256(library.read_bytes()).hexdigest(),
        "binary_version": version().decode("ascii"),
        "source_commit_claim_from_build": options.source_commit,
        "qualification": "feasibility-only, not a release conformance claim",
        "parse_entrypoint": "parser_parse_string_with_escapes(..., false)",
        "initialization": {},
        "cases": [],
    }
    previous_cwd = Path.cwd()
    with tempfile.TemporaryDirectory(prefix="cubrid-parse-only-") as scratch:
        os.environ.update(CUBRID=str(prefix), CUBRID_CONF=scratch, CUBRID_DATABASES=scratch,
                          CUBRID_TMP=scratch, CUBRID_LANG="en_US.utf8")
        config = Path(scratch) / "cubrid.conf"
        config.write_text("[common]\n", encoding="utf-8")
        os.chdir(scratch)
        try:
            for name, inputs in [
                ("er_init", (os.fsencode(Path(scratch) / "probe.err"), 0)),
                ("lang_init", ()),
                ("lang_set_charset_lang", (b"en_US.utf8",)),
                ("msgcat_init", ()),
                ("sysprm_load_and_init", (None, os.fsencode(config), 0)),
            ]:
                result = getattr(lib, name)(*inputs)
                report["initialization"][name] = result
                if result != 0:
                    raise RuntimeError(f"{name} failed: {result}")

            for name, text, expected in fixtures:
                parser = lib.parser_create_parser()
                if not parser:
                    raise RuntimeError("parser allocation failed")
                try:
                    tree = lib.parser_parse_string_with_escapes(parser, text.encode("utf-8"), False)
                    error = lib.pt_get_errors(parser)
                    errors = []
                    while error:
                        statement, line, column = ctypes.c_int(), ctypes.c_int(), ctypes.c_int()
                        message = ctypes.c_char_p()
                        error = lib.pt_get_next_error(error, ctypes.byref(statement), ctypes.byref(line),
                                                      ctypes.byref(column), ctypes.byref(message))
                        errors.append({"statement": statement.value, "line": line.value, "column": column.value,
                                       "message": (message.value or b"").decode("utf-8", errors="replace")})
                    accepted = bool(tree) and not errors
                    report["cases"].append({"id": name, "text": text, "tree": bool(tree), "errors": errors,
                                            "expected_accepted": expected, "observed_accepted": accepted})
                finally:
                    lib.parser_free_parser(parser)
        finally:
            os.chdir(previous_cwd)

    # The existing completion path remains usable while strict parsing rejects incomplete text.
    sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))
    from csql_future.completion import Relation, Schema, suggest
    text = "SELECT e. FROM employees e;"
    result = suggest(text, len("SELECT e."), Schema("DBA", (Relation("DBA", "employees", "CLASS", ("id", "name")),)))
    report["incomplete_completion"] = {"text": text, "cursor": len("SELECT e."),
                                       "candidates": [item.text for item in result.candidates]}
    report["expectations_met"] = all(item["observed_accepted"] == item["expected_accepted"] for item in report["cases"])
    report["expectations_met"] &= report["incomplete_completion"]["candidates"] == ["id", "name"]
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["expectations_met"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
