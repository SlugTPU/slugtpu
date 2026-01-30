export WAVES=1
export HDL_TOPLEVEL_LANG=verilog

test_fifo:
	python3 -m pytest sim/test_fifo.py -s

clean:
	rm -Rf sim_build

.PHONY: test_fifo clean
