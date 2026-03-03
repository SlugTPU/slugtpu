SIM           = icarus
TOPLEVEL_LANG = verilog

VERILOG_SOURCES = $(PWD)/pe.sv $(PWD)/sysray.sv

TOPLEVEL = sysray
COCOTB_TEST_MODULES = test_sysray

include $(shell cocotb-config --makefiles)/Makefile.sim

clean::
	rm -rf sim_build __pycache__ results.xml *.vcd *.log
