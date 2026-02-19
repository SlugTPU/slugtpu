import pytest
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, FallingEdge
from pathlib import Path
from shared import reset_sequence, clock_start
from runner import run_test
import random
from collections import deque


def _to_signed32(val):
	mask = (1 << 32) - 1
	v = val & mask
	if v & (1 << 31):
		return v - (1 << 32)
	return v


class ScaleModel():
	def __init__(self):
		self.scale_r = 0
		self.have_scale = False
		self.q = deque()
		self.checked = 0

	def update_scale(self, dut):
		# read signed value
		raw = dut.data_i.value.to_unsigned()
		self.scale_r = _to_signed32(raw)
		self.have_scale = True
		cocotb.log.info(f"Model: updated scale to {self.scale_r}")

	def capture_data(self, dut):
		raw = int(dut.data_i.value)
		data = _to_signed32(raw)

		# prefer bypass scale if provided in same cycle
		if dut.scale_valid_i.value == 1:
			mul = _to_signed32(int(dut.scale_i.value))
		elif self.have_scale:
			mul = self.scale_r
		else:
			# no scale available; record None to indicate unexpected
			mul = None

		if mul is None:
			cocotb.log.warning("Model: data seen but no scale available — skipping expected output")
		else:
			expect = _to_signed32(mul * data)
			self.q.append(expect)
			cocotb.log.info(f"Model: queued expected {expect} (scale {mul} * data {data})")

	def check_output(self, dut):
		if not self.q:
			raise AssertionError("DUT produced output but model has no expected values")
		got = _to_signed32(int(dut.data_o.value))
		expect = self.q.popleft()
		cocotb.log.info(f"Model: comparing got {got} expect {expect}")
		assert got == expect
		self.checked += 1


class ModelRunner():
	def __init__(self, dut, model):
		self.model = model
		self.dut = dut
		self.clk_i = dut.clk_i
		self.rst_i = dut.rst_i
		self.scale_valid_i = dut.scale_valid_i
		self.data_valid_i = dut.data_valid_i
		self.data_valid_o = dut.data_valid_o

	def start(self):
		cocotb.start_soon(self.run_input())
		cocotb.start_soon(self.run_output())

	async def run_input(self):
		await FallingEdge(self.rst_i)
		while True:
			await RisingEdge(self.clk_i)
			# mirror DUT: when scale_valid_i is asserted the DUT latches the
			# *data_i* into the registered scale. Capture that first so a
			# data+scale (bypass) cycle still prefers the bypass path.
			if self.scale_valid_i.value == 1:
				self.model.update_scale(self.dut)
			if self.data_valid_i.value == 1:
				# capture data and compute expected output (may use bypass or registered scale)
				self.model.capture_data(self.dut)

	async def run_output(self):
		await FallingEdge(self.rst_i)
		while True:
			await RisingEdge(self.clk_i)
			if int(self.data_valid_o.value) == 1:
				self.model.check_output(self.dut)



@cocotb.test()
async def reset_test(dut):
	clk_i = dut.clk_i
	rst_i = dut.rst_i

	await clock_start(clk_i)
	await reset_sequence(clk_i, rst_i)
	await FallingEdge(rst_i)


@cocotb.test()
async def scale_bypass_test(dut):
	"""Provide scale and data in the same cycle (bypass path)."""
	clk_i = dut.clk_i
	rst_i = dut.rst_i

	await clock_start(clk_i)
	await reset_sequence(clk_i, rst_i)

	await FallingEdge(rst_i)

	# start model runner
	m = ScaleModel()
	r = ModelRunner(dut, m)
	r.start()

	# try several random small values to avoid overflow/truncation ambiguity
	expected = 20
	for _ in range(expected):
		# drive inputs after falling edge, then let DUT sample on rising edge
		await FallingEdge(clk_i)
		scale = random.randint(-1000, 1000)
		data = random.randint(-1000, 1000)

		dut.scale_i.value = int(scale)
		dut.scale_valid_i.value = 1
		dut.data_i.value = int(data)
		dut.data_valid_i.value = 1

		await RisingEdge(clk_i)

		# deassert for a cycle
		dut.scale_valid_i.value = 0
		dut.data_valid_i.value = 0

	# wait until model has observed all outputs
	while m.checked < expected:
		await RisingEdge(clk_i)


