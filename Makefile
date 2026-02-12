export WAVES=1

test_fifo:
	python3 -m pytest sim/test_fifo.py -s

test_spi:
	python3 -m pytest sim/test_spi.py -s

test_bias:
	python3 -m pytest sim/test_bias.py -s

clean:
	rm -rf sim_build

.PHONY: test_fifo test_spi clean
