module pe #(
    parameter DATA_WIDTH = 8,
    parameter ACC_WIDTH  = 32
)(
    input  logic                  clk_i,
    input  logic                  rst_i,

    input  logic [DATA_WIDTH:0] act_i, //top bit is select
    output logic [DATA_WIDTH:0] act_o,

    input  logic [DATA_WIDTH:0] weight_i, //shift reg chain
    output logic [DATA_WIDTH:0] weight_o,

    input  logic weight_valid_i,
    output logic weight_valid_o,

    input  logic act_valid_i,
    output logic act_valid_o,

    input  logic [ACC_WIDTH-1:0]  psum_i,
    input  logic psum_valid_i,
    output logic [ACC_WIDTH-1:0]  psum_o,
    output  logic psum_valid_o
);

    logic weight_sel, act_sel, weight_edge, prev_weight_sel;
    assign weight_sel = weight_i[DATA_WIDTH];
    assign act_sel = act_i[DATA_WIDTH];

    assign weight_edge = prev_weight_sel != weight_sel;

    assign weight_valid_o = weight_valid_i & ~weight_edge;

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
        end else if (weight_valid_i)
            weight_buf[weight_sel] <= weight_i;
    end

    logic [DATA_WIDTH-1:0] active_weight;
    assign active_weight = weight_buf[act_sel][DATA_WIDTH-1:0];

    always_ff @(posedge clk_i) begin
        if (rst_i) begin
            psum_o <= '0;
            psum_valid_o <= 1'b0;
        end else if (act_valid_i & psum_valid_i) begin // only update psum if both inputs are valid
            psum_o <=  (psum_i[ACC_WIDTH-1:0] + (act_i[DATA_WIDTH-1:0] * active_weight));
            psum_valid_o <= 1'b1;
        end else begin
            psum_o <= '0;
            psum_valid_o <= 1'b0;
        end
    end

    // pass through activation
    always_ff @(posedge clk_i) begin
        if (rst_i) begin
            act_o <= '0;
            act_valid_o <= '0;
        end else begin
            act_o <= act_i;
            act_valid_o <= act_valid_i;
        end
    end

    assign weight_o = weight_buf[prev_weight_sel];

endmodule
