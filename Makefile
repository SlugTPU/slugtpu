export WAVES=1

test_fifo:
	python3 -m pytest sim/test_fifo.py -s

test_spi:
	python3 -m pytest sim/test_spi.py -s

test_bias:
	python3 -m pytest sim/test_bias.py -s

test_tpuspi:
	python3 -m pytest sim/test_tpu_spi_ctrl.py -s

test_scalar_load:
	python3 -m pytest sim/test_load_data.py -s

test_add_n:
	python3 -m pytest sim/test_add_n.py -s

test_sram:
	python3 -m pytest sim/test_sram.py -s
	
test_tri:
	python3 -m pytest sim/test_tri.py -s

clean:
	rm -rf sim_build

.PHONY: test_fifo test_spi test_bias test_tpuspi test_scalar_load test_add_n clean