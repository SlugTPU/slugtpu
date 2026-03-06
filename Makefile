export WAVES=1
RTL_FILES := $(shell find rtl/ -name "*.sv")

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

test_scale_n:
	python3 -m pytest sim/test_scale_n.py -s

test_sram:
	python3 -m pytest sim/test_sram.py -s
	
test_tri:
	python3 -m pytest sim/test_tri.py -s

test_quantizer_mul:
	python3 -m pytest sim/test_quantizer_mul.py -s

test_write_transaction:
	python3 -m pytest sim/test_write_transaction.py -s

test_read_transaction:
	python3 -m pytest sim/test_read_transaction.py -s

test_relu_n:
	python3 -m pytest sim/test_relu_n.py -s

test_pe_col:
	python3 -m pytest sim/test_pe_col.py -s

test_scalar_pipe:
	python3 -m pytest sim/test_scalar_pipe.py -s

test_scalar_stage:
	python3 -m pytest sim/test_scalar_stage.py -s

test_load:
	python3 -m pytest sim/test_load.py -s

test_subzp:
	python3 -m pytest sim/test_subzp.py -s

test_sysray:
	python3 -m pytest sim/test_sysray.py -s

lint:
	verilator --lint-only -Wall --sv $(RTL_FILES)

clean:
	rm -rf sim_build

.PHONY: test_fifo test_spi test_bias test_tpuspi test_scalar_load test_add_n clean
