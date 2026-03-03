SIM           = icarus
TOPLEVEL_LANG = verilog

VERILOG_SOURCES = $(PWD)/pe.sv $(PWD)/pe_row.sv

TOPLEVEL = pe_row
COCOTB_TEST_MODULES = test_pe_row

include $(shell cocotb-config --makefiles)/Makefile.sim

clean::
	rm -rf sim_build __pycache__ results.xml *.vcd *.log
