module pe #(
    parameter DATA_WIDTH = 8,
    parameter ACC_WIDTH  = 32
)(
    input  logic                  clk_i,
    input  logic                  rst_i,

    input  logic [DATA_WIDTH-1:0] act_in,
    output logic [DATA_WIDTH-1:0] act_out,

    input  logic [DATA_WIDTH-1:0] weight_in,
    output logic [DATA_WIDTH-1:0] weight_out,

    input  logic                  buf_sel_in,
    output logic                  buf_sel_out,

    input  logic                  weight_we,
    output logic                  weight_we_out,

    input  logic [ACC_WIDTH-1:0]  psum_in,
    output logic [ACC_WIDTH-1:0]  psum_out
);

    logic [DATA_WIDTH-1:0] weight_buf [0:1];

    always_ff @(posedge clk_i) begin
        if (weight_we)
            weight_buf[~buf_sel_in] <= weight_in;
    end

    logic [DATA_WIDTH-1:0] active_weight;
    assign active_weight = weight_buf[buf_sel_in];

    always_ff @(posedge clk_i) begin
        if (rst_i)
            psum_out <= '0;
        else
            psum_out <= psum_in + (act_in * active_weight);
    end

    always_ff @(posedge clk_i) begin
        act_out       <= act_in;
        weight_out    <= weight_buf[~buf_sel_in];
        buf_sel_out   <= buf_sel_in;
        weight_we_out <= weight_we;
    end

endmodule
