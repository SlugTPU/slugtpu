module pe #(
    parameter DATA_WIDTH = 8,
    parameter ACC_WIDTH  = 32
)(
    input  logic                  clk_i,
    input  logic                  rst_i,

    input  logic [DATA_WIDTH:0] act_in, //top bit is select
    output logic [DATA_WIDTH:0] act_out,

    input  logic [DATA_WIDTH:0] weight_in, //shift reg chain
    output logic [DATA_WIDTH:0] weight_out,

    input  logic weight_valid,
    output logic weight_valid_o,
    
    input  logic act_valid,
    output logic act_valid_o,

    input  logic [ACC_WIDTH:0]  psum_in,
    output logic [ACC_WIDTH:0]  psum_out
);

    logic weight_sel, act_sel, weight_edge, prev_weight_sel;
    assign weight_sel = weight_in[DATA_WIDTH];
    assign act_sel = act_in[DATA_WIDTH];

    assign weight_edge = prev_weight_sel != weight_sel;

    assign weight_valid_o = weight_valid & ~weight_edge;

    //double buff
    logic [DATA_WIDTH:0] weight_buf [1:0];

    // edge_detector for weight sel
    always_ff @(posedge clk_i) begin
        if (rst_i)
            prev_weight_sel <= '0;
        else if (weight_edge)
            prev_weight_sel <= weight_sel;
    end

    // capture into shadow buffer only on broadcast latch
    always_ff @(posedge clk_i) begin
        if (rst_i) begin
            weight_buf[0] <= '0;
            weight_buf[1] <= '0;
        end else if (weight_valid)
            weight_buf[weight_sel] <= weight_in;
    end

    logic [DATA_WIDTH-1:0] active_weight;
    assign active_weight = weight_buf[act_sel][DATA_WIDTH-1:0];

    always_ff @(posedge clk_i) begin
        if (rst_i)
            psum_out <= '0;
        else if (act_valid)
            psum_out <= {1'b1, psum_in[ACC_WIDTH-1:0] + (act_in[DATA_WIDTH-1:0] * active_weight)};
        else
            psum_out <= '0;
    end

    // pass through activation
    always_ff @(posedge clk_i) begin
        if (rst_i) begin
            act_out <= '0;
            act_valid_o <= '0;
        end else begin
            act_out <= act_in;
            act_valid_o <= act_valid;
        end
    end

    assign weight_out = weight_buf[prev_weight_sel];

endmodule
