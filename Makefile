# dump waveforms
export WAVES := 1

test_fifo:
	HDL_TOPLEVEL_LANG=verilog pytest sim/test_fifo.py -s