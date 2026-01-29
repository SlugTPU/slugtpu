# This file is public domain, it can be freely copied without restrictions.
# SPDX-License-Identifier: CC0-1.0
from __future__ import annotations

import os
import random
from pathlib import Path
import cocotb
from cocotb_tools.runner import get_runner
import pytest
import sys
import importlib

LANGUAGE = os.getenv("HDL_TOPLEVEL_LANG", "verilog").lower().strip()

# @pytest.mark.parametrize("sim", [("icarus"), ("verilator")])
def test_runner():
    if len(sys.argv) < 1:
        assert 0, "Must provide module name (without .py extension) to test!"

    test_module_name = sys.argv[1]
    test_module_path = Path("./sim", test_module_name+".py").resolve()

    # use importlib to import test module at runtime
    spec = importlib.util.spec_from_file_location(test_module_name, test_module_path)
    if spec is None:
        assert 0, "Could not find module in sim directory"
    test_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(test_module)
    test_data = test_module.register_tests()
    print(f"DEBUG: {test_data}, test_module_name is {test_module_name}")

    timescale = ("1ps","1ps")
    sims = ["icarus", "verilator"]

    for sim in sims:
        build_dir = Path("./sim_build", sim)
        build_args = []

        # extra stuff specifically for verilator
        if (sim == "verilator"):
            build_args.append("--trace-fst")

        runner = get_runner(sim)
        runner.build(
            sources=test_data["sources"],
            hdl_toplevel=test_data["hdl_toplevel"],
            always=True,
            timescale=timescale,
            build_dir=build_dir,
            build_args=build_args
        )

        runner.test(hdl_toplevel=test_data["hdl_toplevel"], test_module=test_module_name)


if __name__ == "__main__":
    test_runner()
