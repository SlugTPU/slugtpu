export WAVES=1
export HDL_TOPLEVEL_LANG=verilog

test_fifo:
	python3 sim/test_runner.py fifo_sim

clean:
	rm -Rf sim_build

.PHONY: test_fifo clean
