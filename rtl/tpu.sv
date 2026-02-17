module tpu #(
	parameter int N = 8,
	parameter int DATA_W = 8,
	parameter int PSUM_W = 32
) (
	input  logic                   clk,
	input  logic                   rst,

	// Direct N-byte inputs/weights — TPU only accepts these
	input  logic [DATA_W-1:0]      sysdata_i   [N],
	input  logic [DATA_W-1:0]      sysweight_i [N],
	input  logic [N-1:0]           in_valid_input,
	input  logic [N-1:0]           in_valid_weight,

	// Final result output: two 32-bit results packed into 64-bit word
	output logic [63:0]            result_o,
	output logic                   result_valid_o
);

	// Top-level simply instantiates the systolic array
	sysray #(
		.N(N),
		.DATA_W(DATA_W),
		.PSUM_W(PSUM_W)
	) u_sysray (
		.clk(clk),
		.rst(rst),
		.sysdata_i(sysdata_i),
		.sysweight_i(sysweight_i),
		.in_valid_input(in_valid_input),
		.in_valid_weight(in_valid_weight),
		.psum_o(psum_o),
		.psum_valid_o(psum_v_o)
	);

	// --- internal PSUM outputs from systolic array ---
	logic [PSUM_W-1:0] psum_o   [N];
	logic               psum_v_o [N];

	// instantiate bias/scale internal storage (one entry per column)
	logic signed [31:0] bias_reg  [N];
	logic signed [31:0] scale_reg [N];

	// initialize bias/scale to zero on reset (internal only)
	integer ii;
	always_ff @(posedge clk) begin
		if (rst) begin
			for (ii = 0; ii < N; ii = ii + 1) begin
				bias_reg[ii]  <= '0;
				scale_reg[ii] <= '0;
			end
		end
	end

	// wires between pipeline stages
	logic [PSUM_W-1:0] lane_in   [1:0];
	logic               stage0_valid;
	logic [$clog2(N)-1:0] stage0_idx;

	logic               stage1_valid;
	logic [$clog2(N)-1:0] stage1_idx;

	logic               stage2_valid;
	logic [$clog2(N)-1:0] stage2_idx;

	// results from bias and scale modules
	logic signed [31:0] bias_mid  [1:0];
	logic               bias_mid_v[1:0];
	logic signed [31:0] scale_out [1:0];
	logic               scale_v   [1:0];

	// result registers
	logic signed [31:0] result_reg0, result_reg1;

	// read pointer for pairing outputs (process two columns per cycle when available)
	logic [$clog2(N)-1:0] out_ptr;

	// pipeline control and pairing: capture available psum pairs and advance pointer
	always_ff @(posedge clk) begin
		if (rst) begin
			stage0_valid <= 1'b0;
			stage1_valid <= 1'b0;
			stage2_valid <= 1'b0;
			out_ptr <= '0;
			result_reg0 <= '0;
			result_reg1 <= '0;
			result_o <= 64'd0;
			result_valid_o <= 1'b0;
		end else begin
			// capture pair when available
			if ((psum_v_o[out_ptr]) && (psum_v_o[out_ptr + 1])) begin
				stage0_valid <= 1'b1;
				stage0_idx <= out_ptr;
				lane_in[0] <= psum_o[out_ptr];
				lane_in[1] <= psum_o[out_ptr + 1];
				out_ptr <= out_ptr + 2;
			end else begin
				stage0_valid <= 1'b0;
			end

			// advance pipeline
			stage1_valid <= stage0_valid;
			stage1_idx <= stage0_idx;

			stage2_valid <= stage1_valid;
			stage2_idx <= stage1_idx;

			// capture scaled outputs when available and present final result when stage2 active
			if (scale_v[0]) result_reg0 <= scale_out[0];
			if (scale_v[1]) result_reg1 <= scale_out[1];

			if (stage2_valid) begin
				result_o <= {result_reg1, result_reg0};
				result_valid_o <= 1'b1;
			end else begin
				result_valid_o <= 1'b0;
			end
		end
	end

	// instantiate bias/scale for lane 0
	bias u_bias_0 (
		.clk_i(clk),
		.rst_i(rst),
		.bias_i(bias_reg[stage0_idx]),
		.bias_valid_i(stage0_valid),
		.data_valid_i(stage0_valid),
		.data_i(lane_in[0]),
		.data_valid_o(bias_mid_v[0]),
		.data_o(bias_mid[0])
	);

	scale u_scale_0 (
		.clk_i(clk),
		.rst_i(rst),
		.scale_i(scale_reg[stage1_idx]),
		.scale_valid_i(bias_mid_v[0]),
		.data_valid_i(bias_mid_v[0]),
		.data_i(bias_mid[0]),
		.data_valid_o(scale_v[0]),
		.data_o(scale_out[0])
	);

	// instantiate bias/scale for lane 1
	bias u_bias_1 (
		.clk_i(clk),
		.rst_i(rst),
		.bias_i(bias_reg[stage0_idx + 1]),
		.bias_valid_i(stage0_valid),
		.data_valid_i(stage0_valid),
		.data_i(lane_in[1]),
		.data_valid_o(bias_mid_v[1]),
		.data_o(bias_mid[1])
	);

	scale u_scale_1 (
		.clk_i(clk),
		.rst_i(rst),
		.scale_i(scale_reg[stage1_idx + 1]),
		.scale_valid_i(bias_mid_v[1]),
		.data_valid_i(bias_mid_v[1]),
		.data_i(bias_mid[1]),
		.data_valid_o(scale_v[1]),
		.data_o(scale_out[1])
	);

endmodule