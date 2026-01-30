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
from shared import stringify_dict

LANGUAGE = os.getenv("HDL_TOPLEVEL_LANG", "verilog").lower().strip()

def run_test(parameters, sources, module_name, hdl_toplevel, testcase=None):
    timescale = ("1ps","1ps")
    sims = ["icarus", "verilator"]
    case_name = "all"

    if testcase is not None:
        case_name = testcase

    for sim in sims:
        build_dir = Path("./sim_build", sim, module_name, case_name, stringify_dict(parameters))
        build_args = []

        # extra stuff specifically for verilator
        if (sim == "verilator"):
            build_args.append("--trace-fst")

        runner = get_runner(sim)
        runner.build(
            sources=sources,
            hdl_toplevel=hdl_toplevel,
            always=True,
            timescale=timescale,
            build_dir=build_dir,
            parameters=parameters,
            build_args=build_args
        )

        runner.test(hdl_toplevel=hdl_toplevel, test_module=module_name)