@cocotb.test()
async def scale_registered_test(dut):
	"""Write scale into the module, then stream data (registered path)."""
	clk_i = dut.clk_i
	rst_i = dut.rst_i

	await clock_start(clk_i)
	await reset_sequence(clk_i, rst_i)

	await FallingEdge(rst_i)

	# start model runner
	m = ScaleModel()
	r = ModelRunner(dut, m)
	r.start()

	# present a scale value for one cycle (drive after falling edge)
	await FallingEdge(clk_i)
	scale = random.randint(-1000, 1000)
	dut.scale_i.value = int(scale)
	dut.scale_valid_i.value = 1
	await RisingEdge(clk_i)

	# deassert scale_valid
	dut.scale_valid_i.value = 0
	await FallingEdge(clk_i)

	# now send data values and expect multiply by previously provided scale
	expected = 10
	for data in range(-5, 5):
		# drive data after falling edge so DUT samples on rising edge
		await FallingEdge(clk_i)
		dut.data_i.value = int(data)
		dut.data_valid_i.value = 1
		await RisingEdge(clk_i)

		dut.data_valid_i.value = 0
		await FallingEdge(clk_i)

	# wait until model has observed all outputs
	while m.checked < expected:
		await RisingEdge(clk_i)


@cocotb.test()
async def scale_random_test(dut):
	"""Randomized mixes of bypass and registered operations."""
	clk_i = dut.clk_i
	rst_i = dut.rst_i

	await clock_start(clk_i)
	await reset_sequence(clk_i, rst_i)

	await FallingEdge(rst_i)

	# start model runner
	m = ScaleModel()
	r = ModelRunner(dut, m)
	r.start()

	# choose a scale and sometimes update it
	current_scale = 1
	sent = 0
	for i in range(30):
		if random.random() < 0.3:
			# update scale (registered)
			current_scale = random.randint(-200, 200)
			# drive scale strobe after falling edge, sampled on rising
			await FallingEdge(clk_i)
			dut.scale_i.value = int(current_scale)
			dut.scale_valid_i.value = 1
			dut.data_valid_i.value = 0
			await RisingEdge(clk_i)
			# scale_valid is a one-cycle strobe; deassert and step
			dut.scale_valid_i.value = 0
			await FallingEdge(clk_i)
		else:
			# sometimes do bypass (scale_valid and data_valid same cycle)
			if random.random() < 0.4:
				scale_here = random.randint(-200, 200)
				data = random.randint(-200, 200)
				# drive bypass inputs after falling edge
				await FallingEdge(clk_i)
				dut.scale_i.value = int(scale_here)
				dut.scale_valid_i.value = 1
				dut.data_i.value = int(data)
				dut.data_valid_i.value = 1
				await RisingEdge(clk_i)
				# count an expected output
				sent += 1
				dut.scale_valid_i.value = 0
				dut.data_valid_i.value = 0
				await FallingEdge(clk_i)
			else:
				# use current registered scale
				data = random.randint(-200, 200)
				# drive data after falling edge for registered-scale case
				await FallingEdge(clk_i)
				dut.data_i.value = int(data)
				dut.data_valid_i.value = 1
				await RisingEdge(clk_i)
				sent += 1
				dut.data_valid_i.value = 0
				await FallingEdge(clk_i)

	# wait until model has observed all outputs produced
	while m.checked < sent:
		await RisingEdge(clk_i)


tests = ["reset_test", "scale_bypass_test", "scale_registered_test", "scale_random_test"]


@pytest.mark.parametrize("testcase", tests)
def test_scale_each(testcase):
	proj_path = Path("./rtl").resolve()
	sources = [ proj_path / "scale.sv" ]

	run_test(sources=sources, parameters={}, module_name="test_scale", hdl_toplevel="scale", testcase=testcase)


def test_scale_all():
	proj_path = Path("./rtl").resolve()
	sources = [ proj_path / "scale.sv" ]

	run_test(sources=sources, parameters={}, module_name="test_scale", hdl_toplevel="scale")

