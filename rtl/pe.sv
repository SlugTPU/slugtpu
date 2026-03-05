module pe #(
    parameter DATA_WIDTH = 8,
    parameter ACC_WIDTH  = 32
)(
    input  logic                  clk_i,
    input  logic                  rst_i,

    input  logic [DATA_WIDTH-1:0] act_in,
    output logic [DATA_WIDTH-1:0] act_out,

    input  logic [DATA_WIDTH-1:0] weight_in,//shift reg chain
    output logic [DATA_WIDTH-1:0] weight_out,

    input logic weight_latch,
    input logic buf_sel,

    input  logic [ACC_WIDTH-1:0]  psum_in,
    output logic [ACC_WIDTH-1:0]  psum_out
);
    //double buff
    logic [DATA_WIDTH-1:0] weight_buf [0:1];

    // shift register passes weight data down the column
    always_ff @(posedge clk_i) begin
        weight_out <= weight_in;
    end

    // capture into shadow buffer only on broadcast latch
    always_ff @(posedge clk_i) begin
        if (rst_i) begin
            weight_buf[0] <= '0;
            weight_buf[1] <= '0;
        end else if (weight_latch)
            weight_buf[~buf_sel] <= weight_in;
    end

    logic [DATA_WIDTH-1:0] active_weight;
    assign active_weight = weight_buf[buf_sel];

    always_ff @(posedge clk_i) begin
        if (rst_i)
            psum_out <= '0;
        else
            psum_out <= psum_in + (act_in * active_weight);
    end

    // pass through activation
    always_ff @(posedge clk_i) begin
        act_out <= act_in;
    end

endmodule
