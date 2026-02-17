module tpu #(
	parameter int N = 8,
	parameter int DATA_W = 8,
	parameter int PSUM_W = 32
) (
	input  logic                   clk,
	input  logic                   rst,

	// Simple DRAM-like 64-bit read/write streaming interface
	input  logic [63:0]            dram_read_data_i,
	input  logic                   dram_read_valid_i,
	output logic                   dram_read_ready_o,

	output logic [63:0]            dram_write_data_o,
	output logic                   dram_write_valid_o,
	input  logic                   dram_write_ready_i,

	// SPI control plane (configures bias/scale values)
	input  wire                    spi_sclk,
	input  wire                    spi_mosi,
	input  wire                    spi_cs_n,
	output wire                    spi_miso,

	// External connections to the systolic array (for debugging)
	input  logic [DATA_W-1:0]      sysdata_i [N],
	input  logic [DATA_W-1:0]      sysweight_i [N],
	input  logic [N-1:0]           in_valid_input,
	input  logic [N-1:0]           in_valid_weight,
	output logic [N-1:0]           out_valid_input,
	output logic [N-1:0]           out_valid_weight
);

	// --- SPI slave to receive configuration bytes ---
	logic [7:0] spi_rx_data;
	logic       spi_rx_valid;

	spi_slave u_spi (
		.clk    (clk),
		.rst    (rst),
		.sclk   (spi_sclk),
		.mosi   (spi_mosi),
		.cs_n   (spi_cs_n),
		.miso   (spi_miso),
		.rx_data(spi_rx_data),
		.rx_valid(spi_rx_valid),
		.tx_data(8'd0),
		.tx_valid(1'b0)
	);

	// Simple config loader: 4 x 32-bit words loaded sequentially by SPI
	// Order: 0 -> bias0, 1 -> scale0, 2 -> bias1, 3 -> scale1
	logic [31:0] config_word_r;
	logic [1:0]  config_word_idx_r; // 0..3
	logic [1:0]  cfg_byte_cnt_r;

	logic [31:0] bias0_reg, scale0_reg, bias1_reg, scale1_reg;
	logic        bias0_valid_stb, scale0_valid_stb, bias1_valid_stb, scale1_valid_stb;

	always_ff @(posedge clk) begin
		if (rst) begin
			config_word_r <= '0;
			cfg_byte_cnt_r <= 2'd0;
			config_word_idx_r <= 2'd0;
			bias0_reg <= 32'd0;
			scale0_reg <= 32'd0;
			bias1_reg <= 32'd0;
			scale1_reg <= 32'd0;
			bias0_valid_stb <= 1'b0;
			scale0_valid_stb <= 1'b0;
			bias1_valid_stb <= 1'b0;
			scale1_valid_stb <= 1'b0;
		end else begin
			// default: clear strobes
			bias0_valid_stb <= 1'b0;
			scale0_valid_stb <= 1'b0;
			bias1_valid_stb <= 1'b0;
			scale1_valid_stb <= 1'b0;

			if (spi_rx_valid) begin
				// accumulate bytes MSB-first: shift left then OR new byte
				config_word_r <= {config_word_r[23:0], spi_rx_data};
				cfg_byte_cnt_r <= cfg_byte_cnt_r + 1;

				if (cfg_byte_cnt_r == 2'd3) begin
					// completed a 32-bit word
					case (config_word_idx_r)
						2'd0: begin bias0_reg <= {config_word_r[23:0], spi_rx_data}; bias0_valid_stb <= 1'b1; end
						2'd1: begin scale0_reg <= {config_word_r[23:0], spi_rx_data}; scale0_valid_stb <= 1'b1; end
						2'd2: begin bias1_reg <= {config_word_r[23:0], spi_rx_data}; bias1_valid_stb <= 1'b1; end
						2'd3: begin scale1_reg <= {config_word_r[23:0], spi_rx_data}; scale1_valid_stb <= 1'b1; end
					endcase
					config_word_idx_r <= config_word_idx_r + 1;
					cfg_byte_cnt_r <= 2'd0;
					config_word_r <= 32'd0;
				end
			end
		end
	end

	// --- Two parallel bias -> scale datapaths that slice the 64-bit DRAM bus ---
	// Split read 64-bit into two 32-bit lanes
	logic data_valid_lane0, data_valid_lane1;
	logic signed [31:0] data_lane0_in, data_lane1_in;
	logic signed [31:0] bias0_out, bias1_out;
	logic signed [31:0] scale0_out, scale1_out;
	logic data_valid_after_bias0, data_valid_after_bias1;
	logic data_valid_after_scale0, data_valid_after_scale1;

	assign dram_read_ready_o = 1'b1; // simple always-ready sink

	always_comb begin
		data_lane0_in = dram_read_data_i[31:0];
		data_lane1_in = dram_read_data_i[63:32];
		data_valid_lane0 = dram_read_valid_i;
		data_valid_lane1 = dram_read_valid_i;
	end

	// bias instances
	bias u_bias0 (
		.clk_i(clk),
		.rst_i(rst),
		.bias_i(bias0_reg),
		.bias_valid_i(bias0_valid_stb),
		.data_valid_i(data_valid_lane0),
		.data_i(data_lane0_in),
		.data_valid_o(data_valid_after_bias0),
		.data_o(bias0_out)
	);

	bias u_bias1 (
		.clk_i(clk),
		.rst_i(rst),
		.bias_i(bias1_reg),
		.bias_valid_i(bias1_valid_stb),
		.data_valid_i(data_valid_lane1),
		.data_i(data_lane1_in),
		.data_valid_o(data_valid_after_bias1),
		.data_o(bias1_out)
	);

	// scale instances
	scale u_scale0 (
		.clk_i(clk),
		.rst_i(rst),
		.scale_i(scale0_reg),
		.scale_valid_i(scale0_valid_stb),
		.data_valid_i(data_valid_after_bias0),
		.data_i(bias0_out),
		.data_valid_o(data_valid_after_scale0),
		.data_o(scale0_out)
	);

	scale u_scale1 (
		.clk_i(clk),
		.rst_i(rst),
		.scale_i(scale1_reg),
		.scale_valid_i(scale1_valid_stb),
		.data_valid_i(data_valid_after_bias1),
		.data_i(bias1_out),
		.data_valid_o(data_valid_after_scale1),
		.data_o(scale1_out)
	);

	// compose writeback 64-bit word when both lanes ready
	assign dram_write_data_o = {scale1_out, scale0_out};
	assign dram_write_valid_o = data_valid_after_scale0 & data_valid_after_scale1;

	// --- instantiate the 8x8 systolic array (optional usage) ---
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
		.out_valid_input(out_valid_input),
		.out_valid_weight(out_valid_weight)
	);

endmodule